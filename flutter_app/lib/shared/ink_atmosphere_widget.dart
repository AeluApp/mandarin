import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../theme/aelu_colors.dart';

/// Animated gradient mesh background — Flutter port of the web WebGL atmosphere.
///
/// Renders a fullscreen animated gradient using a custom fragment shader.
/// Falls back to a static gradient if the shader fails to load.
///
/// Usage:
/// ```dart
/// Stack(children: [
///   const InkAtmosphere(intensity: 0.18),
///   // your content
/// ])
/// ```
class InkAtmosphere extends StatefulWidget {
  const InkAtmosphere({
    super.key,
    this.intensity = 0.18,
  });

  /// Gradient intensity (0.0–1.0). Matches web scene configs:
  /// marketing: 0.32, login: 0.22, dashboard: 0.18, admin: 0.12
  final double intensity;

  @override
  State<InkAtmosphere> createState() => _InkAtmosphereState();
}

class _InkAtmosphereState extends State<InkAtmosphere>
    with SingleTickerProviderStateMixin {
  ui.FragmentProgram? _program;
  ui.FragmentShader? _shader;
  late Ticker _ticker;
  double _time = 0;
  bool _shaderFailed = false;

  @override
  void initState() {
    super.initState();
    _ticker = createTicker(_onTick)..start();
    _loadShader();
  }

  Future<void> _loadShader() async {
    try {
      _program = await ui.FragmentProgram.fromAsset('shaders/ink_atmosphere.frag');
      _shader = _program!.fragmentShader();
      if (mounted) setState(() {});
    } catch (e) {
      // Shader compilation failed — fall back to static gradient
      debugPrint('InkAtmosphere shader failed: $e');
      if (mounted) setState(() => _shaderFailed = true);
    }
  }

  void _onTick(Duration elapsed) {
    _time = elapsed.inMilliseconds / 1000.0;
    if (_shader != null && mounted) {
      setState(() {});
    }
  }

  @override
  void dispose() {
    _ticker.dispose();
    _shader?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_shaderFailed || _shader == null) {
      return _StaticGradientFallback(intensity: widget.intensity);
    }

    return RepaintBoundary(
      child: CustomPaint(
        painter: _InkAtmospherePainter(
          shader: _shader!,
          time: _time,
          intensity: widget.intensity,
          brightness: Theme.of(context).brightness,
        ),
        size: Size.infinite,
      ),
    );
  }
}

class _InkAtmospherePainter extends CustomPainter {
  _InkAtmospherePainter({
    required this.shader,
    required this.time,
    required this.intensity,
    required this.brightness,
  });

  final ui.FragmentShader shader;
  final double time;
  final double intensity;
  final Brightness brightness;

  @override
  void paint(Canvas canvas, Size size) {
    final isDark = brightness == Brightness.dark;

    // Set uniforms matching the shader's uniform order
    shader.setFloat(0, time);           // uTime
    shader.setFloat(1, size.width);     // uSize.x
    shader.setFloat(2, size.height);    // uSize.y
    shader.setFloat(3, intensity);      // uIntensity

    // uColor1 (accent)
    final accent = isDark ? AeluColors.accentDark : AeluColors.accentLight;
    shader.setFloat(4, accent.red / 255.0);
    shader.setFloat(5, accent.green / 255.0);
    shader.setFloat(6, accent.blue / 255.0);

    // uColor2 (secondary)
    final secondary = isDark ? AeluColors.secondaryDark : AeluColors.secondaryLight;
    shader.setFloat(7, secondary.red / 255.0);
    shader.setFloat(8, secondary.green / 255.0);
    shader.setFloat(9, secondary.blue / 255.0);

    // uColorBase (base)
    final base = isDark ? AeluColors.surfaceDark : AeluColors.surfaceLight;
    shader.setFloat(10, base.red / 255.0);
    shader.setFloat(11, base.green / 255.0);
    shader.setFloat(12, base.blue / 255.0);

    canvas.drawRect(
      Rect.fromLTWH(0, 0, size.width, size.height),
      Paint()..shader = shader,
    );
  }

  @override
  bool shouldRepaint(_InkAtmospherePainter oldDelegate) =>
      time != oldDelegate.time ||
      intensity != oldDelegate.intensity ||
      brightness != oldDelegate.brightness;
}

/// Static gradient fallback when shader isn't available.
class _StaticGradientFallback extends StatelessWidget {
  const _StaticGradientFallback({required this.intensity});

  final double intensity;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final base = isDark ? AeluColors.surfaceDark : AeluColors.surfaceLight;
    final accent = isDark ? AeluColors.accentDark : AeluColors.accentLight;
    final secondary = isDark ? AeluColors.secondaryDark : AeluColors.secondaryLight;

    return Container(
      decoration: BoxDecoration(
        gradient: RadialGradient(
          center: const Alignment(-0.6, -0.7),
          radius: 1.2,
          colors: [
            Color.lerp(base, accent, intensity * 0.3)!,
            Color.lerp(base, secondary, intensity * 0.2)!,
            base,
          ],
          stops: const [0.0, 0.4, 1.0],
        ),
      ),
    );
  }
}
