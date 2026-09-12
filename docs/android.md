# Android / AAOS recorder

The included Kotlin application records its own actual callbacks. It is separate from the synthetic fault lab. Use an emulator or a parked development device. No vehicle writes are implemented.

## Build and install

Use JDK 17, Gradle **8.9**, Android SDK platform **35** and Build Tools **35.0.0**, or import `android/` in Android Studio and configure those versions. The Android Gradle Plugin is 8.7.3; Kotlin 1.9.25 uses Compose compiler 1.5.15.

```sh
cd android
gradle :app:assembleDebug :app:testDebugUnitTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n dev.ignitiontrace.recorder/.MainActivity
```

The GitHub **Build and test → android** job also uploads `ignition-trace-recorder-debug` containing the debug APK. It is a development build, not a signed store release. There is no checked-in Gradle wrapper; install the specified Gradle version or use the CI artifact.

## Capture a session

1. Start the app. Its window frames and lifecycle events enter a 10,000-event buffer.
2. Choose **Play test tone**, then interrupt it with another audio-focus participant. The recorder captures focus callbacks and its own playback calls. Actual focus behavior depends on Android/AAOS policy.
3. On an AAOS emulator, choose **Connect vehicle** and grant speed permission. Use the emulator's vehicle property controls to change speed. Unsupported or denied properties are reported explicitly.
4. Start the local Python API on your computer, then select **Test local API**. The Android emulator accesses it at `10.0.2.2:8000`. A physical phone needs a different development networking arrangement; the supplied probe is emulator-specific.
5. Choose **Export trace JSON**, select a destination, then open the file in the web workbench. It uses the same analysis as the synthetic scenarios.

The app uses the Android Storage Access Framework and does not upload recordings automatically. If the buffer fills, new events are dropped and export includes `capture.dropped`. Restart the activity to begin a fresh session. Stopping the activity pauses its tone. Foreground requests can complete after the stop callback; all timestamps remain on the session clock.

## Platform limits and verification

Minimum Android API 29; target API 35. Vehicle access is optional. Standard Android devices can exercise frames, focus, playback and the HTTP probe without a vehicle service. No background service, microphone, location or storage permission is requested.

CI compiles the app and runs pure JVM recorder tests. A successful build is not evidence of an emulator or physical head-unit run. Use the steps above to perform that integration check on your target environment, then retain the exported recording as evidence. Measurement caveats are documented in [methods](methods.md).

