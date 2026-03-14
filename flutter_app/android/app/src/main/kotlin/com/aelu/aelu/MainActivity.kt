package com.aelu.aelu

import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * MainActivity with security hardening.
 *
 * OWASP M9 (Reverse Engineering): FLAG_SECURE prevents screenshots/screen recording.
 * CIS Mobile 4.3 (Screen Capture Prevention): Togglable per-screen.
 * NIST SC-28 (Protection of Information at Rest): Prevents task switcher preview.
 */
class MainActivity : FlutterActivity() {
    private val SECURITY_CHANNEL = "aelu/security"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, SECURITY_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "enableSecureFlag" -> {
                        window.setFlags(
                            WindowManager.LayoutParams.FLAG_SECURE,
                            WindowManager.LayoutParams.FLAG_SECURE
                        )
                        result.success(null)
                    }
                    "disableSecureFlag" -> {
                        window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
    }
}
