import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../api/api_client.dart';
import '../../core/error_handler.dart';
import '../../theme/aelu_colors.dart';

/// NPS (Net Promoter Score) dialog — 0-10 scale with follow-up.
class NpsDialog extends StatefulWidget {
  final ApiClient api;

  const NpsDialog({super.key, required this.api});

  static Future<void> show(BuildContext context, ApiClient api) {
    return showDialog(
      context: context,
      builder: (_) => NpsDialog(api: api),
    );
  }

  @override
  State<NpsDialog> createState() => _NpsDialogState();
}

class _NpsDialogState extends State<NpsDialog> {
  int? _score;
  final _feedbackController = TextEditingController();
  bool _submitted = false;

  Future<void> _submit() async {
    if (_score == null) return;
    try {
      await widget.api.post('/api/feedback/nps', data: {
        'score': _score,
        'feedback': _feedbackController.text.trim(),
      });
    } catch (e, st) {
      ErrorHandler.log('NPS submit', e, st);
    }
    setState(() => _submitted = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) Navigator.pop(context);
    });
  }

  @override
  void dispose() {
    _feedbackController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_submitted) {
      return AlertDialog(
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle_outline, color: AeluColors.correctOf(context), size: 48),
            const SizedBox(height: 12),
            Text('Thank you!', style: theme.textTheme.titleMedium),
          ],
        ),
      );
    }

    return AlertDialog(
      title: const Text('How likely are you to recommend Aelu?'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Score row (0-10)
          Wrap(
            spacing: 2,
            runSpacing: 4,
            alignment: WrapAlignment.center,
            children: List.generate(11, (i) {
              final selected = _score == i;
              return SizedBox(
                width: 44,
                height: 44,
                child: OutlinedButton(
                  onPressed: () {
                    unawaited(HapticFeedback.selectionClick());
                    setState(() => _score = i);
                  },
                  style: OutlinedButton.styleFrom(
                    padding: EdgeInsets.zero,
                    minimumSize: const Size(44, 44),
                    backgroundColor: selected ? AeluColors.accentOf(context).withValues(alpha: 0.15) : null,
                    side: BorderSide(
                      color: selected ? AeluColors.accentOf(context) : AeluColors.divider,
                    ),
                  ),
                  child: Text('$i', style: theme.textTheme.bodySmall),
                ),
              );
            }),
          ),
          if (_score != null) ...[
            const SizedBox(height: 16),
            TextField(
              controller: _feedbackController,
              decoration: InputDecoration(
                hintText: _score! >= 9
                    ? 'What do you love most?'
                    : _score! >= 7
                        ? 'What could be better?'
                        : 'What should we improve?',
              ),
              maxLines: 3,
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Later'),
        ),
        if (_score != null)
          ElevatedButton(
            onPressed: _submit,
            child: const Text('Submit'),
          ),
      ],
    );
  }
}
