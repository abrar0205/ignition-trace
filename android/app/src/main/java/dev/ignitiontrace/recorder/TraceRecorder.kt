package dev.ignitiontrace.recorder

data class RecordedEvent(
    val sequence: Int, val timeMs: Double, val kind: String, val name: String,
    val value: Any? = null, val durationMs: Double? = null, val source: String = "android-app",
    val correlationId: String? = null
)

/** One monotonic clock, a bounded buffer, and stable ordering across callback threads. */
class TraceRecorder(private val clockNs: () -> Long, private val capacity: Int = 10_000) {
    private val origin = clockNs()
    private val events = mutableListOf<RecordedEvent>()
    var dropped = 0
        private set
    fun elapsedMs() = (clockNs() - origin) / 1_000_000.0

    @Synchronized
    fun record(kind: String, name: String, value: Any? = null, durationMs: Double? = null,
               atMs: Double = elapsedMs(), source: String = "android-app", correlationId: String? = null) {
        if (!atMs.isFinite() || atMs < 0 || atMs > 86_400_000 ||
            durationMs?.let { !it.isFinite() || it < 0 || atMs + it > 86_400_000 } == true) return
        if (events.size >= capacity) { dropped++; return }
        events.add(RecordedEvent(events.size, atMs, kind, name, value, durationMs, source, correlationId))
    }

    @Synchronized
    fun snapshot(): List<RecordedEvent> = events.sortedWith(compareBy({ it.timeMs }, { it.sequence }))
}
