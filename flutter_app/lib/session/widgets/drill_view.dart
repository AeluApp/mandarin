import 'package:flutter/material.dart';

import '../../core/animations/breathe.dart';
import '../../core/animations/hanzi_reveal.dart';
import '../../core/animations/staggered_column.dart';
import '../../core/animations/timing.dart';
import '../../theme/aelu_colors.dart';
import '../../theme/hanzi_style.dart';
import '../session_provider.dart';

/// Central drill display — hanzi, pinyin, english, prompt text.
///
/// Entrance pulse: each new drill scales from 1.02x to 1.0 for subtle "pop".
/// Children stagger-cascade at 50 ms intervals via [StaggeredColumn].
class DrillView extends StatefulWidget {
  final SessionState session;
  const DrillView({super.key, required this.session});

  @override
  State<DrillView> createState() => _DrillViewState();
}

class _DrillViewState extends State<DrillView>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulse;
  late Animation<double> _scale;
  String _lastHanzi = '';

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(vsync: this, duration: AeluTiming.fast);
    _scale = Tween<double>(begin: 1.02, end: 1.0).animate(
      CurvedAnimation(parent: _pulse, curve: AeluTiming.easeOvershoot),
    );
    _lastHanzi = widget.session.hanzi;
    _pulse.forward();
  }

  @override
  void didUpdateWidget(covariant DrillView old) {
    super.didUpdateWidget(old);
    if (widget.session.hanzi != _lastHanzi) {
      _lastHanzi = widget.session.hanzi;
      _pulse.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final drillType = widget.session.drillType;

    return ScaleTransition(
      scale: _scale,
      child: Semantics(
        liveRegion: true,
        child: StaggeredColumn(
          mainAxisSize: MainAxisSize.min,
          staggerDelay: const Duration(milliseconds: 50),
          children: [
            // Drill type label
            Text(
              drillType.replaceAll('_', ' ').toUpperCase(),
              style: theme.textTheme.bodySmall?.copyWith(
                letterSpacing: 1.5,
                color: AeluColors.mutedOf(context),
              ),
            ),
            const SizedBox(height: 16),

            // Main hanzi display
            if (widget.session.hanzi.isNotEmpty)
              HanziReveal(
                child: Breathe(
                  child: Text(
                    widget.session.hanzi,
                    style: HanziStyle.display.copyWith(
                      color: theme.textTheme.displayLarge?.color,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            const SizedBox(height: 8),

            // Context / prompt text
            if (widget.session.promptText.isNotEmpty)
              Text(
                widget.session.promptText,
                style: theme.textTheme.bodyLarge,
                textAlign: TextAlign.center,
              ),

            // Show pinyin unless drill is testing pinyin
            if (widget.session.pinyin.isNotEmpty &&
                !drillType.contains('pinyin'))
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  widget.session.pinyin,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: AeluColors.mutedOf(context),
                  ),
                ),
              ),

            // Show english unless drill is testing english
            if (widget.session.english.isNotEmpty &&
                !drillType.contains('english'))
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  widget.session.english,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: AeluColors.mutedOf(context),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
