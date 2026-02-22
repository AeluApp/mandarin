/* Service Worker — offline-capable PWA */

var CACHE_VERSION = 'mandarin-v1';
var STATIC_CACHE = CACHE_VERSION + '-static';
var API_CACHE = CACHE_VERSION + '-api';

var STATIC_ASSETS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/favicon.svg',
];

/* Install: pre-cache static assets */
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(function(cache) {
      return cache.addAll(STATIC_ASSETS);
    }).then(function() {
      return self.skipWaiting();
    })
  );
});

/* Activate: clean up old caches */
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(key) {
          return key !== STATIC_CACHE && key !== API_CACHE;
        }).map(function(key) {
          return caches.delete(key);
        })
      );
    }).then(function() {
      return self.clients.claim();
    })
  );
});

/* Fetch: cache-first for static, network-first for API */
self.addEventListener('fetch', function(event) {
  var url = new URL(event.request.url);

  // Skip non-GET and WebSocket
  if (event.request.method !== 'GET') return;
  if (url.protocol === 'ws:' || url.protocol === 'wss:') return;

  // API calls: network-first, only cache safe read-only endpoints
  if (url.pathname.startsWith('/api/')) {
    // Never cache authenticated or sensitive API responses
    var safeToCacheAPIs = ['/api/health'];
    var isSafeToCache = safeToCacheAPIs.some(function(prefix) {
      return url.pathname.startsWith(prefix);
    });
    event.respondWith(
      fetch(event.request).then(function(response) {
        if (response.ok && isSafeToCache) {
          var clone = response.clone();
          caches.open(API_CACHE).then(function(cache) {
            cache.put(event.request, clone);
          });
        }
        return response;
      }).catch(function() {
        if (isSafeToCache) return caches.match(event.request);
        return new Response(JSON.stringify({error: 'Offline'}), {
          status: 503, headers: {'Content-Type': 'application/json'}
        });
      })
    );
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/') || url.pathname === '/') {
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
    return;
  }

  // Everything else: network with cache fallback
  event.respondWith(
    fetch(event.request).catch(function() {
      return caches.match(event.request).then(function(cached) {
        return cached || caches.match('/');
      });
    })
  );
});
