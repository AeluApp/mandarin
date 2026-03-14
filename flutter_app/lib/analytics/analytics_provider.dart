import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/error_handler.dart';

// ── Data models ──

class RetentionData {
  final Map<String, int> stageCounts;
  final List<ForecastDay> forecast;
  final int totalActive;
  final int overdue;

  const RetentionData({
    required this.stageCounts,
    required this.forecast,
    required this.totalActive,
    required this.overdue,
  });
}

class ForecastDay {
  final int dayOffset;
  final int itemsDue;

  const ForecastDay({required this.dayOffset, required this.itemsDue});
}

class ReadingStats {
  final int totalPassages;
  final int weekPassages;
  final double comprehensionPct;
  final double avgReadingTimeSeconds;
  final int totalWordsLookedUp;

  const ReadingStats({
    required this.totalPassages,
    required this.weekPassages,
    required this.comprehensionPct,
    required this.avgReadingTimeSeconds,
    required this.totalWordsLookedUp,
  });
}

class GrammarMastery {
  final Map<String, GrammarLevel> byLevel;
  final int overallStudied;
  final int overallTotal;

  const GrammarMastery({
    required this.byLevel,
    required this.overallStudied,
    required this.overallTotal,
  });

  double get overallPct =>
      overallTotal > 0 ? overallStudied / overallTotal * 100 : 0;
}

class GrammarLevel {
  final int studied;
  final int total;

  const GrammarLevel({required this.studied, required this.total});

  double get pct => total > 0 ? studied / total * 100 : 0;
}

class AnalyticsState {
  final RetentionData retention;
  final ReadingStats reading;
  final GrammarMastery grammar;

  const AnalyticsState({
    required this.retention,
    required this.reading,
    required this.grammar,
  });
}

// ── Provider ──

final analyticsProvider =
    FutureProvider.autoDispose<AnalyticsState>((ref) async {
  final api = ref.watch(apiClientProvider);

  // Fetch all three endpoints concurrently.
  final results = await Future.wait([
    api.get('/api/dashboard/retention_curve').catchError((e, st) {
      ErrorHandler.log('Analytics retention_curve', e, st);
      return _emptyResponse;
    }),
    api.get('/api/reading/stats').catchError((e, st) {
      ErrorHandler.log('Analytics reading/stats', e, st);
      return _emptyResponse;
    }),
    api.get('/api/grammar/mastery').catchError((e, st) {
      ErrorHandler.log('Analytics grammar/mastery', e, st);
      return _emptyResponse;
    }),
  ]);

  final retentionRaw = _safeData(results[0].data);
  final readingRaw = _safeData(results[1].data);
  final grammarRaw = _safeData(results[2].data);

  // ── Parse retention ──
  final rawStages = retentionRaw.nested('stage_counts');
  final stageCounts = <String, int>{};
  for (final entry in rawStages.entries) {
    stageCounts[entry.key] =
        entry.value is num ? (entry.value as num).toInt() : 0;
  }

  final rawForecast = retentionRaw.list('forecast');
  final forecast = rawForecast
      .whereType<Map<String, dynamic>>()
      .map((f) => ForecastDay(
            dayOffset: f.integer('day_offset'),
            itemsDue: f.integer('items_due'),
          ))
      .toList();

  final retention = RetentionData(
    stageCounts: stageCounts,
    forecast: forecast,
    totalActive: retentionRaw.integer('total_active'),
    overdue: retentionRaw.integer('overdue'),
  );

  // ── Parse reading stats ──
  final reading = ReadingStats(
    totalPassages: readingRaw.integer('total_passages'),
    weekPassages: readingRaw.integer('week_passages'),
    comprehensionPct: _safeDouble(readingRaw['comprehension_pct']),
    avgReadingTimeSeconds:
        _safeDouble(readingRaw['avg_reading_time_seconds']),
    totalWordsLookedUp: readingRaw.integer('total_words_looked_up'),
  );

  // ── Parse grammar mastery ──
  final rawByLevel = grammarRaw.nested('levels');
  final byLevel = <String, GrammarLevel>{};
  for (final entry in rawByLevel.entries) {
    if (entry.value is Map<String, dynamic>) {
      final m = entry.value as Map<String, dynamic>;
      byLevel[entry.key] = GrammarLevel(
        studied: m.integer('studied'),
        total: m.integer('total'),
      );
    }
  }

  final rawOverall = grammarRaw.nested('overall');
  final grammar = GrammarMastery(
    byLevel: byLevel,
    overallStudied: rawOverall.integer('studied'),
    overallTotal: rawOverall.integer('total'),
  );

  return AnalyticsState(
    retention: retention,
    reading: reading,
    grammar: grammar,
  );
});

// ── Helpers ──

/// Sentinel response for catchError — Dio Response requires requestOptions,
/// so we just return a map-safe fallback via _safeData.
final _emptyResponse = _FakeResponse();

Map<String, dynamic> _safeData(dynamic data) {
  return data is Map<String, dynamic> ? data : <String, dynamic>{};
}

double _safeDouble(dynamic v) {
  if (v is double) return v;
  if (v is int) return v.toDouble();
  if (v is num) return v.toDouble();
  return 0.0;
}

/// Minimal fake that quacks enough like a Dio Response for catchError.
class _FakeResponse {
  final dynamic data = <String, dynamic>{};
  int get statusCode => 0;
}
