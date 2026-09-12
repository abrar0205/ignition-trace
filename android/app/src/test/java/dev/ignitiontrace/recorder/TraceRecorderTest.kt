package dev.ignitiontrace.recorder
import org.junit.Assert.*
import org.junit.Test

class TraceRecorderTest {
    @Test fun callbacksAreOrderedAndBounded() {
        var now = 1_000_000_000L
        val recorder = TraceRecorder({ now }, 2)
        now += 100_000_000
        recorder.record("audio", "media", "gain")
        recorder.record("span", "http.health", "200", 20.0, 50.0)
        recorder.record("lifecycle", "app", "started")
        assertEquals(1, recorder.dropped)
        assertEquals(listOf(50.0, 100.0), recorder.snapshot().map { it.timeMs })
        assertEquals(100.0, recorder.elapsedMs(), 0.01)
    }
    @Test fun invalidClockValuesDoNotEnterTrace() {
        val recorder = TraceRecorder({ 0L })
        recorder.record("span", "x", durationMs = -1.0)
        recorder.record("audio", "media", atMs = Double.NaN)
        assertTrue(recorder.snapshot().isEmpty())
    }
}
