# Trace contract 1.0

All times are finite milliseconds on one session-relative monotonic clock. Duration is positive and at most 24 hours. Traces contain 1–100,000 events; imported JSON is limited to 8 MiB. Events must be ordered by timestamp, have unique integer sequence IDs, and finish within the recording. Unknown object fields are rejected. The generated [JSON Schema](trace.schema.json) describes structural constraints; ordering, unique sequence IDs, span containment and conditional duration requirements are additionally enforced by both runtime validators.

```json
{
  "schema_version": "1.0",
  "title": "A recorded focus transition",
  "source": "android",
  "duration_ms": 1000,
  "clock": "session-monotonic-ms",
  "events": [
    {"seq": 0, "t_ms": 0, "source": "app", "kind": "audio", "name": "media", "value": "gain", "correlation_id": "player-1"},
    {"seq": 1, "t_ms": 800, "source": "app", "kind": "playback", "name": "media", "value": "playing", "correlation_id": "player-1"}
  ]
}
```

| Event field | Contract |
| --- | --- |
| `seq` | Unique integer from 0 to 1,000,000; need not be contiguous |
| `t_ms` | Session timestamp, 0 through recording duration |
| `source` | Nonempty string up to 80 characters |
| `kind` | `signal`, `frame`, `span`, `audio`, `playback`, or `lifecycle` |
| `name` | Nonempty string up to 120 characters |
| `value` | Finite number, string up to 200 characters, boolean or null |
| `duration_ms` | Required finite nonnegative number for frames/spans; otherwise optional/null |
| `correlation_id` | Optional string up to 80 characters, or null |

Top-level `source` is `synthetic`, `android` or `imported`. `scenario` defaults to `recording` and `seed` to 42; neither affects detector decisions. `Vehicle.Speed` is km/h, traction-battery state of charge is percent, and the synthetic gear is an integer. No wall-clock conversion is performed. Importers must align their own clocks before creating a trace.

Add adapters by mapping observations into this contract and preserving their measurement semantics. Do not relabel reconstructed or synthetic measurements as device recordings.

