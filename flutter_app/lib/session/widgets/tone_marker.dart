import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/aelu_colors.dart';
import '../../core/animations/pressable_scale.dart';

/// Tone selection with haptic contour patterns that teach the tone shape.
///
/// Each tone has a distinct haptic pattern that mimics its pitch contour:
/// - Tone 1 (high flat): sustained vibration
/// - Tone 2 (rising): two ascending taps
/// - Tone 3 (dip-rise): tap-pause-tap-tap (dip then up)
/// - Tone 4 (falling): single sharp heavy tap
/// - Neutral: bare minimum light tap
class ToneMarker extends StatelessWidget {
  final ValueChanged<String> onSelect;

  const ToneMarker({super.key, required this.onSelect});

  static const _tones = [
    _ToneData('1', 'High flat', [0.15, 0.35, 0.55, 0.75], 'ˉ'),
    _ToneData('2', 'Rising', [0.3, 0.7], 'ˊ'),
    _ToneData('3', 'Dip-rise', [0.2, 0.5, 0.8], 'ˇ'),
    _ToneData('4', 'Falling', [0.5], 'ˋ'),
    _ToneData('0', 'Neutral', [0.5], '·'),
  ];

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: _tones.map((tone) {
        return _ToneButton(
          tone: tone,
          onSelect: () => onSelect(tone.number),
        );
      }).toList(),
    );
  }
}

class _ToneData {
  final String number;
  final String label;
  final List<double> hapticTimings; // normalized 0-1 within 300ms window
  final String diacritic;

  const _ToneData(this.number, this.label, this.hapticTimings, this.diacritic);
}

class _ToneButton extends StatefulWidget {
  final _ToneData tone;
  final VoidCallback onSelect;

  const _ToneButton({required this.tone, required this.onSelect});

  @override
  State<_ToneButton> createState() => _ToneButtonState();
}

class _ToneButtonState extends State<_ToneButton> {
  bool _active = false;

  Future<void> _fireHapticPattern() async {
    setState(() => _active = true);

    final pattern = widget.tone.hapticTimings;
    const windowMs = 300;

    for (var i = 0; i < pattern.length; i++) {
      final delayMs = i == 0
          ? (pattern[i] * windowMs).round()
          : ((pattern[i] - pattern[i - 1]) * windowMs).round();

      if (delayMs > 0) {
        await Future.delayed(Duration(milliseconds: delayMs));
      }

      // Vary intensity by tone:
      switch (widget.tone.number) {
        case '1': // sustained = repeated light
          unawaited(HapticFeedback.lightImpact());
          break;
        case '2': // rising = light then medium
          if (i == 0) {
            unawaited(HapticFeedback.lightImpact());
          } else {
            unawaited(HapticFeedback.mediumImpact());
          }
          break;
        case '3': // dip = medium, light, medium
          if (i == 1) {
            unawaited(HapticFeedback.selectionClick());
          } else {
            unawaited(HapticFeedback.mediumImpact());
          }
          break;
        case '4': // falling = single heavy
          unawaited(HapticFeedback.heavyImpact());
          break;
        default: // neutral = bare selection
          unawaited(HapticFeedback.selectionClick());
      }
    }

    if (mounted) setState(() => _active = false);
    widget.onSelect();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Semantics(
      button: true,
      label: 'Tone ${widget.tone.number}, ${widget.tone.label}',
      child: PressableScale(
        onTap: _fireHapticPattern,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          width: 64,
          height: 64,
          decoration: BoxDecoration(
            color: _active
                ? AeluColors.accentOf(context).withValues(alpha: 0.12)
                : (isDark
                    ? AeluColors.surfaceAltDark
                    : AeluColors.surfaceAltLight),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: _active
                  ? AeluColors.accentOf(context)
                  : (isDark ? AeluColors.dividerDark : AeluColors.divider),
              width: _active ? 2 : 1,
            ),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Tone number
              Text(
                widget.tone.number,
                style: theme.textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 2),
              // Tone contour visual
              SizedBox(
                width: 32,
                height: 16,
                child: CustomPaint(
                  painter: _ToneContourPainter(
                    toneNumber: widget.tone.number,
                    color: _active
                        ? AeluColors.accentOf(context)
                        : AeluColors.mutedOf(context),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Paints the pitch contour of each tone.
class _ToneContourPainter extends CustomPainter {
  final String toneNumber;
  final Color color;

  const _ToneContourPainter({required this.toneNumber, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    final w = size.width;
    final h = size.height;
    final path = Path();

    switch (toneNumber) {
      case '1': // High flat line
        path.moveTo(0, h * 0.25);
        path.lineTo(w, h * 0.25);
        break;
      case '2': // Rising
        path.moveTo(0, h * 0.75);
        path.cubicTo(w * 0.3, h * 0.7, w * 0.7, h * 0.35, w, h * 0.15);
        break;
      case '3': // Dip then rise
        path.moveTo(0, h * 0.35);
        path.cubicTo(w * 0.25, h * 0.5, w * 0.45, h * 0.85, w * 0.5, h * 0.85);
        path.cubicTo(w * 0.55, h * 0.85, w * 0.75, h * 0.5, w, h * 0.2);
        break;
      case '4': // Falling
        path.moveTo(0, h * 0.15);
        path.cubicTo(w * 0.3, h * 0.25, w * 0.7, h * 0.65, w, h * 0.85);
        break;
      case '0': // Neutral — dot
        canvas.drawCircle(Offset(w / 2, h / 2), 2.5, Paint()..color = color);
        return;
    }

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _ToneContourPainter old) =>
      old.toneNumber != toneNumber || old.color != color;
}
