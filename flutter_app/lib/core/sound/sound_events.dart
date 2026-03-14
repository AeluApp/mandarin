/// All sound events in the app, mapped to asset filenames and haptic types.
enum SoundEvent {
  sessionStart('session_start', HapticType.heavy),
  sessionComplete('session_complete', HapticType.heavy),
  correct('correct', HapticType.light),
  wrong('wrong', HapticType.medium),
  navigate('navigate', HapticType.selection),
  hintReveal('hint_reveal', HapticType.selection),
  milestone('milestone', HapticType.heavy),
  levelUp('level_up', HapticType.heavy),
  streakMilestone('streak_milestone', HapticType.heavy),
  achievementUnlock('achievement_unlock', HapticType.heavy),
  timerTick('timer_tick', HapticType.none),
  transitionIn('transition_in', HapticType.selection),
  transitionOut('transition_out', HapticType.selection),
  recordPulse('record_pulse', HapticType.light),
  readingLookup('reading_lookup', HapticType.light),
  onboardingStep('onboarding_step', HapticType.selection);

  final String assetName;
  final HapticType haptic;

  const SoundEvent(this.assetName, this.haptic);
}

enum HapticType {
  none,
  selection,
  light,
  medium,
  heavy,
}
