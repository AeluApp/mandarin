# ProGuard rules for Aelu
#
# SECURITY: OWASP M9 (Reverse Engineering) — obfuscate release builds.
# NIST CM-7 (Least Functionality) — strip unused code.
# CIS Mobile 7.1 (Code Obfuscation) — prevent easy reverse engineering.

# Flutter-specific rules
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }
-dontwarn io.flutter.embedding.**

# Keep Dio networking classes
-keep class com.squareup.okhttp3.** { *; }
-dontwarn okhttp3.**
-dontwarn okio.**

# Keep Firebase classes
-keep class com.google.firebase.** { *; }

# Keep Stripe classes
-keep class com.stripe.** { *; }

# Keep WebSocket classes
-keep class org.java_websocket.** { *; }

# Remove debug logging in release
-assumenosideeffects class android.util.Log {
    public static int v(...);
    public static int d(...);
    public static int i(...);
}
