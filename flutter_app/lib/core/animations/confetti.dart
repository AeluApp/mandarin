import 'dart:math';

import 'package:flutter/material.dart';

/// Particle burst celebration — warm-toned confetti that drifts down.
///
/// Fires once on trigger, particles fade and fall with gentle sway.
class ConfettiBurst extends StatefulWidget {
  final bool trigger;
  final int particleCount;

  const ConfettiBurst({
    super.key,
    required this.trigger,
    this.particleCount = 40,
  });

  @override
  State<ConfettiBurst> createState() => _ConfettiBurstState();
}

class _ConfettiBurstState extends State<ConfettiBurst>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late List<_Particle> _particles;
  bool _fired = false;

  // Light-mode palette.
  static const _colorsLight = [
    Color(0xFF946070), // accent
    Color(0xFF6A7A5A), // olive
    Color(0xFFD4A574), // gold
    Color(0xFF5A7A5A), // forest
    Color(0xFFB48898), // accent dim
    Color(0xFF9AAA7A), // light olive
  ];

  // Brighter variants for dark backgrounds — keeps the same hue families
  // but ensures particles are visible against #1C2028.
  static const _colorsDark = [
    Color(0xFFB8808E), // accent (dark-safe)
    Color(0xFF8AA070), // olive (dark-safe)
    Color(0xFFE0BA88), // gold (brighter)
    Color(0xFF7AA07A), // forest (dark-safe)
    Color(0xFFC8A0B0), // accent dim (brighter)
    Color(0xFFB0C090), // light olive (brighter)
  ];

  bool _pendingFire = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2500),
    );
    _particles = [];
    if (widget.trigger) _pendingFire = true;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_pendingFire) {
      _pendingFire = false;
      _fire();
    }
  }

  @override
  void didUpdateWidget(ConfettiBurst old) {
    super.didUpdateWidget(old);
    if (widget.trigger && !old.trigger) _fire();
  }

  void _fire() {
    if (_fired) return;
    _fired = true;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = isDark ? _colorsDark : _colorsLight;
    final rng = Random();
    _particles = List.generate(widget.particleCount, (i) {
      return _Particle(
        x: 0.3 + rng.nextDouble() * 0.4, // cluster center
        y: 0.3 + rng.nextDouble() * 0.2,
        vx: (rng.nextDouble() - 0.5) * 0.6,
        vy: -0.2 - rng.nextDouble() * 0.4, // upward burst
        rotation: rng.nextDouble() * pi * 2,
        rotationSpeed: (rng.nextDouble() - 0.5) * 8,
        size: 4 + rng.nextDouble() * 6,
        color: palette[rng.nextInt(palette.length)],
        shape: rng.nextBool() ? _Shape.circle : _Shape.rect,
      );
    });
    _controller.forward(from: 0);
    // Release particle memory when animation completes.
    _controller.addStatusListener(_onAnimationStatus);
  }

  void _onAnimationStatus(AnimationStatus status) {
    if (status == AnimationStatus.completed) {
      _particles = const [];
      _controller.removeStatusListener(_onAnimationStatus);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_particles.isEmpty) return const SizedBox.expand();

    return RepaintBoundary(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return CustomPaint(
            painter: _ConfettiPainter(
              particles: _particles,
              progress: _controller.value,
            ),
            size: Size.infinite,
          );
        },
      ),
    );
  }
}

enum _Shape { circle, rect }

class _Particle {
  final double x, y, vx, vy;
  final double rotation, rotationSpeed, size;
  final Color color;
  final _Shape shape;

  const _Particle({
    required this.x,
    required this.y,
    required this.vx,
    required this.vy,
    required this.rotation,
    required this.rotationSpeed,
    required this.size,
    required this.color,
    required this.shape,
  });
}

class _ConfettiPainter extends CustomPainter {
  final List<_Particle> particles;
  final double progress;

  const _ConfettiPainter({required this.particles, required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    for (final p in particles) {
      final t = progress;
      // Gravity pulls down, initial velocity is up.
      final x = (p.x + p.vx * t) * size.width;
      final y = (p.y + p.vy * t + 0.6 * t * t) * size.height;
      final opacity = (1.0 - t).clamp(0.0, 1.0);
      final rotation = p.rotation + p.rotationSpeed * t;

      if (opacity <= 0) continue;

      canvas.save();
      canvas.translate(x, y);
      canvas.rotate(rotation);

      final paint = Paint()..color = p.color.withValues(alpha: opacity * 0.8);

      if (p.shape == _Shape.circle) {
        canvas.drawCircle(Offset.zero, p.size / 2, paint);
      } else {
        canvas.drawRect(
          Rect.fromCenter(center: Offset.zero, width: p.size, height: p.size * 0.6),
          paint,
        );
      }

      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(covariant _ConfettiPainter old) =>
      old.progress != progress;
}
