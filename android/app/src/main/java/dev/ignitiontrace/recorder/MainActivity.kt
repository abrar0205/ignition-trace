package dev.ignitiontrace.recorder

import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.FrameMetrics
import android.view.Window
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.SocketTimeoutException
import java.util.concurrent.Executors
import kotlin.math.PI
import kotlin.math.sin

/** Foreground engineering recorder for emulator/parked development use. */
class MainActivity : ComponentActivity() {
    private val recorder = TraceRecorder(SystemClock::elapsedRealtimeNanos)
    private val handler = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor()
    private var vehicle: VehicleReader? = null
    private lateinit var audio: AudioManager
    private lateinit var focus: AudioFocusRequest
    private var tone: AudioTrack? = null
    private var wantsPlayback = false
    private var message by mutableStateOf("Recorder ready. Events stay on this device until you export.")
    private var vehicleStatus by mutableStateOf("Vehicle signals are optional; connect on an AAOS emulator.")
    private var playback by mutableStateOf(false)
    private var exportBody: String? = null
    private val export = registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) try {
            contentResolver.openOutputStream(uri)?.use { it.write((exportBody ?: "").toByteArray()) }
            message = "Trace exported. Open it in the IgnitionTrace web workbench."
        } catch (_: Exception) { message = "Export failed. Choose another destination." }
        exportBody = null
    }
    private val permission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) connectVehicle() else { vehicleStatus = "Speed permission denied; no speed data recorded." }
    }
    private val frameListener = Window.OnFrameMetricsAvailableListener { _, metrics, dropped ->
        val ns = metrics.getMetric(FrameMetrics.TOTAL_DURATION)
        if (ns >= 0) {
            val duration = ns / 1_000_000.0
            val completed = recorder.elapsedMs()
            recorder.record("frame", "frame.render", durationMs = duration, atMs = (completed - duration).coerceAtLeast(0.0))
        }
        if (dropped > 0) recorder.record("lifecycle", "frame.callback_drops", dropped)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        recorder.record("lifecycle", "app", "created")
        audio = getSystemService(AudioManager::class.java)
        val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build()
        focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN).setAudioAttributes(attributes)
            .setWillPauseWhenDucked(true).setOnAudioFocusChangeListener({ change ->
                when (change) {
                    AudioManager.AUDIOFOCUS_GAIN -> { recorder.record("audio", "media", "gain", correlationId = "media-main"); if (wantsPlayback) playTone() }
                    else -> { recorder.record("audio", "media", if (change == AudioManager.AUDIOFOCUS_LOSS) "loss" else "loss_transient", correlationId = "media-main"); pauseTone(); if (change == AudioManager.AUDIOFOCUS_LOSS) wantsPlayback = false }
                }
            }, handler).build()
        window.addOnFrameMetricsAvailableListener(frameListener, handler)
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = Color(0xFF2454D6))) {
                Column(Modifier.fillMaxSize().background(Color(0xFFF5F3EE)).verticalScroll(rememberScrollState()).padding(28.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text("IGNITIONTRACE / RECORDER", style = MaterialTheme.typography.labelLarge)
                    Text("Capture the moments\nbetween systems.", style = MaterialTheme.typography.headlineLarge)
                    Text("Development instrument. Use while parked or in an emulator. Records this app's frames, focus callbacks, test requests and optional vehicle speed.")
                    Card { Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(if (playback) "Test tone playing" else "Test tone stopped", style = MaterialTheme.typography.titleLarge)
                        Text("Play a quiet generated tone, then interrupt it with another app to observe actual focus callbacks.")
                        Button(onClick = { if (playback) stopPlayback() else requestPlayback() }) { Text(if (playback) "Stop tone" else "Play test tone") }
                    } }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        OutlinedButton(onClick = { requestVehicle() }) { Text("Connect vehicle") }
                        OutlinedButton(onClick = { testNetwork() }) { Text("Test local API") }
                    }
                    Text(vehicleStatus)
                    Text(message)
                    Button(onClick = { exportBody = snapshotJson(); export.launch("ignition-android-trace.json") }) { Text("Export trace JSON") }
                    Text("10,000-event buffer. If full, new events are dropped and the exported recording includes a capture.dropped marker. No background tracking.", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        window.decorView.post { recorder.record("span", "app.startup", durationMs = recorder.elapsedMs(), atMs = 0.0) }
    }

    private fun requestPlayback() {
        wantsPlayback = true
        if (audio.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
            recorder.record("audio", "media", "gain", correlationId = "media-main"); playTone()
        } else { wantsPlayback = false; message = "Audio focus request denied."; recorder.record("lifecycle", "audio.request", "denied") }
    }
    private fun playTone() {
        if (tone == null) {
            val samples = ShortArray(48000) { (sin(2 * PI * 220 * it / 48000) * 1200).toInt().toShort() }
            tone = AudioTrack.Builder().setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
                .setAudioFormat(AudioFormat.Builder().setSampleRate(48000).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setBufferSizeInBytes(samples.size * 2).setTransferMode(AudioTrack.MODE_STATIC).build().apply {
                    write(samples, 0, samples.size); setLoopPoints(0, samples.size, -1)
                }
        }
        tone?.play(); playback = true
        recorder.record("playback", "media", "playing", correlationId = "media-main")
    }
    private fun pauseTone() { tone?.pause(); playback = false; recorder.record("playback", "media", "paused", correlationId = "media-main") }
    private fun stopPlayback() { wantsPlayback = false; pauseTone(); audio.abandonAudioFocusRequest(focus); recorder.record("audio", "media", "loss", correlationId = "media-main") }
    private fun requestVehicle() {
        if (!packageManager.hasSystemFeature(PackageManager.FEATURE_AUTOMOTIVE)) { vehicleStatus = "No automotive service on this device. Use an AAOS emulator."; return }
        if (checkSelfPermission("android.car.permission.CAR_SPEED") == PackageManager.PERMISSION_GRANTED) connectVehicle()
        else permission.launch("android.car.permission.CAR_SPEED")
    }
    private fun connectVehicle() {
        try { vehicle?.close(); vehicle = VehicleReader(this, recorder) { vehicleStatus = it } }
        catch (_: Exception) { vehicleStatus = "Could not connect to the vehicle service." }
    }
    private fun testNetwork() {
        message = "Calling the local API through emulator host 10.0.2.2…"
        executor.execute {
            val started = recorder.elapsedMs()
            var value = "error"
            var connection: HttpURLConnection? = null
            try {
                connection = URL("http://10.0.2.2:8000/api/v1/health").openConnection() as HttpURLConnection
                connection.connectTimeout = 2000; connection.readTimeout = 2000
                value = connection.responseCode.toString()
            } catch (_: SocketTimeoutException) { value = "timeout" }
            catch (_: Exception) { value = "error" }
            finally { connection?.disconnect() }
            recorder.record("span", "http.health", value, recorder.elapsedMs() - started, started, correlationId = "health-${started.toLong()}")
            handler.post { message = "Local API result: $value" }
        }
    }
    private fun snapshotJson(): String {
        val snapshot = recorder.snapshot()
        val duration = maxOf(recorder.elapsedMs(), snapshot.maxOfOrNull { it.timeMs + (it.durationMs ?: 0.0) } ?: 0.0, 1.0)
        val events = JSONArray()
        snapshot.forEachIndexed { i, e -> events.put(JSONObject().put("seq", i).put("t_ms", e.timeMs).put("source", e.source).put("kind", e.kind).put("name", e.name).put("value", e.value ?: JSONObject.NULL).put("duration_ms", e.durationMs ?: JSONObject.NULL).put("correlation_id", e.correlationId ?: JSONObject.NULL)) }
        if (recorder.dropped > 0) events.put(JSONObject().put("seq", snapshot.size).put("t_ms", duration).put("source", "android-app").put("kind", "lifecycle").put("name", "capture.dropped").put("value", recorder.dropped))
        return JSONObject().put("schema_version", "1.0").put("title", "Android recorder session").put("source", "android").put("duration_ms", duration).put("clock", "session-monotonic-ms").put("scenario", "recording").put("seed", 0).put("events", events).toString()
    }
    override fun onStop() { super.onStop(); stopPlayback(); recorder.record("lifecycle", "app", "stopped") }
    override fun onDestroy() {
        window.removeOnFrameMetricsAvailableListener(frameListener); vehicle?.close(); tone?.release(); executor.shutdownNow(); super.onDestroy()
    }
}
