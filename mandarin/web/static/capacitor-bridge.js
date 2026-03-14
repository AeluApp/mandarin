/* Capacitor native bridge — detects native environment and provides plugin wrappers.
   No-ops gracefully in browser. */

var CapacitorBridge = (function() {
  'use strict';

  var _log = typeof _debugLog !== 'undefined' ? _debugLog : console;
  var isCapacitor = typeof window !== 'undefined' && typeof window.Capacitor !== 'undefined';

  // ── Haptics ────────────────────────────────────────────
  // Vibrate on correct/incorrect answers. No-ops in browser.

  async function hapticFeedback(type) {
    if (!isCapacitor) return;
    try {
      var Haptics = window.Capacitor.Plugins.Haptics;
      if (!Haptics) return;
      if (type === 'correct') {
        await Haptics.notification({ type: 'SUCCESS' });
      } else if (type === 'incorrect') {
        await Haptics.notification({ type: 'ERROR' });
      } else {
        await Haptics.impact({ style: 'LIGHT' });
      }
    } catch (e) {
      // Plugin not available — ignore
    }
  }

  // ── Push Notifications ─────────────────────────────────

  async function registerPush() {
    if (!isCapacitor) return null;
    try {
      var PushNotifications = window.Capacitor.Plugins.PushNotifications;
      if (!PushNotifications) return null;
      var perm = await PushNotifications.requestPermissions();
      if (perm.receive === 'granted') {
        await PushNotifications.register();
        return new Promise(function(resolve) {
          PushNotifications.addListener('registration', function(token) {
            resolve(token.value);
          });
          // Timeout after 10s in case registration callback never fires
          setTimeout(function() { resolve(null); }, 10000);
        });
      }
    } catch (e) {
      _log.warn('[capacitor] push registration failed:', e);
    }
    return null;
  }

  // ── Network Status ─────────────────────────────────────

  async function isOnline() {
    if (!isCapacitor) return navigator.onLine;
    try {
      var Network = window.Capacitor.Plugins.Network;
      if (!Network) return navigator.onLine;
      var status = await Network.getStatus();
      return status.connected;
    } catch (e) {
      return navigator.onLine;
    }
  }

  function onNetworkChange(callback) {
    if (!isCapacitor) {
      // Browser fallback
      window.addEventListener('online', function() { callback(true); });
      window.addEventListener('offline', function() { callback(false); });
      return;
    }
    try {
      var Network = window.Capacitor.Plugins.Network;
      if (Network) {
        Network.addListener('networkStatusChange', function(status) {
          callback(status.connected);
        });
      }
    } catch (e) {
      // Fallback to browser events
      window.addEventListener('online', function() { callback(true); });
      window.addEventListener('offline', function() { callback(false); });
    }
  }

  // ── Keyboard ───────────────────────────────────────────

  async function setupKeyboard() {
    if (!isCapacitor) return;
    try {
      var Keyboard = window.Capacitor.Plugins.Keyboard;
      if (!Keyboard) return;
      Keyboard.addListener('keyboardWillShow', function(info) {
        document.body.style.setProperty('--keyboard-height', info.keyboardHeight + 'px');
        document.body.classList.add('keyboard-visible');
      });
      Keyboard.addListener('keyboardWillHide', function() {
        document.body.style.setProperty('--keyboard-height', '0px');
        document.body.classList.remove('keyboard-visible');
      });
    } catch (e) {
      // Plugin not available
    }
  }

  // ── Status Bar ─────────────────────────────────────────

  async function setupStatusBar(isDark) {
    if (!isCapacitor) return;
    try {
      var StatusBar = window.Capacitor.Plugins.StatusBar;
      if (!StatusBar) return;
      await StatusBar.setStyle({ style: isDark ? 'DARK' : 'LIGHT' });
      await StatusBar.setBackgroundColor({ color: isDark ? '#1C2028' : '#F2EBE0' });
    } catch (e) {
      // Plugin not available
    }
  }

  // ── Deep Links ─────────────────────────────────────────

  async function setupDeepLinks() {
    if (!isCapacitor) return;
    try {
      var App = window.Capacitor.Plugins.App;
      if (!App) return;
      App.addListener('appUrlOpen', function(data) {
        try {
          var url = new URL(data.url);
          if (url.pathname) {
            window.location.hash = url.pathname;
          }
        } catch (e) {
          // Invalid URL — ignore
        }
      });
    } catch (e) {
      // Plugin not available
    }
  }

  // ── Init ───────────────────────────────────────────────

  async function init() {
    if (!isCapacitor) return;
    await setupKeyboard();
    var isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    await setupStatusBar(isDark);
    await setupDeepLinks();

    // Update status bar on theme change
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
        setupStatusBar(e.matches);
      });
    }

    // Hide splash screen after setup completes
    try {
      var SplashScreen = window.Capacitor.Plugins.SplashScreen;
      if (SplashScreen) await SplashScreen.hide();
    } catch (e) {
      // Plugin not available
    }
  }

  // ── Camera OCR Lookup ────────────────────────────────────
  // Uses Capacitor Camera plugin to capture an image, then sends to
  // POST /api/dictionary/ocr for hanzi detection.
  // Falls back to "OCR not available" in browser.

  async function cameraLookup() {
    if (!isCapacitor) {
      return { error: "OCR camera lookup requires a native app." };
    }
    try {
      var Camera = window.Capacitor.Plugins.Camera;
      if (!Camera) {
        return { error: "Camera plugin not available." };
      }

      // Capture photo
      var photo = await Camera.getPhoto({
        quality: 80,
        allowEditing: false,
        resultType: 'base64',  // CameraResultType.Base64
        source: 'CAMERA',      // CameraSource.Camera
        width: 1024,
        height: 1024,
      });

      if (!photo || !photo.base64String) {
        return { error: "No image captured." };
      }

      // Send to OCR endpoint
      var response = await fetch('/api/dictionary/ocr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          image_base64: photo.base64String,
          format: photo.format || 'jpeg',
        }),
      });

      if (!response.ok) {
        return { error: "OCR request failed (HTTP " + response.status + ")" };
      }

      var data = await response.json();
      return data;  // {hanzi: "...", definitions: [...]} or {error: "..."}
    } catch (e) {
      _log.warn('[capacitor] camera lookup failed:', e);
      return { error: "Camera lookup failed: " + (e.message || e) };
    }
  }

  return {
    isCapacitor: isCapacitor,
    hapticFeedback: hapticFeedback,
    registerPush: registerPush,
    isOnline: isOnline,
    onNetworkChange: onNetworkChange,
    setupKeyboard: setupKeyboard,
    setupStatusBar: setupStatusBar,
    setupDeepLinks: setupDeepLinks,
    cameraLookup: cameraLookup,
    init: init,
  };
})();
