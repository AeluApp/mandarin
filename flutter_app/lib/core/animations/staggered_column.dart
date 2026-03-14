import 'package:flutter/material.dart';

import 'timing.dart';

/// Animates children in with a cascading stagger delay.
///
/// Each child fades in and slides up with a delay based on its index.
/// Use this for list tiles, settings rows, or any vertical list of items.
class StaggeredColumn extends StatefulWidget {
  final List<Widget> children;
  final Duration itemDuration;
  final Duration staggerDelay;
  final CrossAxisAlignment crossAxisAlignment;
  final MainAxisAlignment mainAxisAlignment;
  final MainAxisSize mainAxisSize;

  const StaggeredColumn({
    super.key,
    required this.children,
    this.itemDuration = AeluTiming.base,
    this.staggerDelay = const Duration(milliseconds: 50),
    this.crossAxisAlignment = CrossAxisAlignment.center,
    this.mainAxisAlignment = MainAxisAlignment.start,
    this.mainAxisSize = MainAxisSize.max,
  });

  @override
  State<StaggeredColumn> createState() => _StaggeredColumnState();
}

class _StaggeredColumnState extends State<StaggeredColumn>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    final totalDelay =
        widget.staggerDelay.inMilliseconds * widget.children.length;
    final totalDuration =
        widget.itemDuration.inMilliseconds + totalDelay;
    _controller = AnimationController(
      vsync: this,
      duration: Duration(milliseconds: totalDuration),
    )..forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final totalMs = _controller.duration!.inMilliseconds;
    final itemMs = widget.itemDuration.inMilliseconds;
    final staggerMs = widget.staggerDelay.inMilliseconds;

    return Column(
      crossAxisAlignment: widget.crossAxisAlignment,
      mainAxisAlignment: widget.mainAxisAlignment,
      mainAxisSize: widget.mainAxisSize,
      children: List.generate(widget.children.length, (i) {
        final startMs = i * staggerMs;
        final endMs = startMs + itemMs;
        final begin = (startMs / totalMs).clamp(0.0, 1.0);
        final end = (endMs / totalMs).clamp(0.0, 1.0);

        final animation = CurvedAnimation(
          parent: _controller,
          curve: Interval(begin, end, curve: AeluTiming.easeDefault),
        );

        return AnimatedBuilder(
          animation: animation,
          builder: (context, child) {
            return Opacity(
              opacity: animation.value,
              child: Transform.translate(
                offset: Offset(0, 12 * (1 - animation.value)),
                child: child,
              ),
            );
          },
          child: widget.children[i],
        );
      }),
    );
  }
}
