import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';
import '../../core/animations/pressable_scale.dart';
import '../dashboard_provider.dart';

/// 6-stage segmented mastery bars with animated fill and tap tooltip.
class MasteryBars extends StatelessWidget {
  final Map<String, MasteryLevel> mastery;
  const MasteryBars({super.key, required this.mastery});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (mastery.isEmpty) {
      return Text('No mastery data yet.', style: theme.textTheme.bodyMedium);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Progress', style: theme.textTheme.titleMedium),
        const SizedBox(height: 12),
        ...mastery.entries
            .map((e) => _MasteryBarRow(label: e.key, level: e.value)),
      ],
    );
  }
}

class _MasteryBarRow extends StatefulWidget {
  final String label;
  final MasteryLevel level;
  const _MasteryBarRow({required this.label, required this.level});

  @override
  State<_MasteryBarRow> createState() => _MasteryBarRowState();
}

class _MasteryBarRowState extends State<_MasteryBarRow>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _fill;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _fill = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic),
    );
    // Stagger start slightly based on label hash for visual cascade.
    Future.delayed(
      Duration(milliseconds: 100 + (widget.label.hashCode.abs() % 200)),
      () {
        if (mounted) _controller.forward();
      },
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final level = widget.level;
    if (level.total == 0) return const SizedBox.shrink();

    return Semantics(
      label: '${widget.label}: ${level.durable} durable, ${level.stable} stable, '
          '${level.stabilizing} stabilizing, ${level.passed} passed, '
          '${level.seen} seen, ${level.unseen} unseen of ${level.total} total',
      child: Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: PressableScale(
          onTap: () => _showTooltip(context),
          child: Row(
            children: [
              SizedBox(
                width: 48,
                child: Text(widget.label,
                    style: theme.textTheme.bodySmall),
              ),
              Expanded(
                child: AnimatedBuilder(
                  animation: _fill,
                  builder: (context, _) {
                    return SizedBox(
                      height: 8,
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: CustomPaint(
                          painter: _SegmentedBarPainter(
                            level: level,
                            fillProgress: _fill.value,
                          ),
                          size: const Size(double.infinity, 8),
                        ),
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                width: 38,
                child: Text(
                  '${level.pct.round()}%',
                  style: theme.textTheme.bodySmall,
                  textAlign: TextAlign.right,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showTooltip(BuildContext context) {
    final theme = Theme.of(context);
    final level = widget.level;
    showModalBottomSheet(
      context: context,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Handle bar
            Center(
              child: Container(
                width: 36,
                height: 4,
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: AeluColors.muted.withValues(alpha: 0.3),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            Text(widget.label, style: theme.textTheme.headlineMedium),
            const SizedBox(height: 16),
            _TooltipRow('Durable', level.durable, AeluColors.masteryDurable),
            _TooltipRow('Stable', level.stable, AeluColors.masteryStable),
            _TooltipRow(
                'Stabilizing', level.stabilizing, AeluColors.masteryStabilizing),
            _TooltipRow('Passed', level.passed, AeluColors.masteryPassed),
            _TooltipRow('Seen', level.seen, AeluColors.masterySeen),
            _TooltipRow('Unseen', level.unseen, AeluColors.masteryUnseen),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}

class _TooltipRow extends StatelessWidget {
  final String label;
  final int count;
  final Color color;
  const _TooltipRow(this.label, this.count, this.color);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Container(
            width: 14,
            height: 14,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(3),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(label)),
          Text('$count',
              style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _SegmentedBarPainter extends CustomPainter {
  final MasteryLevel level;
  final double fillProgress;
  const _SegmentedBarPainter(
      {required this.level, required this.fillProgress});

  @override
  void paint(Canvas canvas, Size size) {
    final total = level.total.toDouble();
    if (total == 0) return;

    // Background.
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(0, 0, size.width, size.height),
        const Radius.circular(4),
      ),
      Paint()..color = AeluColors.masteryUnseen.withValues(alpha: 0.3),
    );

    final segments = [
      (level.durable, AeluColors.masteryDurable),
      (level.stable, AeluColors.masteryStable),
      (level.stabilizing, AeluColors.masteryStabilizing),
      (level.passed, AeluColors.masteryPassed),
      (level.seen, AeluColors.masterySeen),
      (level.unseen, AeluColors.masteryUnseen),
    ];

    final maxWidth = size.width * fillProgress;
    var x = 0.0;

    for (final (count, color) in segments) {
      if (count <= 0) continue;
      final w = count / total * size.width;
      final visibleW = (x + w > maxWidth) ? (maxWidth - x) : w;
      if (visibleW <= 0) break;

      canvas.drawRect(
        Rect.fromLTWH(x, 0, visibleW, size.height),
        Paint()..color = color,
      );
      x += w;
    }
  }

  @override
  bool shouldRepaint(covariant _SegmentedBarPainter old) =>
      old.fillProgress != fillProgress;
}
