import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../theme/aelu_colors.dart';

/// One-time gesture tutorial overlay for the session screen.
///
/// Shows swipe-right-to-submit, swipe-left-to-skip, pull-down-for-hint.
/// Displayed only on first session (flag stored in SharedPreferences).
class GestureTutorial extends StatefulWidget {
  final VoidCallback onDismiss;
  const GestureTutorial({super.key, required this.onDismiss});

  /// Returns true if the tutorial has already been shown.
  static Future<bool> hasBeenShown() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(prefKey) ?? false;
  }

  /// Marks the tutorial as shown.
  static Future<void> markShown() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(prefKey, true);
  }

  static const prefKey = 'gesture_tutorial_shown';

  @override
  State<GestureTutorial> createState() => _GestureTutorialState();
}

class _GestureTutorialState extends State<GestureTutorial>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _fade;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    )..forward();
    _fade = CurvedAnimation(parent: _controller, curve: Curves.easeOut);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _dismiss() async {
    await _controller.reverse();
    await GestureTutorial.markShown();
    widget.onDismiss();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _fade,
      child: GestureDetector(
        onTap: _dismiss,
        behavior: HitTestBehavior.opaque,
        child: Container(
          color: AeluColors.overlay.withValues(alpha: 0.85),
          child: SafeArea(
            child: Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 40),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const _GestureRow(
                      icon: Icons.arrow_forward_rounded,
                      label: 'Swipe right to submit',
                    ),
                    const SizedBox(height: 28),
                    const _GestureRow(
                      icon: Icons.arrow_back_rounded,
                      label: 'Swipe left to skip',
                    ),
                    const SizedBox(height: 28),
                    const _GestureRow(
                      icon: Icons.arrow_downward_rounded,
                      label: 'Pull down for hint',
                    ),
                    const SizedBox(height: 48),
                    Text(
                      'Tap anywhere to continue',
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AeluColors.onAccent.withValues(alpha: 0.5),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _GestureRow extends StatelessWidget {
  final IconData icon;
  final String label;
  const _GestureRow({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AeluColors.accent.withValues(alpha: 0.3),
          ),
          child: Icon(icon, color: AeluColors.onAccent, size: 24),
        ),
        const SizedBox(width: 16),
        Text(
          label,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            color: AeluColors.onAccent,
          ),
        ),
      ],
    );
  }
}
