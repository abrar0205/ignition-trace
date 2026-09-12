"""Seeded test inputs; fault labels are never inputs to the detector."""

import math

from .model import Event, ScenarioConfig, Trace

SPEED = "Vehicle.Speed"
BATTERY = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current"


def simulate(config: ScenarioConfig | None = None) -> Trace:
    config = config or ScenarioConfig()
    state = config.seed
    events = []

    def rnd():
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state / 4294967296

    def add(t, kind, name, value=None, duration=None, source="headunit", correlation=None):
        events.append(
            {
                "seq": len(events),
                "t_ms": float(t),
                "source": source,
                "kind": kind,
                "name": name,
                "value": value,
                "duration_ms": duration,
                "correlation_id": correlation,
            }
        )

    def has(fault):
        return config.scenario in (fault, "mixed")

    for t in range(0, 60_001, 250):
        speed = round(
            max(0, min(110, (t / 1000 - 3) * 4, (60 - t / 1000) * 6) + math.sin(t / 4000) * 4), 2
        )
        if not (has("signal-stall") and 28_000 <= t < 33_000):
            add(t, "signal", SPEED, speed, source="vehicle-sim")
        if t % 1000 == 0:
            add(t, "signal", BATTERY, round(82 - t / 60_000 * 2, 2), source="vehicle-sim")
            add(
                t,
                "signal",
                "Vehicle.Powertrain.Transmission.CurrentGear",
                0 if speed == 0 else 1,
                source="vehicle-sim",
            )
        if t % 1000 == 0 and t < 59_000:
            duration = 12 + int(rnd() * 5)
            if has("frame-jank") and 40_000 <= t <= 44_000:
                duration += 80 + int(rnd() * 60)
            add(t, "frame", "frame.render", duration=duration)
        if t % 5000 == 0 and 0 < t < 55_000:
            duration = 70 + int(rnd() * 120)
            timeout = has("network") and 20_000 <= t <= 25_000
            add(
                t,
                "span",
                "http.catalog",
                "timeout" if timeout else "200",
                2500 if timeout else duration,
                correlation=f"request-{t}",
            )
    add(0, "lifecycle", "app", "created")
    add(0, "span", "app.startup", duration=680)
    add(1000, "audio", "media", "gain", correlation="media-main")
    add(1100, "playback", "media", "playing", correlation="media-main")
    add(12_000, "audio", "media", "loss_transient", correlation="media-main")
    add(12_030, "playback", "media", "paused", correlation="media-main")
    add(18_000, "audio", "media", "gain", correlation="media-main")
    add(
        20_400 if has("audio-resume") else 18_120,
        "playback",
        "media",
        "playing",
        correlation="media-main",
    )
    events.sort(key=lambda e: (e["t_ms"], e["seq"]))
    for seq, e in enumerate(events):
        e["seq"] = seq
    return Trace(
        title=f"Alpine commute / {config.scenario}",
        source="synthetic",
        duration_ms=60_000,
        scenario=config.scenario,
        seed=config.seed,
        events=[Event(**e) for e in events],
    )
