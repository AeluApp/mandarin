import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';
import '../../core/animations/timing.dart';

/// 48px centered horizontal line, the "horizon" divider.
class Horizon extends StatelessWidget {
  final bool animated;

  const Horizon({super.key, this.animated = false});

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).brightness == Brightness.dark
        ? AeluColors.dividerDark
        : AeluColors.divider;

    if (!animated) {
      return Center(
        child: Container(width: 48, height: 1, color: color),
      );
    }

    return Center(child: _AnimatedHorizon(color: color));
  }
}

class _AnimatedHorizon extends StatefulWidget {
  final Color color;
  const _AnimatedHorizon({required this.color});

  @override
  State<_AnimatedHorizon> createState() => _AnimatedHorizonState();
}

class _AnimatedHorizonState extends State<_AnimatedHorizon>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _width;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: AeluTiming.slow)..forward();
    _width = Tween<double>(begin: 0, end: 48).animate(
      CurvedAnimation(parent: _controller, curve: AeluTiming.easeUpward),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _width,
      builder: (context, _) => Container(
        width: _width.value,
        height: 1,
        color: widget.color,
      ),
    );
  }
}
