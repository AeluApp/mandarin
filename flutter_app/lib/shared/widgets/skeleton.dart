import 'package:flutter/material.dart';

import '../../core/animations/shimmer.dart';
import '../../theme/aelu_colors.dart';

/// Skeleton loading line placeholder.
class SkeletonLine extends StatelessWidget {
  final double width;
  final double height;

  const SkeletonLine(
      {super.key, this.width = double.infinity, this.height = 14});

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).brightness == Brightness.dark
        ? AeluColors.surfaceAltDark
        : AeluColors.surfaceAltLight;

    return Shimmer(
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(4),
        ),
      ),
    );
  }
}

/// Skeleton loading panel (card-sized block).
class SkeletonPanel extends StatelessWidget {
  final double height;

  const SkeletonPanel({super.key, this.height = 80});

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).brightness == Brightness.dark
        ? AeluColors.surfaceAltDark
        : AeluColors.surfaceAltLight;

    return Shimmer(
      child: Container(
        width: double.infinity,
        height: height,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(12),
        ),
      ),
    );
  }
}

/// Dashboard skeleton — matches CTA-dominant layout.
class DashboardSkeleton extends StatelessWidget {
  const DashboardSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        children: [
          // Top bar skeleton
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            child: Row(
              children: [
                SkeletonLine(width: 80, height: 20),
                Spacer(),
                SkeletonLine(width: 24, height: 24),
              ],
            ),
          ),
          // Center CTA skeleton
          const Expanded(
            flex: 3,
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SkeletonLine(width: 120, height: 24),
                  SizedBox(height: 24),
                  _CircleSkeleton(size: 172),
                  SizedBox(height: 20),
                  SkeletonLine(width: 140, height: 14),
                ],
              ),
            ),
          ),
          // Bottom mastery skeleton
          Expanded(
            flex: 2,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SkeletonLine(width: 80, height: 16),
                  const SizedBox(height: 12),
                  ...List.generate(
                    3,
                    (_) => const Padding(
                      padding: EdgeInsets.only(bottom: 10),
                      child: SkeletonLine(height: 8),
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      SkeletonLine(width: 56, height: 48),
                      SkeletonLine(width: 56, height: 48),
                      SkeletonLine(width: 56, height: 48),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Session loading skeleton — centered, calm.
class SessionSkeleton extends StatelessWidget {
  const SessionSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return const SafeArea(
      child: Padding(
        padding: EdgeInsets.all(24),
        child: Column(
          children: [
            // Progress bar skeleton
            Padding(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: SkeletonLine(height: 3),
            ),
            Spacer(flex: 2),
            SkeletonLine(width: 80, height: 12),
            SizedBox(height: 16),
            SkeletonLine(width: 120, height: 48),
            SizedBox(height: 12),
            SkeletonLine(width: 200, height: 16),
            Spacer(),
            SkeletonPanel(height: 48),
            SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}

class _CircleSkeleton extends StatelessWidget {
  final double size;
  const _CircleSkeleton({required this.size});

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).brightness == Brightness.dark
        ? AeluColors.surfaceAltDark
        : AeluColors.surfaceAltLight;

    return Shimmer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: color,
        ),
      ),
    );
  }
}
