/// Haptic feedback service for drill results and milestones.
///
/// Provides tactile feedback that reinforces learning outcomes:
/// - Correct answer: light impact (satisfying confirmation)
/// - Near-miss: soft impact (acknowledgment without punishment)
/// - Incorrect: medium impact (clear signal without jarring)
/// - Milestone: heavy impact (celebration)
///
/// Matches the Capacitor bridge haptics at
/// mandarin/web/static/capacitor-bridge.js for cross-platform parity.
///
/// DOCTRINE §9: "Crafted, not decorated" — haptics communicate state,
/// not decoration. Sound + haptic together create ritual (§9).
library;

import 'package:flutter/services.dart';

class HapticsService {
  /// Correct answer — light, satisfying confirmation.
  static Future<void> correctAnswer() async {
    await HapticFeedback.lightImpact();
  }

  /// Near-miss — soft acknowledgment (DOCTRINE §3: normalize error).
  static Future<void> nearMiss() async {
    await HapticFeedback.selectionClick();
  }

  /// Incorrect answer — clear signal, not jarring.
  static Future<void> incorrectAnswer() async {
    await HapticFeedback.mediumImpact();
  }

  /// Milestone reached — celebratory heavy impact.
  static Future<void> milestone() async {
    await HapticFeedback.heavyImpact();
  }

  /// Session complete — medium impact to mark the transition.
  static Future<void> sessionComplete() async {
    await HapticFeedback.mediumImpact();
  }

  /// Generic light tap for UI interactions (button press, selection).
  static Future<void> tap() async {
    await HapticFeedback.selectionClick();
  }
}
