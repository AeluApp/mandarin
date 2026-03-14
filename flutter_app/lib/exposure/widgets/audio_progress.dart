import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

/// Seekable audio progress bar.
class AudioProgress extends StatelessWidget {
  final Duration position;
  final Duration duration;
  final ValueChanged<Duration> onSeek;

  const AudioProgress({
    super.key,
    required this.position,
    required this.duration,
    required this.onSeek,
  });

  @override
  Widget build(BuildContext context) {
    final total = duration.inMilliseconds.toDouble();
    final current = position.inMilliseconds.toDouble();
    final value = total > 0 ? (current / total).clamp(0.0, 1.0) : 0.0;

    return Semantics(
      label: '${_format(position)} of ${_format(duration)}',
      child: Column(
        children: [
          SliderTheme(
            data: SliderThemeData(
              trackHeight: 3,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
              activeTrackColor: AeluColors.accentOf(context),
              inactiveTrackColor: Theme.of(context).dividerTheme.color,
              thumbColor: AeluColors.accentOf(context),
              overlayShape: const RoundSliderOverlayShape(overlayRadius: 16),
            ),
            child: Slider(
              value: value,
              onChanged: (v) {
                final ms = (v * total).round();
                onSeek(Duration(milliseconds: ms));
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_format(position), style: Theme.of(context).textTheme.bodySmall),
                Text(_format(duration), style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _format(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }
}
