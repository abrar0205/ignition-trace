"""Deterministic analysis. Findings describe observations, never inferred causality."""

import hashlib
import json
from collections import defaultdict

from .model import Budgets, Trace
from .simulate import SPEED


def trace_hash(trace: Trace) -> str:
    # Numeric representation is Python-specific; browser imports retain their own IDs.
    raw = json.dumps(trace.model_dump(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    at = (len(values) - 1) * p
    low = int(at)
    return round(
        values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (at - low), 3
    )


def analyze(trace: Trace, budgets: Budgets | None = None):
    budgets = budgets or Budgets()
    findings, frames, network, startup, resumes = [], [], [], [], []
    signals = defaultdict(list)
    pending = {}

    def issue(code, title, event, value, budget, end=None, evidence=None):
        findings.append(
            {
                "id": f"{code}-{event.seq}",
                "code": code,
                "title": title,
                "source": event.source,
                "start_ms": event.t_ms,
                "end_ms": event.t_ms if end is None else end,
                "observed_ms": round(value, 3),
                "budget_ms": budget,
                "evidence": evidence or [event.seq],
            }
        )

    for e in trace.events:
        duration = e.duration_ms or 0
        if e.kind == "frame":
            frames.append(duration)
            if duration > budgets.frame_ms:
                issue(
                    "FRAME_BUDGET", "Slow frame", e, duration, budgets.frame_ms, e.t_ms + duration
                )
        if e.kind == "span" and e.name.startswith("http."):
            network.append(duration)
            if e.value == "timeout" or duration > budgets.network_ms:
                issue(
                    "NETWORK_BUDGET",
                    "Network request exceeded budget",
                    e,
                    duration,
                    budgets.network_ms,
                    e.t_ms + duration,
                )
        if e.kind == "span" and e.name == "app.startup":
            startup.append(duration)
            if duration > budgets.startup_ms:
                issue(
                    "STARTUP_BUDGET",
                    "Slow application startup",
                    e,
                    duration,
                    budgets.startup_ms,
                    e.t_ms + duration,
                )
        if e.kind == "signal" and e.name == SPEED:
            signals[(e.source, e.name)].append(e)
        key = (e.source, e.name, e.correlation_id)
        if e.kind == "audio":
            if e.value == "gain":
                pending.setdefault(key, e)
            else:
                pending.pop(key, None)
        if e.kind == "playback" and e.value == "playing" and key in pending:
            gained = pending.pop(key)
            delay = e.t_ms - gained.t_ms
            resumes.append(delay)
            if delay > budgets.audio_resume_ms:
                issue(
                    "AUDIO_RESUME",
                    "Late playback after focus gain",
                    gained,
                    delay,
                    budgets.audio_resume_ms,
                    e.t_ms,
                    [gained.seq, e.seq],
                )
    for gained in pending.values():
        wait = trace.duration_ms - gained.t_ms
        if wait > budgets.audio_resume_ms:
            issue(
                "AUDIO_UNRESOLVED",
                "No observed playback after focus gain",
                gained,
                wait,
                budgets.audio_resume_ms,
                trace.duration_ms,
            )
    for events in signals.values():
        for i, e in enumerate(events):
            end = events[i + 1].t_ms if i + 1 < len(events) else trace.duration_ms
            gap = end - e.t_ms
            if gap > budgets.signal_gap_ms:
                evidence = [e.seq] + ([events[i + 1].seq] if i + 1 < len(events) else [])
                issue(
                    "SIGNAL_GAP",
                    "Speed signal went stale",
                    e,
                    gap,
                    budgets.signal_gap_ms,
                    end,
                    evidence,
                )
    findings.sort(key=lambda f: (f["start_ms"], f["code"]))
    return {
        "schema_version": "1.0",
        "engine_version": "0.1.0",
        "trace_sha256": trace_hash(trace),
        "budgets": budgets.model_dump(),
        "event_count": len(trace.events),
        "finding_count": len(findings),
        "findings": findings[:200],
        "omitted_findings": max(0, len(findings) - 200),
        "metrics": {
            "frame_p95_ms": percentile(frames, 0.95),
            "network_p95_ms": percentile(network, 0.95),
            "startup_max_ms": max(startup) if startup else None,
            "audio_resume_max_ms": max(resumes) if resumes else None,
        },
    }


def state_at(trace: Trace, cursor_ms: float):
    """Reduce measured events up to the cursor; seek does not command a real device."""
    if not 0 <= cursor_ms <= trace.duration_ms:
        raise ValueError("Cursor outside trace")
    signals, media = {}, "unknown"
    for e in trace.events:
        if e.t_ms > cursor_ms:
            break
        if e.kind == "signal":
            signals[e.name] = {"value": e.value, "age_ms": cursor_ms - e.t_ms, "source": e.source}
        if e.kind == "playback":
            media = e.value
    return {"cursor_ms": cursor_ms, "signals": signals, "playback": media}


def compare(baseline: dict, candidate: dict):
    if baseline["budgets"] != candidate["budgets"]:
        raise ValueError("Compare runs with identical budgets")
    return {
        key: None
        if value is None or candidate["metrics"][key] is None
        else round(candidate["metrics"][key] - value, 3)
        for key, value in baseline["metrics"].items()
    }
