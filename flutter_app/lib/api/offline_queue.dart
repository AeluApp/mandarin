import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;
import 'package:connectivity_plus/connectivity_plus.dart';

import 'api_client.dart';
import '../core/error_handler.dart';

/// SQLite-backed offline queue with exponential backoff retry.
///
/// Queues actions when offline, flushes to /api/sync/push on network restore.
/// Retry: exponential backoff (2s, 4s, 8s, 16s, 32s) with jitter.
/// Max 5 retry attempts per flush cycle, then waits for next connectivity event.
class OfflineQueue {
  Database? _db;
  final ApiClient _api;
  final Connectivity _connectivity = Connectivity();
  StreamSubscription? _connectivitySub;
  int _retryAttempt = 0;
  Timer? _retryTimer;

  /// SECURITY: Allowlist of valid offline queue actions.
  static const _validActions = {
    'submit_answer', 'skip', 'hint', 'audio_data',
    'mark_watched', 'mark_complete', 'lookup', 'encounter',
  };

  /// Maximum number of pending items to prevent unbounded queue growth.
  static const _maxQueueSize = 1000;

  OfflineQueue(this._api);

  Future<void> init() async {
    final dbPath =
        p.join(await getDatabasesPath(), 'aelu_offline_queue.db');
    _db = await openDatabase(
      dbPath,
      version: 2,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0
          )
        ''');
        await db.execute(
            'CREATE INDEX idx_queue_action ON queue(action)');
        await db.execute(
            'CREATE INDEX idx_queue_timestamp ON queue(timestamp)');
      },
      onUpgrade: (db, oldVersion, newVersion) async {
        if (oldVersion < 2) {
          // Add indexes for existing databases.
          await db.execute(
              'CREATE INDEX IF NOT EXISTS idx_queue_action ON queue(action)');
          await db.execute(
              'CREATE INDEX IF NOT EXISTS idx_queue_timestamp ON queue(timestamp)');
        }
      },
    );

    // Listen for network changes and auto-flush.
    _connectivitySub = _connectivity.onConnectivityChanged.listen((results) {
      final hasNetwork =
          results.any((r) => r != ConnectivityResult.none);
      if (hasNetwork) {
        _retryAttempt = 0;
        flush();
      }
    });
  }

  /// Enqueue an action for later sync.
  ///
  /// SECURITY: Action names are validated against allowlist (OWASP M7, M4).
  Future<void> enqueue(
      String action, Map<String, dynamic> payload) async {
    // SECURITY: Validate action against strict allowlist.
    if (!_validActions.contains(action)) return;

    // Prevent unbounded queue growth — evict oldest if at capacity.
    final count = await pendingCount();
    if (count >= _maxQueueSize) {
      await _db?.delete('queue',
          where: 'id IN (SELECT id FROM queue ORDER BY id ASC LIMIT 10)');
    }

    await _db?.insert('queue', {
      'action': action,
      'payload_json': jsonEncode(payload),
      'timestamp': DateTime.now().toUtc().toIso8601String(),
      'retry_count': 0,
    });
  }

  /// Flush all queued actions to the server with backoff retry.
  ///
  /// Uses a Completer-based mutex to prevent concurrent flushes.
  Completer<void>? _flushLock;

  Future<void> flush() async {
    if (_db == null) return;

    // Prevent concurrent flushes — wait for existing one to finish.
    if (_flushLock != null && !_flushLock!.isCompleted) return;
    _flushLock = Completer<void>();

    try {
      final rows =
          await _db!.query('queue', orderBy: 'id ASC', limit: 50);
      if (rows.isEmpty) {
        _flushLock!.complete();
        return;
      }

      final actions = <Map<String, dynamic>>[];
      for (final row in rows) {
        try {
          actions.add({
            'action': row['action'],
            'payload': jsonDecode(row['payload_json'] as String? ?? '{}'),
            'timestamp': row['timestamp'],
          });
        } catch (e, st) {
          ErrorHandler.log('Queue entry decode', e, st);
          // Skip corrupted queue entries.
        }
      }

      if (actions.isEmpty) {
        _flushLock!.complete();
        return;
      }

      await _api.post('/api/sync/push', data: {'actions': actions});

      // SECURITY: Delete synced items using parameterized query (OWASP M7).
      final ids = rows.map((r) => r['id'] as int).toList();
      final placeholders = List.filled(ids.length, '?').join(',');
      await _db!
          .delete('queue', where: 'id IN ($placeholders)', whereArgs: ids);

      // Reset retry counter on success.
      _retryAttempt = 0;
      _flushLock!.complete();

      // If more items remain, flush again.
      final remaining = await pendingCount();
      if (remaining > 0) {
        unawaited(flush());
      }
    } catch (e, st) {
      ErrorHandler.log('Queue flush', e, st);
      _flushLock!.complete();
      // Exponential backoff with jitter.
      if (_retryAttempt < 5) {
        _retryAttempt++;
        final baseDelay = Duration(seconds: pow(2, _retryAttempt).toInt());
        final jitter = Duration(
            milliseconds: Random().nextInt(500));
        _retryTimer?.cancel();
        _retryTimer = Timer(baseDelay + jitter, () => flush());
      }
      // After 5 retries, wait for next connectivity event.
    }
  }

  /// Number of pending items.
  Future<int> pendingCount() async {
    final result =
        await _db?.rawQuery('SELECT COUNT(*) as cnt FROM queue');
    return (result?.first['cnt'] as int?) ?? 0;
  }

  Future<void> dispose() async {
    _retryTimer?.cancel();
    await _connectivitySub?.cancel();
    await _db?.close();
  }
}

final offlineQueueProvider = Provider<OfflineQueue>((ref) {
  final api = ref.watch(apiClientProvider);
  final queue = OfflineQueue(api);
  unawaited(queue.init());
  ref.onDispose(() => queue.dispose());
  return queue;
});
