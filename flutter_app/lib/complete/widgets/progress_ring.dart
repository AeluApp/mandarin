import 'dart:math';

import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';
import '../../core/animations/timing.dart';

/// Animated accuracy ring with glow and gradient stroke.
///
/// Fills from 0→value over 1.2s with overshoot ease. The ring glows
/// at the leading edge to create a sense of energy and completion.
class ProgressRing extends StatefulWidget {
  final double value; // 0.0 to 1.0
  final double size;

  const ProgressRing({super.key, required this.value, this.size = 160});

  @override
  State<ProgressRing> createState() => _ProgressRingState();
}

class _ProgressRingState extends State<ProgressRing>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _progress;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _progress = Tween<double>(begin: 0, end: widget.value).animate(
      CurvedAnimation(parent: _controller, curve: AeluTiming.easeOvershoot),
    );
    // Delay start for dramatic effect — let the screen settle first.
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pct = (widget.value * 100).round();
    final isGood = pct >= 80;
    final color = isGood ? AeluColors.correctOf(context) : AeluColors.accentOf(context);

    return Semantics(
      label: '$pct percent accuracy',
      child: SizedBox(
        width: widget.size,
        height: widget.size,
        child: RepaintBoundary(
          child: AnimatedBuilder(
          animation: _progress,
          builder: (context, _) => CustomPaint(
            painter: _GlowingRingPainter(
              progress: _progress.value.clamp(0.0, 1.0),
              color: color,
              glowColor: color.withValues(alpha: 0.3),
              backgroundColor:
                  Theme.of(context).dividerTheme.color ?? AeluColors.divider,
            ),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '$pct%',
                    style: Theme.of(context).textTheme.displayLarge?.copyWith(
                          fontSize: 36,
                          fontWeight: FontWeight.w700,
                          color: color,
                        ),
                  ),
                  Text(
                    'accuracy',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ),
        ),
        ),
      ),
    );
  }
}

class _GlowingRingPainter extends CustomPainter {
  final double progress;
  final Color color;
  final Color glowColor;
  final Color backgroundColor;

  const _GlowingRingPainter({
    required this.progress,
    required this.color,
    required this.glowColor,
    required this.backgroundColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 10;
    const strokeWidth = 10.0;
    final sweepAngle = 2 * pi * progress;

    // Background ring.
    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..color = backgroundColor
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeWidth,
    );

    if (progress <= 0) return;

    // Glow layer — wider, blurred behind the main arc.
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -pi / 2,
      sweepAngle,
      false,
      Paint()
        ..color = glowColor
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeWidth + 8
        ..strokeCap = StrokeCap.round
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6),
    );

    // Main arc — solid color with round caps.
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -pi / 2,
      sweepAngle,
      false,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeWidth
        ..strokeCap = StrokeCap.round,
    );

    // Leading-edge bright dot — the "head" of the ring.
    if (progress > 0.02) {
      final headAngle = -pi / 2 + sweepAngle;
      final headX = center.dx + radius * cos(headAngle);
      final headY = center.dy + radius * sin(headAngle);
      canvas.drawCircle(
        Offset(headX, headY),
        strokeWidth / 2 + 2,
        Paint()
          ..color = color.withValues(alpha: 0.5)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _GlowingRingPainter old) =>
      old.progress != progress;
}
