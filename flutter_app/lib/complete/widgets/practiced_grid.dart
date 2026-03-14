import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';
import '../../theme/hanzi_style.dart';

/// Practiced hanzi with cascading entrance — each character fades in
/// with a stagger delay, creating a "waterfall" reveal.
class PracticedGrid extends StatefulWidget {
  final List<dynamic> items;

  const PracticedGrid({super.key, required this.items});

  @override
  State<PracticedGrid> createState() => _PracticedGridState();
}

class _PracticedGridState extends State<PracticedGrid>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      // Total duration scales with item count: ~60ms per item + 400ms base.
      duration: Duration(
        milliseconds: 400 + widget.items.length * 60,
      ),
    )..forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.items.isEmpty) return const SizedBox.shrink();

    final count = widget.items.length;

    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Wrap(
          spacing: 10,
          runSpacing: 10,
          alignment: WrapAlignment.center,
          children: List.generate(count, (i) {
            final map = widget.items[i] is Map<String, dynamic>
                ? widget.items[i] as Map<String, dynamic>
                : <String, dynamic>{};
            final hanzi = map['hanzi'] is String ? map['hanzi'] as String : '';
            final correct = map['correct'] == true;

            // Stagger: each item enters slightly after the previous.
            final itemStart = i / (count + 4);
            final itemEnd = (i + 4) / (count + 4);
            final itemProgress = Interval(
              itemStart.clamp(0.0, 1.0),
              itemEnd.clamp(0.0, 1.0),
              curve: Curves.easeOut,
            ).transform(_controller.value);

            return Transform.translate(
              offset: Offset(0, 8 * (1 - itemProgress)),
              child: Opacity(
                opacity: itemProgress,
                child: _HanziChip(
                  hanzi: hanzi,
                  correct: correct,
                ),
              ),
            );
          }),
        );
      },
    );
  }
}

class _HanziChip extends StatelessWidget {
  final String hanzi;
  final bool correct;
  const _HanziChip({required this.hanzi, required this.correct});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final correctColor = isDark ? AeluColors.correctDark : AeluColors.correct;
    final incorrectColor = isDark ? AeluColors.incorrectDark : AeluColors.incorrect;
    final borderColor = correct ? correctColor : incorrectColor;
    final bgColor = borderColor.withValues(alpha: 0.08);

    return Semantics(
      label: '$hanzi ${correct ? "correct" : "incorrect"}',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: borderColor, width: 1.5),
        ),
        child: Text(hanzi, style: HanziStyle.compact),
      ),
    );
  }
}
