/// Optional biometric authentication gate.
///
/// Uses local_auth for fingerprint / Face ID on supported devices.
/// Configurable: user can enable or disable in settings.
/// Fallback: device PIN / passcode via [AuthenticationOptions.biometricOnly] = false.
///
/// Security references:
/// - OWASP M4 (Insecure Authentication): Local biometric factor.
/// - NIST IA-2 (Identification and Authentication): Multi-factor support.
/// - ISO 27001 A.9.4.2 (Secure log-on procedures): Device-level gate.
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:local_auth/local_auth.dart';

class BiometricGate {
  BiometricGate._();

  static final _auth = LocalAuthentication();

  /// Check if the device supports any form of biometric authentication.
  ///
  /// Returns false on devices without biometric hardware, when
  /// no biometrics are enrolled, or when the platform call fails.
  static Future<bool> isAvailable() async {
    try {
      final canCheck = await _auth.canCheckBiometrics;
      final isDeviceSupported = await _auth.isDeviceSupported();
      return canCheck || isDeviceSupported;
    } on PlatformException catch (e, st) {
      _logError('isAvailable', e, st);
      return false;
    }
  }

  /// Return the list of biometric types enrolled on this device.
  ///
  /// Possible values: [BiometricType.fingerprint], [BiometricType.face],
  /// [BiometricType.iris], [BiometricType.strong], [BiometricType.weak].
  ///
  /// Returns an empty list on failure or when no biometrics are enrolled.
  static Future<List<BiometricType>> availableTypes() async {
    try {
      return await _auth.getAvailableBiometrics();
    } on PlatformException catch (e, st) {
      _logError('availableTypes', e, st);
      return [];
    }
  }

  /// Authenticate the user with biometric or device credential.
  ///
  /// [reason] is displayed in the system authentication dialog.
  /// Keep it factual and calm — Civic Sanctuary voice.
  ///
  /// On iOS: uses Face ID or Touch ID, falling back to passcode.
  /// On Android: uses BiometricPrompt, falling back to device credential.
  ///
  /// Returns true if authentication succeeded, false otherwise.
  /// Never throws — all platform exceptions are caught and logged.
  static Future<bool> authenticate({
    String reason = 'Verify your identity to continue',
  }) async {
    try {
      return await _auth.authenticate(
        localizedReason: reason,
        options: const AuthenticationOptions(
          // Allow device PIN/passcode as fallback.
          biometricOnly: false,
          // Use the platform-native dialog (no custom UI).
          useErrorDialogs: true,
          // Require the user to actively confirm (no passive face unlock).
          stickyAuth: true,
        ),
      );
    } on PlatformException catch (e, st) {
      _logError('authenticate', e, st);
      return false;
    }
  }

  /// Cancel any in-progress authentication dialog.
  ///
  /// Safe to call even if no dialog is currently showing.
  static Future<void> cancelAuthentication() async {
    try {
      await _auth.stopAuthentication();
    } on PlatformException catch (e, st) {
      _logError('cancelAuthentication', e, st);
    }
  }

  // ── Internal ──

  static void _logError(String operation, Object error, StackTrace st) {
    if (kDebugMode) {
      debugPrint('BiometricGate.$operation failed: $error');
    }
  }
}
