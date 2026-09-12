# Measurement and replay semantics

## A finding is an observation

Detectors consume event fields, never scenario labels. Each finding contains its source, time interval, measured value, budget and supporting event sequence IDs. Association on a timeline is not causal attribution. The interface uses “finding” rather than claiming a root cause.

| Check | Definition | Default |
| --- | --- | --- |
| Frame | Recorded `frame` duration strictly exceeds budget | 50 ms |
| Network | `http.*` span duration strictly exceeds budget, or value is `timeout` | 500 ms |
| Startup | `app.startup` span duration strictly exceeds budget | 1500 ms |
| Audio resume | Elapsed time from `gain` to `playing`, grouped by source, name and correlation ID | 500 ms |
| Signal freshness | Gap between speed samples from the same source, including last sample to recording end | 1000 ms |

A focus loss cancels a pending gain. Repeated gains preserve the earliest outstanding gain. A gain without observed playback before recording end produces `AUDIO_UNRESOLVED` if the budget elapsed. That does not prove the player was expected to resume. Speed cannot be checked before its first observed sample. No speed samples means no speed findings, not a healthy vehicle signal.

P95 uses linear interpolation at `(n−1) × 0.95`, rounded to three decimals. Metrics without samples are null. Startup and audio metrics are maxima. Reports contain total finding count and at most 200 detailed findings; omitted details are counted explicitly. Comparisons require identical budgets. Python's normalized JSON SHA-256 identifies local archived content; it is not specified as a cross-language canonical JSON hash.

## Deterministic synthetic scenarios

The generator uses a uint32 linear congruential PRNG with multiplier 1664525 and increment 1013904223. No private recordings or downloaded datasets are used. The 60-second drive includes speed at 4 Hz, battery/gear at 1 Hz, sampled frame observations and HTTP spans. Synthetic frames are sampled observations, not a full 60 fps stream; their P95 describes those samples only. Four independently selectable faults delay playback, remove speed updates, time out requests and increase frame durations. `mixed` combines them.

The Python and TypeScript detectors and generators share an 18-recording conformance corpus. This checks representative calculations, not all possible inputs. The test suite separately checks malformed inputs, evidence, correlation, replay boundaries and report escaping.

## Event replay

Replay reduces events in `(time, stored order)` through the selected cursor, inclusive. Signal values are held until a later sample and show their age. The last observed playback event determines the media state. If multiple sources use the same signal name, the latest observed sample is displayed and its source is retained; analysis still groups speed sources separately. The route artwork is illustrative. The web player does not play an audio recording or drive a device.

## Android measurements

The recorder uses `elapsedRealtimeNanos()` relative to the recorder's creation. Export sorts callback observations by timestamp and stable insertion order. Frame intervals are approximated from callback receipt time minus `FrameMetrics.TOTAL_DURATION`; this is not a precise cross-process presentation timestamp. Dropped frame callbacks are marked.

`app.startup` measures recorder construction through a posted task on the decor view, not cold-launch latency from an OS process start or time-to-fully-drawn. Audio `playing` records an `AudioTrack.play()` call, not acoustic output latency. VHAL speed is converted from m/s to km/h and timestamped at callback receipt, not at the vehicle ECU. The HTTP probe measures one request to the local API; `error` represents non-timeout transport errors and remains visible in the event explorer. The current network budget check does not classify every HTTP error status.

The app observes its own window and player, and a permitted speed property. It does not provide system-wide tracing, multi-zone audio policy verification, physical vehicle fault injection, CAN decoding, arbitrary third-party app instrumentation or safety certification. Those require additional hardware/platform integration and validation.

## References

- [Android audio focus](https://developer.android.com/media/optimize/audio-focus)
- [FrameMetrics](https://developer.android.com/reference/android/view/FrameMetrics)
- [CarPropertyManager](https://developer.android.com/reference/android/car/hardware/property/CarPropertyManager)
- [VehiclePropertyIds](https://developer.android.com/reference/android/car/VehiclePropertyIds)
- [COVESA Vehicle Signal Specification](https://github.com/COVESA/vehicle_signal_specification) — naming inspiration; only the documented subset is used, not a complete VSS server or conformance claim.

