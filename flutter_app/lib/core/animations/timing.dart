import 'package:flutter/animation.dart';

/// Animation timing tokens matching the web CSS system.
class AeluTiming {
  AeluTiming._();

  // ── Durations ──
  static const press = Duration(milliseconds: 100);
  static const micro = Duration(milliseconds: 120);
  static const fast = Duration(milliseconds: 200);
  static const nav = Duration(milliseconds: 300);
  static const base = Duration(milliseconds: 400);
  static const slow = Duration(milliseconds: 500);
  static const reveal = Duration(milliseconds: 800);
  static const complete = Duration(milliseconds: 1200);
  static const ambient = Duration(milliseconds: 1800);

  // ── Curves ──
  static const easeDefault = Curves.easeOutCubic;
  static const easeUpward = Cubic(0.16, 1.0, 0.3, 1.0);
  static const easeOvershoot = Cubic(0.34, 1.56, 0.64, 1.0);
}
