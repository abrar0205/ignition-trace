from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(allow_inf_nan=False, ge=0, le=86_400_000)]


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    seq: int = Field(ge=0, le=1_000_000)
    t_ms: Number
    source: str = Field(min_length=1, max_length=80)
    kind: Literal["signal", "frame", "span", "audio", "playback", "lifecycle"]
    name: str = Field(min_length=1, max_length=120)
    value: float | str | bool | None = None
    duration_ms: Number | None = None
    correlation_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_value(self):
        import math

        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("Values must be finite")
        if isinstance(self.value, str) and len(self.value) > 200:
            raise ValueError("Value too long")
        if self.kind in {"span", "frame"} and self.duration_ms is None:
            raise ValueError("Durations are required for frame and span events")
        return self


class Trace(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"] = "1.0"
    title: str = Field(min_length=1, max_length=120)
    source: Literal["synthetic", "android", "imported"]
    duration_ms: Number
    clock: Literal["session-monotonic-ms"] = "session-monotonic-ms"
    scenario: str = Field(default="recording", max_length=80)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    events: list[Event] = Field(min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def validate_events(self):
        if self.duration_ms <= 0:
            raise ValueError("Duration must be positive")
        ids = set()
        last = -1.0
        for e in self.events:
            if e.seq in ids or e.t_ms < last or e.t_ms > self.duration_ms:
                raise ValueError("Events must be ordered, unique and inside recording")
            if e.duration_ms is not None and e.t_ms + e.duration_ms > self.duration_ms:
                raise ValueError("Span end exceeds recording")
            ids.add(e.seq)
            last = e.t_ms
        return self


class Budgets(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    frame_ms: float = Field(default=50, gt=0, le=1000, allow_inf_nan=False)
    network_ms: float = Field(default=500, gt=0, le=60_000, allow_inf_nan=False)
    startup_ms: float = Field(default=1500, gt=0, le=60_000, allow_inf_nan=False)
    audio_resume_ms: float = Field(default=500, gt=0, le=60_000, allow_inf_nan=False)
    signal_gap_ms: float = Field(default=1000, gt=0, le=60_000, allow_inf_nan=False)


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scenario: Literal["clean", "audio-resume", "signal-stall", "network", "frame-jank", "mixed"] = (
        "mixed"
    )
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
