import 'dart:math';
import 'dart:ui';

import 'package:flutter/material.dart';

import '../theme/aelu_colors.dart';

/// Brief ink trail following the finger on answer submission.
///
/// Wraps a child widget. On tap/swipe, renders a short ink trail
/// along the gesture path that fades over 400ms.
///
/// Usage:
/// ```dart
/// InkTrailOverlay(
///   onTap: () => submitAnswer(),
///   child: AnswerButton(...),
/// )
/// ```
class InkTrailOverlay extends StatefulWidget {
  const InkTrailOverlay({
    super.key,
    required this.child,
    this.onTap,
    this.enabled = true,
  });

  final Widget child;
  final VoidCallback? onTap;
  final bool enabled;

  @override
  State<InkTrailOverlay> createState() => _InkTrailOverlayState();
}

class _InkTrailOverlayState extends State<InkTrailOverlay>
    with SingleTickerProviderStateMixin {
  final List<_TrailPoint> _points = [];
  late AnimationController _fadeController;

  @override
  void initState() {
    super.initState();
    _fadeController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    )..addStatusListener((status) {
        if (status == AnimationStatus.completed) {
          setState(() => _points.clear());
        }
      });
  }

  @override
  void dispose() {
    _fadeController.dispose();
    super.dispose();
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (!widget.enabled) return;
    setState(() {
      _points.add(_TrailPoint(
        offset: details.localPosition,
        timestamp: DateTime.now(),
      ));
      // Keep trail short
      if (_points.length > 30) _points.removeAt(0);
    });
  }

  void _onPanEnd(DragEndDetails details) {
    _fadeController.forward(from: 0);
    widget.onTap?.call();
  }

  void _onTapDown(TapDownDetails details) {
    if (!widget.enabled) return;
    setState(() {
      _points.clear();
      _points.add(_TrailPoint(
        offset: details.localPosition,
        timestamp: DateTime.now(),
      ));
    });
  }

  void _onTapUp(TapUpDetails details) {
    _fadeController.forward(from: 0);
    widget.onTap?.call();
  }

  @override
  Widget build(BuildContext context) {
    // Respect reduced motion
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    if (reduceMotion || !widget.enabled) {
      return GestureDetector(onTap: widget.onTap, child: widget.child);
    }

    return GestureDetector(
      onTapDown: _onTapDown,
      onTapUp: _onTapUp,
      onPanUpdate: _onPanUpdate,
      onPanEnd: _onPanEnd,
      child: AnimatedBuilder(
        animation: _fadeController,
        builder: (context, child) {
          return CustomPaint(
            foregroundPainter: _InkTrailPainter(
              points: _points,
              fadeProgress: _fadeController.value,
              color: Theme.of(context).brightness == Brightness.dark
                  ? AeluColors.accentDark
                  : AeluColors.accentLight,
            ),
            child: child,
          );
        },
        child: widget.child,
      ),
    );
  }
}

class _TrailPoint {
  _TrailPoint({required this.offset, required this.timestamp});
  final Offset offset;
  final DateTime timestamp;
}

class _InkTrailPainter extends CustomPainter {
  _InkTrailPainter({
    required this.points,
    required this.fadeProgress,
    required this.color,
  });

  final List<_TrailPoint> points;
  final double fadeProgress;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.isEmpty) return;

    final opacity = (1 - fadeProgress) * 0.4;
    if (opacity <= 0) return;

    final paint = Paint()
      ..color = color.withOpacity(opacity)
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    for (var i = 1; i < points.length; i++) {
      final t = i / points.length;
      paint.strokeWidth = 2.0 + (1 - t) * 2.0; // thicker at start
      canvas.drawLine(points[i - 1].offset, points[i].offset, paint);
    }

    // Draw dots at each point
    final dotPaint = Paint()
      ..color = color.withOpacity(opacity * 0.6)
      ..style = PaintingStyle.fill;

    for (var i = 0; i < points.length; i += 3) {
      final t = i / points.length;
      final radius = 1.5 + (1 - t) * 1.5;
      canvas.drawCircle(points[i].offset, radius * (1 - fadeProgress), dotPaint);
    }
  }

  @override
  bool shouldRepaint(_InkTrailPainter oldDelegate) =>
      fadeProgress != oldDelegate.fadeProgress || points.length != oldDelegate.points.length;
}
