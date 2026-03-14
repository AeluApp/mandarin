import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';
import '../../theme/hanzi_style.dart';

/// RichText-based passage renderer — uses TextSpan instead of per-character widgets.
/// Supports multi-char lookup: tries 4→3→2→1 char substrings from tap position.
///
/// Performance: TapGestureRecognizers are cached and reused across rebuilds.
/// They are only recreated when the text changes, and properly disposed.
class ReaderPassage extends StatefulWidget {
  final String text;
  final ValueChanged<String> onWordTap;

  const ReaderPassage({super.key, required this.text, required this.onWordTap});

  @override
  State<ReaderPassage> createState() => _ReaderPassageState();
}

class _ReaderPassageState extends State<ReaderPassage> {
  static final _hanziRegex = RegExp(r'[\u4e00-\u9fff]');

  final List<TapGestureRecognizer> _recognizers = [];
  String _cachedText = '';

  @override
  void dispose() {
    _disposeRecognizers();
    super.dispose();
  }

  void _disposeRecognizers() {
    for (final r in _recognizers) {
      r.dispose();
    }
    _recognizers.clear();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? AeluColors.textDark : AeluColors.textLight;
    final underlineColor = isDark
        ? AeluColors.accent.withValues(alpha: 0.45)
        : AeluColors.muted.withValues(alpha: 0.5);

    // Only rebuild recognizers when text changes.
    if (widget.text != _cachedText) {
      _disposeRecognizers();
      _cachedText = widget.text;
    }

    final chars = widget.text.characters.toList();
    final spans = <InlineSpan>[];
    var recognizerIndex = 0;

    for (var i = 0; i < chars.length; i++) {
      final char = chars[i];
      final isHanzi = _hanziRegex.hasMatch(char);

      if (isHanzi) {
        final tapIndex = i;

        // Reuse existing recognizer or create a new one.
        TapGestureRecognizer recognizer;
        if (recognizerIndex < _recognizers.length) {
          recognizer = _recognizers[recognizerIndex];
        } else {
          recognizer = TapGestureRecognizer();
          _recognizers.add(recognizer);
        }
        recognizer.onTap = () => _handleTap(chars, tapIndex);
        recognizerIndex++;

        spans.add(TextSpan(
          text: char,
          style: HanziStyle.reader.copyWith(
            color: textColor,
            decoration: TextDecoration.underline,
            decorationStyle: TextDecorationStyle.dotted,
            decorationColor: underlineColor,
            decorationThickness: isDark ? 1.5 : 1.0,
          ),
          recognizer: recognizer,
        ));
      } else {
        spans.add(TextSpan(
          text: char,
          style: HanziStyle.reader.copyWith(color: textColor),
        ));
      }
    }

    // Dispose any excess recognizers from a previous longer text.
    while (_recognizers.length > recognizerIndex) {
      _recognizers.removeLast().dispose();
    }

    return SelectionArea(
      child: RichText(
        text: TextSpan(children: spans),
      ),
    );
  }

  /// Multi-char lookup: try 4→3→2→1 char substring from tap position.
  void _handleTap(List<String> chars, int index) {
    for (var len = 4; len >= 1; len--) {
      if (index + len > chars.length) continue;
      final substr = chars.sublist(index, index + len).join();
      final allHanzi = _hanziRegex.hasMatch(substr);
      if (allHanzi && len > 1) {
        widget.onWordTap(substr);
        return;
      }
    }
    // Single char fallback.
    widget.onWordTap(chars[index]);
  }
}
