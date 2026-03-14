import 'package:flutter_test/flutter_test.dart';

import 'package:aelu/core/sound/sound_events.dart';

void main() {
  group('SoundEvent', () {
    test('all events have non-empty asset names', () {
      for (final event in SoundEvent.values) {
        expect(event.assetName, isNotEmpty,
            reason: '${event.name} should have a non-empty assetName');
      }
    });

    test('all events have a haptic type', () {
      for (final event in SoundEvent.values) {
        expect(HapticType.values, contains(event.haptic),
            reason: '${event.name} should have a valid haptic type');
      }
    });

    test('no duplicate asset names', () {
      final names = SoundEvent.values.map((e) => e.assetName).toList();
      expect(names.toSet().length, names.length,
          reason: 'All SoundEvent asset names should be unique');
    });

    test('correct has light haptic', () {
      expect(SoundEvent.correct.haptic, HapticType.light);
    });

    test('wrong has medium haptic', () {
      expect(SoundEvent.wrong.haptic, HapticType.medium);
    });

    test('sessionComplete has heavy haptic', () {
      expect(SoundEvent.sessionComplete.haptic, HapticType.heavy);
    });

    test('timerTick has no haptic', () {
      expect(SoundEvent.timerTick.haptic, HapticType.none);
    });

    test('navigate has selection haptic', () {
      expect(SoundEvent.navigate.haptic, HapticType.selection);
    });

    test('sessionStart has heavy haptic', () {
      expect(SoundEvent.sessionStart.haptic, HapticType.heavy);
    });

    test('milestone has medium haptic', () {
      expect(SoundEvent.milestone.haptic, HapticType.medium);
    });

    test('asset names follow naming convention', () {
      final validPattern = RegExp(r'^[a-z][a-z0-9_]*$');
      for (final event in SoundEvent.values) {
        expect(validPattern.hasMatch(event.assetName), true,
            reason: '${event.name} assetName "${event.assetName}" should be lowercase_underscore');
      }
    });
  });

  group('HapticType', () {
    test('has all expected values', () {
      expect(HapticType.values.length, 5);
      expect(HapticType.values, contains(HapticType.none));
      expect(HapticType.values, contains(HapticType.selection));
      expect(HapticType.values, contains(HapticType.light));
      expect(HapticType.values, contains(HapticType.medium));
      expect(HapticType.values, contains(HapticType.heavy));
    });

    test('intensity ordering is logical', () {
      // Verify the enum values are ordered by intensity.
      expect(HapticType.none.index, lessThan(HapticType.selection.index));
      expect(HapticType.selection.index, lessThan(HapticType.light.index));
      expect(HapticType.light.index, lessThan(HapticType.medium.index));
      expect(HapticType.medium.index, lessThan(HapticType.heavy.index));
    });
  });
}
