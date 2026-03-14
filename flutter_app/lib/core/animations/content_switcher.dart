import 'package:flutter/material.dart';

import 'timing.dart';

/// Cross-fades between child widgets when they change.
///
/// Use this to wrap loading/error/content ternary patterns so state
/// transitions animate smoothly instead of popping in abruptly.
///
/// Each child must have a unique [ValueKey] for AnimatedSwitcher to
/// detect the change and trigger the cross-fade.
class ContentSwitcher extends StatelessWidget {
  final Widget child;
  final Duration duration;

  const ContentSwitcher({
    super.key,
    required this.child,
    this.duration = AeluTiming.fast,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: duration,
      switchInCurve: AeluTiming.easeDefault,
      switchOutCurve: AeluTiming.easeDefault,
      transitionBuilder: (child, animation) {
        return FadeTransition(opacity: animation, child: child);
      },
      child: child,
    );
  }
}
