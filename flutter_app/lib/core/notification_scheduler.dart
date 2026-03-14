import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest_all.dart' as tz;
import 'package:timezone/timezone.dart' as tz;

import 'error_handler.dart';

/// Schedules local notifications for streak reminders and return hooks.
///
/// Tracks user's typical practice time and schedules accordingly.
/// Uses SharedPreferences to persist practice time pattern.
class NotificationScheduler {
  static const _keyLastPracticeHour = 'last_practice_hour';
  static const _keyPracticeHourCounts = 'practice_hour_counts';
  static const _keyReminderEnabled = 'reminder_enabled';

  static const _returnReminderId = 1;
  static const _streakReminderId = 2;

  final _plugin = FlutterLocalNotificationsPlugin();
  bool _initialized = false;

  /// Initialize the notification plugin and timezone data.
  Future<void> init() async {
    if (_initialized) return;
    tz.initializeTimeZones();

    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );
    const initSettings = InitializationSettings(
      android: androidSettings,
      iOS: iosSettings,
    );
    await _plugin.initialize(initSettings);
    _initialized = true;
  }

  /// Record that the user practiced at this hour.
  Future<void> recordPracticeTime() async {
    final prefs = await SharedPreferences.getInstance();
    final hour = DateTime.now().hour;
    await prefs.setInt(_keyLastPracticeHour, hour);

    // Track hourly distribution to learn user's pattern.
    final countsJson = prefs.getString(_keyPracticeHourCounts) ?? '';
    final counts = <int>[...List.filled(24, 0)];
    if (countsJson.isNotEmpty) {
      final parts = countsJson.split(',');
      for (var i = 0; i < parts.length && i < 24; i++) {
        counts[i] = int.tryParse(parts[i]) ?? 0;
      }
    }
    counts[hour]++;
    await prefs.setString(_keyPracticeHourCounts, counts.join(','));
  }

  /// Get the user's most common practice hour.
  Future<int> preferredPracticeHour() async {
    final prefs = await SharedPreferences.getInstance();
    final countsJson = prefs.getString(_keyPracticeHourCounts) ?? '';
    if (countsJson.isEmpty) return 9; // default 9am

    final parts = countsJson.split(',');
    var maxCount = 0;
    var maxHour = 9;
    for (var i = 0; i < parts.length && i < 24; i++) {
      final count = int.tryParse(parts[i]) ?? 0;
      if (count > maxCount) {
        maxCount = count;
        maxHour = i;
      }
    }
    return maxHour;
  }

  /// Schedule a "come back tomorrow" notification at the user's preferred hour.
  Future<void> scheduleReturnReminder({
    required String title,
    required String body,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final enabled = prefs.getBool(_keyReminderEnabled) ?? true;
    if (!enabled) return;

    try {
      await init();
      final hour = await preferredPracticeHour();
      final scheduledDate = _nextInstanceOfHour(hour);

      await _plugin.zonedSchedule(
        _returnReminderId,
        title,
        body,
        scheduledDate,
        const NotificationDetails(
          android: AndroidNotificationDetails(
            'aelu_reminders',
            'Practice Reminders',
            channelDescription: 'Reminds you to practice at your preferred time',
            importance: Importance.defaultImportance,
            priority: Priority.defaultPriority,
          ),
          iOS: DarwinNotificationDetails(),
        ),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
        matchDateTimeComponents: DateTimeComponents.time,
      );
    } catch (e, st) {
      ErrorHandler.log('Notification schedule return', e, st);
    }
  }

  /// Schedule streak-at-risk notification for 8pm if user hasn't practiced today.
  Future<void> scheduleStreakReminder(int streakDays) async {
    if (streakDays <= 0) return;
    final prefs = await SharedPreferences.getInstance();
    final enabled = prefs.getBool(_keyReminderEnabled) ?? true;
    if (!enabled) return;

    try {
      await init();
      final scheduledDate = _nextInstanceOfHour(20); // 8pm

      await _plugin.zonedSchedule(
        _streakReminderId,
        '$streakDays-day streak',
        'Items ready for review. About 5 minutes.',
        scheduledDate,
        const NotificationDetails(
          android: AndroidNotificationDetails(
            'aelu_streak',
            'Streak Reminders',
            channelDescription: 'Alerts when your streak is at risk',
            importance: Importance.high,
            priority: Priority.high,
          ),
          iOS: DarwinNotificationDetails(),
        ),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
      );
    } catch (e, st) {
      ErrorHandler.log('Notification schedule streak', e, st);
    }
  }

  /// Cancel all scheduled notifications (e.g. after a session).
  Future<void> cancelAll() async {
    try {
      await init();
      await _plugin.cancelAll();
    } catch (e, st) {
      ErrorHandler.log('Notification cancel all', e, st);
    }
  }

  /// Get the next occurrence of a given hour in the local timezone.
  tz.TZDateTime _nextInstanceOfHour(int hour) {
    final now = tz.TZDateTime.now(tz.local);
    var scheduled = tz.TZDateTime(tz.local, now.year, now.month, now.day, hour);
    if (scheduled.isBefore(now)) {
      scheduled = scheduled.add(const Duration(days: 1));
    }
    return scheduled;
  }
}

final notificationSchedulerProvider = Provider<NotificationScheduler>((ref) {
  return NotificationScheduler();
});
