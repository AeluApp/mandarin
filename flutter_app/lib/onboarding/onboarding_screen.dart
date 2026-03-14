import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/animations/drift_up.dart';
import '../core/animations/pressable_scale.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../theme/aelu_colors.dart';
import '../theme/aelu_spacing.dart';
import '../api/api_client.dart';
import '../core/error_handler.dart';
import '../auth/auth_provider.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import 'widgets/placement_quiz.dart';

class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _pageController = PageController();
  int _currentPage = 0;
  String? _selectedLevel;
  String? _selectedGoal;
  bool _showPlacementQuiz = false;

  final _slides = const [
    _SlideData(
      title: 'Remember More',
      body: 'Aelu spaces your reviews so you retain twice as much — no cramming, no wasted effort.',
      icon: Icons.auto_awesome_outlined,
    ),
    _SlideData(
      title: 'Speak Real Mandarin',
      body: 'Reading, listening, speaking — every session builds toward real conversations, not just flashcard recognition.',
      icon: Icons.menu_book_outlined,
    ),
    _SlideData(
      title: 'Built Around You',
      body: 'Tell us your level and goal. Aelu builds a practice plan that fits your life and grows with you.',
      icon: Icons.route_outlined,
    ),
  ];

  void _next() {
    HapticFeedback.selectionClick();
    ref.read(soundProvider).play(SoundEvent.onboardingStep);
    if (_currentPage < _slides.length) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    }
  }

  void _skipToLevelPicker() {
    HapticFeedback.selectionClick();
    _pageController.animateToPage(
      _slides.length,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
    );
  }

  Future<void> _startPlacement() async {
    if (_selectedLevel == null) return;
    unawaited(ref.read(soundProvider).play(SoundEvent.navigate));

    // Save onboarding preferences.
    try {
      await ref.read(apiClientProvider).post('/api/onboarding', data: {
        'level': _selectedLevel,
        'goal': _selectedGoal ?? 'general',
      });
    } catch (e, st) {
      ErrorHandler.log('Onboarding save preferences', e, st);
      if (mounted) {
        AeluSnackbar.show(
          context,
          'Couldn\'t save your preferences. You can update them in Settings.',
          type: SnackbarType.error,
        );
      }
    }

    // Show placement quiz.
    if (mounted) setState(() => _showPlacementQuiz = true);
  }

  void _finishOnboarding() {
    ref.read(authProvider.notifier).completeOnboarding();
    if (mounted) context.go('/');
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_showPlacementQuiz) {
      return Scaffold(
        appBar: AppBar(title: const Text('Placement')),
        body: PlacementQuiz(onComplete: _finishOnboarding),
      );
    }

    final totalPages = _slides.length + 1; // slides + level picker

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Top row: page indicator + skip button
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
              child: Row(
                children: [
                  const Spacer(),
                  // Page indicator
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: List.generate(totalPages, (i) => AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      width: i == _currentPage ? 10 : 6,
                      height: i == _currentPage ? 10 : 6,
                      margin: const EdgeInsets.symmetric(horizontal: 4),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: i == _currentPage
                            ? AeluColors.accentOf(context)
                            : AeluColors.mutedOf(context).withValues(alpha: 0.3),
                      ),
                    )),
                  ),
                  const Spacer(),
                  // Skip button — visible on slides 0-2 (not on level picker)
                  if (_currentPage < _slides.length)
                    TextButton(
                      onPressed: _skipToLevelPicker,
                      child: Text(
                        'Skip',
                        style: TextStyle(color: AeluColors.mutedOf(context)),
                      ),
                    )
                  else
                    const SizedBox(width: 60), // balance layout
                ],
              ),
            ),

            // Pages
            Expanded(
              child: PageView(
                controller: _pageController,
                onPageChanged: (i) {
                  HapticFeedback.lightImpact();
                  setState(() => _currentPage = i);
                },
                children: [
                  ..._slides.asMap().entries.map((e) => _SlideView(
                    data: e.value,
                    isActive: _currentPage == e.key,
                  )),
                  _LevelPicker(
                    selectedLevel: _selectedLevel,
                    selectedGoal: _selectedGoal,
                    onLevelChanged: (v) => setState(() => _selectedLevel = v),
                    onGoalChanged: (v) => setState(() => _selectedGoal = v),
                  ),
                ],
              ),
            ),

            // Bottom button
            Padding(
              padding: const EdgeInsets.all(24),
              child: SizedBox(
                width: double.infinity,
                child: PressableScale(
                  onTap: _currentPage < _slides.length ? _next : _startPlacement,
                  child: Container(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    decoration: BoxDecoration(
                      color: AeluColors.accent,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      _currentPage < _slides.length ? 'Next' : 'Get started',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: AeluColors.onAccent,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SlideData {
  final String title;
  final String body;
  final IconData icon;
  const _SlideData({required this.title, required this.body, required this.icon});
}

class _SlideView extends StatelessWidget {
  final _SlideData data;
  final bool isActive;
  const _SlideView({required this.data, this.isActive = false});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          DriftUp(
            key: ValueKey('${data.title}_$isActive'),
            child: Icon(data.icon, size: 64, color: AeluColors.accentOf(context)),
          ),
          const SizedBox(height: 32),
          DriftUp(
            delay: const Duration(milliseconds: 100),
            key: ValueKey('${data.title}_title_$isActive'),
            child: Text(data.title, style: theme.textTheme.displayMedium, textAlign: TextAlign.center),
          ),
          const SizedBox(height: 16),
          DriftUp(
            delay: const Duration(milliseconds: 200),
            key: ValueKey('${data.title}_body_$isActive'),
            child: Text(data.body, style: theme.textTheme.bodyLarge, textAlign: TextAlign.center),
          ),
        ],
      ),
    );
  }
}

class _LevelPicker extends StatelessWidget {
  final String? selectedLevel;
  final String? selectedGoal;
  final ValueChanged<String> onLevelChanged;
  final ValueChanged<String> onGoalChanged;

  const _LevelPicker({
    required this.selectedLevel,
    required this.selectedGoal,
    required this.onLevelChanged,
    required this.onGoalChanged,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    const levels = ['Beginner (HSK 1)', 'Elementary (HSK 2-3)', 'Intermediate (HSK 4-5)', 'Advanced (HSK 6+)'];
    const levelValues = ['hsk1', 'hsk2-3', 'hsk4-5', 'hsk6+'];
    const goals = ['General fluency', 'Travel & conversation', 'Business Mandarin', 'Academic study'];
    const goalValues = ['general', 'travel', 'business', 'academic'];

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 24),
          Text('Your level', style: theme.textTheme.headlineMedium),
          const SizedBox(height: 12),
          ...List.generate(levels.length, (i) => RadioListTile<String>(
            title: Text(levels[i]),
            value: levelValues[i],
            // ignore: deprecated_member_use
            groupValue: selectedLevel,
            // ignore: deprecated_member_use
            onChanged: (v) {
              HapticFeedback.selectionClick();
              onLevelChanged(v!);
            },
            activeColor: AeluColors.accentOf(context),
          )),
          const SizedBox(height: 24),
          Text('Your goal', style: theme.textTheme.headlineMedium),
          const SizedBox(height: 12),
          ...List.generate(goals.length, (i) => RadioListTile<String>(
            title: Text(goals[i]),
            value: goalValues[i],
            // ignore: deprecated_member_use
            groupValue: selectedGoal,
            // ignore: deprecated_member_use
            onChanged: (v) {
              HapticFeedback.selectionClick();
              onGoalChanged(v!);
            },
            activeColor: AeluColors.accentOf(context),
          )),
        ],
      ),
    );
  }
}
