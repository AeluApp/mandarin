import 'package:flutter_test/flutter_test.dart';

import 'package:aelu/dashboard/dashboard_provider.dart';

void main() {
  group('MasteryLevel', () {
    test('pct returns 0 when total is 0', () {
      const level = MasteryLevel(total: 0);
      expect(level.pct, 0);
    });

    test('pct calculates correctly', () {
      const level = MasteryLevel(
        durable: 10,
        stable: 20,
        stabilizing: 30,
        passed: 5,
        seen: 10,
        unseen: 25,
        total: 100,
      );
      expect(level.pct, 60.0); // (10+20+30)/100*100
    });

    test('pct is 100 when all items mastered', () {
      const level = MasteryLevel(
        durable: 50,
        stable: 30,
        stabilizing: 20,
        total: 100,
      );
      expect(level.pct, 100.0);
    });

    test('pct handles small totals', () {
      const level = MasteryLevel(
        durable: 1,
        total: 3,
      );
      expect(level.pct, closeTo(33.33, 0.01));
    });

    test('defaults to zero for all fields', () {
      const level = MasteryLevel();
      expect(level.durable, 0);
      expect(level.stable, 0);
      expect(level.stabilizing, 0);
      expect(level.passed, 0);
      expect(level.seen, 0);
      expect(level.unseen, 0);
      expect(level.total, 0);
      expect(level.pct, 0);
    });

    test('pct only counts durable + stable + stabilizing', () {
      // passed, seen, unseen should NOT contribute to pct
      const level = MasteryLevel(
        durable: 0,
        stable: 0,
        stabilizing: 0,
        passed: 50,
        seen: 30,
        unseen: 20,
        total: 100,
      );
      expect(level.pct, 0);
    });
  });

  group('DashboardData', () {
    test('can be constructed with required fields', () {
      const data = DashboardData(
        streakDays: 5,
        itemCount: 100,
        recentAccuracy: 85,
        mastery: {},
        sessionsThisWeek: 3,
        wordsLongTerm: 42,
        momentum: 'rising',
        upcomingItems: [],
        weeklyActivity: [1, 2, 0, 1, 3, 0, 2],
      );
      expect(data.streakDays, 5);
      expect(data.itemCount, 100);
      expect(data.recentAccuracy, 85);
      expect(data.mastery, isEmpty);
      expect(data.sessionsThisWeek, 3);
      expect(data.wordsLongTerm, 42);
      expect(data.momentum, 'rising');
      expect(data.upcomingItems, isEmpty);
      expect(data.weeklyActivity.length, 7);
    });

    test('supports mastery map with HSK levels', () {
      const data = DashboardData(
        streakDays: 0,
        itemCount: 0,
        recentAccuracy: 0,
        mastery: {
          'HSK 1': MasteryLevel(durable: 30, stable: 20, total: 100),
          'HSK 2': MasteryLevel(durable: 10, stable: 5, total: 50),
        },
        sessionsThisWeek: 0,
        wordsLongTerm: 0,
        momentum: 'steady',
        upcomingItems: [],
        weeklyActivity: [0, 0, 0, 0, 0, 0, 0],
      );
      expect(data.mastery.length, 2);
      expect(data.mastery['HSK 1']!.pct, 50.0);
      expect(data.mastery['HSK 2']!.pct, 30.0);
    });

    test('supports upcoming items', () {
      const data = DashboardData(
        streakDays: 1,
        itemCount: 10,
        recentAccuracy: 90,
        mastery: {},
        sessionsThisWeek: 1,
        wordsLongTerm: 5,
        momentum: 'rising',
        upcomingItems: [
          {'hanzi': '你好', 'pinyin': 'nǐ hǎo'},
          {'hanzi': '谢谢', 'pinyin': 'xiè xie'},
        ],
        weeklyActivity: [1, 0, 0, 0, 0, 0, 0],
      );
      expect(data.upcomingItems.length, 2);
      expect(data.upcomingItems[0]['hanzi'], '你好');
    });

    test('weekly activity sums to total sessions', () {
      const activity = [1, 2, 0, 1, 3, 0, 2];
      const data = DashboardData(
        streakDays: 0,
        itemCount: 0,
        recentAccuracy: 0,
        mastery: {},
        sessionsThisWeek: 9,
        wordsLongTerm: 0,
        momentum: 'steady',
        upcomingItems: [],
        weeklyActivity: activity,
      );
      final sum = data.weeklyActivity.fold<int>(0, (a, b) => a + b);
      expect(sum, data.sessionsThisWeek);
    });
  });
}
