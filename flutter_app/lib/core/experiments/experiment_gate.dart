import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'experiment_provider.dart';

/// Renders [child] only if the user is in the specified [variant]
/// of the specified [experiment]. Otherwise renders [fallback] or nothing.
///
/// Automatically logs exposure on first render.
///
/// Usage:
/// ```dart
/// ExperimentGate(
///   experiment: 'drill_hint_system',
///   variant: 'treatment',
///   child: HintWidget(),
///   fallback: DefaultWidget(),  // optional
/// )
/// ```
class ExperimentGate extends ConsumerStatefulWidget {
  final String experiment;
  final String variant;
  final Widget child;
  final Widget? fallback;

  const ExperimentGate({
    super.key,
    required this.experiment,
    required this.variant,
    required this.child,
    this.fallback,
  });

  @override
  ConsumerState<ExperimentGate> createState() => _ExperimentGateState();
}

class _ExperimentGateState extends ConsumerState<ExperimentGate> {
  bool _exposureLogged = false;

  @override
  Widget build(BuildContext context) {
    final experiments = ref.watch(experimentProvider);
    final isInVariant =
        experiments.isInVariant(widget.experiment, widget.variant);

    if (isInVariant && !_exposureLogged) {
      _exposureLogged = true;
      // Log exposure asynchronously after the frame renders.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        ref.read(experimentProvider.notifier).logExposure(
              widget.experiment,
              context: 'gate:${widget.variant}',
            );
      });
    }

    if (isInVariant) return widget.child;
    return widget.fallback ?? const SizedBox.shrink();
  }
}
