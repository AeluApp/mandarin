import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/api_response.dart';
import '../../core/error_handler.dart';
import '../../shared/widgets/aelu_snackbar.dart';
import '../../theme/aelu_colors.dart';
import '../../theme/hanzi_style.dart';

/// Placement quiz fetched from /api/onboarding/placement/start.
class PlacementQuiz extends ConsumerStatefulWidget {
  final VoidCallback onComplete;

  const PlacementQuiz({super.key, required this.onComplete});

  @override
  ConsumerState<PlacementQuiz> createState() => _PlacementQuizState();
}

class _PlacementQuizState extends ConsumerState<PlacementQuiz> {
  List<Map<String, dynamic>> _questions = [];
  int _currentIndex = 0;
  final List<Map<String, dynamic>> _answers = [];
  bool _loading = true;
  bool _loadError = false;

  @override
  void initState() {
    super.initState();
    _loadQuiz();
  }

  Future<void> _loadQuiz() async {
    setState(() {
      _loading = true;
      _loadError = false;
    });
    try {
      final response = await ref.read(apiClientProvider).get('/api/onboarding/placement/start');
      final data = SafeMap.from(response.data);
      if (data == null) return;
      setState(() {
        _questions = data.list('questions')
                .whereType<Map<String, dynamic>>()
                .toList();
        _loading = false;
      });
    } catch (e, st) {
      ErrorHandler.log('Placement quiz load', e, st);
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadError = true;
      });
    }
  }

  Future<void> _submitAnswer(String answer) async {
    final question = _questions[_currentIndex];
    _answers.add({
      'question_id': question['id'],
      'answer': answer,
    });

    if (_currentIndex < _questions.length - 1) {
      setState(() => _currentIndex++);
    } else {
      // Submit all answers.
      try {
        await ref.read(apiClientProvider).post(
          '/api/onboarding/placement/submit',
          data: {'answers': _answers},
        );
      } catch (e, st) {
        ErrorHandler.log('Placement quiz submit', e, st);
        if (mounted) {
          AeluSnackbar.show(
            context,
            'Couldn\'t submit your answers. We\'ll start you at a default level.',
            type: SnackbarType.error,
          );
        }
      }
      widget.onComplete();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_loadError) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline, size: 56, color: AeluColors.mutedOf(context)),
              const SizedBox(height: 16),
              Text('Couldn\'t load the placement quiz', style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(
                'Check your connection and try again, or skip to start at a default level.',
                style: theme.textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              OutlinedButton(onPressed: _loadQuiz, child: const Text('Retry')),
              const SizedBox(height: 8),
              TextButton(onPressed: widget.onComplete, child: const Text('Skip')),
            ],
          ),
        ),
      );
    }

    if (_questions.isEmpty) {
      return const SizedBox.shrink();
    }

    final question = _questions[_currentIndex];
    final hanzi = question['hanzi'] is String ? question['hanzi'] as String : '';
    final prompt = question['prompt'] is String ? question['prompt'] as String : '';
    final options = question['options'] is List ? question['options'] as List<dynamic> : <dynamic>[];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Progress
          Text(
            '${_currentIndex + 1} / ${_questions.length}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 24),

          if (hanzi.isNotEmpty)
            Text(hanzi, style: HanziStyle.display),
          const SizedBox(height: 16),

          if (prompt.isNotEmpty)
            Text(prompt, style: theme.textTheme.bodyLarge, textAlign: TextAlign.center),
          const SizedBox(height: 24),

          // Options
          ...options.map((opt) {
            final text = opt is Map ? (opt['text'] ?? '') : opt.toString();
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () => _submitAnswer(text.toString()),
                  child: Text(text.toString()),
                ),
              ),
            );
          }),

          const SizedBox(height: 16),
          TextButton(
            onPressed: () => _submitAnswer('skip'),
            child: const Text('Not sure'),
          ),
        ],
      ),
    );
  }
}
