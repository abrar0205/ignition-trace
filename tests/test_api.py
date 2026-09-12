import json

import pytest
from fastapi.testclient import TestClient

from ignition_trace.api import create_app
from ignition_trace.simulate import simulate


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "archive.sqlite3")) as client:
        yield client


def test_roundtrip_deduplication_and_stream(client):
    body = simulate().model_dump(mode="json")
    first = client.post("/api/v1/traces", json=body)
    assert first.status_code == 200
    key = first.json()["id"]
    assert client.post("/api/v1/traces", json=body).json()["id"] == key
    assert len(client.get("/api/v1/traces").json()) == 1
    assert client.get(f"/api/v1/traces/{key}").json() == body
    events = client.get(f"/api/v1/traces/{key}/events")
    assert [json.loads(line) for line in events.text.splitlines()] == body["events"]


def test_archive_survives_restart(tmp_path):
    db = tmp_path / "archive.sqlite3"
    with TestClient(create_app(db)) as first:
        key = first.post("/api/v1/traces", json=simulate().model_dump()).json()["id"]
    with TestClient(create_app(db)) as second:
        assert second.get(f"/api/v1/traces/{key}").status_code == 200


def test_bad_inputs_and_cross_origin_are_rejected(client):
    assert client.post("/api/v1/traces", content="{").status_code == 422
    assert client.post("/api/v1/traces", content="x" * (8 * 1024 * 1024 + 1)).status_code == 413
    assert (
        client.post(
            "/api/v1/traces", json={}, headers={"Origin": "https://other.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/traces/invalid").status_code == 404
    assert client.get("/api/v1/traces/" + "a" * 64).status_code == 404
    assert client.get("/api/v1/health", headers={"Host": "other.example"}).status_code == 400
    assert client.get("/api/v1/health", headers={"Host": "10.0.2.2:8000"}).status_code == 200


def test_demo_validates_scenario_and_seed(client):
    assert client.get("/api/v1/demo/clean?seed=0").json()["seed"] == 0
    assert client.get("/api/v1/demo/unknown").status_code == 422
    assert client.get("/api/v1/demo/mixed?seed=-1").status_code == 422
