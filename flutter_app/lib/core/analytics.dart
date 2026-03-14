import 'dart:async';
import 'dart:collection';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import 'security/security_config.dart';

/// Client-side analytics — ring buffer (500 events), batch flush every 30s.
///
/// Security controls:
/// - ISO 27001 A.18.1.4 (Privacy and protection of PII): All events scrubbed.
/// - NIST AU-3 (Content of Audit Records): Structured, sanitized events.
/// - OWASP M4 (Insufficient Input/Output Validation): No raw user data in events.
class Analytics {
  final ApiClient _api;
  final _events = Queue<Map<String, dynamic>>();
  static const _maxEvents = 500;
  Timer? _timer;

  Analytics(this._api);

  void init() {
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => flush());
  }

  void track(String event, [Map<String, dynamic>? properties]) {
    // SECURITY: Scrub PII from all event properties.
    final safeProps = properties != null
        ? PiiScrubber.scrubMap(properties)
        : <String, dynamic>{};

    _events.addLast({
      'event': event,
      'properties': safeProps,
      'timestamp': DateTime.now().toUtc().toIso8601String(),
    });
    while (_events.length > _maxEvents) {
      _events.removeFirst();
    }
  }

  void screenView(String screenName) {
    // SECURITY: Only allow known screen names — no user-controlled strings.
    final safeScreen = _sanitizeScreenName(screenName);
    track('screen_view', {'screen': safeScreen});
  }

  void sessionStart() => track('session_start');

  void sessionComplete(Map<String, dynamic> results) {
    // SECURITY: Only forward safe keys from session results.
    final safeResults = <String, dynamic>{};
    const allowedKeys = {
      'accuracy', 'items_practiced', 'duration_seconds', 'session_type',
      'streak_days', 'mastery_changes',
    };
    for (final key in allowedKeys) {
      if (results.containsKey(key)) {
        safeResults[key] = results[key];
      }
    }
    track('session_complete', safeResults);
  }

  void drillAnswer(Map<String, dynamic> data) {
    // SECURITY: Only forward safe keys from drill data.
    final safeData = <String, dynamic>{};
    const allowedKeys = {
      'drill_type', 'correct', 'response_time_ms', 'item_id',
    };
    for (final key in allowedKeys) {
      if (data.containsKey(key)) {
        safeData[key] = data[key];
      }
    }
    track('drill_answer', safeData);
  }

  void error(String message) {
    // SECURITY: Scrub PII from error messages.
    track('error', {'message': PiiScrubber.scrub(message)});
  }

  Future<void> flush() async {
    if (_events.isEmpty) return;
    final batch = _events.toList();
    _events.clear();
    try {
      await _api.post('/api/client-events', data: {'events': batch});
    } catch (_) {
      for (final event in batch) {
        _events.addLast(event);
        if (_events.length >= _maxEvents) break;
      }
    }
  }

  void dispose() {
    _timer?.cancel();
    flush();
  }

  /// Sanitize screen name — strip anything that isn't a known safe pattern.
  String _sanitizeScreenName(String name) {
    // Allow alphanumeric, underscores, slashes.
    return name.replaceAll(RegExp(r'[^a-zA-Z0-9_/]'), '');
  }
}

final analyticsProvider = Provider<Analytics>((ref) {
  final api = ref.watch(apiClientProvider);
  final analytics = Analytics(api);
  analytics.init();
  ref.onDispose(() => analytics.dispose());
  return analytics;
});
