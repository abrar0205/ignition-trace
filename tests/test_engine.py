import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from ignition_trace.engine import analyze, compare, state_at, trace_hash
from ignition_trace.model import Budgets, ScenarioConfig, Trace
from ignition_trace.simulate import SPEED, simulate


def recording(events, duration=3000):
    return Trace.model_validate(
        {
            "title": "Test recording",
            "source": "imported",
            "duration_ms": duration,
            "events": [dict(seq=i, source="app", name="media", **e) for i, e in enumerate(events)],
        }
    )


@pytest.mark.parametrize(
    "scenario,count",
    [
        ("clean", 0),
        ("audio-resume", 1),
        ("signal-stall", 1),
        ("network", 2),
        ("frame-jank", 5),
        ("mixed", 9),
    ],
)
def test_faults_have_explainable_evidence(scenario, count):
    trace = simulate(ScenarioConfig(scenario=scenario))
    before = trace.model_dump_json()
    report = analyze(trace)
    assert report["finding_count"] == count
    assert all(set(f["evidence"]) <= {e.seq for e in trace.events} for f in report["findings"])
    assert trace.model_dump_json() == before


def test_replay_is_seekable_and_respects_boundary():
    trace = simulate()
    assert state_at(trace, 20400)["playback"] == "playing"
    assert state_at(trace, 20399)["playback"] == "paused"
    assert state_at(trace, 32000)["signals"][SPEED]["age_ms"] == 4250
    assert state_at(trace, 33000)["signals"][SPEED]["age_ms"] == 0
    for cursor in (-1, 60001, math.nan, math.inf):
        with pytest.raises(ValueError):
            state_at(trace, cursor)


def test_audio_correlation_does_not_join_unrelated_players():
    t = recording(
        [
            {"t_ms": 0, "kind": "audio", "value": "gain", "correlation_id": "a"},
            {"t_ms": 100, "kind": "audio", "value": "gain", "correlation_id": "b"},
            {"t_ms": 200, "kind": "playback", "value": "playing", "correlation_id": "b"},
            {"t_ms": 1200, "kind": "playback", "value": "playing", "correlation_id": "a"},
        ]
    )
    report = analyze(t)
    assert report["finding_count"] == 1
    assert report["findings"][0]["evidence"] == [0, 3]
    assert report["metrics"]["audio_resume_max_ms"] == 1200


def test_duplicate_gain_preserves_first_gain_and_loss_cancels_pending():
    t = recording(
        [
            {"t_ms": 0, "kind": "audio", "value": "gain"},
            {"t_ms": 100, "kind": "audio", "value": "gain"},
            {"t_ms": 600, "kind": "playback", "value": "playing"},
            {"t_ms": 1000, "kind": "audio", "value": "gain"},
            {"t_ms": 1100, "kind": "audio", "value": "loss"},
        ]
    )
    assert analyze(t)["findings"][0]["observed_ms"] == 600
    assert analyze(t)["finding_count"] == 1


def test_unresolved_audio_and_missing_metrics_are_distinct():
    r = analyze(recording([{"t_ms": 0, "kind": "audio", "value": "gain"}]))
    assert r["findings"][0]["code"] == "AUDIO_UNRESOLVED"
    assert all(v is None for v in r["metrics"].values())


def test_exact_budget_does_not_fail():
    t = recording([{"t_ms": 0, "kind": "frame", "duration_ms": 50}])
    assert analyze(t)["finding_count"] == 0
    assert analyze(t, Budgets(frame_ms=49))["finding_count"] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda t: t["events"].append(t["events"][0]),
        lambda t: t["events"].reverse(),
        lambda t: t["events"][0].update(t_ms=-1),
        lambda t: t["events"][0].update(value=math.inf),
        lambda t: t["events"][0].update(value="x" * 201),
        lambda t: t.update(clock="wall-clock"),
        lambda t: t.update(secret="unknown field"),
        lambda t: t["events"][0].update(kind="span", duration_ms=None),
        lambda t: t["events"][0].update(duration_ms=60001),
    ],
)
def test_contract_rejects_invalid_records(mutation):
    data = simulate().model_dump()
    mutation(data)
    with pytest.raises(ValidationError):
        Trace.model_validate(data)


def test_seed_reproducibility_and_distinct_content_hash():
    a = simulate(ScenarioConfig(seed=42))
    assert trace_hash(a) == trace_hash(simulate(ScenarioConfig(seed=42)))
    assert trace_hash(a) != trace_hash(simulate(ScenarioConfig(seed=43)))


def test_comparison_requires_common_budget_and_preserves_unknown():
    clean = analyze(simulate(ScenarioConfig(scenario="clean")))
    bad = analyze(simulate())
    assert compare(clean, bad)["audio_resume_max_ms"] == 2280
    other = copy.deepcopy(bad)
    other["budgets"]["frame_ms"] = 100
    with pytest.raises(ValueError):
        compare(clean, other)
    other = copy.deepcopy(bad)
    other["metrics"]["frame_p95_ms"] = None
    assert compare(clean, other)["frame_p95_ms"] is None


def test_findings_are_bounded_but_total_is_preserved():
    trace = recording([{"t_ms": i, "kind": "frame", "duration_ms": 80} for i in range(250)])
    report = analyze(trace)
    assert report["finding_count"] == 250
    assert len(report["findings"]) == 200
    assert report["omitted_findings"] == 50


def test_shared_corpus_is_current():
    corpus = json.loads((Path(__file__).parent / "fixtures/conformance.json").read_text())
    for case in corpus:
        trace = Trace.model_validate(case["trace"])
        assert analyze(trace) == case["report"]


def test_cli_regression_gate_and_export(tmp_path):
    demo = subprocess.run(
        [sys.executable, "-m", "ignition_trace.cli", "demo", "--out", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(demo.stdout)["findings"] == 9
    gate = subprocess.run(
        [
            sys.executable,
            "-m",
            "ignition_trace.cli",
            "analyze",
            str(tmp_path / "trace.json"),
            "--out",
            str(tmp_path / "check"),
            "--fail-on-findings",
        ],
        capture_output=True,
        check=False,
    )
    assert gate.returncode == 2
    assert (tmp_path / "check/report.json").exists()
