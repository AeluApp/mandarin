import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';
import '../../core/animations/timing.dart';

/// Full-width feedback bar — unmistakable correct/wrong signal.
///
/// Slides in with stronger visual: background wash, bold border, icon.
class FeedbackBar extends StatefulWidget {
  final String message;
  final bool correct;

  const FeedbackBar(
      {super.key, required this.message, required this.correct});

  @override
  State<FeedbackBar> createState() => _FeedbackBarState();
}

class _FeedbackBarState extends State<FeedbackBar>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<Offset> _slide;
  late final Animation<double> _opacity;

  @override
  void initState() {
    super.initState();
    _controller =
        AnimationController(vsync: this, duration: AeluTiming.snappy)
          ..forward();
    _slide = Tween<Offset>(
      begin: const Offset(0, 0.15),
      end: Offset.zero,
    ).animate(CurvedAnimation(
        parent: _controller, curve: AeluTiming.easeDefault));
    _opacity = CurvedAnimation(parent: _controller, curve: Curves.easeIn);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final color = widget.correct
        ? (isDark ? AeluColors.correctDark : AeluColors.correct)
        : (isDark ? AeluColors.incorrectDark : AeluColors.incorrect);
    final bgOpacity = widget.correct ? 0.15 : 0.13;
    final icon = widget.correct
        ? Icons.check_circle_outline
        : Icons.cancel_outlined;

    return SlideTransition(
      position: _slide,
      child: FadeTransition(
        opacity: _opacity,
        child: Semantics(
          liveRegion: true,
          label: widget.correct ? 'Correct' : 'Incorrect',
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: color.withValues(alpha: bgOpacity),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: color.withValues(alpha: 0.3)),
            ),
            child: Row(
              children: [
                Icon(icon, size: 18, color: color),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    widget.message,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: color,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
