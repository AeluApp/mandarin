import 'package:flutter/material.dart';
import 'timing.dart';

/// Fade in for hanzi character display (500ms).
class HanziReveal extends StatefulWidget {
  final Widget child;

  const HanziReveal({super.key, required this.child});

  @override
  State<HanziReveal> createState() => _HanziRevealState();
}

class _HanziRevealState extends State<HanziReveal> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: AeluTiming.slow)..forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: FadeTransition(opacity: _controller, child: widget.child),
    );
  }
}
