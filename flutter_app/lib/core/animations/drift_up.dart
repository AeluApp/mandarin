import 'package:flutter/material.dart';
import 'timing.dart';

/// Content entrance — translateY(24→0) + fade.
///
/// 24px is the minimum to register as intentional motion on a phone screen.
class DriftUp extends StatefulWidget {
  final Widget child;
  final Duration delay;
  final Duration duration;

  const DriftUp({
    super.key,
    required this.child,
    this.delay = Duration.zero,
    this.duration = AeluTiming.base,
  });

  @override
  State<DriftUp> createState() => _DriftUpState();
}

class _DriftUpState extends State<DriftUp> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<Offset> _offset;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: widget.duration);
    _opacity = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: AeluTiming.easeUpward),
    );
    _offset = Tween<Offset>(
      begin: const Offset(0, 24),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _controller, curve: AeluTiming.easeUpward));

    if (widget.delay == Duration.zero) {
      _controller.forward();
    } else {
      Future.delayed(widget.delay, () {
        if (mounted) _controller.forward();
      });
    }
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
          offset: _offset.value,
          child: Opacity(opacity: _opacity.value, child: child),
        ),
        child: widget.child,
      ),
    );
  }
}
