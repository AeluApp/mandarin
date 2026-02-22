/* Offline queue — IndexedDB-backed queue for drill results when disconnected.
   Replays queued actions to /api/sync/push on reconnect. */

var OfflineQueue = (function() {
  'use strict';

  var _log = typeof _debugLog !== 'undefined' ? _debugLog : console;
  var DB_NAME = 'mandarin_offline';
  var STORE_NAME = 'queue';
  var DB_VERSION = 1;
  var _db = null;

  // ── IndexedDB setup ────────────────────────────────────

  function openDB() {
    return new Promise(function(resolve, reject) {
      if (_db) { resolve(_db); return; }
      try {
        var request = indexedDB.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = function(event) {
          var db = event.target.result;
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
          }
        };
        request.onsuccess = function(event) {
          _db = event.target.result;
          resolve(_db);
        };
        request.onerror = function() {
          reject(new Error('IndexedDB open failed'));
        };
      } catch (e) {
        reject(e);
      }
    });
  }

  // ── Enqueue ────────────────────────────────────────────

  function enqueue(action, payload) {
    return openDB().then(function(db) {
      return new Promise(function(resolve, reject) {
        var tx = db.transaction(STORE_NAME, 'readwrite');
        var store = tx.objectStore(STORE_NAME);
        var entry = {
          action: action,
          payload: payload,
          timestamp: new Date().toISOString(),
        };
        var request = store.add(entry);
        request.onsuccess = function() { resolve(); };
        request.onerror = function() { reject(new Error('Enqueue failed')); };
      });
    });
  }

  // ── Get all queued items ───────────────────────────────

  function getAll() {
    return openDB().then(function(db) {
      return new Promise(function(resolve, reject) {
        var tx = db.transaction(STORE_NAME, 'readonly');
        var store = tx.objectStore(STORE_NAME);
        var request = store.getAll();
        request.onsuccess = function() { resolve(request.result || []); };
        request.onerror = function() { reject(new Error('GetAll failed')); };
      });
    });
  }

  // ── Clear queue ────────────────────────────────────────

  function clear() {
    return openDB().then(function(db) {
      return new Promise(function(resolve, reject) {
        var tx = db.transaction(STORE_NAME, 'readwrite');
        var store = tx.objectStore(STORE_NAME);
        var request = store.clear();
        request.onsuccess = function() { resolve(); };
        request.onerror = function() { reject(new Error('Clear failed')); };
      });
    });
  }

  // ── Queue size ─────────────────────────────────────────

  function getQueueSize() {
    return openDB().then(function(db) {
      return new Promise(function(resolve, reject) {
        var tx = db.transaction(STORE_NAME, 'readonly');
        var store = tx.objectStore(STORE_NAME);
        var request = store.count();
        request.onsuccess = function() { resolve(request.result); };
        request.onerror = function() { reject(new Error('Count failed')); };
      });
    });
  }

  // ── Flush — send all queued actions to server ──────────

  function flush() {
    return getAll().then(function(items) {
      if (items.length === 0) return Promise.resolve(0);

      var actions = items.map(function(item) {
        return {
          type: item.action,
          data: item.payload,
          timestamp: item.timestamp,
        };
      });

      var token = null;
      try { token = sessionStorage.getItem('jwt_token'); } catch (e) {}

      var headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
      if (token) headers['Authorization'] = 'Bearer ' + token;

      return fetch('/api/sync/push', {
        method: 'POST',
        headers: headers,
        credentials: 'include',
        body: JSON.stringify({ actions: actions }),
      }).then(function(response) {
        if (response.ok) {
          return clear().then(function() { return items.length; });
        }
        throw new Error('Sync push failed: ' + response.status);
      });
    });
  }

  // ── Auto-flush on reconnect ────────────────────────────

  function setupAutoFlush() {
    window.addEventListener('online', function() {
      flush().then(function(count) {
        if (count > 0) {
          _log.log('[offline-queue] flushed', count, 'items on reconnect');
        }
      }).catch(function(e) {
        _log.warn('[offline-queue] auto-flush failed:', e);
      });
    });

    // Also flush if Capacitor network change detected
    if (typeof CapacitorBridge !== 'undefined' && CapacitorBridge.onNetworkChange) {
      CapacitorBridge.onNetworkChange(function(connected) {
        if (connected) {
          flush().catch(function(e) {
            _log.warn('[offline-queue] capacitor auto-flush failed:', e);
          });
        }
      });
    }
  }

  return {
    enqueue: enqueue,
    flush: flush,
    getAll: getAll,
    clear: clear,
    getQueueSize: getQueueSize,
    setupAutoFlush: setupAutoFlush,
  };
})();
