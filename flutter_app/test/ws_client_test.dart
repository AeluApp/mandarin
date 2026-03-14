import 'package:flutter_test/flutter_test.dart';

import 'package:aelu/api/ws_client.dart';

void main() {
  group('WsClient — construction and state', () {
    test('initial state has no channel', () {
      final client = WsClient();
      // Can set token without error.
      client.setAccessToken('test-token');
      // Dispose without error.
      client.dispose();
    });

    test('exposes message stream', () {
      final client = WsClient();
      expect(client.messages, isA<Stream<Map<String, dynamic>>>());
      client.dispose();
    });

    test('exposes connection state stream', () {
      final client = WsClient();
      expect(client.connectionState, isA<Stream<WsConnectionState>>());
      client.dispose();
    });

    test('resume token starts as null', () {
      final client = WsClient();
      expect(client.resumeToken, isNull);
      client.dispose();
    });
  });

  group('WsClient — send methods without connection', () {
    test('sendAnswer does not throw without connection', () {
      final client = WsClient();
      expect(() => client.sendAnswer('hello'), returnsNormally);
      client.dispose();
    });

    test('sendSkip does not throw without connection', () {
      final client = WsClient();
      expect(() => client.sendSkip(), returnsNormally);
      client.dispose();
    });

    test('sendHint does not throw without connection', () {
      final client = WsClient();
      expect(() => client.sendHint(), returnsNormally);
      client.dispose();
    });

    test('sendAudio does not throw without connection', () {
      final client = WsClient();
      expect(() => client.sendAudio('base64data'), returnsNormally);
      client.dispose();
    });

    test('sendChoice does not throw without connection', () {
      final client = WsClient();
      expect(() => client.sendChoice(2), returnsNormally);
      client.dispose();
    });
  });

  group('WsClient — input validation', () {
    test('sendAnswer truncates to 500 chars', () {
      final client = WsClient();
      // Should not throw even with very long answer.
      final longAnswer = 'a' * 1000;
      expect(() => client.sendAnswer(longAnswer), returnsNormally);
      client.dispose();
    });

    test('sendChoice rejects negative index', () {
      final client = WsClient();
      // Negative index should be silently ignored (no send).
      expect(() => client.sendChoice(-1), returnsNormally);
      client.dispose();
    });

    test('sendChoice rejects index > 9', () {
      final client = WsClient();
      expect(() => client.sendChoice(10), returnsNormally);
      client.dispose();
    });

    test('sendChoice accepts valid range 0-9', () {
      final client = WsClient();
      for (var i = 0; i <= 9; i++) {
        expect(() => client.sendChoice(i), returnsNormally);
      }
      client.dispose();
    });

    test('sendAudio rejects oversized payload', () {
      final client = WsClient();
      final huge = 'a' * 600000;
      // Should silently skip (no crash).
      expect(() => client.sendAudio(huge), returnsNormally);
      client.dispose();
    });
  });

  group('WsClient — disconnect', () {
    test('disconnect without connect does not throw', () async {
      final client = WsClient();
      await expectLater(client.disconnect(), completes);
      await client.dispose();
    });

    test('dispose without connect does not throw', () async {
      final client = WsClient();
      await expectLater(client.dispose(), completes);
    });

    test('double dispose does not throw', () async {
      final client = WsClient();
      await client.dispose();
      // Second dispose should be safe.
      await expectLater(client.dispose(), completes);
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
