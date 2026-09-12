"""Single-user local trace archive. The public demo needs no server."""

import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .engine import analyze, trace_hash
from .model import ScenarioConfig, Trace
from .simulate import simulate

MAX_BODY = 8 * 1024 * 1024


def create_app(db_path: Path | None = None, web_dir: Path | None = None):
    app = FastAPI(title="IgnitionTrace", version="0.1.0")
    db = db_path or Path(os.getenv("IGNITION_DB", "runs/traces.sqlite3"))
    slots = threading.BoundedSemaphore(2)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "10.0.2.2", "testserver"]
    )

    @contextmanager
    def connect():
        db.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(db, timeout=10)
        try:
            with con:
                con.execute(
                    "CREATE TABLE IF NOT EXISTS traces (id TEXT PRIMARY KEY, title TEXT, source TEXT, body TEXT, report TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)"
                )
                yield con
        finally:
            con.close()

    @app.middleware("http")
    async def origin_check(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method == "POST"
            and origin
            and origin.rstrip("/") != str(request.base_url).rstrip("/")
        ):
            return JSONResponse({"detail": "Cross-origin requests disabled"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def read(request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                raise HTTPException(413, "Maximum trace size is 8 MiB")
        return body

    def archive(trace):
        report = analyze(trace)
        key = trace_hash(trace)
        with connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO traces(id,title,source,body,report) VALUES(?,?,?,?,?)",
                (key, trace.title, trace.source, trace.model_dump_json(), json.dumps(report)),
            )
        return {"id": key, "report": report}

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "mode": "local", "version": "0.1.0"}

    @app.post("/api/v1/traces")
    async def ingest(request: Request):
        if not slots.acquire(blocking=False):
            raise HTTPException(503, "Analysis capacity reached")
        try:
            body = await read(request)

            def work():
                try:
                    trace = Trace.model_validate_json(body)
                except ValidationError as exc:
                    raise HTTPException(422, "Invalid trace; see docs/trace.schema.json") from exc
                return archive(trace)

            return await run_in_threadpool(work)
        finally:
            slots.release()

    @app.get("/api/v1/traces")
    def list_traces():
        with connect() as con:
            rows = con.execute(
                "SELECT id,title,source,created FROM traces ORDER BY created DESC,id DESC LIMIT 100"
            ).fetchall()
        return [dict(zip(("id", "title", "source", "created"), row)) for row in rows]

    @app.get("/api/v1/traces/{key}")
    def get_trace(key: str):
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise HTTPException(404, "Trace not found")
        with connect() as con:
            row = con.execute("SELECT body FROM traces WHERE id=?", (key,)).fetchone()
        if row is None:
            raise HTTPException(404, "Trace not found")
        return json.loads(row[0])

    @app.get("/api/v1/demo/{scenario}")
    def demo(scenario: str, seed: int = 42):
        try:
            config = ScenarioConfig(scenario=scenario, seed=seed)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid scenario or seed") from exc
        return simulate(config).model_dump()

    @app.get("/api/v1/traces/{key}/events")
    def events(key: str):
        trace = get_trace(key)

        def chunks():
            for event in trace["events"]:
                yield json.dumps(event, separators=(",", ":")) + "\n"

        return StreamingResponse(chunks(), media_type="application/x-ndjson")

    static = web_dir or Path(os.getenv("IGNITION_WEB_DIR", "web/out"))
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="workbench")
    return app


app = create_app()
