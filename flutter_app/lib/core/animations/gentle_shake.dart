import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Horizontal shake on incorrect answer: translateX(-8, 8, -5, 2, 0).
///
/// 8px amplitude + haptic = unmistakable "wrong" signal.
class GentleShake extends StatefulWidget {
  final Widget child;
  final bool trigger;

  const GentleShake({
    super.key,
    required this.child,
    required this.trigger,
  });

  @override
  State<GentleShake> createState() => _GentleShakeState();
}

class _GentleShakeState extends State<GentleShake>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _offset;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 500),
    );
    _offset = TweenSequence<double>([
      TweenSequenceItem(tween: Tween(begin: 0, end: -8), weight: 1),
      TweenSequenceItem(tween: Tween(begin: -8, end: 8), weight: 1),
      TweenSequenceItem(tween: Tween(begin: 8, end: -5), weight: 1),
      TweenSequenceItem(tween: Tween(begin: -5, end: 2), weight: 1),
      TweenSequenceItem(tween: Tween(begin: 2, end: 0), weight: 1),
    ]).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));

    if (widget.trigger) _fire();
  }

  @override
  void didUpdateWidget(GentleShake old) {
    super.didUpdateWidget(old);
    if (widget.trigger && !old.trigger) _fire();
  }

  void _fire() {
    HapticFeedback.mediumImpact();
    _controller.forward(from: 0);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) => Transform.translate(
          offset: Offset(_offset.value, 0),
          child: child,
        ),
        child: widget.child,
      ),
    );
  }
}
