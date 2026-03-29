import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

/// A single confidence bucket with predicted and actual accuracy rates.
class CalibrationBucket {
  /// The predicted accuracy for this confidence level (0.0 to 1.0).
  final double predictedRate;

  /// The actual accuracy observed for this confidence level (0.0 to 1.0).
  final double actualRate;

  /// Number of reviews at this confidence level.
  final int count;

  const CalibrationBucket({
    required this.predictedRate,
    required this.actualRate,
    required this.count,
  });
}

/// Card showing the alignment between a learner's confidence and actual
/// performance.
///
/// Displays a simple bar chart comparing predicted vs actual accuracy
/// for each confidence level (confident, guessing, unsure, unknown).
///
/// Uses Civic Sanctuary aesthetic: serif fonts, warm Mediterranean tones,
/// no gamification, calm data-grounded presentation.
///
/// Empty state shown when fewer than 20 drills have been completed.
class CalibrationCard extends StatelessWidget {
  /// Calibration data keyed by confidence level.
  ///
  /// Expected keys: "full", "half", "narrowed", "unknown".
  final Map<String, CalibrationBucket> buckets;

  /// Overall Brier score (0 = perfect, 1 = worst). Displayed as a
  /// small text indicator beneath the chart.
  final double? brierScore;

  /// Optional calibration feedback message.
  final String? feedback;

  const CalibrationCard({
    super.key,
    required this.buckets,
    this.brierScore,
    this.feedback,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final surfaceColor =
        isDark ? AeluColors.surfaceAltDark : AeluColors.surfaceAltLight;
    final dimColor = isDark ? AeluColors.textDimDark : AeluColors.textDimLight;

    final totalReviews =
        buckets.values.fold<int>(0, (sum, b) => sum + b.count);

    return Semantics(
      label: 'Calibration: comparing your confidence with actual accuracy',
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: surfaceColor,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            // Title
            Text(
              'Calibration',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            Text(
              'Confidence vs accuracy',
              style: theme.textTheme.bodySmall?.copyWith(color: dimColor),
            ),
            const SizedBox(height: 16),

            // Main content: chart or empty state
            if (totalReviews < 20)
              _buildEmptyState(context, dimColor)
            else ...[
              _buildChart(context),
              if (brierScore != null) ...[
                const SizedBox(height: 12),
                _buildBrierIndicator(context, dimColor),
              ],
              if (feedback != null) ...[
                const SizedBox(height: 12),
                _buildFeedback(context),
              ],
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState(BuildContext context, Color dimColor) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24),
      child: Center(
        child: Text(
          'Complete 20+ drills to see your calibration',
          style: theme.textTheme.bodyMedium?.copyWith(color: dimColor),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }

  Widget _buildChart(BuildContext context) {
    // Display order: confident, guessing, unsure, unknown.
    const order = [
      ('full', 'Confident'),
      ('half', 'Guessing'),
      ('narrowed', 'Unsure'),
      ('unknown', 'Unknown'),
    ];

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final (key, label) in order) ...[
          if (buckets.containsKey(key))
            _CalibrationRow(
              label: label,
              bucket: buckets[key]!,
            ),
          if (buckets.containsKey(key) && key != 'unknown')
            const SizedBox(height: 12),
        ],
      ],
    );
  }

  Widget _buildBrierIndicator(BuildContext context, Color dimColor) {
    final theme = Theme.of(context);
    final score = brierScore!;

    // Qualitative label for the Brier score.
    final String quality;
    if (score < 0.1) {
      quality = 'well calibrated';
    } else if (score < 0.2) {
      quality = 'reasonably calibrated';
    } else {
      quality = 'room to improve';
    }

    return Row(
      children: [
        Text(
          'Brier score: ${score.toStringAsFixed(2)}',
          style: theme.textTheme.bodySmall?.copyWith(color: dimColor),
        ),
        const SizedBox(width: 6),
        Text(
          quality,
          style: theme.textTheme.bodySmall?.copyWith(
            color: dimColor,
            fontStyle: FontStyle.italic,
          ),
        ),
      ],
    );
  }

  Widget _buildFeedback(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final accentColor = isDark ? AeluColors.accentDark : AeluColors.accent;

    return Text(
      feedback!,
      style: theme.textTheme.bodySmall?.copyWith(color: accentColor),
    );
  }
}

/// A single row in the calibration chart, showing predicted vs actual bars
/// side by side for one confidence level.
class _CalibrationRow extends StatelessWidget {
  final String label;
  final CalibrationBucket bucket;

  const _CalibrationRow({
    required this.label,
    required this.bucket,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final dimColor = isDark ? AeluColors.textDimDark : AeluColors.textDimLight;
    final accentColor = AeluColors.accentOf(context);
    final trackColor = isDark ? AeluColors.dividerDark : AeluColors.divider;
    final predictedPct = (bucket.predictedRate * 100).round();
    final actualPct = (bucket.actualRate * 100).round();

    return Semantics(
      label: '$label: predicted $predictedPct%, actual $actualPct%, '
          '${bucket.count} reviews',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Label row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                label,
                style: theme.textTheme.bodySmall,
              ),
              Text(
                '${bucket.count} reviews',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: dimColor,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),

          // Predicted bar
          _BarRow(
            label: 'Expected',
            fraction: bucket.predictedRate,
            color: dimColor,
            trackColor: trackColor,
            pctLabel: '$predictedPct%',
          ),
          const SizedBox(height: 3),

          // Actual bar
          _BarRow(
            label: 'Actual',
            fraction: bucket.actualRate,
            color: accentColor,
            trackColor: trackColor,
            pctLabel: '$actualPct%',
          ),
        ],
      ),
    );
  }
}

/// A single horizontal bar with a label and percentage.
class _BarRow extends StatelessWidget {
  final String label;
  final double fraction;
  final Color color;
  final Color trackColor;
  final String pctLabel;

  const _BarRow({
    required this.label,
    required this.fraction,
    required this.color,
    required this.trackColor,
    required this.pctLabel,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final dimColor = isDark ? AeluColors.textDimDark : AeluColors.textDimLight;

    return Row(
      children: [
        SizedBox(
          width: 56,
          child: Text(
            label,
            style: theme.textTheme.labelSmall?.copyWith(
              color: dimColor,
              fontSize: 10,
            ),
          ),
        ),
        Expanded(
          child: SizedBox(
            height: 6,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: Stack(
                children: [
                  // Track
                  Container(
                    decoration: BoxDecoration(
                      color: trackColor,
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                  // Fill
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 400),
                    curve: Curves.easeOutCubic,
                    width: double.infinity,
                    alignment: Alignment.centerLeft,
                    child: FractionallySizedBox(
                      widthFactor: fraction.clamp(0.0, 1.0),
                      child: Container(
                        decoration: BoxDecoration(
                          color: color,
                          borderRadius: BorderRadius.circular(3),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 32,
          child: Text(
            pctLabel,
            style: theme.textTheme.labelSmall?.copyWith(
              color: dimColor,
              fontSize: 10,
            ),
            textAlign: TextAlign.right,
          ),
        ),
      ],
    );
  }
}
