import 'package:flutter_test/flutter_test.dart';

import 'package:aelu/api/ws_client.dart';
import 'package:aelu/session/session_provider.dart';

void main() {
  group('SessionState defaults', () {
    test('defaults are correct', () {
      const state = SessionState();
      expect(state.connectionState, WsConnectionState.connecting);
      expect(state.currentPrompt, isNull);
      expect(state.inputMode, DrillInputMode.text);
      expect(state.itemsCompleted, 0);
      expect(state.totalItems, 0);
      expect(state.feedback, isNull);
      expect(state.feedbackCorrect, false);
      expect(state.showingFeedback, false);
      expect(state.hint, isNull);
      expect(state.resumeToken, isNull);
      expect(state.sessionStartMs, 0);
      expect(state.usingCache, false);
    });
  });

  group('SessionState.copyWith', () {
    test('preserves unmodified fields', () {
      const state = SessionState(
        itemsCompleted: 5,
        totalItems: 10,
        sessionStartMs: 1000,
      );
      final updated = state.copyWith(showingFeedback: true);
      expect(updated.itemsCompleted, 5);
      expect(updated.totalItems, 10);
      expect(updated.sessionStartMs, 1000);
      expect(updated.showingFeedback, true);
    });

    test('hint can be set to null', () {
      const state = SessionState(hint: 'some hint');
      // copyWith(hint: null) should clear the hint since hint uses
      // direct assignment (not ?? pattern)
      final updated = state.copyWith(hint: null);
      expect(updated.hint, isNull);
    });

    test('updates multiple fields at once', () {
      const state = SessionState();
      final updated = state.copyWith(
        connectionState: WsConnectionState.connected,
        itemsCompleted: 3,
        totalItems: 10,
        feedback: 'Correct!',
        feedbackCorrect: true,
        showingFeedback: true,
      );
      expect(updated.connectionState, WsConnectionState.connected);
      expect(updated.itemsCompleted, 3);
      expect(updated.totalItems, 10);
      expect(updated.feedback, 'Correct!');
      expect(updated.feedbackCorrect, true);
      expect(updated.showingFeedback, true);
    });
  });

  group('SessionState.withNewPrompt', () {
    test('clears feedback and hint', () {
      const state = SessionState(
        feedback: 'old feedback',
        feedbackCorrect: true,
        showingFeedback: true,
        hint: 'old hint',
        itemsCompleted: 3,
        totalItems: 10,
        resumeToken: 'tok123',
      );

      final prompt = {'drill_type': 'hanzi_to_english', 'hanzi': '你好'};
      final updated = state.withNewPrompt(prompt, DrillInputMode.text);

      expect(updated.currentPrompt, prompt);
      expect(updated.inputMode, DrillInputMode.text);
      expect(updated.feedback, isNull);
      expect(updated.feedbackCorrect, false);
      expect(updated.showingFeedback, false);
      expect(updated.hint, isNull);
      // Preserved fields:
      expect(updated.itemsCompleted, 3);
      expect(updated.totalItems, 10);
      expect(updated.resumeToken, 'tok123');
      // Always sets usingCache to false:
      expect(updated.usingCache, false);
    });
  });

  group('SessionState getters', () {
    test('drillType extracts from currentPrompt', () {
      const state = SessionState(
        currentPrompt: {'drill_type': 'hanzi_to_english'},
      );
      expect(state.drillType, 'hanzi_to_english');
    });

    test('drillType returns empty when no prompt', () {
      const state = SessionState();
      expect(state.drillType, '');
    });

    test('drillType returns empty when drill_type is null', () {
      const state = SessionState(currentPrompt: {'other': 'data'});
      expect(state.drillType, '');
    });

    test('hanzi extracts from currentPrompt', () {
      const state = SessionState(
        currentPrompt: {'hanzi': '你好'},
      );
      expect(state.hanzi, '你好');
    });

    test('pinyin extracts from currentPrompt', () {
      const state = SessionState(
        currentPrompt: {'pinyin': 'nǐ hǎo'},
      );
      expect(state.pinyin, 'nǐ hǎo');
    });

    test('english extracts from currentPrompt', () {
      const state = SessionState(
        currentPrompt: {'english': 'hello'},
      );
      expect(state.english, 'hello');
    });

    test('promptText extracts from currentPrompt', () {
      const state = SessionState(
        currentPrompt: {'prompt_text': 'What does this mean?'},
      );
      expect(state.promptText, 'What does this mean?');
    });

    test('options returns empty list when null prompt', () {
      const state = SessionState();
      expect(state.options, isEmpty);
    });

    test('options returns empty list when no options key', () {
      const state = SessionState(currentPrompt: {'drill_type': 'text'});
      expect(state.options, isEmpty);
    });

    test('options returns list from prompt', () {
      const state = SessionState(
        currentPrompt: {
          'options': ['a', 'b', 'c'],
        },
      );
      expect(state.options.length, 3);
      expect(state.options, ['a', 'b', 'c']);
    });
  });

  group('DrillInputMode', () {
    test('has all expected values', () {
      expect(DrillInputMode.values.length, 6);
      expect(DrillInputMode.values, contains(DrillInputMode.text));
      expect(DrillInputMode.values, contains(DrillInputMode.multipleChoice));
      expect(DrillInputMode.values, contains(DrillInputMode.audio));
      expect(DrillInputMode.values, contains(DrillInputMode.recording));
      expect(DrillInputMode.values, contains(DrillInputMode.action));
      expect(DrillInputMode.values, contains(DrillInputMode.toneMarking));
    });
  });

  group('WsConnectionState', () {
    test('has all expected values', () {
      expect(WsConnectionState.values.length, 5);
      expect(WsConnectionState.values, contains(WsConnectionState.connecting));
      expect(WsConnectionState.values, contains(WsConnectionState.connected));
      expect(WsConnectionState.values, contains(WsConnectionState.disconnected));
      expect(WsConnectionState.values, contains(WsConnectionState.reconnecting));
      expect(WsConnectionState.values, contains(WsConnectionState.failed));
    });
  });
}
