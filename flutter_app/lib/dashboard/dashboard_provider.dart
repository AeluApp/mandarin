import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/error_handler.dart';
import '../core/notification_scheduler.dart';
import '../session/drill_cache.dart';

class DashboardData {
  final int streakDays;
  final int itemCount;
  final int recentAccuracy;
  final Map<String, MasteryLevel> mastery;
  final int sessionsThisWeek;
  final int wordsLongTerm;
  final String momentum;
  final List<Map<String, dynamic>> upcomingItems;
  final List<int> weeklyActivity; // 7 days of session counts

  const DashboardData({
    required this.streakDays,
    required this.itemCount,
    required this.recentAccuracy,
    required this.mastery,
    required this.sessionsThisWeek,
    required this.wordsLongTerm,
    required this.momentum,
    required this.upcomingItems,
    required this.weeklyActivity,
  });
}

class MasteryLevel {
  final int durable;
  final int stable;
  final int stabilizing;
  final int passed;
  final int seen;
  final int unseen;
  final int total;

  const MasteryLevel({
    this.durable = 0,
    this.stable = 0,
    this.stabilizing = 0,
    this.passed = 0,
    this.seen = 0,
    this.unseen = 0,
    this.total = 0,
  });

  double get pct =>
      total > 0 ? (durable + stable + stabilizing) / total * 100 : 0;
}

final dashboardProvider = FutureProvider.autoDispose<DashboardData>((ref) async {
  final api = ref.watch(apiClientProvider);

  final statusResponse = await api.get('/api/status');
  final status = statusResponse.data;

  // Validate response structure.
  if (status is! Map<String, dynamic> || status.isEmpty) {
    throw Exception('Invalid status response');
  }

  // Parse full mastery breakdown.
  final rawMastery = status.nested('mastery');
  final mastery = <String, MasteryLevel>{};
  for (final entry in rawMastery.entries) {
    if (entry.value is Map<String, dynamic>) {
      final m = entry.value as Map<String, dynamic>;
      mastery['HSK ${entry.key}'] = MasteryLevel(
        durable: m.integer('durable'),
        stable: m.integer('stable'),
        stabilizing: m.integer('stabilizing'),
        passed: m.integer('passed'),
        seen: m.integer('seen'),
        unseen: m.integer('unseen'),
        total: m.integer('total', 1),
      );
    }
  }

  final upcoming = status.list('upcoming_items')
      .whereType<Map<String, dynamic>>()
      .toList();

  final weekly = status.list('weekly_activity')
      .map((e) => e is num ? e.toInt() : 0)
      .toList();
  if (weekly.length < 7) {
    weekly.addAll(List.filled(7 - weekly.length, 0));
  }

  final streakDays = status.integer('streak_days');
  final momentum = status.str('momentum');

  // Pre-fetch drill items for offline support (fire-and-forget).
  try {
    unawaited(ref.read(drillCacheProvider).prefetch('full'));
  } catch (e, st) {
    ErrorHandler.log('Dashboard drill prefetch', e, st);
  }

  // Schedule streak reminder if streak is active.
  try {
    unawaited(ref.read(notificationSchedulerProvider).scheduleStreakReminder(streakDays));
  } catch (e, st) {
    ErrorHandler.log('Dashboard schedule streak reminder', e, st);
  }

  return DashboardData(
    streakDays: streakDays,
    itemCount: status.integer('item_count'),
    recentAccuracy: status.integer('accuracy_this_week'),
    mastery: mastery,
    sessionsThisWeek: status.integer('sessions_this_week'),
    wordsLongTerm: status.integer('words_long_term'),
    momentum: momentum,
    upcomingItems: upcoming,
    weeklyActivity: weekly,
  );
});
