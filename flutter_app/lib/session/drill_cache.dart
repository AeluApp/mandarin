import 'dart:convert';

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../core/error_handler.dart';

/// Local cache of upcoming drill items for offline session support.
///
/// On each dashboard load, pre-fetches the next session's items and stores
/// them in SQLite. If the WS connection fails at session start, the app
/// can run a degraded local-only session from this cache.
class DrillCache {
  Database? _db;
  final ApiClient _api;

  DrillCache(this._api);

  Future<void> init() async {
    final dbPath = p.join(await getDatabasesPath(), 'aelu_drill_cache.db');
    _db = await openDatabase(
      dbPath,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE cached_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_json TEXT NOT NULL,
            session_type TEXT NOT NULL,
            fetched_at TEXT NOT NULL
          )
        ''');
      },
    );
  }

  /// Pre-fetch items for the next session. Call on dashboard load.
  Future<void> prefetch(String sessionType) async {
    try {
      final response = await _api.get('/api/session/preview', queryParameters: {
        'type': sessionType,
      });
      final data = response.data;
      if (data is! Map<String, dynamic>) return;
      final rawItems = data['items'];
      final items = rawItems is List ? rawItems : <dynamic>[];

      if (items.isEmpty || _db == null) return;

      // Replace cache for this session type.
      await _db!.delete('cached_items', where: 'session_type = ?', whereArgs: [sessionType]);
      final now = DateTime.now().toUtc().toIso8601String();
      for (final item in items) {
        await _db!.insert('cached_items', {
          'item_json': jsonEncode(item),
          'session_type': sessionType,
          'fetched_at': now,
        });
      }
    } catch (e, st) {
      ErrorHandler.log('DrillCache prefetch', e, st);
      // Prefetch is best-effort. Stale cache is better than no cache.
    }
  }

  /// Get cached items for offline session fallback.
  Future<List<Map<String, dynamic>>> getCached(String sessionType) async {
    if (_db == null) return [];
    final rows = await _db!.query(
      'cached_items',
      where: 'session_type = ?',
      whereArgs: [sessionType],
      orderBy: 'id ASC',
    );
    final items = <Map<String, dynamic>>[];
    for (final row in rows) {
      try {
        final decoded = jsonDecode(row['item_json'] as String);
        if (decoded is Map<String, dynamic>) {
          items.add(decoded);
        }
      } catch (e, st) {
        ErrorHandler.log('DrillCache decode entry', e, st);
        // Skip corrupted cache entries.
      }
    }
    return items;
  }

  /// How old is the cache? Returns null if no cache exists.
  Future<Duration?> cacheAge(String sessionType) async {
    if (_db == null) return null;
    final rows = await _db!.query(
      'cached_items',
      where: 'session_type = ?',
      whereArgs: [sessionType],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    final fetchedAt = DateTime.parse(rows.first['fetched_at'] as String);
    return DateTime.now().toUtc().difference(fetchedAt);
  }

  Future<void> dispose() async {
    await _db?.close();
  }
}

final drillCacheProvider = Provider<DrillCache>((ref) {
  final api = ref.watch(apiClientProvider);
  final cache = DrillCache(api);
  cache.init();
  ref.onDispose(() => cache.dispose());
  return cache;
});
