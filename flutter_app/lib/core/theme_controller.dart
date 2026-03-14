import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Theme mode: auto (time-based), light, or dark.
enum ThemePreference { auto, light, dark }

class ThemeController extends StateNotifier<ThemeMode> {
  ThemePreference _preference = ThemePreference.auto;
  Timer? _timer;

  ThemeController() : super(ThemeMode.system) {
    _loadPreference();
    _startAutoCheck();
  }

  ThemePreference get preference => _preference;

  Future<void> _loadPreference() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString('theme_preference');
    if (stored != null) {
      _preference = ThemePreference.values.firstWhere(
        (p) => p.name == stored,
        orElse: () => ThemePreference.auto,
      );
    }
    _applyPreference();
  }

  Future<void> setPreference(ThemePreference pref) async {
    _preference = pref;
    _applyPreference();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('theme_preference', pref.name);
  }

  void _applyPreference() {
    switch (_preference) {
      case ThemePreference.light:
        state = ThemeMode.light;
        break;
      case ThemePreference.dark:
        state = ThemeMode.dark;
        break;
      case ThemePreference.auto:
        state = _autoMode();
        break;
    }
  }

  /// Dark 8pm–6am, light otherwise.
  ThemeMode _autoMode() {
    final hour = DateTime.now().hour;
    return (hour >= 20 || hour < 6) ? ThemeMode.dark : ThemeMode.light;
  }

  void _startAutoCheck() {
    // Check every 15 minutes — transitions only happen at 6am/8pm,
    // so per-minute polling wastes CPU/battery (15x reduction).
    _timer = Timer.periodic(const Duration(minutes: 15), (_) {
      if (_preference == ThemePreference.auto) {
        _applyPreference();
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

final themeControllerProvider = StateNotifierProvider<ThemeController, ThemeMode>((ref) {
  return ThemeController();
});
