package dev.ignitiontrace.recorder

import android.car.Car
import android.car.VehiclePropertyIds
import android.car.hardware.CarPropertyValue
import android.car.hardware.property.CarPropertyManager
import android.content.Context

/** Read-only VHAL client. Permission failures are explicit, never simulated as real samples. */
class VehicleReader(context: Context, private val recorder: TraceRecorder, private val status: (String) -> Unit) {
    private val car = Car.createCar(context)
    private val manager = car?.getCarManager(Car.PROPERTY_SERVICE) as? CarPropertyManager
    private val callback = object : CarPropertyManager.CarPropertyEventCallback {
        override fun onChangeEvent(value: CarPropertyValue<*>) {
            if (value.status != CarPropertyValue.STATUS_AVAILABLE) {
                recorder.record("lifecycle", "vhal.speed", "unavailable"); return
            }
            val speed = (value.value as? Number)?.toDouble() ?: return
            if (!speed.isFinite()) return
            // Receipt time on our session clock; VHAL device timestamp is not assumed aligned.
            recorder.record("signal", "Vehicle.Speed", speed * 3.6, source = "vhal-receipt")
        }
        override fun onErrorEvent(propertyId: Int, areaId: Int) {
            recorder.record("lifecycle", "vhal.speed", "read_error")
        }
    }
    init {
        try {
            val registered = manager?.registerCallback(callback, VehiclePropertyIds.PERF_VEHICLE_SPEED, CarPropertyManager.SENSOR_RATE_NORMAL) == true
            status(if (registered) "VHAL speed subscribed (km/h)" else "VHAL speed unavailable on this device")
        } catch (_: SecurityException) { status("Vehicle speed permission denied") }
        catch (_: IllegalArgumentException) { status("Vehicle speed property unsupported") }
    }
    fun close() { manager?.unregisterCallback(callback); car?.disconnect() }
}
