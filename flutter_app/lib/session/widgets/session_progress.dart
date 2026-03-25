import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

/// Drill / session progress bar — styled to match the web:
///   4px height, 85% opacity, accent-color gradient fill.
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
            Opacity(
              opacity: 0.85,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(2),
                child: SizedBox(
                  height: 4,
                  child: Stack(
                    children: [
                      // Track background
                      Container(
                        color: Theme.of(context).dividerTheme.color,
                      ),
                      // Gradient fill
                      FractionallySizedBox(
                        widthFactor: progress,
                        child: Container(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              colors: [
                                AeluColors.accentOf(context),
                                AeluColors.secondaryOf(context),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
