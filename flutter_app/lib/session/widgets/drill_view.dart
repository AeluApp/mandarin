import 'package:flutter/material.dart';

import '../../core/animations/breathe.dart';
import '../../core/animations/hanzi_reveal.dart';
import '../../theme/aelu_colors.dart';
import '../../theme/hanzi_style.dart';
import '../session_provider.dart';

/// Central drill display — hanzi, pinyin, english, prompt text.
class DrillView extends StatelessWidget {
  final SessionState session;
  const DrillView({super.key, required this.session});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final drillType = session.drillType;

    return Semantics(
      liveRegion: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
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
          if (session.hanzi.isNotEmpty)
            HanziReveal(
              child: Breathe(
                child: Text(
                  session.hanzi,
                  style: HanziStyle.display.copyWith(
                    color: theme.textTheme.displayLarge?.color,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          const SizedBox(height: 8),

          // Context / prompt text
          if (session.promptText.isNotEmpty)
            Text(
              session.promptText,
              style: theme.textTheme.bodyLarge,
              textAlign: TextAlign.center,
            ),

          // Show pinyin unless drill is testing pinyin
          if (session.pinyin.isNotEmpty && !drillType.contains('pinyin'))
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                session.pinyin,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: AeluColors.mutedOf(context),
                ),
              ),
            ),

          // Show english unless drill is testing english
          if (session.english.isNotEmpty && !drillType.contains('english'))
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                session.english,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: AeluColors.mutedOf(context),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
