# Run IgnitionTrace

## Browser only

Open the deployed workbench or build the static app below. Choose a scenario, generate a run, select a finding, then inspect its evidence. **Open trace** accepts an IgnitionTrace JSON file up to 8 MiB. **Compare runs** accepts a second file or pins the current recording as a baseline. **Budgets** reanalyzes both recordings with identical thresholds.

Trace files are processed in browser memory. No account, API key or external telemetry service is required. The local archive tab connects only when this page is served alongside the included Python API.

## Complete local application

```sh
docker compose up --build
```

Open http://localhost:8000. SQLite data survives container restarts in the `trace-data` Docker volume. `docker compose down` preserves it; deleting the volume removes the archive. The published port binds to your machine's loopback interface.

## Manual setup

Requirements: Python 3.11+, Node 22.13+ and pnpm 11.25.0. JDK/Android SDK are only needed for the recorder.

```sh
python -m venv .venv
. .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt
pip install --no-deps -e .
cd web
pnpm install --frozen-lockfile
pnpm build:static
cd ..
uvicorn ignition_trace.api:app --host 127.0.0.1 --port 8000
```

On Windows activate with `.venv\Scripts\activate`. To serve only the browser app, run `python -m http.server 8080 --directory web/out` and open http://localhost:8080. The archive is unavailable in that mode.

## Command line

```sh
ignition-trace demo --scenario audio-resume --seed 42 --out runs/audio
ignition-trace analyze runs/audio/trace.json --out runs/check --fail-on-findings
ignition-trace replay runs/audio/trace.json --at-ms 18000
```

Available scenarios: `clean`, `audio-resume`, `signal-stall`, `network`, `frame-jank`, `mixed`. Seeds range from 0 through 4294967295. The simulator is deterministic for a given scenario, seed and engine version. Output writes are atomic. Invalid input fails before a report is generated. A regression gate exits 2 on findings, 0 otherwise.

Custom budgets are JSON; missing keys use defaults:

```json
{"frame_ms": 33.3, "network_ms": 800, "startup_ms": 1500, "audio_resume_ms": 500, "signal_gap_ms": 1000}
```

Pass with `--budgets budgets.json`. These are observed-duration thresholds, not certified automotive requirements.

## Local API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/health` | Mode and version |
| `POST /api/v1/traces` | Validate and archive one JSON trace; returns ID and report |
| `GET /api/v1/traces` | Up to 100 most recent archive entries |
| `GET /api/v1/traces/{id}` | Original normalized trace |
| `GET /api/v1/traces/{id}/events` | NDJSON event export, without replay pacing |
| `GET /api/v1/demo/{scenario}?seed=42` | Generated trace |
| `GET /docs` | Interactive OpenAPI documentation |

Set `IGNITION_DB` to choose a database path and `IGNITION_WEB_DIR` to choose static output. The API is deliberately single-user and local; do not expose it directly to the internet. Saving identical normalized content returns the same SHA-256 ID. Reports stored by the API use default budgets; browser custom budgets apply to the in-memory view.

## GitHub Pages

1. In repository **Settings → Pages**, select **GitHub Actions** as the source.
2. Open **Actions → Deploy workbench → Run workflow** on `main`.
3. Wait for the deployment job to succeed; open https://abrar0205.github.io/ignition-trace/.

The workflow builds with `/ignition-trace` as its base path. Pages hosts the browser workbench; use the local installation for SQLite and the API. The README provides the entry link for repository visitors.
