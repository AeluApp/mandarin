import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Radial fill animation on correct answer — visible, warm, satisfying.
///
/// Spreads from center with 0.25 opacity peak and radial gradient.
class InkSpread extends StatefulWidget {
  final Widget child;
  final Color color;
  final bool trigger;

  const InkSpread({
    super.key,
    required this.child,
    required this.color,
    required this.trigger,
  });

  @override
  State<InkSpread> createState() => _InkSpreadState();
}

class _InkSpreadState extends State<InkSpread>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    if (widget.trigger) _fire();
  }

  @override
  void didUpdateWidget(InkSpread old) {
    super.didUpdateWidget(old);
    if (widget.trigger && !old.trigger) {
      _fire();
    } else if (!widget.trigger && old.trigger) {
      _controller.reset();
    }
  }

  void _fire() {
    unawaited(HapticFeedback.lightImpact());
    _controller.forward(from: 0);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final t = _controller.value;
        // Opacity peaks at 0.25 then fades out.
        final opacity = t < 0.5 ? t * 0.5 : (1.0 - t) * 0.5;

        return RepaintBoundary(
          child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: CustomPaint(
            painter: _InkPainter(
              color: widget.color,
              progress: t,
              opacity: opacity,
            ),
            child: child,
          ),
        ),
        );
      },
      child: widget.child,
    );
  }
}

class _InkPainter extends CustomPainter {
  final Color color;
  final double progress;
  final double opacity;

  const _InkPainter({
    required this.color,
    required this.progress,
    required this.opacity,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (opacity <= 0) return;

    final center = Offset(size.width / 2, size.height / 2);
    final maxRadius = size.longestSide * 0.8;
    final radius = maxRadius * Curves.easeOut.transform(progress);

    final paint = Paint()
      ..shader = RadialGradient(
        colors: [
          color.withValues(alpha: opacity),
          color.withValues(alpha: opacity * 0.3),
          color.withValues(alpha: 0),
        ],
        stops: const [0.0, 0.6, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: radius));

    canvas.drawCircle(center, radius, paint);
  }

  @override
  bool shouldRepaint(covariant _InkPainter old) =>
      old.progress != progress || old.opacity != opacity;
}
