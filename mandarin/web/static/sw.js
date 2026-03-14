/* Service Worker — offline-capable PWA for Aelu Mandarin
   Cache versioning: bump CACHE_VERSION to invalidate all caches on deploy. */

var CACHE_VERSION = 'mandarin-v7';
var STATIC_CACHE = CACHE_VERSION + '-static';
var API_CACHE = CACHE_VERSION + '-api';
var FONT_CACHE = CACHE_VERSION + '-fonts';
var AUDIO_CACHE = CACHE_VERSION + '-audio';

/* Maximum items in runtime caches to prevent unbounded growth */
var AUDIO_CACHE_LIMIT = 200;
var API_CACHE_LIMIT = 50;

var STATIC_ASSETS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/offline-queue.js',
  '/static/capacitor-bridge.js',
  '/static/manifest.json',
  '/static/favicon.ico',
  '/static/favicon-32.png',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon-app.png',
  '/static/icon-app-dark.png',
  '/static/logo-horizontal.svg',
  '/static/logo-horizontal-dark.svg',
  '/static/logo-mark.svg',
  '/static/logo-mark-dark.svg',
  '/static/logo-monochrome.svg',
  '/static/logo-wordmark.svg',
  '/static/ui-icons.svg',
  '/static/recorder-worklet.js',
];

/* All known cache names for this version */
var EXPECTED_CACHES = [STATIC_CACHE, API_CACHE, FONT_CACHE, AUDIO_CACHE];

/* ── Utility: trim a cache to a maximum number of entries ── */

function trimCache(cacheName, maxItems) {
  caches.open(cacheName).then(function(cache) {
    cache.keys().then(function(keys) {
      if (keys.length > maxItems) {
        cache.delete(keys[0]).then(function() {
          if (keys.length - 1 > maxItems) trimCache(cacheName, maxItems);
        });
      }
    });
  });
}

/* ── Install: pre-cache static assets + app shell ── */
/* NOTE: We do NOT call self.skipWaiting() here. The new SW waits until
   the client explicitly sends a SKIP_WAITING message (after the user
   acknowledges the update banner). This prevents version skew between
   the active page JS and the SW's cached assets. */

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(function(cache) {
      return cache.addAll(STATIC_ASSETS);
    })
  );
});

/* ── Message handler: controlled activation + kill-switch ── */

self.addEventListener('message', function(event) {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'KILL_SW') {
    /* Emergency kill-switch: unregister this SW and clear all caches */
    caches.keys().then(function(keys) {
      return Promise.all(keys.map(function(k) { return caches.delete(k); }));
    }).then(function() {
      return self.registration.unregister();
    });
  }
});

/* ── Activate: clean up ALL old-version caches + check kill-switch ── */

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(key) {
          /* Delete any cache not in our expected set for this version */
          return EXPECTED_CACHES.indexOf(key) === -1;
        }).map(function(key) {
          console.log('[sw] deleting old cache:', key);
          return caches.delete(key);
        })
      );
    }).then(function() {
      return self.clients.claim();
    }).then(function() {
      /* Check kill-switch on activate */
      return _checkKillSwitch();
    })
  );
});

/* Kill-switch: fetch /api/sw-status and unregister if told to */
function _checkKillSwitch() {
  return fetch('/api/sw-status').then(function(r) {
    return r.json();
  }).then(function(data) {
    if (data && data.active === false) {
      console.log('[sw] kill-switch active — unregistering');
      caches.keys().then(function(keys) {
        return Promise.all(keys.map(function(k) { return caches.delete(k); }));
      });
      return self.registration.unregister();
    }
  }).catch(function() {
    /* Offline or server error — continue normally */
  });
}

/* ── Fetch strategies ── */

self.addEventListener('fetch', function(event) {
  var url = new URL(event.request.url);

  /* Skip non-GET and WebSocket */
  if (event.request.method !== 'GET') return;
  if (url.protocol === 'ws:' || url.protocol === 'wss:') return;

  /* ── Audio: cache-then-network (audio files rarely change, save bandwidth) ── */
  if (url.pathname.startsWith('/api/audio/') || url.pathname.startsWith('/api/tts/')) {
    event.respondWith(
      caches.open(AUDIO_CACHE).then(function(cache) {
        return cache.match(event.request).then(function(cached) {
          if (cached) return cached;
          return fetch(event.request).then(function(response) {
            if (response.ok) {
              cache.put(event.request, response.clone());
              trimCache(AUDIO_CACHE, AUDIO_CACHE_LIMIT);
            }
            return response;
          });
        });
      }).catch(function() {
        /* Audio unavailable offline — return empty audio */
        return new Response('', {
          status: 503,
          headers: { 'Content-Type': 'audio/mpeg' }
        });
      })
    );
    return;
  }

  /* ── API calls: network-first, cache safe read-only endpoints ── */
  if (url.pathname.startsWith('/api/')) {
    var safeToCacheAPIs = ['/api/health', '/api/reading/', '/api/media/'];
    var isSafeToCache = safeToCacheAPIs.some(function(prefix) {
      return url.pathname.startsWith(prefix);
    });
    event.respondWith(
      fetch(event.request).then(function(response) {
        if (response.ok && isSafeToCache) {
          var clone = response.clone();
          caches.open(API_CACHE).then(function(cache) {
            cache.put(event.request, clone);
            trimCache(API_CACHE, API_CACHE_LIMIT);
          });
        }
        return response;
      }).catch(function() {
        if (isSafeToCache) return caches.match(event.request);
        return new Response(JSON.stringify({ error: 'Offline' }), {
          status: 503, headers: { 'Content-Type': 'application/json' }
        });
      })
    );
    return;
  }

  /* ── Google Fonts: cache-first (font files rarely change, large) ── */
  if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
    event.respondWith(
      caches.open(FONT_CACHE).then(function(cache) {
        return cache.match(event.request).then(function(cached) {
          if (cached) return cached;
          return fetch(event.request).then(function(response) {
            if (response.ok) cache.put(event.request, response.clone());
            return response;
          });
        });
      })
    );
    return;
  }

  /* ── Static assets: network-first for versioned CSS/JS, cache-first otherwise ── */
  if (url.pathname.startsWith('/static/')) {
    var hasVersion = url.search && url.search.indexOf('v=') !== -1;
    if (hasVersion) {
      /* Network-first for versioned assets — ensures fresh CSS/JS after deploys.
         Falls back to cache (ignoring query string) if network fails. */
      event.respondWith(
        fetch(event.request).then(function(response) {
          if (response.ok) {
            var clone = response.clone();
            caches.open(STATIC_CACHE).then(function(cache) {
              /* Cache under both versioned URL and bare pathname for fallback */
              cache.put(event.request, clone.clone());
              cache.put(new Request(url.pathname), clone);
            });
          }
          return response;
        }).catch(function() {
          /* Offline: try exact URL, then bare pathname (ignoring version hash) */
          return caches.match(event.request).then(function(cached) {
            if (cached) return cached;
            return caches.match(new Request(url.pathname));
          }).then(function(cached) {
            return cached || new Response('', { status: 503 });
          });
        })
      );
    } else {
      /* Cache-first for unversioned static assets */
      event.respondWith(
        caches.match(event.request).then(function(cached) {
          if (cached) return cached;
          return fetch(event.request).then(function(response) {
            if (response.ok) {
              var clone = response.clone();
              caches.open(STATIC_CACHE).then(function(cache) {
                cache.put(event.request, clone);
              });
            }
            return response;
          });
        })
      );
    }
    return;
  }

  /* ── Navigation requests: network-first with offline app shell fallback ── */
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).then(function(response) {
        /* Cache successful navigation responses for offline shell */
        if (response.ok) {
          var clone = response.clone();
          caches.open(STATIC_CACHE).then(function(cache) {
            cache.put('/', clone);
          });
        }
        return response;
      }).catch(function() {
        /* Offline: serve cached app shell */
        return caches.match('/').then(function(cached) {
          return cached || new Response(
            '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aelu — Offline</title><style>body{font-family:Georgia,serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#F2EBE0;color:#2A3650;text-align:center;padding:2rem;margin:0}h1{font-size:1.4rem;font-weight:400;margin-bottom:0.5rem}p{color:#5A6678;font-size:0.9rem}</style></head><body><div><h1>Aelu</h1><p>You are offline. Please reconnect to continue studying.</p></div></body></html>',
            { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        });
      })
    );
    return;
  }

  /* ── Everything else: network with cache fallback ── */
  event.respondWith(
    fetch(event.request).catch(function() {
      return caches.match(event.request).then(function(cached) {
        return cached || caches.match('/');
      });
    })
  );
});

/* ── Background sync: replay drill results queued while offline ── */

self.addEventListener('sync', function(event) {
  if (event.tag === 'sync-drill-results') {
    event.waitUntil(
      syncDrillResults()
    );
  }
});

function syncDrillResults() {
  /* Open the offline-queue IndexedDB and flush pending actions */
  return new Promise(function(resolve, reject) {
    var request = indexedDB.open('mandarin_offline', 1);
    request.onerror = function() { reject(new Error('IndexedDB open failed in SW')); };
    request.onsuccess = function(event) {
      var db = event.target.result;
      if (!db.objectStoreNames.contains('queue')) { resolve(); return; }
      var tx = db.transaction('queue', 'readonly');
      var store = tx.objectStore('queue');
      var getAll = store.getAll();
      getAll.onsuccess = function() {
        var items = getAll.result || [];
        if (items.length === 0) { resolve(); return; }

        var actions = items.map(function(item) {
          return { type: item.action, data: item.payload, timestamp: item.timestamp };
        });

        fetch('/api/sync/push', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ actions: actions }),
        }).then(function(response) {
          if (response.ok) {
            /* Clear the queue after successful sync */
            var clearTx = db.transaction('queue', 'readwrite');
            var clearStore = clearTx.objectStore('queue');
            clearStore.clear();
            resolve();
          } else {
            reject(new Error('Sync push failed: ' + response.status));
          }
        }).catch(reject);
      };
      getAll.onerror = function() { reject(new Error('GetAll failed in SW')); };
    };
  });
}

/* ── Push notifications ── */

self.addEventListener('push', function(event) {
  var data = { title: 'Aelu', body: '', url: '/', icon: '/static/icon-192.png' };
  if (event.data) {
    try {
      data = Object.assign(data, event.data.json());
    } catch (e) {
      data.body = event.data.text();
    }
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon,
      badge: '/static/icon-192.png',
      tag: data.tag || 'aelu-reminder',
      renotify: true,
      data: { url: data.url },
      actions: [
        { action: 'open', title: 'Start session' },
      ],
    })
  );
});

/* ── Notification click ── */

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  var url = (event.notification.data && event.notification.data.url) || '/';
  if (event.action === 'open') {
    url = '/';
  }
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(windowClients) {
      for (var i = 0; i < windowClients.length; i++) {
        if (windowClients[i].url.indexOf(url) !== -1 && 'focus' in windowClients[i]) {
          return windowClients[i].focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});
