import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

/// Progress bar + item counter for session header.
class SessionProgress extends StatelessWidget {
  final int completed;
  final int total;

  const SessionProgress({super.key, required this.completed, required this.total});

  @override
  Widget build(BuildContext context) {
    final progress = total > 0 ? completed / total : 0.0;

    return Semantics(
      label: '$completed of $total items completed',
      child: Column(
        children: [
          if (total > 0)
            LinearProgressIndicator(
              value: progress,
              backgroundColor: Theme.of(context).dividerTheme.color,
              valueColor: AlwaysStoppedAnimation(AeluColors.secondaryOf(context)),
              minHeight: 3,
            ),
        ],
      ),
    );
  }
}
