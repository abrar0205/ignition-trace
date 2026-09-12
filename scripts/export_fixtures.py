"""Regenerate the shared corpus. No private recordings or external datasets."""

import json
from pathlib import Path

from ignition_trace.engine import analyze
from ignition_trace.model import ScenarioConfig, Trace
from ignition_trace.simulate import simulate

root = Path(__file__).resolve().parents[1]
target = root / "tests" / "fixtures"
target.mkdir(parents=True, exist_ok=True)
corpus = []
for scenario in ("clean", "audio-resume", "signal-stall", "network", "frame-jank", "mixed"):
    for seed in (0, 42, 4294967295):
        trace = simulate(ScenarioConfig(scenario=scenario, seed=seed))
        corpus.append({"trace": trace.model_dump(), "report": analyze(trace)})
(target / "conformance.json").write_text(json.dumps(corpus, separators=(",", ":")) + "\n")
(root / "docs").mkdir(exist_ok=True)
(root / "docs" / "trace.schema.json").write_text(
    json.dumps(Trace.model_json_schema(), indent=2) + "\n"
)
