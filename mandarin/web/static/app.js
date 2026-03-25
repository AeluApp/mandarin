/* Aelu web — WebSocket client for drill sessions */

/* Debug logging — suppressed in production */
var _debugLog = (function() {
  var isDebug = !window.IS_PRODUCTION && (location.hostname === 'localhost' || location.hostname === '127.0.0.1');
  return {
    log: function() { if (isDebug) console.log.apply(console, arguments); },
    warn: function() { if (isDebug) console.warn.apply(console, arguments); },
    error: function() { console.error.apply(console, arguments); },  // always log errors
  };
})();

/* ── GA4 event helper ────── */
function trackEvent(name, params) {
  if (typeof gtag === 'function') {
    gtag('event', name, params || {});
  }
}

/* ── Dark mode illustration helper ────── */
function themedIllustration(basePath) {
  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (!isDark) return basePath;
  return basePath.replace(/\.(png|webp|jpg)$/, '-dark.$1');
}

/* ── Session checkpoint (localStorage persistence for crash resume) ────── */
var SessionCheckpoint = (function() {
  var KEY = "aelu_session_checkpoint";
  var MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

  function save(sessionId, drillIndex, drillTotal, correct, completed, sessionType) {
    try {
      localStorage.setItem(KEY, JSON.stringify({
        sessionId: sessionId,
        drillIndex: drillIndex,
        drillTotal: drillTotal,
        correct: correct,
        completed: completed,
        sessionType: sessionType || "standard",
        ts: Date.now()
      }));
    } catch (e) {}
  }

  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data || !data.sessionId || !data.ts) return null;
      if (Date.now() - data.ts > MAX_AGE_MS) {
        clear();
        return null;
      }
      return data;
    } catch (e) {
      return null;
    }
  }

  function clear() {
    try { localStorage.removeItem(KEY); } catch (e) {}
  }

  return { save: save, load: load, clear: clear };
})();

/* ── Client-side event log (ring buffer, last 200 events) ────── */
/* Captures screen transitions, session lifecycle, WS events, and errors.
   Used by "Report a Problem" to give the developer a reproducible trace.
   No PII — only structural events, drill IDs, and timestamps. */
var EventLog = (function() {
  var MAX_ENTRIES = 200;
  var entries = [];
  var installId = null;

  // Stable install ID — persists across sessions, anonymous
  try {
    installId = localStorage.getItem("mandarin_install_id");
    if (!installId) {
      installId = "m-" + Date.now().toString(36) + "-" + Math.random().toString(36).substr(2, 6);
      localStorage.setItem("mandarin_install_id", installId);
    }
  } catch (e) {
    installId = "m-unknown";
  }

  function record(category, event, detail) {
    var entry = {
      t: new Date().toISOString(),
      cat: category,
      evt: event,
    };
    if (detail !== undefined && detail !== null) entry.d = detail;
    entries.push(entry);
    if (entries.length > MAX_ENTRIES) entries.shift();
  }

  function getEntries() { return entries.slice(); }
  function getInstallId() { return installId; }

  function getSnapshot() {
    var visibleSection = "unknown";
    ["dashboard", "session", "complete", "reading", "media", "media-quiz", "listening", "grammar", "teacher-dashboard"].forEach(function(id) {
      var el = document.getElementById(id);
      if (el && !el.classList.contains("hidden")) visibleSection = id;
    });

    var buildMeta = document.querySelector('meta[name="build-id"]');
    return {
      install_id: installId,
      build_id: buildMeta ? buildMeta.content : "unknown",
      timestamp: new Date().toISOString(),
      url: location.pathname,
      screen: visibleSection,
      session_active: typeof sessionActive !== "undefined" ? sessionActive : false,
      drill_progress: (typeof drillCount !== "undefined" ? drillCount : 0) + "/" + (typeof drillTotal !== "undefined" ? drillTotal : 0),
      user_agent: navigator.userAgent,
      viewport: window.innerWidth + "x" + window.innerHeight,
      online: navigator.onLine,
      events: getEntries(),
    };
  }

  // ── Auto-report: queue + debounced flush to /api/error-report ──
  var _pendingErrors = [];
  var _recentlySent = {};  // message → timestamp (5-min dedup)
  var _flushTimer = null;
  var DEDUP_WINDOW_MS = 5 * 60 * 1000;
  var FLUSH_DELAY_MS = 5000;
  var MAX_BATCH = 10;

  function _queueError(errorObj) {
    var key = (errorObj.message || "").substring(0, 200);
    var now = Date.now();
    if (_recentlySent[key] && (now - _recentlySent[key]) < DEDUP_WINDOW_MS) return;
    _recentlySent[key] = now;
    _pendingErrors.push(errorObj);
    if (!_flushTimer) {
      _flushTimer = setTimeout(_flushErrors, FLUSH_DELAY_MS);
    }
  }

  function _flushErrors() {
    _flushTimer = null;
    var batch = _pendingErrors.splice(0, MAX_BATCH);
    batch.forEach(function(err) {
      try {
        apiFetch("/api/error-report", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(err),
        }).catch(function() {});  // fire-and-forget
      } catch (ex) { /* ignore */ }
    });
  }

  // Capture unhandled errors
  window.addEventListener("error", function(e) {
    record("error", "unhandled", {
      msg: (e.message || "").substring(0, 200),
      src: (e.filename || "").split("/").pop(),
      line: e.lineno,
    });
    _queueError({
      error_type: "js_error",
      message: (e.message || "").substring(0, 2000),
      source: (e.filename || ""),
      line: e.lineno,
      col: e.colno,
      stack: (e.error && e.error.stack) ? e.error.stack.substring(0, 10000) : "",
      page_url: location.href,
    });
  });

  window.addEventListener("unhandledrejection", function(e) {
    record("error", "promise", {
      msg: String(e.reason || "").substring(0, 200),
    });
    _queueError({
      error_type: "promise_rejection",
      message: String(e.reason || "").substring(0, 2000),
      stack: (e.reason && e.reason.stack) ? e.reason.stack.substring(0, 10000) : "",
      page_url: location.href,
    });
  });

  // Flush remaining errors on page unload
  window.addEventListener("pagehide", function() {
    if (_pendingErrors.length === 0) return;
    var batch = _pendingErrors.splice(0, MAX_BATCH);
    batch.forEach(function(err) {
      try {
        var blob = new Blob([JSON.stringify(err)], {type: "application/json"});
        navigator.sendBeacon("/api/error-report", blob);
      } catch (ex) { /* ignore */ }
    });
  });

  // ── Client event batch flush to server ──
  var _clientEventQueue = [];
  var _clientFlushTimer = null;
  var CLIENT_FLUSH_INTERVAL = 60000; // 60s

  function _startClientFlush() {
    if (_clientFlushTimer) return;
    _clientFlushTimer = setInterval(_flushClientEvents, CLIENT_FLUSH_INTERVAL);
  }

  function _flushClientEvents() {
    if (_clientEventQueue.length === 0) return;
    var batch = _clientEventQueue.splice(0, 50);
    try {
      var payload = JSON.stringify({events: batch, install_id: installId});
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/api/client-events", new Blob([payload], {type: "application/json"}));
      } else {
        apiFetch("/api/client-events", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: payload,
        }).catch(function() {});
      }
    } catch (ex) { /* ignore */ }
  }

  // Flush remaining client events on page unload
  window.addEventListener("pagehide", function() {
    _flushClientEvents();
  });

  // Generate a UUID v4 for event dedup (crypto.randomUUID with fallback)
  function _uuid() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function(c) {
      var r = Math.random() * 16 | 0;
      return (c === "x" ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  // Queue a client event for server-side persistence
  function queueClientEvent(category, event, detail) {
    _clientEventQueue.push({
      id: _uuid(),
      t: new Date().toISOString(),
      cat: category,
      evt: event,
      d: detail || null,
    });
    _startClientFlush();
  }

  // First-use feature adoption logger — fires once per feature
  function logFirstFeatureUse(feature) {
    try {
      var key = "aelu_first_" + feature;
      if (localStorage.getItem(key)) return;
      localStorage.setItem(key, "1");
    } catch (e) { return; }
    record("adoption", feature);
    queueClientEvent("adoption", feature);
  }

  return {
    record: record,
    getEntries: getEntries,
    getInstallId: getInstallId,
    getSnapshot: getSnapshot,
    reportError: _queueError,
    flush: _flushClientEvents,
    queueClientEvent: queueClientEvent,
    logFirstFeatureUse: logFirstFeatureUse,
  };
})();

/* ── Rage click detection: 3+ clicks in same area within 1.5s ── */
(function() {
  var _rageClicks = [];
  var RAGE_WINDOW = 1500;
  var RAGE_THRESHOLD = 3;
  var PROXIMITY_PX = 50; // clicks within 50px radius count as "same area"

  document.addEventListener("click", function(e) {
    var now = Date.now();
    var x = e.clientX;
    var y = e.clientY;

    // Filter to recent clicks within proximity
    _rageClicks = _rageClicks.filter(function(c) {
      if ((now - c.t) >= RAGE_WINDOW) return false;
      var dx = c.x - x;
      var dy = c.y - y;
      return (dx * dx + dy * dy) < PROXIMITY_PX * PROXIMITY_PX;
    });
    _rageClicks.push({x: x, y: y, t: now, el: e.target});

    if (_rageClicks.length >= RAGE_THRESHOLD) {
      // Use the nearest interactive ancestor or the target itself for labeling
      var labelEl = e.target;
      var ancestor = e.target.closest("a, button, [role=button], [onclick]");
      if (ancestor) labelEl = ancestor;
      var selector = labelEl.tagName.toLowerCase();
      if (labelEl.id) selector += "#" + labelEl.id;
      else if (labelEl.className && typeof labelEl.className === "string") selector += "." + labelEl.className.split(" ")[0];
      EventLog.queueClientEvent("ux", "rage_click", {target: selector, count: _rageClicks.length});
      _rageClicks = [];
    }
  }, true);
})();

/* ── Dead click detection: click on non-interactive element ── */
(function() {
  var _lastDeadClick = 0;
  var COOLDOWN = 2000; // 2s cooldown to avoid flooding on text selection etc.

  function isInteractive(el) {
    if (!el || el === document.body || el === document.documentElement) return false;
    var tag = el.tagName;
    if (tag === "A" || tag === "BUTTON" || tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || tag === "LABEL") return true;
    if (el.hasAttribute("onclick") || el.getAttribute("role") === "button" || el.hasAttribute("tabindex")) return true;
    // Check for cursor:pointer style (common interactive indicator)
    var style = window.getComputedStyle(el);
    if (style && style.cursor === "pointer") return true;
    return isInteractive(el.parentElement);
  }

  function isTextContent(el) {
    // Skip clicks on text content — users click to select text, not expecting interaction
    var tag = el.tagName;
    if (tag === "P" || tag === "SPAN" || tag === "LI" || tag === "TD" || tag === "TH"
        || tag === "H1" || tag === "H2" || tag === "H3" || tag === "H4" || tag === "H5" || tag === "H6"
        || tag === "EM" || tag === "STRONG" || tag === "CODE" || tag === "PRE") return true;
    return false;
  }

  document.addEventListener("click", function(e) {
    var now = Date.now();
    if (now - _lastDeadClick < COOLDOWN) return;
    if (isInteractive(e.target)) return;
    if (isTextContent(e.target)) return;
    // Skip if user is selecting text
    var sel = window.getSelection();
    if (sel && sel.toString().length > 0) return;

    _lastDeadClick = now;
    var target = e.target;
    var selector = target.tagName.toLowerCase();
    if (target.id) selector += "#" + target.id;
    else if (target.className && typeof target.className === "string") selector += "." + target.className.split(" ")[0];
    EventLog.queueClientEvent("ux", "dead_click", {target: selector, selector: selector});
  }, true);
})();

/* API fetch wrapper — adds X-Requested-With header for CSRF protection on
   cookie-authenticated POST/PUT/DELETE requests (Zero Trust: verify every request) */
function apiFetch(url, opts) {
  opts = opts || {};
  opts.credentials = opts.credentials || 'include';
  if (!opts.headers) opts.headers = {};
  if (typeof opts.headers.set === 'function') {
    opts.headers.set('X-Requested-With', 'XMLHttpRequest');
  } else {
    opts.headers['X-Requested-With'] = 'XMLHttpRequest';
  }
  return fetch(url, opts);
}

/* ── Haptic Feedback (mobile web) ────── */
function _hapticFeedback(type) {
  if (typeof navigator === 'undefined' || !navigator.vibrate) return;
  try {
    if (type === 'correct') {
      navigator.vibrate(30);  // Short, crisp tap
    } else if (type === 'incorrect') {
      navigator.vibrate([50, 30, 50]);  // Double buzz
    } else if (type === 'tap') {
      navigator.vibrate(15);  // Subtle tap
    }
  } catch (e) { /* vibrate not supported */ }
}

/* ── Swipe Gesture Handler ────── */
var SwipeHandler = (function() {
  var _startX = 0, _startY = 0, _threshold = 60;

  function attach(el, callbacks) {
    if (!el) return;
    el.addEventListener("touchstart", function(e) {
      if (e.touches.length !== 1) return;
      _startX = e.touches[0].clientX;
      _startY = e.touches[0].clientY;
    }, {passive: true});

    el.addEventListener("touchend", function(e) {
      if (e.changedTouches.length !== 1) return;
      var dx = e.changedTouches[0].clientX - _startX;
      var dy = e.changedTouches[0].clientY - _startY;
      // Only trigger horizontal swipe if horizontal distance > threshold
      // and is at least 2x the vertical distance (avoid diagonal)
      if (Math.abs(dx) > _threshold && Math.abs(dx) > Math.abs(dy) * 2) {
        if (dx > 0 && callbacks.onSwipeRight) callbacks.onSwipeRight();
        if (dx < 0 && callbacks.onSwipeLeft) callbacks.onSwipeLeft();
      }
    }, {passive: true});
  }

  return { attach: attach };
})();

/* ── Inline Dictionary Lookup ────── */
function showInlineDictionary(hanzi, event) {
  if (!hanzi) return;
  _hapticFeedback('tap');
  apiFetch("/api/dictionary/lookup?q=" + encodeURIComponent(hanzi))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      // Find or create the global gloss tooltip
      var gloss = document.getElementById("global-gloss");
      if (!gloss) {
        gloss = document.createElement("div");
        gloss.id = "global-gloss";
        gloss.className = "reading-gloss";
        document.body.appendChild(gloss);
      }

      var content = "";
      if (data.found) {
        content = '<span class="dict-hanzi">' + escapeHtml(data.hanzi) + '</span>';
        if (data.pinyin) content += ' <span class="dict-pinyin">' + escapeHtml(data.pinyin) + '</span>';
        if (data.english) content += '<br><span class="dict-english">' + escapeHtml(data.english) + '</span>';
        if (data.hsk_level) content += ' <span class="dict-hsk">HSK ' + data.hsk_level + '</span>';
      } else {
        content = escapeHtml(hanzi) + " (not in dictionary)";
      }
      gloss.innerHTML = content;
      gloss.classList.remove("hidden");

      // Position near click/tap
      if (event) {
        var x = event.clientX || (event.touches && event.touches[0] && event.touches[0].clientX) || 100;
        var y = (event.clientY || (event.touches && event.touches[0] && event.touches[0].clientY) || 100) - 50;
        if (y < 10) y += 70;
        gloss.style.left = Math.max(8, Math.min(x - 60, window.innerWidth - 240)) + "px";
        gloss.style.top = y + "px";
      }

      clearTimeout(gloss._hideTimer);
      gloss._hideTimer = setTimeout(function() { gloss.classList.add("hidden"); }, 4000);
    })
    .catch(function() {});
}

let ws = null;
let currentPromptId = null;
let drillCount = 0;
let drillTotal = 0;
let sessionActive = false;
var _readingOpenerActive = false;

/* ── Cached zh voice for speechSynthesis (6D) ── */
var _cachedZhVoice = null;
if (typeof speechSynthesis !== "undefined") {
  function _cacheZhVoice() {
    var voices = speechSynthesis.getVoices();
    var zhv = voices.find(function(v) { return v.lang.startsWith("zh"); });
    if (zhv) _cachedZhVoice = zhv;
  }
  _cacheZhVoice();
  speechSynthesis.addEventListener("voiceschanged", _cacheZhVoice);
}

/* ── Nielsen fix state ── */
var _sessionTimerInterval = null;
var _sessionStartTime = null;
var _lastSubmitTime = 0;           // #7 debounce
var _doneConfirmPending = false;   // #8 done confirmation
var _doneConfirmTimer = null;
var _hintUsedBefore = false;       // #29 hint first-use
var _preMastery = null;            // #22 session delta
var _currentMcMode = false;        // #21 MC shortcut hiding
var _lastDrillMeta = null;         // drill result metadata for override

/* ── Drill micro-timing state ── */
var _drillShownAt = null;          // Date.now() when current drill prompt shown
var _lastDrillAnsweredAt = null;   // Date.now() when last answer was sent
var _wsOpenedAt = null;            // Date.now() when WS opened for first-drill latency
var _firstDrillLogged = false;     // only log first-drill latency once per session
var _navTransitionCount = 0;       // view transitions per session

/* ── Timing constants — mirror CSS custom property values ── */
/* These MUST match :root { --duration-fast, --duration-base } in style.css */
var DURATION_FAST = 200;     // ms — matches --duration-fast: 0.2s
var DURATION_BASE = 400;     // ms — matches --duration-base: 0.4s
var FLASH_DURATION = 1500;   // ms — how long a temporary status message stays visible
var FOCUS_DELAY = 50;        // ms — brief delay before focusing MC options (DOM needs to settle)

/* ── Subscription tier cache + upgrade prompt ────────── */
var _cachedTier = null;
var _tierFetchPromise = null;
var _paywallShownTime = null;

function getCachedTier() {
  if (_cachedTier) return Promise.resolve(_cachedTier);
  if (_tierFetchPromise) return _tierFetchPromise;
  _tierFetchPromise = apiFetch("/api/subscription/status")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _cachedTier = data.tier || "free";
      _tierFetchPromise = null;
      return _cachedTier;
    })
    .catch(function() {
      _tierFetchPromise = null;
      return "free";
    });
  return _tierFetchPromise;
}

function isFreeTier() {
  return getCachedTier().then(function(tier) { return tier === "free"; });
}

var UPGRADE_MESSAGES = {
  unlimited_sessions: "You\u2019ve completed 3 sessions today. Unlock unlimited daily sessions.",
  reading: "Graded reading is a Full Access feature. Read real Chinese at your level.",
  listening: "Listening practice is a Full Access feature. Train your ear at any speed.",
  media: "The media shelf is a Full Access feature. Watch real Chinese content at your level.",
  forecast: "See how many sessions until your next HSK milestone.",
  export: "Export your progress data as CSV or Anki deck.",
  all_drill_types: "Unlock speaking, writing, and 22 more drill types.",
};

function showUpgradePrompt(feature, context) {
  EventLog.queueClientEvent("paywall", "shown", {feature: feature});
  _paywallShownTime = Date.now();

  var existing = document.getElementById("upgrade-modal");
  if (existing) existing.remove();

  var msg = context || UPGRADE_MESSAGES[feature] || "This feature requires Full Access.";

  // Build progress stats section if upgrade_context is cached
  var progressHtml = '';
  if (window._upgradeContext) {
    var uc = window._upgradeContext;
    progressHtml = '<div class="upgrade-progress">'
      + '<div class="upgrade-stat"><span class="upgrade-stat-value">' + (uc.total_sessions || 0) + '</span><span class="upgrade-stat-label">sessions</span></div>'
      + '<div class="upgrade-stat"><span class="upgrade-stat-value">' + (uc.items_learned || 0) + '</span><span class="upgrade-stat-label">words learned</span></div>'
      + '<div class="upgrade-stat"><span class="upgrade-stat-value">' + (uc.days_active || 0) + '</span><span class="upgrade-stat-label">days active</span></div>'
      + '</div>';
    if (uc.hsk2_pct > 0) {
      progressHtml += '<div class="upgrade-hsk-bar">'
        + '<div class="upgrade-hsk-bar-label">HSK 2: ' + uc.hsk2_pct + '% mastered</div>'
        + '<div class="upgrade-hsk-bar-track"><div class="upgrade-hsk-bar-fill" style="width:' + Math.min(uc.hsk2_pct, 100) + '%"></div></div>'
        + '<div class="upgrade-hsk-bar-hint">' + (uc.hsk2_pct >= 60 ? 'Ready for HSK 3\u20139 content.' : 'Keep going \u2014 you\u2019re building a strong foundation.') + '</div>'
        + '</div>';
    }
  }

  var overlay = document.createElement("div");
  overlay.id = "upgrade-modal";
  overlay.className = "upgrade-modal";
  overlay.innerHTML =
    '<div class="upgrade-modal-inner">'
    + '<div class="upgrade-promise">10 minutes a day. Every word you learn stays learned.</div>'
    + '<div class="upgrade-context">' + msg + '</div>'
    + progressHtml
    + '<div class="upgrade-pricing">'
    +   '<div class="upgrade-plan upgrade-plan-annual upgrade-plan-selected" data-plan="annual">'
    +     '<div class="upgrade-plan-price">$' + ((window.AELU_PRICING && window.AELU_PRICING.annual_monthly) || '12.42') + '<span>/mo</span></div>'
    +     '<div class="upgrade-plan-note">Billed annually ($' + ((window.AELU_PRICING && window.AELU_PRICING.annual) || '149') + '/year)</div>'
    +     '<div class="upgrade-plan-badge">Save $' + ((window.AELU_PRICING && window.AELU_PRICING.annual_savings) || '30') + '</div>'
    +   '</div>'
    +   '<div class="upgrade-plan upgrade-plan-monthly" data-plan="monthly">'
    +     '<div class="upgrade-plan-price">$' + ((window.AELU_PRICING && window.AELU_PRICING.monthly) || '14.99') + '<span>/mo</span></div>'
    +     '<div class="upgrade-plan-note">Billed monthly</div>'
    +   '</div>'
    + '</div>'
    + '<button class="btn-primary upgrade-cta" data-plan="annual">Get Full Access</button>'
    + '<button class="upgrade-dismiss">Maybe later</button>'
    + '<div class="upgrade-trust">30-day refund. Cancel anytime.</div>'
    + '</div>';

  document.body.appendChild(overlay);

  // Plan selection
  var selectedPlan = "annual";
  overlay.querySelectorAll(".upgrade-plan").forEach(function(el) {
    el.addEventListener("click", function() {
      overlay.querySelectorAll(".upgrade-plan").forEach(function(p) { p.classList.remove("upgrade-plan-selected"); });
      el.classList.add("upgrade-plan-selected");
      selectedPlan = el.dataset.plan;
      overlay.querySelector(".upgrade-cta").dataset.plan = selectedPlan;
    });
  });

  // CTA → checkout
  overlay.querySelector(".upgrade-cta").addEventListener("click", function() {
    EventLog.queueClientEvent("paywall", "click", {feature: feature, plan: selectedPlan});
    EventLog.queueClientEvent("paywall", "checkout_started", {plan: selectedPlan});
    trackEvent('upgrade_click', {current_plan: 'free', source: feature});
    EventLog.flush();
    apiFetch("/api/checkout", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({plan: selectedPlan}),
    }).then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.url) window.location.href = data.url;
      })
      .catch(function() {
        _debugLog.error("[upgrade] checkout failed");
      });
  });

  // Dismiss
  overlay.querySelector(".upgrade-dismiss").addEventListener("click", function() {
    var dismissTime = Date.now();
    EventLog.queueClientEvent("paywall", "dismiss", {feature: feature});
    overlay.remove();

    // Rage bounce detection: if dismissed within 10s, watch for inactivity
    if (_paywallShownTime && (dismissTime - _paywallShownTime) < 10000) {
      var _rageTimer = setTimeout(function() {
        EventLog.queueClientEvent("paywall", "rage_bounce", {
          feature: feature,
          time_to_dismiss_ms: dismissTime - _paywallShownTime,
        });
      }, 30000);
      // Cancel if user interacts
      var _rageCanceller = function() {
        clearTimeout(_rageTimer);
        document.removeEventListener("click", _rageCanceller);
        document.removeEventListener("keydown", _rageCanceller);
      };
      document.addEventListener("click", _rageCanceller);
      document.addEventListener("keydown", _rageCanceller);
    }
  });

  // Close on overlay click (outside inner)
  overlay.addEventListener("click", function(e) {
    if (e.target === overlay) overlay.querySelector(".upgrade-dismiss").click();
  });
}
var OPTION_STAGGER = 0.04;   // seconds — animation-delay increment per MC option button

/* ── Reconnect state ────────────────────────── */
var _hideInputTimer = null;

let reconnectAttempts = 0;
let maxReconnectAttempts = 5;
let reconnectDelay = 1000;
let lastSessionType = null;
let resumeToken = null;
var _reconnectCountdownTimer = null;

/* ── Sound synthesis v2: physically-modeled instruments ──── */
/*
 * Sound palette:
 *   Bowl  — singing bowl: inharmonic partials (1.0, 2.0, 2.71, 3.56×),
 *           per-partial decay, strike transient, detuned beating
 *   Wood  — temple block: dual-resonant bandpass body, fast decay
 *   Chime — wind chime: clean harmonics (f, 2f, 3f), per-harmonic decay
 *   Brush — swept bandpass noise for transitions
 *
 * Design constraints:
 *   - All pitched content ≥ 550Hz (above vocal F0 range 75–500Hz)
 *   - Master gain 0.04–0.08 (felt more than heard)
 *   - Feedback latency < 20ms (small scheduling lookahead)
 *   - TTS content audio > silence > UI sounds
 *   - Session start fires on section visible; complete fires on section enter
 *   - Feedback sounds fire on message render, not WS receive
 *
 * Architecture:
 *   Sources → per-sound filter → dry gain → destination
 *                               → shared ConvolverNode → destination
 *   One convolver for the whole room. One noise buffer for all percussion.
 */

var AeluSound = (function() {
  var ctx = null;
  var enabled = true;
  try {
    var saved = localStorage.getItem("soundEnabled");
    if (saved !== null) enabled = saved !== "false";
  } catch (e) {}

  function getCtx() {
    if (!ctx) {
      try { ctx = new (window.AudioContext || window.webkitAudioContext)(); }
      catch (e) { enabled = false; }
    }
    return ctx;
  }

  // Get context + resume + check enabled. Returns null if unavailable.
  function ready() {
    var c = getCtx();
    if (!c || !enabled) return null;
    if (c.state === "suspended") c.resume();
    return c;
  }

  // ── Shared resources ──────────────────────────────────────────────

  // Pre-generated white noise (1 second, reused by all percussive sounds)
  var _noise = null;
  function noise(c) {
    if (_noise) return _noise;
    var len = c.sampleRate;
    _noise = c.createBuffer(1, len, c.sampleRate);
    var d = _noise.getChannelData(0);
    for (var i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    return _noise;
  }

  // Impulse response: warm stone room (1.4s tail).
  // Two-stage decay: sparse early reflections (5–60ms) + smooth late diffusion.
  var _ir = null;
  function ir(c) {
    if (_ir) return _ir;
    var sr = c.sampleRate;
    var len = Math.floor(sr * 1.4);
    _ir = c.createBuffer(2, len, sr);
    for (var ch = 0; ch < 2; ch++) {
      var d = _ir.getChannelData(ch);
      for (var i = 0; i < len; i++) {
        var t = i / sr;
        var early = (t > 0.005 && t < 0.06)
          ? (Math.random() * 2 - 1) * 0.5 * (1 - t / 0.06) : 0;
        var late = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3.2);
        d[i] = early + late;
      }
    }
    return _ir;
  }

  // Single shared ConvolverNode — all sounds share one room.
  var _conv = null;
  function conv(c) {
    if (_conv) return _conv;
    _conv = c.createConvolver();
    _conv.buffer = ir(c);
    _conv.connect(c.destination);
    return _conv;
  }

  // ── Reverb send helper ────────────────────────────────────────────
  // Returns the filter node (connect sources here).
  // Signal: input → lowpass → dry → destination
  //                         → wetGain → shared convolver → destination
  function reverbSend(c, filterFreq, wetLevel) {
    var f = c.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.value = filterFreq || 2400;
    f.Q.value = 0.5;

    var dry = c.createGain();
    dry.gain.value = 1.0 - (wetLevel || 0.2);
    var wet = c.createGain();
    wet.gain.value = wetLevel || 0.2;

    f.connect(dry);  dry.connect(c.destination);
    f.connect(wet);  wet.connect(conv(c));

    return f;
  }

  // ── Singing bowl ──────────────────────────────────────────────────
  // Modal ratios from physical bowl acoustics. Non-integer ratios produce
  // the inharmonic spectrum that separates bowls/bells from organ pipes.
  // Two detuned oscillators per partial create natural ~1.6Hz beating.
  // 15ms filtered-noise transient simulates mallet contact on metal.
  var BOWL = [
    { r: 1.00, a: 1.0,  d: 1.0  },   // fundamental
    { r: 2.00, a: 0.40, d: 0.75 },   // octave (slightly damped)
    { r: 2.71, a: 0.18, d: 0.50 },   // inharmonic — the "bell" character
    { r: 3.56, a: 0.07, d: 0.30 },   // upper shimmer
  ];

  function playBowl(freq, t0, dur, gain) {
    var c = getCtx();
    if (!c) return;

    var send = reverbSend(c, 3200, 0.28);
    var master = c.createGain();
    master.gain.value = gain;
    master.connect(send);

    for (var i = 0; i < BOWL.length; i++) {
      var p = BOWL[i];
      var pf = freq * p.r;
      if (pf > 8000) continue;

      // Detuned pair → beating warmth
      var oA = c.createOscillator(); oA.type = "sine"; oA.frequency.value = pf - 0.8;
      var oB = c.createOscillator(); oB.type = "sine"; oB.frequency.value = pf + 0.8;

      var gA = c.createGain();
      var gB = c.createGain();
      var amp = p.a * 0.5;
      var pDur = dur * p.d;

      // Per-partial decay envelope
      gA.gain.setValueAtTime(amp, t0);
      gA.gain.exponentialRampToValueAtTime(0.001, t0 + pDur);
      gB.gain.setValueAtTime(amp, t0);
      gB.gain.exponentialRampToValueAtTime(0.001, t0 + pDur);

      oA.connect(gA); gA.connect(master);
      oB.connect(gB); gB.connect(master);
      oA.start(t0); oB.start(t0);
      oA.stop(t0 + pDur + 0.2); oB.stop(t0 + pDur + 0.2);
    }

    // Strike transient: brief filtered noise (mallet on metal)
    var ns = c.createBufferSource(); ns.buffer = noise(c);
    var bp = c.createBiquadFilter();
    bp.type = "bandpass"; bp.frequency.value = freq * 2.5; bp.Q.value = 2.0;
    var tg = c.createGain();
    tg.gain.setValueAtTime(gain * 0.6, t0);
    tg.gain.exponentialRampToValueAtTime(0.001, t0 + 0.018);
    ns.connect(bp); bp.connect(tg); tg.connect(master);
    ns.start(t0, 0, 0.025);
  }

  // ── Wood tap (temple block / mokugyo) ─────────────────────────────
  // Dual-resonance body: two bandpass filters at related frequencies
  // simulate a hollow wooden percussion instrument. Very fast attack,
  // exponential decay. Minimal reverb — wood is dry.
  function playWood(t0, gain, bodyFreq, bright) {
    var c = getCtx();
    if (!c) return;
    bright = bright != null ? bright : 0.6;

    var send = reverbSend(c, 2000, 0.08);

    var ns = c.createBufferSource(); ns.buffer = noise(c);

    // Primary body resonance
    var b1 = c.createBiquadFilter();
    b1.type = "bandpass"; b1.frequency.value = bodyFreq; b1.Q.value = 6 + bright * 8;

    // Secondary knock resonance
    var b2 = c.createBiquadFilter();
    b2.type = "bandpass"; b2.frequency.value = bodyFreq * 2.4; b2.Q.value = 3;

    var g1 = c.createGain(); g1.gain.value = 0.65;
    var g2 = c.createGain(); g2.gain.value = 0.35 * bright;

    var mix = c.createGain(); mix.gain.value = 1.0;

    // Fast exponential decay
    var decay = 0.035 + (1 - bright) * 0.035;
    var env = c.createGain();
    env.gain.setValueAtTime(gain, t0);
    env.gain.exponentialRampToValueAtTime(0.001, t0 + decay);

    ns.connect(b1); b1.connect(g1); g1.connect(mix);
    ns.connect(b2); b2.connect(g2); g2.connect(mix);
    mix.connect(env); env.connect(send);

    ns.start(t0, Math.random() * 0.5, decay + 0.05);
  }

  // ── Wind chime ────────────────────────────────────────────────────
  // Clean harmonics (f, 2f, 3f) with individual decay rates. Brighter
  // and thinner than bowl — metal rod vs metal bowl. Brief highpass
  // noise transient at onset.
  function playChime(freq, t0, dur, gain) {
    var c = getCtx();
    if (!c) return;

    var send = reverbSend(c, 4500, 0.24);
    var master = c.createGain();
    master.gain.setValueAtTime(0.001, t0);
    master.gain.exponentialRampToValueAtTime(gain, t0 + 0.015);
    master.gain.setValueAtTime(gain, t0 + dur * 0.2);
    master.gain.exponentialRampToValueAtTime(0.001, t0 + dur + 0.3);
    master.connect(send);

    var harmonics = [
      { r: 1.0, a: 0.65, d: 1.0  },
      { r: 2.0, a: 0.25, d: 0.55 },
      { r: 3.0, a: 0.10, d: 0.25 },
    ];

    for (var i = 0; i < harmonics.length; i++) {
      var h = harmonics[i];
      var o = c.createOscillator();
      o.type = "sine"; o.frequency.value = freq * h.r;
      var g = c.createGain();
      g.gain.setValueAtTime(h.a, t0);
      g.gain.exponentialRampToValueAtTime(0.001, t0 + dur * h.d);
      o.connect(g); g.connect(master);
      o.start(t0); o.stop(t0 + dur + 0.3);
    }

    // Tiny strike transient
    var ns = c.createBufferSource(); ns.buffer = noise(c);
    var hp = c.createBiquadFilter();
    hp.type = "highpass"; hp.frequency.value = freq * 2;
    var tg = c.createGain();
    tg.gain.setValueAtTime(gain * 0.25, t0);
    tg.gain.exponentialRampToValueAtTime(0.001, t0 + 0.012);
    ns.connect(hp); hp.connect(tg); tg.connect(master);
    ns.start(t0, 0, 0.018);
  }

  // ── Brush texture ─────────────────────────────────────────────────
  // Filtered noise with optional frequency sweep. Used for transitions.
  function playBrush(t0, dur, gain, freq, sweepTo) {
    var c = getCtx();
    if (!c) return;

    var send = reverbSend(c, 3000, 0.15);

    var ns = c.createBufferSource(); ns.buffer = noise(c);
    var bp = c.createBiquadFilter();
    bp.type = "bandpass"; bp.frequency.setValueAtTime(freq, t0); bp.Q.value = 0.7;
    if (sweepTo) bp.frequency.exponentialRampToValueAtTime(sweepTo, t0 + dur);

    var env = c.createGain();
    env.gain.setValueAtTime(0.001, t0);
    env.gain.exponentialRampToValueAtTime(gain, t0 + dur * 0.12);
    env.gain.exponentialRampToValueAtTime(0.001, t0 + dur);

    ns.connect(bp); bp.connect(env); env.connect(send);
    ns.start(t0, Math.random() * 0.5, dur + 0.1);
  }

  // ── Frequencies ───────────────────────────────────────────────────
  // Pentatonic A major. All above vocal F0 range.
  var A5 = 880, E5 = 659.26, Cs5 = 554.37, B5 = 987.77;

  var api = {
    // ── Session bookends ─────────────────────────────────────────────

    // Two bowl strikes a fifth apart — "we begin."
    sessionStart: function() {
      var c = ready(); if (!c) return;
      var t = c.currentTime + 0.05;
      playBowl(A5, t, 1.3, 0.07);
      playBowl(E5, t + 0.5, 1.5, 0.06);
    },

    // Descending bowl triad: A → E → C#. Final note lingers 2.5s.
    sessionComplete: function() {
      var c = ready(); if (!c) return;
      var t = c.currentTime + 0.05;
      playBowl(A5, t, 0.9, 0.06);
      playBowl(E5, t + 0.4, 0.9, 0.055);
      playBowl(Cs5, t + 0.8, 2.5, 0.06);
    },

    // ── Drill feedback ───────────────────────────────────────────────

    // Bright wood tap — warm "tok", fast and satisfying.
    correct: function() {
      var c = ready(); if (!c) return;
      playWood(c.currentTime + 0.02, 0.065, 1800, 0.7);
    },

    // Muted wood tap — lower, softer. Neutral, not punishing.
    wrong: function() {
      var c = ready(); if (!c) return;
      playWood(c.currentTime + 0.02, 0.04, 700, 0.25);
    },

    // ── Navigation ───────────────────────────────────────────────────

    // Barely-there tactile tap.
    navigate: function() {
      var c = ready(); if (!c) return;
      playWood(c.currentTime + 0.02, 0.02, 2800, 0.5);
    },

    // Single wind chime — gentle reveal.
    hintReveal: function() {
      var c = ready(); if (!c) return;
      playChime(E5, c.currentTime + 0.05, 0.5, 0.04);
    },

    // ── Achievements ─────────────────────────────────────────────────

    // Ascending bowl triad: C# → E → A.
    levelUp: function() {
      var c = ready(); if (!c) return;
      var t = c.currentTime + 0.05;
      playBowl(Cs5, t, 0.9, 0.06);
      playBowl(E5, t + 0.3, 0.9, 0.06);
      playBowl(A5, t + 0.6, 1.3, 0.065);
    },

    // Octave leap: A5 → A6.
    milestone: function() {
      var c = ready(); if (!c) return;
      var t = c.currentTime + 0.05;
      playBowl(A5, t, 0.7, 0.05);
      playBowl(1760, t + 0.35, 1.2, 0.055);
    },

    // Four ascending bowl tones with generous overlap.
    streakMilestone: function() {
      var c = ready(); if (!c) return;
      var t = c.currentTime + 0.05;
      playBowl(Cs5, t, 0.7, 0.055);
      playBowl(E5, t + 0.22, 0.7, 0.055);
      playBowl(A5, t + 0.44, 0.7, 0.055);
      playBowl(1760, t + 0.66, 1.4, 0.06);
    },

    // Sustained single bowl — pure acknowledgment.
    achievementUnlock: function() {
      var c = ready(); if (!c) return;
      playBowl(A5, c.currentTime + 0.05, 2.2, 0.06);
    },

    // ── Ambient ──────────────────────────────────────────────────────

    // Subliminal tap.
    timerTick: function() {
      var c = ready(); if (!c) return;
      playWood(c.currentTime + 0.02, 0.01, 3500, 0.3);
    },

    // Upward brush sweep.
    transitionIn: function() {
      var c = ready(); if (!c) return;
      playBrush(c.currentTime + 0.02, 0.22, 0.025, 1400, 3200);
    },

    // Downward brush sweep.
    transitionOut: function() {
      var c = ready(); if (!c) return;
      playBrush(c.currentTime + 0.02, 0.22, 0.02, 2800, 1000);
    },

    // Two muted taps.
    errorAlert: function() {
      var c = ready(); if (!c) return;
      var t = c.currentTime + 0.02;
      playWood(t, 0.04, 550, 0.2);
      playWood(t + 0.12, 0.04, 550, 0.2);
    },

    // ── Reading ──────────────────────────────────────────────────────

    // Barely-there chime — confirms tap without breaking reading flow.
    readingLookup: function() {
      var c = ready(); if (!c) return;
      playChime(E5, c.currentTime + 0.05, 0.15, 0.025);
    },

    // ── Onboarding ───────────────────────────────────────────────────

    // Gentle high chime — B5 through stone-room reverb.
    onboardingStep: function() {
      var c = ready(); if (!c) return;
      playChime(B5, c.currentTime + 0.05, 0.6, 0.03);
    },

    // ── Preferences ──────────────────────────────────────────────────

    toggle: function() {
      enabled = !enabled;
      try { localStorage.setItem("soundEnabled", enabled ? "true" : "false"); } catch (e) {}
      fetch("/api/settings/audio", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        body: JSON.stringify({enabled: enabled})
      }).catch(function() {});
      return enabled;
    },

    isEnabled: function() { return enabled; },

    syncFromServer: function() {
      fetch("/api/settings/audio", {
        headers: {"X-Requested-With": "XMLHttpRequest"}
      })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (typeof d.audio_enabled === "boolean") {
          enabled = d.audio_enabled;
          try { localStorage.setItem("soundEnabled", enabled ? "true" : "false"); } catch (e) {}
          var btn = document.getElementById("sound-toggle");
          if (btn) btn.classList.toggle("sound-off", !enabled);
        }
      })
      .catch(function() { /* offline — keep localStorage value */ });
    }
  };

  // Self-reference: callers use both AeluSound.method() and
  // AeluSound.instance.method() patterns.
  api.instance = api;

  return api;
})();

/* ── State visibility ────────────────────────── */

function setStatus(state, text) {
  const dot = document.getElementById("status-dot");
  const label = document.getElementById("status-text");
  dot.className = "dot-" + state;
  label.textContent = text;
}

/* ── Milestone toast system ────────────────────── */
/* Data-grounded celebrations — calm acknowledgment, not praise inflation. */

var MilestoneToast = (function() {
  var _shown = {};  // milestone key → true (dedup within session)
  var _queue = [];
  var _showing = false;

  try {
    var stored = JSON.parse(localStorage.getItem("milestones_seen") || "{}");
    _shown = stored;
  } catch (e) { _shown = {}; }

  function _save() {
    try { localStorage.setItem("milestones_seen", JSON.stringify(_shown)); } catch (e) {}
  }

  function _key(m) {
    return m.type + ":" + (m.threshold || "") + ":" + (m.level || "");
  }

  function show(milestone) {
    var k = _key(milestone);
    if (_shown[k]) return;  // Already shown this milestone
    _shown[k] = true;
    _save();
    _queue.push(milestone);
    if (!_showing) _next();
  }

  function _next() {
    if (_queue.length === 0) { _showing = false; return; }
    _showing = true;
    var m = _queue.shift();
    var toast = document.createElement("div");
    toast.className = "milestone-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");

    var icon = m.type === "streak" ? "\u2605" : m.type === "words_learned" ? "\u8a00" : "\u25cf";
    toast.innerHTML = '<span class="milestone-icon">' + icon + '</span>'
      + '<span class="milestone-text">' + m.message + '</span>';
    document.body.appendChild(toast);

    // Play milestone sound
    if (AeluSound.instance) AeluSound.instance.milestone();

    // Animate in
    requestAnimationFrame(function() {
      toast.classList.add("milestone-visible");
    });

    // Remove after 4 seconds
    setTimeout(function() {
      toast.classList.remove("milestone-visible");
      toast.classList.add("milestone-exit");
      setTimeout(function() {
        toast.remove();
        _next();
      }, 400);
    }, 4000);
  }

  function checkMilestones(milestones) {
    if (!milestones || !milestones.length) return;
    // Only show the highest milestone per type to avoid spam
    var byType = {};
    milestones.forEach(function(m) {
      var existing = byType[m.type + (m.level || "")];
      if (!existing || m.threshold > existing.threshold) {
        byType[m.type + (m.level || "")] = m;
      }
    });
    Object.values(byType).forEach(function(m) { show(m); });
  }

  return { show: show, checkMilestones: checkMilestones };
})();

function transitionTo(hideId, showId, callback) {
  _navTransitionCount++;
  EventLog.record("nav", "transition", {from: hideId, to: showId});
  var hideEl = document.getElementById(hideId);
  var showEl = document.getElementById(showId);
  if (AeluSound.instance) AeluSound.instance.transitionOut();
  hideEl.classList.add("section-exit");
  setTimeout(function() {
    hideEl.classList.add("hidden");
    hideEl.classList.remove("section-exit");
    showEl.classList.remove("hidden");
    showEl.classList.add("section-enter");
    if (AeluSound.instance) AeluSound.instance.transitionIn();
    setTimeout(function() {
      showEl.classList.remove("section-enter");
      // Focus management: move focus to the new section's main content
      if (showId === "session") {
        var drillArea = document.getElementById("drill-area");
        if (drillArea) drillArea.focus();
      } else if (showId === "complete") {
        var completeContent = document.getElementById("complete-content");
        if (completeContent) { completeContent.setAttribute("tabindex", "-1"); completeContent.focus(); }
      }
      if (callback) callback();
    }, DURATION_BASE);
  }, DURATION_FAST);
}

function startSession(type) {
  // First-session modal: show guidance before the very first session
  if (window._showFirstSessionModal) {
    window._showFirstSessionModal = false;
    showFirstSessionModal(function() { startSession(type); });
    return;
  }
  const drillArea = document.getElementById("drill-area");
  drillArea.textContent = "";
  sessionActive = true;
  document.body.classList.add('in-session');
  if (typeof setSessionColorState === 'function') setSessionColorState('active');
  EventLog.record("session", "start", {type: type});
  trackEvent('session_start', {session_type: type});
  lastSessionType = type;
  reconnectAttempts = 0;
  resumeToken = null;
  _doneConfirmPending = false;
  _currentMcMode = false;
  SessionCheckpoint.clear();
  try { sessionStorage.removeItem("resumeToken"); } catch (e) {}
  try { sessionStorage.removeItem("sessionType"); } catch (e) {}
  hideDisconnectBanner();
  setStatus("loading", "Preparing session");

  // #3 — Session timer (deferred until first drill renders in showInput)
  _sessionStartTime = null;
  if (_sessionTimerInterval) clearInterval(_sessionTimerInterval);
  _sessionTimerInterval = null;
  var _timerEl = document.getElementById("session-timer");
  if (_timerEl) _timerEl.textContent = "";

  // Hide keyboard shortcuts for first 3 sessions to reduce overload
  if (window._totalSessionsBefore != null && window._totalSessionsBefore < 3) {
    var shortcutsDiv = document.querySelector("#input-area .shortcuts");
    if (shortcutsDiv) shortcutsDiv.style.display = "none";
  }

  // #1 — Clear drill-type label
  var dtLabel = document.getElementById("drill-type-label");
  if (dtLabel) dtLabel.textContent = "";

  // #22 — Capture pre-session mastery for delta display
  fetch("/api/progress").then(function(r) { return r.json(); }).then(function(data) {
    _preMastery = data.mastery || null;
  }).catch(function() { _preMastery = null; });

  transitionTo("dashboard", "session", function() {
    connectWebSocket(type);
  });
}

function showResumeBanner(checkpoint, serverData) {
  var existing = document.getElementById("resume-banner");
  if (existing) existing.remove();
  var completed = serverData.items_completed || checkpoint.completed || 0;
  var total = serverData.items_planned || checkpoint.drillTotal || 0;
  var banner = document.createElement("div");
  banner.id = "resume-banner";
  banner.className = "resume-banner";
  banner.innerHTML =
    '<p>You have an unfinished session (' + completed + '/' + total + ' drills).</p>' +
    '<div class="resume-banner-actions">' +
      '<button class="btn-primary resume-btn" id="resume-continue">Resume</button>' +
      '<button class="btn-secondary resume-btn" id="resume-discard">Start fresh</button>' +
    '</div>';
  var app = document.getElementById("app");
  var dashboard = document.getElementById("dashboard");
  if (dashboard) {
    dashboard.insertBefore(banner, dashboard.firstChild);
  } else if (app) {
    app.insertBefore(banner, app.firstChild);
  }
  document.getElementById("resume-continue").addEventListener("click", function() {
    banner.remove();
    // Start a new session of the same type — the server-side WS resume
    // handles reconnect via sessionStorage token. For cross-restart resume,
    // we start a fresh session (drills already saved to DB).
    startSession(checkpoint.sessionType || "standard");
  });
  document.getElementById("resume-discard").addEventListener("click", function() {
    SessionCheckpoint.clear();
    banner.remove();
  });
}

function updateSessionTimer() {
  var timerEl = document.getElementById("session-timer");
  if (!timerEl || !_sessionStartTime) return;
  // Hide timer for first 3 sessions to reduce cognitive load
  if (window._totalSessionsBefore != null && window._totalSessionsBefore < 3) {
    timerEl.style.display = "none";
    return;
  }
  var elapsed = Math.floor((Date.now() - _sessionStartTime) / 1000);
  var mins = Math.floor(elapsed / 60);
  var secs = elapsed % 60;
  timerEl.textContent = mins + ":" + (secs < 10 ? "0" : "") + secs;
}

function connectWebSocket(type) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const path = type === "mini" ? "/ws/mini" : "/ws/session";
  var hasMic = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  // JWT token sent as first WS message, NOT in URL (prevents token leakage in logs)
  const url = `${proto}//${location.host}${path}?mic=${hasMic ? 1 : 0}`;
  _debugLog.log("[ws] connecting to", url);
  // Close existing WebSocket before creating new one to prevent leak
  if (ws) {
    try { ws.onclose = null; ws.onerror = null; ws.close(); } catch (e) {}
  }
  ws = new WebSocket(url);

  ws.onopen = function() {
    _wsOpenedAt = Date.now();
    _firstDrillLogged = false;
    _lastDrillAnsweredAt = null;
    _drillShownAt = null;
    EventLog.record("ws", "open");
    _debugLog.log("[ws] connected");
    // Send JWT token as first protocol message (not in URL to prevent log leakage)
    var jwtToken = null;
    try { jwtToken = sessionStorage.getItem('jwt_token'); } catch (e) {}
    if (jwtToken) {
      ws.send(JSON.stringify({type: "auth", token: jwtToken}));
    }
    // If we have a resume token, send it as first message
    let savedToken = resumeToken;
    try { if (!savedToken) savedToken = sessionStorage.getItem("resumeToken"); } catch (e) {}
    if (savedToken) {
      _debugLog.log("[ws] sending resume token:", savedToken);
      ws.send(JSON.stringify({type: "resume", resume_token: savedToken}));
      setStatus("loading", "Resuming session...");
      hideDisconnectBanner();
    } else {
      // Tell server immediately that this is a new session (no resume token)
      // so it doesn't wait for a token that will never come
      ws.send(JSON.stringify({type: "new"}));
      reconnectAttempts = 0;
      setStatus("connected", "In session");
      hideDisconnectBanner();
      // Sound fires when session section is fully visible (via startSession callback),
      // not on WS connect. The connectWebSocket is called from the transitionTo callback
      // so the section is already visible at this point.
      AeluSound.sessionStart();
    }
  };

  ws.onmessage = function(event) {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (e) {
      _debugLog.error("[ws] invalid JSON from server:", e);
      setStatus("disconnected", getUserFriendlyError("server"));
      addMessage(getUserFriendlyError("server"), "msg msg-wrong");
      return;
    }
    _debugLog.log("[ws] recv:", data.type, data.type === "show" ? (data.text || "").substring(0, 60) : "");
    handleMessage(data);
  };

  ws.onclose = function(event) {
    EventLog.record("ws", "close", {code: event.code, reason: event.reason});
    _debugLog.log("[ws] closed, code:", event.code, "reason:", event.reason);
    if (sessionActive && event.code !== 1000) {
      attemptReconnect();
    } else if (sessionActive) {
      setStatus("disconnected", getUserFriendlyError("ws_closed"));
      showDisconnectBanner();
      hideInput();
    } else {
      setStatus("idle", "Session complete");
      hideInput();
    }
  };

  ws.onerror = function(event) {
    EventLog.record("ws", "error");
    _debugLog.error("[ws] error:", event);
    setStatus("disconnected", "Connection error");
  };
}

function attemptReconnect() {
  if (reconnectAttempts >= maxReconnectAttempts) {
    _debugLog.log("[ws] max reconnect attempts reached");
    setStatus("disconnected", "Connection lost");
    resumeToken = null;
    try { sessionStorage.removeItem("resumeToken"); } catch (e) {}
    try { sessionStorage.removeItem("sessionType"); } catch (e) {}
    showPermanentReloadBanner();
    hideInput();
    return;
  }

  reconnectAttempts++;
  const delay = reconnectDelay * Math.pow(2, reconnectAttempts - 1);
  let hasToken = !!resumeToken;
  try { if (!hasToken) hasToken = !!sessionStorage.getItem("resumeToken"); } catch (e) {}
  _debugLog.log("[ws] reconnecting in " + delay + "ms (attempt " + reconnectAttempts + "/" + maxReconnectAttempts + ")" + (hasToken ? " [resume]" : " [new]"));
  setStatus("loading", "Reconnecting (" + reconnectAttempts + "/" + maxReconnectAttempts + ")");
  showDisconnectBanner();

  // Show countdown in disconnect banner
  if (_reconnectCountdownTimer) { clearInterval(_reconnectCountdownTimer); _reconnectCountdownTimer = null; }
  var _reconnectSecondsLeft = Math.ceil(delay / 1000);
  var countdownSpan = document.getElementById("reconnect-countdown");
  if (!countdownSpan) {
    var banner = document.getElementById("disconnect-banner");
    if (banner) {
      countdownSpan = document.createElement("span");
      countdownSpan.id = "reconnect-countdown";
      countdownSpan.className = "reconnect-countdown";
      banner.appendChild(countdownSpan);
    }
  }
  if (countdownSpan) {
    countdownSpan.textContent = " Retrying in " + _reconnectSecondsLeft + "s (" + reconnectAttempts + "/" + maxReconnectAttempts + ")";
  }
  _reconnectCountdownTimer = setInterval(function() {
    _reconnectSecondsLeft--;
    if (_reconnectSecondsLeft <= 0) {
      clearInterval(_reconnectCountdownTimer);
      _reconnectCountdownTimer = null;
      if (countdownSpan) countdownSpan.textContent = " Reconnecting\u2026";
    } else if (countdownSpan) {
      countdownSpan.textContent = " Retrying in " + _reconnectSecondsLeft + "s (" + reconnectAttempts + "/" + maxReconnectAttempts + ")";
    }
  }, 1000);

  setTimeout(function() {
    if (_reconnectCountdownTimer) { clearInterval(_reconnectCountdownTimer); _reconnectCountdownTimer = null; }
    if (sessionActive) {
      connectWebSocket(lastSessionType);
    }
  }, delay);
}

function handleMessage(data) {
  switch (data.type) {
    case "session_init":
      // Store resume token for reconnection
      resumeToken = data.resume_token;
      try { sessionStorage.setItem("resumeToken", data.resume_token); } catch (e) {}
      try { sessionStorage.setItem("sessionType", lastSessionType || "standard"); } catch (e) {}
      if (data.resumed) {
        reconnectAttempts = 0;
        setStatus("connected", "Session resumed");
        addMessage("Session resumed.", "msg msg-dim");
        hideDisconnectBanner();
      }
      _debugLog.log("[ws] session_init, token:", data.resume_token, "resumed:", !!data.resumed);
      break;
    case "show":
      displayShow(data);
      break;
    case "prompt":
      showInput(data.text, data.id);
      break;
    case "done":
      // Stop any currently playing audio when session ends
      if (currentAudio) {
        try { currentAudio.pause(); currentAudio.currentTime = 0; } catch (e) {}
      }
      if (data.summary && data.summary.early_exit) {
        EventLog.record("session", "early_exit", {drill_index: drillCount, drill_total: drillTotal});
      } else {
        EventLog.record("session", "complete", {drills: drillTotal});
      }
      sessionActive = false;
      document.body.classList.remove('in-session');
      if (typeof setSessionColorState === 'function') setSessionColorState('complete');
      // Reset to idle after 10s
      setTimeout(function() { if (typeof setSessionColorState === 'function') setSessionColorState('idle'); }, 10000);
      resumeToken = null;
      SessionCheckpoint.clear();
      try { sessionStorage.removeItem("resumeToken"); } catch (e) {}
      try { sessionStorage.removeItem("sessionType"); } catch (e) {}
      // Sound fires when the complete section enters (200ms into transition),
      // not immediately on message receive. showComplete handles this.
      if (typeof CapacitorBridge !== 'undefined') CapacitorBridge.hapticFeedback('success');
      showComplete(data.summary);
      break;
    case "reading_opener":
      showReadingOpener(data);
      break;
    // ── Reading block (in-session comprehension) ──
    case "reading_block":
      showReadingBlock(data);
      break;
    case "reading_question":
      showReadingQuestion(data);
      break;
    case "reading_feedback":
      showReadingBlockFeedback(data);
      break;
    case "reading_summary":
      showReadingBlockSummary(data);
      break;
    // ── Conversation block (in-session dialogue) ──
    case "conversation_block":
      showConversationBlock(data);
      break;
    case "conversation_feedback":
      showConversationFeedback(data);
      break;
    case "conversation_prompt":
      showConversationPrompt(data);
      break;
    case "conversation_summary":
      showConversationSummary(data);
      break;
    // ── Listening block (in-session comprehension) ──
    case "listening_block":
      showListeningBlock(data);
      break;
    case "listening_question":
      showListeningQuestion(data);
      break;
    case "listening_feedback":
      showListeningBlockFeedback(data);
      break;
    case "listening_transcript":
      showListeningTranscript(data);
      break;
    case "listening_summary":
      showListeningSummary(data);
      break;
    // ── Minimal pair drills ──
    case "minimal_pair":
      showMinimalPair(data);
      break;
    case "minimal_pair_feedback":
      showMinimalPairFeedback(data);
      break;
    // ── Tone sandhi drills ──
    case "sandhi_contrast":
      showSandhiContrast(data);
      break;
    case "sandhi_feedback":
      showSandhiFeedback(data);
      break;
    // ── Character decomposition ──
    case "character_decomposition":
      showCharacterDecomposition(data);
      break;
    // ── Metacognitive prompts ──
    case "confidence_prompt":
      showConfidencePrompt(data);
      break;
    case "error_reflection":
      showErrorReflection(data);
      break;
    case "session_assessment":
      showSessionAssessment(data);
      break;
    // ── SDT Motivation ──
    case "session_choice":
      showSessionChoice(data);
      break;
    case "competence_feedback":
      showCompetenceFeedback(data);
      break;
    case "prerequisite_notice":
      showPrerequisiteNotice(data);
      break;
    case "focus_insight":
      showFocusInsight(data);
      break;
    case "audio_play":
      playAudioFromServer(data.url);
      break;
    case "record_request":
      handleRecordRequest(data.max_duration || data.duration, data.id, data.allow_skip);
      break;
    case "progress":
      SessionCheckpoint.save(data.session_id, data.drill_index, data.drill_total,
                              data.correct, data.completed, data.session_type);
      break;
    case "audio_state":
      updateAudioState(data.state);
      break;
    case "drill_meta":
      _lastDrillMeta = data;
      break;
    case "error":
      EventLog.record("ws", "server_error", {msg: (data.message || "").substring(0, 100)});
      // Fatal session error — clean up and return to dashboard
      sessionActive = false;
      document.body.classList.remove('in-session');
      resumeToken = null;
      SessionCheckpoint.clear();
      try { sessionStorage.removeItem("resumeToken"); } catch (e) {}
      try { sessionStorage.removeItem("sessionType"); } catch (e) {}
      if (_sessionTimerInterval) { clearInterval(_sessionTimerInterval); _sessionTimerInterval = null; }
      // Close WebSocket so server releases the session lock immediately
      if (ws) { try { ws.close(1000); } catch (e) {} ws = null; }
      hideDisconnectBanner();
      hideInput();
      // Detect session limit / tier gate errors → show upgrade prompt instead of raw error
      var errMsg = (data.message || "").toLowerCase();
      if (errMsg.indexOf("session limit") !== -1 || errMsg.indexOf("upgrade") !== -1 || errMsg.indexOf("daily limit") !== -1) {
        transitionTo("session", "dashboard", function() { loadDashboardPanels(); });
        showUpgradePrompt("unlimited_sessions");
      } else {
        showSessionError(data.message || getUserFriendlyError("server"));
      }
      break;
  }
}

function getCurrentDrillGroup() {
  /* Find the current (non-past) drill group in drill-area.
   * Uses querySelectorAll + last element instead of :last-child,
   * because :last-child fails when standalone elements (user echoes,
   * progress indicators) are appended after the drill group. */
  var area = document.getElementById("drill-area");
  if (!area) return null;
  var groups = area.querySelectorAll(".drill-group:not(.past)");
  if (groups.length > 0) return groups[groups.length - 1];
  // Fallback: last group even if past (for late-arriving messages)
  var allGroups = area.querySelectorAll(".drill-group");
  if (allGroups.length > 0) {
    var last = allGroups[allGroups.length - 1];
    if (!last.classList.contains("past")) return last;
  }
  return null;
}

function showReadingOpener(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  _readingOpenerActive = true;
  _currentPassageId = data.passage_id || null;
  hideInput();  // Ensure input area is hidden — opener has its own Continue button

  var isPostDrills = data.position === "post_drills";
  var scaffold = data.scaffold || {};

  var html = '<div class="reading-opener' + (isPostDrills ? ' reading-opener-post' : '') + '">';
  html += '<div class="reading-opener-label">' + (isPostDrills ? 'Reading practice' : 'Today\'s passage') + '</div>';
  if (isPostDrills) {
    html += '<div class="reading-opener-intro">Nice work on the drills. Try reading this — words you haven\'t learned yet have hints.</div>';
  }
  if (data.title) html += '<div class="reading-opener-title">' + escapeHtml(data.title) + '</div>';
  html += '<div class="reading-opener-text">';
  var text = data.text_zh || "";
  for (var i = 0; i < text.length; i++) {
    var ch = text[i];
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) {
      var info = scaffold[ch];
      var isUnknown = info && !info.known;
      if (isUnknown && info.pinyin) {
        // Ruby annotation: pinyin above unknown characters
        html += '<ruby class="reading-word reading-word-unknown" data-char="' + escapeHtml(ch) + '"'
          + (info.english ? ' data-english="' + escapeHtml(info.english) + '"' : '')
          + '>' + escapeHtml(ch) + '<rp>(</rp><rt>' + escapeHtml(info.pinyin) + '</rt><rp>)</rp></ruby>';
      } else {
        html += '<span class="reading-word' + (info && info.known ? ' reading-word-known' : '') + '" data-char="' + escapeHtml(ch) + '">' + escapeHtml(ch) + '</span>';
      }
    } else {
      html += escapeHtml(ch);
    }
  }
  html += '</div>';
  html += '<div class="reading-opener-hint">Tap any character to look it up</div>';
  html += '<button class="btn btn-primary reading-opener-continue">' + (isPostDrills ? 'Finish session' : 'Continue to drills') + '</button>';
  html += '</div>';
  area.innerHTML = html;

  // Scroll to top of passage
  area.scrollIntoView({behavior: 'smooth', block: 'start'});

  // Attach lookup handlers
  area.querySelectorAll(".reading-word, ruby.reading-word-unknown").forEach(function(el) {
    el.addEventListener("click", function(e) {
      var ch = el.dataset.char;
      lookupWord(ch, e);
    });
  });

  // Continue button sends empty answer to unblock server
  area.querySelector(".reading-opener-continue").addEventListener("click", function() {
    _readingOpenerActive = false;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({type: "answer", value: "", id: ""}));
    }
    area.innerHTML = '';
  });
}

// ── Reading Block Handlers (cleanup loop: exposure → drills → re-read) ──

function showReadingBlock(data) {
  var mode = data.mode || "exposure";
  if (mode === "reread") {
    _showReadingReread(data);
  } else {
    _showReadingExposure(data);
  }
}

function _showReadingExposure(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  hideInput();
  var p = data.passage || {};
  var scaffold = data.scaffold || {};
  var text = p.content_hanzi || "";

  var html = '<div class="reading-block reading-block-exposure">';
  html += '<div class="reading-block-label">Read at your pace</div>';
  if (p.title) html += '<div class="reading-block-title">' + escapeHtml(p.title) + '</div>';

  // Render passage with per-character tap-to-gloss (same pattern as reading opener)
  html += '<div class="reading-block-text">';
  for (var i = 0; i < text.length; i++) {
    var ch = text[i];
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) {
      var info = scaffold[ch];
      var isUnknown = info && !info.known;
      if (isUnknown && info.pinyin) {
        html += '<ruby class="reading-word reading-word-unknown" data-char="' + escapeHtml(ch) + '"'
          + (info.english ? ' data-english="' + escapeHtml(info.english) + '"' : '')
          + '>' + escapeHtml(ch) + '<rp>(</rp><rt>' + escapeHtml(info.pinyin) + '</rt><rp>)</rp></ruby>';
      } else {
        html += '<span class="reading-word' + (info && info.known ? ' reading-word-known' : '') + '" data-char="' + escapeHtml(ch) + '">' + escapeHtml(ch) + '</span>';
      }
    } else {
      html += escapeHtml(ch);
    }
  }
  html += '</div>';

  html += '<div class="reading-block-hint">Tap any character to look it up</div>';
  html += '<button class="btn btn-primary reading-block-ready">Done reading</button>';
  html += '</div>';
  area.innerHTML = html;
  area.scrollIntoView({behavior: "smooth", block: "start"});

  // Attach tap-to-gloss + word_lookup notification
  area.querySelectorAll(".reading-word, ruby.reading-word-unknown").forEach(function(el) {
    el.addEventListener("click", function(e) {
      var ch = el.dataset.char;
      lookupWord(ch, e);
      // Notify server this word was looked up (for cleanup drill injection)
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: "word_lookup", hanzi: ch}));
      }
    });
  });

  // "Done reading" signals server to proceed
  area.querySelector(".reading-block-ready").addEventListener("click", function() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({type: "answer", value: "reading_done", id: ""}));
    }
  });
}

function _showReadingReread(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  hideInput();
  var p = data.passage || {};
  var drilledWords = data.drilled_words || [];
  var drilledSet = {};
  for (var d = 0; d < drilledWords.length; d++) {
    drilledSet[drilledWords[d]] = true;
  }
  var text = p.content_hanzi || "";

  var html = '<div class="reading-block reading-block-reread">';
  html += '<div class="reading-block-label">Read again — see what you learned</div>';
  if (p.title) html += '<div class="reading-block-title">' + escapeHtml(p.title) + '</div>';

  // Render passage with drilled words highlighted
  html += '<div class="reading-block-text">';
  for (var i = 0; i < text.length; i++) {
    var ch = text[i];
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) {
      var isDrilled = drilledSet[ch];
      html += '<span class="reading-word' + (isDrilled ? ' reading-word-drilled' : '') + '" data-char="' + escapeHtml(ch) + '">' + escapeHtml(ch) + '</span>';
    } else {
      html += escapeHtml(ch);
    }
  }
  html += '</div>';

  if (drilledWords.length > 0) {
    html += '<div class="reading-block-hint">Words you just drilled are highlighted</div>';
  }
  html += '<button class="btn btn-primary reading-block-ready">Continue</button>';
  html += '</div>';
  area.innerHTML = html;
  area.scrollIntoView({behavior: "smooth", block: "start"});

  // Tap-to-gloss still works on re-read (but no word_lookup events sent)
  area.querySelectorAll(".reading-word").forEach(function(el) {
    el.addEventListener("click", function(e) {
      var ch = el.dataset.char;
      lookupWord(ch, e);
    });
  });

  // "Continue" advances the session
  area.querySelector(".reading-block-ready").addEventListener("click", function() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({type: "answer", value: "", id: ""}));
    }
  });
}

function showReadingQuestion(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="reading-question">';
  html += '<div class="reading-question-label">Question ' + (data.index + 1) + ' of ' + (data.total || "?") + '</div>';
  html += '<div class="reading-question-text">' + escapeHtml(data.question) + '</div>';
  html += '<div class="reading-question-options">';
  var options = data.options || [];
  for (var i = 0; i < options.length; i++) {
    html += '<button class="btn reading-option" data-index="' + i + '">' + escapeHtml(options[i]) + '</button>';
  }
  html += '</div></div>';
  area.innerHTML = html;
  area.querySelectorAll(".reading-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: "answer", value: btn.dataset.index, id: ""}));
      }
      area.querySelectorAll(".reading-option").forEach(function(b) { b.disabled = true; });
      btn.classList.add("selected");
    });
  });
}

function showReadingBlockFeedback(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var existing = area.querySelector(".reading-question");
  if (existing) {
    var fb = document.createElement("div");
    fb.className = "reading-feedback " + (data.correct ? "correct" : "incorrect");
    fb.innerHTML = (data.correct ? "Correct!" : "Incorrect — " + escapeHtml(data.correct_answer || ""))
      + (data.explanation ? '<div class="reading-explanation">' + escapeHtml(data.explanation) + '</div>' : '');
    existing.appendChild(fb);
  }
  // Auto-advance after 2s
  setTimeout(function() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      // Server sends next question automatically
    }
  }, 2000);
}

function showReadingBlockSummary(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="reading-summary">';
  html += '<div class="reading-summary-label">Reading Complete</div>';
  if (data.passage_title) html += '<div class="reading-summary-title">' + escapeHtml(data.passage_title) + '</div>';

  // Show words looked up (cleanup loop) or question score (legacy)
  var parts = [];
  if (data.words_looked_up > 0) {
    parts.push(data.words_looked_up + ' word' + (data.words_looked_up === 1 ? '' : 's') + ' looked up');
  }
  if (data.total > 0) {
    parts.push((data.correct || 0) + '/' + data.total + ' questions correct');
  }
  if (data.reading_seconds > 0) {
    var mins = Math.floor(data.reading_seconds / 60);
    var secs = data.reading_seconds % 60;
    parts.push((mins > 0 ? mins + 'm ' : '') + secs + 's reading');
  }
  if (parts.length > 0) {
    html += '<div class="reading-summary-score">' + escapeHtml(parts.join(' · ')) + '</div>';
  }

  html += '</div>';
  area.innerHTML = html;
}

// ── Conversation Block Handlers (in-session dialogue) ──────────────

function showConversationBlock(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="conversation-block">';
  html += '<div class="conversation-block-label">Conversation Practice</div>';
  html += '<div class="conversation-scenario">' + escapeHtml(data.scenario_title || "") + '</div>';
  html += '<div class="conversation-situation">' + escapeHtml(data.situation || "") + '</div>';
  html += '<div class="conversation-messages" id="conv-messages">';
  html += '<div class="conv-msg conv-msg-tutor">';
  html += '<div class="conv-msg-zh">' + escapeHtml(data.prompt_zh || "") + '</div>';
  if (data.prompt_pinyin) html += '<div class="conv-msg-pinyin">' + escapeHtml(data.prompt_pinyin) + '</div>';
  if (data.prompt_en) html += '<div class="conv-msg-en">' + escapeHtml(data.prompt_en) + '</div>';
  html += '</div></div>';
  html += '<div class="conversation-input-area">';
  html += '<textarea id="conv-input" class="conv-input" rows="2" placeholder="Type your response in Chinese..."></textarea>';
  html += '<button class="btn btn-primary conv-send" id="conv-send">Send</button>';
  html += '</div></div>';
  area.innerHTML = html;
  area.scrollIntoView({behavior: "smooth", block: "start"});

  document.getElementById("conv-send").addEventListener("click", function() {
    var input = document.getElementById("conv-input");
    var text = (input ? input.value : "").trim();
    if (!text) return;
    // Show user message
    var msgs = document.getElementById("conv-messages");
    if (msgs) msgs.innerHTML += '<div class="conv-msg conv-msg-user">' + escapeHtml(text) + '</div>';
    if (input) input.value = "";
    // Send to server
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({type: "answer", value: text, id: ""}));
    }
  });

  // Allow Enter to submit (Shift+Enter for newline)
  var convInput = document.getElementById("conv-input");
  if (convInput) {
    convInput.addEventListener("keydown", function(e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        document.getElementById("conv-send").click();
      }
    });
  }
}

function showConversationFeedback(data) {
  var msgs = document.getElementById("conv-messages");
  if (!msgs) return;
  var html = '<div class="conv-feedback">';
  var score = data.score || 0;
  html += '<div class="conv-feedback-score">Score: ' + Math.round(score * 100) + '%</div>';
  if (data.feedback) html += '<div class="conv-feedback-text">' + escapeHtml(data.feedback) + '</div>';
  if (data.patterns_used && data.patterns_used.length) {
    html += '<div class="conv-patterns">Patterns used: ' + data.patterns_used.map(escapeHtml).join(", ") + '</div>';
  }
  if (data.suggestions && data.suggestions.length) {
    html += '<div class="conv-suggestions">Try: ' + data.suggestions.map(escapeHtml).join("; ") + '</div>';
  }
  html += '</div>';
  msgs.innerHTML += html;
  msgs.scrollTop = msgs.scrollHeight;
}

function showConversationPrompt(data) {
  var msgs = document.getElementById("conv-messages");
  if (!msgs) return;
  var html = '<div class="conv-msg conv-msg-tutor">';
  html += '<div class="conv-msg-zh">' + escapeHtml(data.prompt_zh || "") + '</div>';
  if (data.prompt_pinyin) html += '<div class="conv-msg-pinyin">' + escapeHtml(data.prompt_pinyin) + '</div>';
  if (data.prompt_en) html += '<div class="conv-msg-en">' + escapeHtml(data.prompt_en) + '</div>';
  html += '</div>';
  msgs.innerHTML += html;
  msgs.scrollTop = msgs.scrollHeight;
  // Re-enable input
  var input = document.getElementById("conv-input");
  if (input) { input.disabled = false; input.focus(); }
}

function showConversationSummary(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var pct = Math.round((data.avg_score || 0) * 100);
  var html = '<div class="conversation-summary">';
  html += '<div class="conversation-summary-label">Conversation Complete</div>';
  if (data.scenario_title) html += '<div class="conversation-summary-title">' + escapeHtml(data.scenario_title) + '</div>';
  html += '<div class="conversation-summary-score">Average: ' + pct + '% (' + (data.turns_completed || 0) + ' turns)</div>';
  html += '</div>';
  area.innerHTML = html;
}

// ── Listening Block Handlers (in-session audio comprehension) ───────

function showListeningBlock(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  hideInput();
  var html = '<div class="listening-block">';
  html += '<div class="listening-block-label">Listening Comprehension</div>';
  html += '<div class="listening-block-hint">Listen to the passage, then answer comprehension questions.<br>You may replay and adjust speed. The transcript is hidden until after questions.</div>';
  html += '<div class="listening-audio-controls">';
  html += '<audio id="listening-audio" preload="auto"><source src="' + escapeHtml(data.audio_url || "") + '" type="audio/mpeg"></audio>';
  html += '<div class="listening-btn-row">';
  html += '<button class="btn listening-play" id="listening-play-btn">Play</button>';
  html += '<button class="btn listening-replay" id="listening-replay-btn">Replay</button>';
  html += '</div>';
  html += '<div class="listening-speed-row">';
  html += '<label>Speed: </label>';
  html += '<button class="btn btn-sm listening-speed-btn" data-speed="0.6">0.6x</button>';
  html += '<button class="btn btn-sm listening-speed-btn" data-speed="0.8">0.8x</button>';
  html += '<button class="btn btn-sm listening-speed-btn selected" data-speed="1.0">1.0x</button>';
  html += '<button class="btn btn-sm listening-speed-btn" data-speed="1.2">1.2x</button>';
  html += '</div>';
  html += '</div>';
  html += '<button class="btn btn-primary listening-block-ready" id="listening-ready-btn">Ready for questions (' + (data.question_count || 0) + ')</button>';
  html += '</div>';
  area.innerHTML = html;
  area.scrollIntoView({behavior: "smooth", block: "start"});

  var audioEl = document.getElementById("listening-audio");
  var playBtn = document.getElementById("listening-play-btn");
  var replayBtn = document.getElementById("listening-replay-btn");

  playBtn.addEventListener("click", function() {
    if (audioEl) {
      if (audioEl.paused) {
        audioEl.play();
        playBtn.textContent = "Pause";
      } else {
        audioEl.pause();
        playBtn.textContent = "Play";
      }
    }
  });

  replayBtn.addEventListener("click", function() {
    if (audioEl) {
      audioEl.currentTime = 0;
      audioEl.play();
      playBtn.textContent = "Pause";
    }
  });

  if (audioEl) {
    audioEl.addEventListener("ended", function() {
      playBtn.textContent = "Play";
    });
  }

  area.querySelectorAll(".listening-speed-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var speed = parseFloat(btn.dataset.speed) || 1.0;
      if (audioEl) audioEl.playbackRate = speed;
      area.querySelectorAll(".listening-speed-btn").forEach(function(b) { b.classList.remove("selected"); });
      btn.classList.add("selected");
    });
  });

  document.getElementById("listening-ready-btn").addEventListener("click", function() {
    if (audioEl) { try { audioEl.pause(); } catch (e) {} }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({type: "answer", value: "listening_done", id: ""}));
    }
  });
}

function showListeningQuestion(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="listening-question">';
  html += '<div class="listening-question-label">Question ' + (data.index + 1) + ' of ' + (data.total || "?") + '</div>';
  html += '<div class="listening-question-text">' + escapeHtml(data.question) + '</div>';
  html += '<div class="listening-question-options">';
  var options = data.options || [];
  for (var i = 0; i < options.length; i++) {
    html += '<button class="btn listening-option" data-index="' + i + '">' + escapeHtml(options[i]) + '</button>';
  }
  html += '</div></div>';
  area.innerHTML = html;
  area.querySelectorAll(".listening-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: "answer", value: btn.dataset.index, id: ""}));
      }
      area.querySelectorAll(".listening-option").forEach(function(b) { b.disabled = true; });
      btn.classList.add("selected");
    });
  });
}

function showListeningBlockFeedback(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var existing = area.querySelector(".listening-question");
  if (existing) {
    var fb = document.createElement("div");
    fb.className = "listening-feedback " + (data.correct ? "correct" : "incorrect");
    fb.innerHTML = (data.correct ? "Correct!" : "Incorrect \u2014 " + escapeHtml(data.correct_answer || ""))
      + (data.explanation ? '<div class="listening-explanation">' + escapeHtml(data.explanation) + '</div>' : '');
    existing.appendChild(fb);
  }
}

function showListeningTranscript(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="listening-transcript">';
  html += '<div class="listening-transcript-label">Transcript</div>';
  html += '<div class="listening-transcript-zh">';
  // Render each character as a tappable span for gloss (reuse reading word pattern)
  var text = data.transcript_zh || "";
  for (var i = 0; i < text.length; i++) {
    var ch = text[i];
    // CJK character range check
    var code = ch.charCodeAt(0);
    if ((code >= 0x4e00 && code <= 0x9fff) || (code >= 0x3400 && code <= 0x4dbf)) {
      html += '<span class="listening-word" data-char="' + escapeHtml(ch) + '">' + escapeHtml(ch) + '</span>';
    } else {
      html += escapeHtml(ch);
    }
  }
  html += '</div>';
  if (data.transcript_pinyin) {
    html += '<div class="listening-transcript-pinyin" style="display:none;">' + escapeHtml(data.transcript_pinyin) + '</div>';
    html += '<button class="btn btn-sm listening-toggle-pinyin">Show pinyin</button>';
  }
  html += '</div>';
  area.innerHTML = html;
  area.scrollIntoView({behavior: "smooth", block: "start"});

  // Toggle pinyin
  var toggleBtn = area.querySelector(".listening-toggle-pinyin");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", function() {
      var py = area.querySelector(".listening-transcript-pinyin");
      if (py) { py.style.display = py.style.display === "none" ? "block" : "none"; }
      toggleBtn.textContent = py && py.style.display === "none" ? "Show pinyin" : "Hide pinyin";
    });
  }

  // Tap-to-gloss: look up character via existing API
  area.querySelectorAll(".listening-word").forEach(function(span) {
    span.addEventListener("click", function() {
      var ch = span.dataset.char;
      if (!ch) return;
      // Toggle existing popup
      var existingPopup = span.querySelector(".word-popup");
      if (existingPopup) {
        existingPopup.remove();
        return;
      }
      // Close other popups
      area.querySelectorAll(".word-popup").forEach(function(p) { p.remove(); });
      // Fetch definition
      apiFetch("/api/lookup?q=" + encodeURIComponent(ch))
        .then(function(resp) { return resp.json(); })
        .then(function(info) {
          var popup = document.createElement("div");
          popup.className = "word-popup";
          popup.innerHTML = '<b>' + escapeHtml(info.pinyin || "") + '</b><br>' + escapeHtml(info.english || info.definition || "");
          span.appendChild(popup);
          // Auto-dismiss after 4s
          setTimeout(function() { if (popup.parentNode) popup.remove(); }, 4000);
        })
        .catch(function() {});
    });
  });
}

function showListeningSummary(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var pct = Math.round((data.score || 0) * 100);
  var html = '<div class="listening-summary">';
  html += '<div class="listening-summary-label">Listening Complete</div>';
  html += '<div class="listening-summary-score">' + (data.correct || 0) + '/' + (data.total || 0) + ' (' + pct + '%)</div>';
  html += '</div>';
  area.innerHTML = html;
}

// ── Minimal Pair Handlers (Flege 1995) ─────────────────────────────

function showMinimalPair(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="minimal-pair">';
  html += '<div class="mp-label">Which one is correct?</div>';
  html += '<div class="mp-question">' + escapeHtml(data.question || "") + '</div>';
  html += '<div class="mp-options">';
  html += '<button class="btn mp-option" data-choice="a"><div class="mp-hanzi">' + escapeHtml((data.item_a || {}).hanzi || "") + '</div><div class="mp-pinyin">' + escapeHtml((data.item_a || {}).pinyin || "") + '</div></button>';
  html += '<button class="btn mp-option" data-choice="b"><div class="mp-hanzi">' + escapeHtml((data.item_b || {}).hanzi || "") + '</div><div class="mp-pinyin">' + escapeHtml((data.item_b || {}).pinyin || "") + '</div></button>';
  html += '</div>';
  var typeLabel = (data.interference_type === "near_homophone") ? "These sound similar" : (data.interference_type === "visual_similarity") ? "These look similar" : "Easy to confuse";
  html += '<div class="mp-hint">' + typeLabel + '</div>';
  html += '</div>';
  area.innerHTML = html;
  area.querySelectorAll(".mp-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: "answer", value: btn.dataset.choice, id: ""}));
      area.querySelectorAll(".mp-option").forEach(function(b) { b.disabled = true; });
      btn.classList.add("selected");
    });
  });
}

function showMinimalPairFeedback(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var mp = area.querySelector(".minimal-pair");
  if (mp) {
    var fb = document.createElement("div");
    fb.className = "mp-feedback " + (data.correct ? "correct" : "incorrect");
    fb.textContent = data.correct ? "Correct!" : "Not quite — look at the difference.";
    mp.appendChild(fb);
  }
}

// ── Tone Sandhi Handlers (Chen 2000) ───────────────────────────────

function showSandhiContrast(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="sandhi-drill">';
  html += '<div class="sandhi-label">Tone Sandhi</div>';
  html += '<div class="sandhi-hanzi">' + escapeHtml(data.hanzi || "") + '</div>';
  html += '<div class="sandhi-question">' + escapeHtml(data.question || "") + '</div>';
  html += '<div class="sandhi-options">';
  var opts = [{v: "correct", t: data.correct_answer || ""}, {v: "wrong", t: data.distractor || ""}];
  if (Math.random() > 0.5) opts.reverse();
  for (var i = 0; i < opts.length; i++) {
    html += '<button class="btn sandhi-option" data-value="' + opts[i].v + '">' + escapeHtml(opts[i].t) + '</button>';
  }
  html += '</div></div>';
  area.innerHTML = html;
  area.querySelectorAll(".sandhi-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: "answer", value: btn.dataset.value, id: ""}));
      area.querySelectorAll(".sandhi-option").forEach(function(b) { b.disabled = true; });
      btn.classList.add("selected");
    });
  });
}

function showSandhiFeedback(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var drill = area.querySelector(".sandhi-drill");
  if (drill) {
    var fb = document.createElement("div");
    fb.className = "sandhi-feedback " + (data.correct ? "correct" : "incorrect");
    fb.innerHTML = (data.correct ? "Correct!" : "Not quite.") + '<div class="sandhi-explanation">' + escapeHtml(data.explanation || "") + '</div>';
    drill.appendChild(fb);
  }
}

// ── Character Decomposition Handler (Shen 2005) ────────────────────

function showCharacterDecomposition(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var overlay = document.createElement("div");
  overlay.className = "char-decomposition";
  var html = '<div class="char-decomp-main">' + escapeHtml(data.character || "") + '</div>';
  if (data.radical) html += '<div class="char-decomp-radical"><span class="char-decomp-radical-char">' + escapeHtml(data.radical) + '</span> <span class="char-decomp-radical-meaning">' + escapeHtml(data.radical_meaning || "") + '</span></div>';
  if (data.phonetic_hint) html += '<div class="char-decomp-phonetic">Sound hint: ' + escapeHtml(data.phonetic_hint) + '</div>';
  if (data.family_examples && data.family_examples.length) html += '<div class="char-decomp-family">Family: ' + data.family_examples.map(escapeHtml).join(" ") + '</div>';
  html += '<div class="char-decomp-dismiss">Tap to continue</div>';
  overlay.innerHTML = html;
  area.prepend(overlay);
  var timer = setTimeout(function() { overlay.remove(); }, 4000);
  overlay.addEventListener("click", function() { clearTimeout(timer); overlay.remove(); });
}

// ── Metacognitive Handlers (Dunlosky 2013) ─────────────────────────

function showConfidencePrompt(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="meta-prompt"><div class="meta-label">Before you answer...</div><div class="meta-question">How confident are you?</div><div class="meta-options">';
  html += '<button class="btn meta-option" data-value="high">Confident</button>';
  html += '<button class="btn meta-option" data-value="medium">Somewhat</button>';
  html += '<button class="btn meta-option" data-value="low">Guessing</button>';
  html += '</div></div>';
  area.innerHTML = html;
  area.querySelectorAll(".meta-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: "answer", value: btn.dataset.value, id: "confidence"}));
    });
  });
}

function showErrorReflection(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="meta-prompt"><div class="meta-label">What tripped you up?</div><div class="meta-options meta-options-col">';
  html += '<button class="btn meta-option" data-value="similar_chars">Similar-looking characters</button>';
  html += '<button class="btn meta-option" data-value="tone_confusion">Tone confusion</button>';
  html += '<button class="btn meta-option" data-value="forgot_meaning">Forgot the meaning</button>';
  html += '<button class="btn meta-option" data-value="guessed">Just guessed</button>';
  html += '</div></div>';
  area.innerHTML = html;
  area.querySelectorAll(".meta-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: "answer", value: btn.dataset.value, id: "reflection"}));
    });
  });
}

function showSessionAssessment(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var html = '<div class="meta-prompt session-assessment"><div class="meta-label">How was this session?</div><div class="meta-options">';
  html += '<button class="btn meta-option" data-value="too_easy">Too easy</button>';
  html += '<button class="btn meta-option" data-value="about_right">About right</button>';
  html += '<button class="btn meta-option" data-value="too_hard">Too hard</button>';
  html += '</div></div>';
  area.innerHTML = html;
  area.querySelectorAll(".meta-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: "answer", value: btn.dataset.value, id: "assessment"}));
    });
  });
}

// ── SDT Motivation Handlers (Ryan & Deci 2000) ────────────────────

function showSessionChoice(data) {
  var area = document.getElementById("drill-area");
  if (!area) return;
  var opts = data.options || [];
  var html = '<div class="session-choice"><div class="session-choice-label">What would you like to focus on?</div><div class="session-choice-options">';
  for (var i = 0; i < opts.length; i++) {
    html += '<button class="btn session-choice-option" data-value="' + (opts[i].value || "") + '">' + escapeHtml(opts[i].label || "") + '</button>';
  }
  html += '</div></div>';
  area.innerHTML = html;
  area.querySelectorAll(".session-choice-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: "answer", value: btn.dataset.value, id: "session_choice"}));
    });
  });
}

function showCompetenceFeedback(data) {
  var toast = document.createElement("div");
  toast.className = "competence-toast";
  toast.textContent = data.message || "";
  document.body.appendChild(toast);
  setTimeout(function() { toast.classList.add("visible"); }, 50);
  setTimeout(function() { toast.classList.remove("visible"); setTimeout(function() { toast.remove(); }, 300); }, 4000);
}

function showFocusInsight(data) {
  var area = document.getElementById("drill-area");
  if (!area || !data.insights || data.insights.length === 0) return;
  var card = document.createElement("div");
  card.className = "focus-insight";
  var html = '<div class="focus-insight-header">Today\'s focus</div>';
  html += '<ul class="focus-insight-list">';
  for (var i = 0; i < data.insights.length; i++) {
    html += '<li>' + escapeHtml(data.insights[i]) + '</li>';
  }
  html += '</ul>';
  if (data.micro_plan) {
    html += '<div class="focus-insight-plan">' + escapeHtml(data.micro_plan) + '</div>';
  }
  card.innerHTML = html;
  area.appendChild(card);
  // Auto-dismiss after 8 seconds or when first drill arrives
  setTimeout(function() {
    if (card.parentNode) {
      card.style.opacity = "0";
      setTimeout(function() { if (card.parentNode) card.parentNode.removeChild(card); }, 400);
    }
  }, 8000);
}

function showPrerequisiteNotice(data) {
  if (!data.message) return;
  var toast = document.createElement("div");
  toast.className = "prereq-notice";
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");
  toast.textContent = data.message;
  document.body.appendChild(toast);
  setTimeout(function() { toast.classList.add("prereq-visible"); }, 50);
  setTimeout(function() {
    toast.classList.remove("prereq-visible");
    toast.classList.add("prereq-exit");
    setTimeout(function() { if (toast.parentNode) toast.remove(); }, 400);
  }, 4000);
}

function displayShow(data) {
  // Dismiss focus insight card when first drill content arrives
  var insightCard = document.querySelector(".focus-insight");
  if (insightCard && insightCard.parentNode) {
    insightCard.parentNode.removeChild(insightCard);
  }
  // Stop any currently playing audio when new content arrives
  if (currentAudio) {
    try { currentAudio.pause(); currentAudio.currentTime = 0; } catch (e) {}
  }
  // Clean up recording panel if it's in analyzing state (results arrived)
  if (document.getElementById("recording-panel") && _recState === "analyzing") {
    _recCleanupPanel();
  }
  const html = data.html || escapeHtml(data.text);
  const text = data.text || "";

  // Detect hanzi display (large centered characters with Rich markup)
  // Matches both prominent (bold bright_magenta) and compact (bold magenta) styles
  if (text.match(/^\n?\[bold (?:bright_)?magenta\]\s+.+\[\/bold (?:bright_)?magenta\]\n?$/)) {
    const hanzi = text.replace(/\[.*?\]/g, "").trim();
    addMessage(hanzi, "msg-hanzi");
    return;
  }

  // Detect progress indicator like [3/12] or [3/12 <1min]
  const progressMatch = text.match(/\[(\d+)\/(\d+)(?:\s[^\]]*)?\]/);
  if (progressMatch) {
    drillCount = parseInt(progressMatch[1]);
    drillTotal = parseInt(progressMatch[2]);
    updateProgress(drillCount, drillTotal);
  }

  // Detect correct/wrong markers
  let cls = "msg";
  if (text.trim().startsWith("\u2713") || text.includes("\u2713")) cls = "msg msg-correct";
  else if (text.trim().startsWith("\u2717") || text.includes("\u2717")) cls = "msg msg-wrong";
  else if (text.includes("[dim italic]")) cls = "msg msg-dim";

  // Detect drill labels — all drill types from DRILL_REGISTRY
  const labels = ["Reading", "Recognition", "Typing", "Tone", "Listening", "Listening (detail)",
                  "Tone ID", "Dictation", "Intuition", "Pinyin recall", "Pinyin reading",
                  "Hanzi recall", "Dialogue", "Register", "Pragmatic", "Slang", "Speaking",
                  "Transfer", "Measure word", "Word order", "Sentence build", "Particle",
                  "Homophone", "Translation", "Confusable", "Cloze", "Synonym",
                  "Passage", "Sentence dictation", "Minimal pair"];
  const trimmed = text.trim().replace(/\[.*?\]/g, "").trim();
  // Label must be the label itself + optional suffix like (new), ★, ↻, [supplementary], (retry)
  // Exclude lines like "Dialogue score: 100%" by rejecting if a colon follows the label word
  var _isLabel = labels.some(l => trimmed.startsWith(l)) && trimmed.length < 50
                 && !/score\s*:/i.test(trimmed);
  if (_isLabel) {
    cls = "msg msg-label";
    // #1 — Update persistent drill-type label in session header
    var dtLabel = document.getElementById("drill-type-label");
    if (dtLabel) dtLabel.textContent = trimmed;
  }

  // Detect dialogue/score summary (e.g. "✓ Dialogue score: 85%")
  // Add score-summary class alongside any existing correct/wrong class
  if (/score:\s*\d+%/i.test(trimmed)) {
    cls += " msg-score-summary";
  }

  // Detect mastery stage indicators (e.g. "seen (1 streak)", "stable", "durable")
  var _stageLabels = ["seen", "passed once", "stabilizing", "stable", "durable", "needs review"];
  if (_stageLabels.some(function(s) { return trimmed === s || trimmed.match(new RegExp("^" + s + " \\(\\d+ streak\\)$")); })) {
    cls = "msg msg-mastery-stage";
  }

  // Detect modality break ("· · ·")
  if (/^[·\s·]+$/.test(trimmed) && trimmed.indexOf("·") !== -1) {
    cls = "msg msg-modality-break";
  }

  // Don't add empty messages
  if (text.trim() === "" && data.end === "\n") return;

  const div = document.createElement("div");
  div.className = cls;
  div.innerHTML = html;

  // Screen reader: announce correct/wrong feedback immediately
  if (cls.indexOf("msg-correct") !== -1 || cls.indexOf("msg-wrong") !== -1) {
    div.setAttribute("role", "alert");
  }

  var area = document.getElementById("drill-area");

  // Drill grouping: when a new label appears, close previous group and start new one
  if (cls.indexOf("msg-label") !== -1) {
    // Mark all previous drill groups as past
    var prevGroups = area.querySelectorAll(".drill-group:not(.past)");
    for (var g = 0; g < prevGroups.length; g++) {
      prevGroups[g].classList.add("past");
    }
    // Clear stale audio from prior drill — prevents replay button from playing old audio
    if (currentAudio) {
      try { currentAudio.pause(); currentAudio.currentTime = 0; } catch (e) {}
      currentAudio = null;
    }
    // Create new drill group
    var group = document.createElement("div");
    group.className = "drill-group";
    // Announce drill label to screen readers
    div.setAttribute("role", "status");
    group.appendChild(div);
    area.appendChild(group);
  } else {
    // Append to current drill group if one exists
    var currentGroup = getCurrentDrillGroup();
    if (currentGroup) {
      currentGroup.appendChild(div);
    } else {
      area.appendChild(div);
    }
  }

  // Feedback sounds fire on message render — coupled to the visual moment
  if (cls.indexOf("msg-correct") !== -1) {
    AeluSound.correct();
    if (typeof CapacitorBridge !== 'undefined') CapacitorBridge.hapticFeedback('correct');
    _hapticFeedback('correct');
    // Ink bloom + settle visual feedback
    if (window.AeluCelebrations && el) {
      AeluCelebrations.inkBloom(el);
      AeluCelebrations.inkSettle(el);
    }
  } else if (cls.indexOf("msg-wrong") !== -1) {
    AeluSound.wrong();
    if (typeof CapacitorBridge !== 'undefined') CapacitorBridge.hapticFeedback('incorrect');
    _hapticFeedback('incorrect');
    // Ink scatter visual feedback
    if (window.AeluCelebrations && el) {
      AeluCelebrations.inkScatter(el);
    }
    // Inject "I was right" override button
    if (_lastDrillMeta && !_lastDrillMeta.correct) {
      var overrideBtn = document.createElement("button");
      overrideBtn.className = "btn-override";
      overrideBtn.textContent = "I was right";
      overrideBtn.setAttribute("aria-label", "Override: mark this answer as correct");
      var meta = _lastDrillMeta;
      overrideBtn.addEventListener("click", function() {
        overrideBtn.disabled = true;
        overrideBtn.textContent = "Updating\u2026";
        fetch("/api/mark-correct", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({content_item_id: meta.content_item_id, modality: meta.modality})
        }).then(function(r) { return r.json(); }).then(function(resp) {
          if (resp.status === "ok") {
            overrideBtn.textContent = "Corrected";
            overrideBtn.classList.add("btn-override-done");
          } else {
            overrideBtn.textContent = "Couldn\u2019t save";
          }
        }).catch(function() {
          overrideBtn.textContent = "Try again";
          overrideBtn.disabled = false;
        });
      });
      div.appendChild(overrideBtn);
    }
    // Inject error_type elaboration tag below feedback
    if (_lastDrillMeta && _lastDrillMeta.error_type) {
      var _errorElabMap = {
        "tone": "Tone \u2014 the pitch shape was off here",
        "tone_confusion": "Tone mix-up \u2014 listen for the pitch pattern.",
        "segment": "Syllable \u2014 close, but one sound shifted",
        "segmentation": "Word boundary issue \u2014 2-character pairs are common.",
        "vocab": "Meaning \u2014 this word looks similar to the right one",
        "wrong_meaning": "Different meaning \u2014 try a vivid mental image.",
        "ime_confusable": "Similar characters \u2014 easy to confuse these two",
        "similar_chars": "Similar-looking characters \u2014 focus on the radical.",
        "grammar": "Word order \u2014 your meaning came through, the structure needs adjusting",
        "register_mismatch": "Register \u2014 right word, different formality level",
        "particle_misuse": "Particle \u2014 tricky one, these are subtle",
        "measure_word": "Measure word \u2014 specific measure word needed for this noun.",
        "pinyin_error": "Pinyin spelling \u2014 check vowels and initials."
      };
      var elaboration = _errorElabMap[_lastDrillMeta.error_type];
      if (elaboration) {
        var elabDiv = document.createElement("div");
        elabDiv.className = "error-elaboration";
        elabDiv.textContent = elaboration;
        div.appendChild(elabDiv);
      }
    }
  }

  // "Why this item?" provenance tag — only on wrong answers to reduce clutter
  if (_lastDrillMeta && _lastDrillMeta.requirement_ref &&
      cls.indexOf("msg-wrong") !== -1) {
    var ref = _lastDrillMeta.requirement_ref;
    var refDiv = document.createElement("div");
    refDiv.className = "requirement-ref";
    refDiv.textContent = "Why this item: " + ref.source + " \u2014 " +
        ref.type + ": " + ref.name + " (HSK " + ref.hsk_level + ")";
    div.appendChild(refDiv);
  }

  // Sticky review card for wrong answers — stays at top until next prompt
  if (cls.indexOf("msg-wrong") !== -1) {
    dismissReviewCard();
    var card = document.createElement("div");
    card.className = "review-card";
    card.id = "review-card";
    card.innerHTML = html;
    var dismissBtn = document.createElement("button");
    dismissBtn.className = "review-card-dismiss";
    dismissBtn.textContent = "\u00d7";
    dismissBtn.setAttribute("aria-label", "Dismiss review");
    dismissBtn.addEventListener("click", function() { dismissReviewCard(); });
    card.appendChild(dismissBtn);
    area.insertBefore(card, area.firstChild);
  }

  // Smart scroll: scroll to feedback messages specifically, otherwise to bottom.
  // Respect prefers-reduced-motion for scrollIntoView (CSS kill-switch doesn't cover JS).
  var scrollBehavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  if (cls.indexOf("msg-correct") !== -1 || cls.indexOf("msg-wrong") !== -1) {
    div.scrollIntoView({ behavior: scrollBehavior, block: "center" });
  } else {
    area.scrollTop = area.scrollHeight;
  }
}

function dismissReviewCard() {
  var existing = document.getElementById("review-card");
  if (existing) {
    existing.classList.add("review-card-exit");
    setTimeout(function() { if (existing.parentNode) existing.remove(); }, 300);
  }
}

function addMessage(text, cls) {
  var div = document.createElement("div");
  div.className = cls || "msg";
  div.textContent = text;
  var area = document.getElementById("drill-area");
  // Append into current drill group if one exists (same logic as displayShow)
  var currentGroup = getCurrentDrillGroup();
  if (currentGroup) {
    currentGroup.appendChild(div);
  } else {
    area.appendChild(div);
  }
  area.scrollTop = area.scrollHeight;
}

function showInput(prompt, id) {
  // Reading opener has its own Continue button — suppress the empty prompt
  if (_readingOpenerActive) {
    currentPromptId = id;
    return;
  }

  // ── Drill micro-timing: mark when this drill was shown ──
  var now = Date.now();
  _drillShownAt = now;

  // Clear drill transition loader (next drill has arrived)
  if (_drillTransitionTimer) { clearTimeout(_drillTransitionTimer); _drillTransitionTimer = null; }
  var loaders = document.querySelectorAll(".drill-transition-loader");
  for (var li = 0; li < loaders.length; li++) { loaders[li].parentNode.removeChild(loaders[li]); }

  // Timer is started in updateProgress() when first drill progress [X/Y] arrives

  // First-drill latency: time from WS open to first drill render
  if (_wsOpenedAt && !_firstDrillLogged) {
    _firstDrillLogged = true;
    var firstDrillMs = now - _wsOpenedAt;
    EventLog.queueClientEvent("drill_timing", "first_drill_latency", {ms: firstDrillMs});
  }

  // Stop any currently playing audio when a new prompt arrives
  if (currentAudio) {
    try { currentAudio.pause(); currentAudio.currentTime = 0; } catch (e) {}
  }
  // Dismiss any active review card when the next prompt appears
  dismissReviewCard();
  // Clean up recording panel if results arrived
  if (document.getElementById("recording-panel") && _recState === "analyzing") {
    _recCleanupPanel();
  }
  currentPromptId = id;
  var inputArea = document.getElementById("input-area");
  var promptText = document.getElementById("prompt-text");
  var input = document.getElementById("answer-input");
  var inputRow = inputArea.querySelector(".input-row");

  // Cancel any pending hideInput timer — prevents the race condition where
  // hideInput's setTimeout fires AFTER showInput makes the input visible again
  if (_hideInputTimer) {
    clearTimeout(_hideInputTimer);
    _hideInputTimer = null;
  }

  // Clear any exit animation left over from hideInput
  inputArea.classList.remove("input-exit");
  inputArea.classList.remove("hidden");

  // Clean up any previous option buttons
  var oldOpts = document.getElementById("option-buttons");
  if (oldOpts) oldOpts.remove();

  // Detect numbered MC options in recent messages
  var options = detectNumberedOptions();
  var actions = detectActionPrompt(prompt);
  var audioNearby = hasRecentAudio();
  _debugLog.log("[input] prompt:", prompt, "options:", options.length, "actions:", !!actions, "audio:", audioNearby);

  if (options.length >= 2) {
    // MC drill — show clickable option buttons instead of text input
    promptText.textContent = "";
    inputRow.classList.add("hidden");

    var optDiv = document.createElement("div");
    optDiv.id = "option-buttons";
    optDiv.className = "option-buttons";
    optDiv.setAttribute("role", "radiogroup");
    optDiv.setAttribute("aria-label", "Answer options");

    for (var i = 0; i < options.length; i++) {
      var btn = document.createElement("button");
      btn.className = "btn-option";
      btn.setAttribute("role", "radio");
      btn.setAttribute("aria-checked", "false");
      btn.setAttribute("tabindex", i === 0 ? "0" : "-1");
      btn.textContent = options[i].text;
      // Keyboard hint pill (1-9)
      if (i < 9) {
        var hint = document.createElement("span");
        hint.className = "key-hint";
        hint.setAttribute("aria-hidden", "true");
        hint.textContent = String(i + 1);
        btn.appendChild(hint);
      }
      btn.style.animationDelay = (i * OPTION_STAGGER) + "s";
      btn.addEventListener("click", (function(val, txt, btnRef) {
        return function() {
          // Brief selected-state highlight before answer sends
          btnRef.classList.add("btn-option-selected");
          btnRef.setAttribute("aria-checked", "true");
          var siblings = btnRef.parentNode.querySelectorAll(".btn-option");
          for (var s = 0; s < siblings.length; s++) {
            if (siblings[s] !== btnRef) {
              siblings[s].classList.add("btn-option-unselected");
              siblings[s].setAttribute("aria-checked", "false");
            }
          }
          quickAnswer(val, txt);
        };
      })(options[i].value, options[i].text, btn));
      optDiv.appendChild(btn);
    }

    // Add replay button for listening drills
    if (audioNearby) {
      var rBtn = document.createElement("button");
      rBtn.className = "btn-option btn-option-replay";
      rBtn.textContent = "Replay audio";
      rBtn.addEventListener("click", function() { quickAnswer("R"); });
      optDiv.appendChild(rBtn);
    }

    // Skip button — lets user skip drill without guessing
    var skipWrap = document.createElement("div");
    skipWrap.className = "drill-skip-wrap";
    var skipBtn = document.createElement("button");
    skipBtn.className = "btn btn-link drill-skip";
    skipBtn.textContent = "Skip";
    skipBtn.addEventListener("click", function() { skipDrill(); });
    skipWrap.appendChild(skipBtn);
    optDiv.appendChild(skipWrap);

    // Arrow key navigation for MC options (roving tabindex per ARIA radiogroup)
    optDiv.addEventListener("keydown", function(e) {
      var btns = optDiv.querySelectorAll(".btn-option");
      var idx = Array.prototype.indexOf.call(btns, document.activeElement);
      var target = -1;
      if (e.key === "ArrowDown" || e.key === "ArrowRight") {
        e.preventDefault();
        target = (idx + 1) % btns.length;
      } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
        e.preventDefault();
        target = (idx - 1 + btns.length) % btns.length;
      }
      if (target >= 0) {
        for (var t = 0; t < btns.length; t++) btns[t].setAttribute("tabindex", "-1");
        btns[target].setAttribute("tabindex", "0");
        btns[target].focus();
      }
    });

    inputArea.insertBefore(optDiv, inputArea.querySelector(".shortcuts"));
    inputArea.classList.remove("hidden");

    // Force synchronous layout reflow after DOM insertion.
    // WebKit (Safari/WKWebView) can leave hit-test regions stale after
    // inserting animated elements — reading offsetHeight forces the browser
    // to recalculate layout so buttons are immediately clickable.
    void optDiv.offsetHeight;

    // #21 — Hide hint/unsure shortcuts during MC
    _currentMcMode = true;
    var shortcuts = inputArea.querySelector(".shortcuts");
    if (shortcuts) { shortcuts.classList.add("mc-mode"); shortcuts.classList.remove("action-mode"); }
    // Focus first option for keyboard accessibility
    var firstBtn = optDiv.querySelector(".btn-option");
    if (firstBtn) setTimeout(function() { firstBtn.focus(); }, FOCUS_DELAY);
  } else if (actions) {
    // Action prompt (Press Enter to begin, etc.) — show action buttons
    _currentMcMode = false;
    var shortcuts2 = inputArea.querySelector(".shortcuts");
    // Hide all shortcuts during action prompts (Begin/Mini/Quit, Continue, etc.)
    if (shortcuts2) shortcuts2.classList.add("action-mode");
    promptText.textContent = "";
    inputRow.classList.add("hidden");

    var actDiv = document.createElement("div");
    actDiv.id = "option-buttons";
    actDiv.className = "option-buttons option-buttons-row";

    for (var j = 0; j < actions.length; j++) {
      var aBtn = document.createElement("button");
      aBtn.className = actions[j].primary ? "btn-option btn-option-primary" : "btn-option btn-option-action";
      aBtn.textContent = actions[j].label;
      aBtn.addEventListener("click", (function(val) {
        return function() { quickAnswer(val); };
      })(actions[j].value));
      actDiv.appendChild(aBtn);
    }

    inputArea.insertBefore(actDiv, inputArea.querySelector(".shortcuts"));
    inputArea.classList.remove("hidden");
    // Force reflow — same WebKit hit-test fix as MC options above
    void actDiv.offsetHeight;
  } else {
    // Free-text input — show text box (pinyin, IME, etc.)
    _currentMcMode = false;
    var shortcuts3 = inputArea.querySelector(".shortcuts");
    if (shortcuts3) { shortcuts3.classList.remove("mc-mode"); shortcuts3.classList.remove("action-mode"); }
    // Clean CLI-style prompt characters ("> ", "pinyin> ", etc.) for web UI
    var cleanPrompt = prompt.replace(/^\s*\S*>\s*$/, "").trim();
    promptText.textContent = cleanPrompt;
    // Set placeholder and inputmode based on prompt type
    if (/pinyin/i.test(prompt)) {
      input.placeholder = "Type pinyin\u2026";
      input.setAttribute("inputmode", "text");
      input.setAttribute("enterkeyhint", "send");
    } else if (/hanzi/i.test(prompt)) {
      input.placeholder = "Type characters\u2026";
      input.setAttribute("inputmode", "text");
      input.setAttribute("enterkeyhint", "send");
    } else if (/sentence/i.test(prompt)) {
      input.placeholder = "Type sentence\u2026";
      input.setAttribute("inputmode", "text");
      input.setAttribute("enterkeyhint", "send");
    } else if (/order/i.test(prompt)) {
      input.placeholder = "Reorder the words\u2026";
      input.setAttribute("inputmode", "text");
      input.setAttribute("enterkeyhint", "send");
    } else if (/^\s*>\s*$/.test(prompt) || /\d/.test(prompt)) {
      // Bare "> " prompts in dialogues expect a number
      input.placeholder = "Your answer\u2026";
      input.setAttribute("inputmode", "numeric");
      input.setAttribute("enterkeyhint", "send");
    } else {
      input.placeholder = "Your answer\u2026";
      input.setAttribute("inputmode", "text");
      input.setAttribute("enterkeyhint", "send");
    }
    inputRow.classList.remove("hidden");
    input.value = "";
    inputArea.classList.remove("hidden");

    // Add replay button if this is a listening drill
    if (audioNearby) {
      var rDiv = document.createElement("div");
      rDiv.id = "option-buttons";
      rDiv.className = "option-buttons";
      var rBtn2 = document.createElement("button");
      rBtn2.className = "btn-option btn-option-replay";
      rBtn2.textContent = "Replay audio";
      rBtn2.addEventListener("click", function() { quickAnswer("R"); });
      rDiv.appendChild(rBtn2);
      inputArea.insertBefore(rDiv, inputRow);
    }

    input.focus();
  }

  setStatus("connected", "In session");
}

function hideInput() {
  var inputArea = document.getElementById("input-area");
  if (inputArea.classList.contains("hidden")) { currentPromptId = null; return; }
  // Graceful exit: slide down + fade, then hide
  inputArea.classList.add("input-exit");
  currentPromptId = null;
  // Cancel any previous pending timer before scheduling a new one
  if (_hideInputTimer) clearTimeout(_hideInputTimer);
  _hideInputTimer = setTimeout(function() {
    _hideInputTimer = null;
    inputArea.classList.add("hidden");
    inputArea.classList.remove("input-exit");
    // Restore input row visibility for next prompt
    var inputRow = inputArea.querySelector(".input-row");
    if (inputRow) inputRow.classList.remove("hidden");
    // Clean up option buttons
    var opts = document.getElementById("option-buttons");
    if (opts) opts.remove();
  }, DURATION_FAST);
}

/* ── Option detection helpers ────────────────────────── */

function detectNumberedOptions() {
  /* Scan CURRENT drill group for numbered options like "  1. good".
   * Only looks at the active (non-past) drill group to avoid picking up
   * numbered options from previous MC drills still in the DOM.
   * Also hides the original text messages when buttons will replace them. */
  var area = document.getElementById("drill-area");
  if (!area) return [];
  // Only scan the current drill group (not past groups)
  var currentGroup = getCurrentDrillGroup();
  var container = currentGroup || area;
  var msgs = container.querySelectorAll(".msg");
  var options = [];
  var matchedEls = [];
  // Scan backwards from end, collecting consecutive numbered lines
  for (var i = msgs.length - 1; i >= 0; i--) {
    var text = msgs[i].textContent;
    var match = text.match(/^\s*(\d+)\.\s+(.+)/);
    if (match) {
      options.unshift({value: match[1], text: match[1] + ". " + match[2].trim()});
      matchedEls.unshift(msgs[i]);
    } else if (options.length > 0) {
      break; // Stop at first non-option line after finding options
    }
  }
  // Hide the original text options — they'll be replaced by clickable buttons
  if (options.length >= 2) {
    for (var k = 0; k < matchedEls.length; k++) {
      matchedEls[k].style.display = "none";
      matchedEls[k].setAttribute("aria-hidden", "true");
    }
  }
  return options;
}

function hasRecentAudio() {
  /* Check if current drill group indicates audio was played (listening drill).
   * Only checks the CURRENT (non-past) drill group to avoid stale audio. */
  var currentGroup = getCurrentDrillGroup();
  if (!currentGroup) return false;
  // Don't show replay for past drill groups
  if (currentGroup.classList.contains("past")) return false;
  var msgs = currentGroup.querySelectorAll(".msg");
  for (var i = msgs.length - 1; i >= 0; i--) {
    var text = msgs[i].textContent;
    if (text.indexOf("Listen") !== -1 || text.indexOf("replaying") !== -1 || text.indexOf("Identify the tones") !== -1) return true;
  }
  return false;
}

function detectActionPrompt(prompt) {
  /* Parse prompt text for common action patterns and return button configs. */
  if (prompt.indexOf("Press Enter to begin") !== -1) {
    var actions = [{label: "Begin", value: "", primary: true}];
    if (prompt.indexOf("M=mini") !== -1) actions.push({label: "Mini", value: "M", primary: false});
    if (prompt.indexOf("Q=quit") !== -1) actions.push({label: "Quit", value: "Q", primary: false});
    return actions;
  }
  if (prompt.indexOf("start recording") !== -1) {
    var rActions = [{label: "Record", value: "", primary: true}];
    if (prompt.indexOf("S=skip") !== -1) rActions.push({label: "Skip", value: "S", primary: false});
    if (prompt.indexOf("Q=quit") !== -1) rActions.push({label: "Quit", value: "Q", primary: false});
    return rActions;
  }
  if (prompt.indexOf("Press Enter") !== -1 && prompt.length < 60) {
    return [{label: "Continue", value: "", primary: true}];
  }
  if (prompt.indexOf("Enter to finish") !== -1 && prompt.indexOf("d for details") !== -1) {
    return [
      {label: "Finish", value: "", primary: true},
      {label: "Details", value: "d", primary: false}
    ];
  }
  if (prompt.indexOf("Liked?") !== -1) {
    return [
      {label: "Yes", value: "y", primary: true},
      {label: "No", value: "n", primary: false},
      {label: "Skip", value: "", primary: false}
    ];
  }
  if (prompt.indexOf("next session?") !== -1 || prompt.indexOf("When's your") !== -1) {
    return [
      {label: "Tomorrow", value: "tomorrow", primary: true},
      {label: "Skip", value: "", primary: false}
    ];
  }
  return null;
}

function submitAnswer() {
  // #7 — Debounce: block rapid double-submit (300ms)
  var now = Date.now();
  if (now - _lastSubmitTime < 300) return;
  _lastSubmitTime = now;

  const input = document.getElementById("answer-input");
  const value = input.value;

  // #14 — Prevent empty submission for free-text inputs
  if (value.trim() === "" && !_currentMcMode) {
    input.classList.add("input-shake");
    setTimeout(function() { input.classList.remove("input-shake"); }, 350);
    return;
  }
  sendAnswer(value);
}

var _lastQuickAnswerTime = 0;
var _drillTransitionTimer = null;
function quickAnswer(value, displayText) {
  // Debounce: prevent rage-click double-submit on MC options (300ms)
  var now = Date.now();
  if (now - _lastQuickAnswerTime < 300) return;
  _lastQuickAnswerTime = now;
  // Disable all option buttons after selection to prevent re-clicks
  var allBtns = document.querySelectorAll(".btn-option");
  for (var i = 0; i < allBtns.length; i++) {
    allBtns[i].disabled = true;
  }
  sendAnswer(value, displayText);
}

function skipDrill() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({type: "answer", value: "__skip__", id: ""}));
  }
}

function sendAnswer(value, displayText) {
  // ── Drill micro-timing: record response time and inter-drill gap ──
  var now = Date.now();
  if (_drillShownAt) {
    var responseMs = now - _drillShownAt;
    var detail = {ms: responseMs};
    if (_lastDrillAnsweredAt) {
      detail.gap_ms = now - _lastDrillAnsweredAt;
    }
    EventLog.queueClientEvent("drill_timing", "response", detail);
  }
  _lastDrillAnsweredAt = now;
  _drillShownAt = null;

  // Stop any playing audio immediately on answer submit
  if (currentAudio) {
    try { currentAudio.pause(); currentAudio.currentTime = 0; } catch (e) {}
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    _debugLog.warn("[ws] cannot send answer: ws not open");
    setStatus("disconnected", "Disconnected");
    showDisconnectBanner();
    return;
  }
  if (!currentPromptId) {
    _debugLog.warn("[ws] cannot send answer: no active prompt");
    // Show brief visual feedback instead of silently swallowing
    flashStatus("loading", "Checking");
    return;
  }
  _debugLog.log("[ws] sending answer:", value);
  setStatus("loading", "Checking");
  ws.send(JSON.stringify({
    type: "answer",
    id: currentPromptId,
    value: value
  }));
  hideInput();

  // Show loading indicator after 1.5s if next drill hasn't arrived yet
  // This addresses >5s gaps between drills where user sees no feedback
  if (_drillTransitionTimer) clearTimeout(_drillTransitionTimer);
  _drillTransitionTimer = setTimeout(function() {
    if (sessionActive && !currentPromptId) {
      var area = document.getElementById("drill-area");
      var loader = document.createElement("div");
      loader.className = "msg msg-dim drill-transition-loader";
      loader.textContent = "Preparing next item\u2026";
      loader.style.opacity = "0.6";
      area.appendChild(loader);
      area.scrollTop = area.scrollHeight;
    }
  }, 1500);

  // Show what user typed — append to current drill group to preserve grouping
  var echoText = displayText || value;
  if (echoText && echoText !== "") {
    const div = document.createElement("div");
    div.className = "msg msg-user-echo";
    div.textContent = "  > " + echoText;
    var echoGroup = getCurrentDrillGroup();
    if (echoGroup) {
      echoGroup.appendChild(div);
    } else {
      document.getElementById("drill-area").appendChild(div);
    }
  }
}

function flashStatus(state, text) {
  /* Briefly show a status message, then revert to previous state. */
  const dot = document.getElementById("status-dot");
  const label = document.getElementById("status-text");
  const prevClass = dot.className;
  const prevText = label.textContent;
  dot.className = "dot-" + state;
  label.textContent = text;
  setTimeout(function() {
    dot.className = prevClass;
    label.textContent = prevText;
  }, FLASH_DURATION);
}

function showComplete(summary) {
  const content = document.getElementById("complete-content");

  // #3 — Stop session timer
  if (_sessionTimerInterval) { clearInterval(_sessionTimerInterval); _sessionTimerInterval = null; }

  hideDisconnectBanner();
  setStatus("idle", "Session complete");
  transitionTo("session", "complete");
  // Sound synced to the moment the complete section enters — fires when section becomes visible
  setTimeout(function() { AeluSound.sessionComplete(); }, DURATION_FAST);
  // First session celebration: ascending bowl triad after completion sound
  if (window._totalSessionsBefore === 0) {
    setTimeout(function() { AeluSound.levelUp(); }, 1500);
  }

  const total = summary.items_completed || 0;
  const correct = summary.items_correct || 0;
  const pct = total > 0 ? Math.round(correct / total * 100) : 0;

  // Paper lantern celebration for strong sessions
  if (pct >= 80 && total >= 3 && window.AeluCelebrations) {
    setTimeout(function() { AeluCelebrations.paperLanterns(); }, 300);
  }

  trackEvent('session_complete', {items_completed: total, accuracy: pct});

  // Log nav depth for this session
  if (_navTransitionCount > 0) {
    EventLog.queueClientEvent("ux", "nav_depth", {depth: _navTransitionCount});
    _navTransitionCount = 0;
  }

  // #3 — Elapsed time for completion display
  var elapsedStr = "";
  if (_sessionStartTime) {
    var elapsed = Math.floor((Date.now() - _sessionStartTime) / 1000);
    var eMins = Math.floor(elapsed / 60);
    var eSecs = elapsed % 60;
    elapsedStr = eMins + ":" + (eSecs < 10 ? "0" : "") + eSecs;
  }

  // Score class — muted, not celebratory
  const scoreClass = pct >= 80 ? "score-high" : pct >= 50 ? "score-mid" : "score-low";
  const scoreLabel = "session summary";

  let html = '<img src="' + themedIllustration('/static/illustrations/session-complete.webp') + '" alt="" class="complete-illustration" aria-hidden="true">';
  html += '<h2>Session complete.</h2>';
  html += '<div class="complete-score ' + scoreClass + '">' + correct + ' of ' + total + '<span class="sr-only"> — ' + scoreLabel + '</span></div>';
  html += '<div class="complete-pct">' + pct + '% recalled';
  if (elapsedStr) html += ' &middot; ' + elapsedStr;
  html += '</div>';
  html += '<div class="complete-accuracy-bar"><div class="complete-accuracy-fill' + (pct >= 80 ? ' score-high' : '') + '" style="--accuracy-pct:' + pct + '%"></div></div>';

  if (summary.early_exit) {
    // If the user completed a good chunk, soften the message
    if (total > 0 && correct / total >= 0.5) {
      html += '<div class="complete-message">Good stopping point. Drill progress saved.</div>';
    } else {
      html += '<div class="complete-message">Session ended early. Drill progress saved.</div>';
    }
  }

  // Session message — describe system response, not learner performance
  if (total > 0) {
    html += '<div class="complete-message">Spacing adjusts based on this session. Items you missed resurface sooner.</div>';
  }

  // #4 — Show loading skeleton while fetching details
  content.innerHTML = html + '<div class="complete-skeleton"><div class="skeleton-line"></div><div class="skeleton-line short"></div><div class="skeleton-line"></div></div>';
  handleImgErrors(content, '/static/illustrations/session-complete.webp');

  // Animated number counting on score
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    var scoreEl = content.querySelector('.complete-score');
    if (scoreEl && total > 0) {
      scoreEl.textContent = '0 of ' + total;
      var countStart = performance.now();
      (function countUp(now) {
        var p = Math.min(1, (now - countStart) / 800);
        var ease = 1 - Math.pow(1 - p, 3);
        var cur = Math.round(correct * ease);
        scoreEl.innerHTML = cur + ' of ' + total + '<span class="sr-only"> — session summary</span>';
        if (p < 1) requestAnimationFrame(countUp);
      })(performance.now());
    }
  }

  // Fetch additional session data for the complete screen
  fetchCompleteDetails(content, html, summary);
}

function fetchCompleteDetails(contentEl, baseHtml, summary) {
  summary = summary || {};
  var isEarlyUser = (window._totalSessionsBefore != null && window._totalSessionsBefore < 3);

  // For early users, skip /api/progress to reduce data overload
  var fetches = isEarlyUser
    ? [Promise.resolve({}), fetch("/api/status").then(r => r.json()).catch(() => ({})), fetch("/api/session-items").then(r => r.json()).catch(() => ({}))]
    : [fetch("/api/progress").then(r => r.json()).catch(() => ({})), fetch("/api/status").then(r => r.json()).catch(() => ({})), fetch("/api/session-items").then(r => r.json()).catch(() => ({}))];

  Promise.all(fetches).then(function(results) {
    const progress = results[0];
    const status = results[1];
    const sessionItems = results[2];
    let html = baseHtml;

    // Streak display — quiet, no celebration
    if (status.days_since_last != null && status.days_since_last <= 1) {
      html += '<div class="complete-streak">Returning.</div>';
    }

    // Accuracy delta vs previous session
    if (status.prev_session_accuracy != null) {
      // Compute current session pct from baseHtml context
      var curPctMatch = baseHtml.match(/(\d+)% recalled/);
      var curPct = curPctMatch ? parseInt(curPctMatch[1]) : null;
      if (curPct != null && curPct !== Math.round(status.prev_session_accuracy)) {
        var accDelta = curPct - Math.round(status.prev_session_accuracy);
        if (accDelta > 0) {
          html += '<div class="complete-accuracy-delta rich-correct">\u2191 from ' + Math.round(status.prev_session_accuracy) + '% last session</div>';
        } else if (accDelta < -10) {
          html += '<div class="complete-accuracy-delta complete-accuracy-down">Harder material today \u2014 that\u2019s the system working</div>';
        }
      }
    }

    // First session contextual explanation
    var wasFirstSession = (typeof window._totalSessionsBefore !== "undefined") && window._totalSessionsBefore === 0;
    if (wasFirstSession) {
      html += '<div class="complete-message complete-first-explain">'
            + 'Your first session focused on recognition \u2014 matching, listening, tones. '
            + 'Future sessions add writing and speaking.</div>';
    }

    // "What you practiced" — show actual hanzi with stages
    var items = (sessionItems && sessionItems.items) || [];
    if (items.length > 0) {
      var stageLabels = {
        "seen": "Encountered", "passed_once": "Introduced", "stabilizing": "Building",
        "stable": "Strong", "durable": "Mastered", "decayed": "Review",
        "weak": "Fresh", "improving": "Recovering"
      };

      // Summary: count correct/incorrect
      var correctCount = 0, incorrectCount = 0;
      for (var bc = 0; bc < items.length; bc++) {
        if (items[bc].correct === false) incorrectCount++;
        else correctCount++;
      }
      html += '<div class="complete-details complete-practiced"><h3>What you practiced</h3>';
      html += '<div class="complete-felt-progress">' + items.length + ' word' + (items.length !== 1 ? 's' : '');
      if (incorrectCount > 0) {
        html += ' — ' + correctCount + ' correct, ' + incorrectCount + ' to review';
      }
      html += '</div>';
      html += '<div class="practiced-grid">';
      for (var pi = 0; pi < items.length && pi < 16; pi++) {
        var it = items[pi];
        var stageClass = "stage-" + (it.stage || "seen").replace(/_/g, "-");
        var resultClass = it.correct === false ? " practiced-wrong" : " practiced-right";
        var label = stageLabels[it.stage] || it.stage;
        html += '<div class="practiced-item ' + stageClass + resultClass + '">';
        html += '<span class="practiced-hanzi">' + escapeHtml(it.hanzi) + '</span>';
        html += '<span class="practiced-pinyin">' + escapeHtml(it.pinyin || '') + '</span>';
        if (it.correct === false && it.expected_answer) {
          html += '<span class="practiced-correction">' + escapeHtml(it.expected_answer) + '</span>';
        } else {
          html += '<span class="practiced-english">' + escapeHtml(it.english || '') + '</span>';
        }
        html += '<span class="practiced-stage">' + label + '</span>';
        html += '</div>';
      }
      if (items.length > 16) {
        html += '<div class="practiced-item practiced-more">+' + (items.length - 16) + ' more</div>';
      }
      html += '</div></div>';
    }

    // Comprehension gain — words that advanced mastery stage this session
    if (items.length > 0 && !isEarlyUser) {
      var gainLabels = {"passed_once": "recognized", "stabilizing": "building", "stable": "strong", "durable": "mastered"};
      var gains = [];
      for (var gi = 0; gi < items.length; gi++) {
        var stage = items[gi].stage;
        if (stage && stage !== "seen" && gainLabels[stage]) {
          gains.push({hanzi: items[gi].hanzi, stage: stage, label: gainLabels[stage]});
        }
      }
      if (gains.length > 0) {
        html += '<div class="complete-details complete-gains"><h3>Comprehension gain</h3>';
        html += '<div class="gains-summary">' + gains.length + ' word' + (gains.length !== 1 ? 's' : '') + ' advancing</div>';
        html += '<div class="gains-list">';
        for (var gj = 0; gj < gains.length && gj < 8; gj++) {
          html += '<span class="gain-chip stage-' + gains[gj].stage.replace(/_/g, '-') + '">'
                + escapeHtml(gains[gj].hanzi) + ' <small>' + gains[gj].label + '</small></span>';
        }
        if (gains.length > 8) html += '<span class="gain-chip gain-more">+' + (gains.length - 8) + '</span>';
        html += '</div></div>';
      }
    }

    // Session insights — speed + error breakdown from enriched done message
    var hasInsights = summary.speed_avg_s || summary.error_types || summary.new_count;
    if (hasInsights && !isEarlyUser) {
      html += '<div class="complete-details complete-insights"><h3>Session insights</h3>';
      if (summary.speed_avg_s) {
        html += '<div class="complete-row"><span>Avg response</span><span>' + summary.speed_avg_s + 's</span></div>';
      }
      if (summary.new_count) {
        html += '<div class="complete-row"><span>New words</span><span>' + summary.new_count + ' introduced</span></div>';
      }
      if (summary.error_types) {
        var errorParts = [];
        var etEntries = Object.entries(summary.error_types).sort(function(a, b) { return b[1] - a[1]; });
        for (var ei = 0; ei < etEntries.length && ei < 4; ei++) {
          var etLabel = {tone: 'Tone', segment: 'Syllable', vocab: 'Vocabulary', ime_confusable: 'Similar chars', grammar: 'Grammar', register_mismatch: 'Register', particle_misuse: 'Particle', measure_word: 'Measure word'}[etEntries[ei][0]] || etEntries[ei][0];
          errorParts.push(etLabel + ' (' + etEntries[ei][1] + ')');
        }
        html += '<div class="complete-row"><span>Focus areas</span><span>' + errorParts.join(', ') + '</span></div>';
      }
      html += '</div>';
    }

    // "What happens next" — explain adaptive reactions to this session
    if (!isEarlyUser && !summary.early_exit) {
      var nextItems = [];
      if (summary.error_types) {
        var topError = Object.entries(summary.error_types).sort(function(a, b) { return b[1] - a[1]; })[0];
        if (topError) {
          var errName = {tone: 'tone', segment: 'segmentation', vocab: 'vocabulary', ime_confusable: 'similar characters', grammar: 'grammar'}[topError[0]] || topError[0];
          nextItems.push("More " + errName + " practice queued for next session");
        }
      }
      var total2 = summary.items_completed || 0;
      var correct2 = summary.items_correct || 0;
      var pct2 = total2 > 0 ? Math.round(correct2 / total2 * 100) : 0;
      if (pct2 >= 90 && total2 >= 8) {
        nextItems.push("Strong recall \u2014 new material enters next session");
      } else if (pct2 < 50 && total2 >= 5) {
        nextItems.push("Next session adds extra support for today\u2019s challenging items");
      }
      if (summary.new_count && summary.new_count >= 3) {
        nextItems.push("New words enter the spaced repetition cycle");
      }
      if (nextItems.length > 0) {
        html += '<div class="complete-details complete-next"><h3>What happens next</h3>';
        for (var ni = 0; ni < nextItems.length; ni++) {
          html += '<div class="complete-row complete-next-item">' + escapeHtml(nextItems[ni]) + '</div>';
        }
        html += '</div>';
      }
    }

    // For early users: show simplified progress ring from status mastery, skip detailed rows
    if (isEarlyUser && status.mastery && Object.keys(status.mastery).length > 0) {
      var sEntries = Object.entries(status.mastery).sort();
      var sRingLevel = null, sRingPct = 0;
      for (var si = 0; si < sEntries.length; si++) {
        var sp = sEntries[si][1].pct != null ? Math.round(sEntries[si][1].pct) : 0;
        if (sp < 100) { sRingLevel = sEntries[si][0]; sRingPct = sp; break; }
      }
      if (!sRingLevel && sEntries.length > 0) { sRingLevel = sEntries[sEntries.length - 1][0]; sRingPct = 100; }
      if (sRingLevel) {
        var sCircum = 2 * Math.PI * 42;
        var sOffset = sCircum * (1 - sRingPct / 100);
        var sColor = sRingPct >= 80 ? 'var(--color-correct)' : sRingPct >= 50 ? 'var(--color-secondary)' : 'var(--color-accent)';
        html += '<div class="complete-details"><h3>Progress</h3>';
        html += '<div class="progress-ring-container">';
        html += '<svg class="progress-ring" viewBox="0 0 100 100">';
        html += '<circle cx="50" cy="50" r="42" fill="none" stroke="var(--color-divider)" stroke-width="6"/>';
        html += '<circle cx="50" cy="50" r="42" fill="none" stroke="' + sColor + '" stroke-width="6"'
              + ' stroke-linecap="round" stroke-dasharray="' + sCircum.toFixed(1) + '"'
              + ' stroke-dashoffset="' + sOffset.toFixed(1) + '"'
              + ' transform="rotate(-90 50 50)" class="progress-ring-fill"/>';
        html += '</svg>';
        html += '<div class="progress-ring-label">';
        html += '<span class="progress-ring-pct">' + (sRingPct < 20 ? 'Started' : sRingPct + '%') + '</span>';
        html += '<span class="progress-ring-level">HSK ' + sRingLevel + '</span>';
        html += '</div></div></div>';
      }
    }

    // Mastery summary — progress ring + rows with deltas (skip for early users)
    if (!isEarlyUser && progress.mastery && Object.keys(progress.mastery).length > 0) {
      // Find the current working HSK level (lowest with < 100% mastery)
      var entries = Object.entries(progress.mastery).sort();
      var ringLevel = null, ringPct = 0, ringTotal = 0, ringDelta = 0;
      for (var ei = 0; ei < entries.length; ei++) {
        var lv = entries[ei][0], ld = entries[ei][1];
        var pct = ld.pct != null ? Math.round(ld.pct) : 0;
        if (pct < 100) { ringLevel = lv; ringPct = pct; ringTotal = ld.total || 0; break; }
      }
      if (!ringLevel && entries.length > 0) {
        ringLevel = entries[entries.length - 1][0];
        ringPct = 100;
        ringTotal = entries[entries.length - 1][1].total || 0;
      }
      // Compute delta for ring level
      if (ringLevel && _preMastery && _preMastery[ringLevel] && _preMastery[ringLevel].pct != null) {
        ringDelta = ringPct - Math.round(_preMastery[ringLevel].pct);
      }

      html += '<div class="complete-details"><h3>Mastery</h3>';

      // SVG progress ring
      if (ringLevel) {
        var circumference = 2 * Math.PI * 42;
        var dashOffset = circumference * (1 - ringPct / 100);
        var ringColor = ringPct >= 80 ? 'var(--color-correct)' : ringPct >= 50 ? 'var(--color-secondary)' : 'var(--color-accent)';
        html += '<div class="progress-ring-container">';
        html += '<svg class="progress-ring" viewBox="0 0 100 100">';
        html += '<circle cx="50" cy="50" r="42" fill="none" stroke="var(--color-divider)" stroke-width="6"/>';
        html += '<circle cx="50" cy="50" r="42" fill="none" stroke="' + ringColor + '" stroke-width="6"'
              + ' stroke-linecap="round" stroke-dasharray="' + circumference.toFixed(1) + '"'
              + ' stroke-dashoffset="' + dashOffset.toFixed(1) + '"'
              + ' transform="rotate(-90 50 50)" class="progress-ring-fill"/>';
        html += '</svg>';
        html += '<div class="progress-ring-label">';
        html += '<span class="progress-ring-pct">' + ringPct + '%</span>';
        html += '<span class="progress-ring-level">HSK ' + ringLevel + '</span>';
        if (ringDelta > 0) html += '<span class="progress-ring-delta rich-correct">+' + ringDelta + '%</span>';
        html += '</div></div>';
      }

      // Mastery rows — only show levels with progress or the working level
      var shownLevels = 0;
      for (var mi = 0; mi < entries.length; mi++) {
        var level = entries[mi][0], data = entries[mi][1];
        var masteryPct = data.pct != null ? Math.round(data.pct) : 0;
        var totalItems = data.total || 0;
        var masteredCount = Math.round(totalItems * masteryPct / 100);
        // Skip levels with 0% that aren't the working level
        if (masteryPct === 0 && level !== ringLevel) continue;
        var deltaStr = "";
        if (_preMastery && _preMastery[level] && _preMastery[level].pct != null) {
          var prePct = Math.round(_preMastery[level].pct);
          var diff = masteryPct - prePct;
          if (diff > 0) deltaStr = ' <span class="rich-correct">(+' + diff + '%)</span>';
          else if (diff < 0) deltaStr = ' <span class="rich-incorrect">(' + diff + '%)</span>';
        }
        html += '<div class="complete-row">';
        html += '<span>HSK ' + level + '</span>';
        html += '<span>' + masteredCount + ' of ' + totalItems + ' (' + masteryPct + '%)' + deltaStr + '</span>';
        html += '</div>';
        shownLevels++;
      }
      html += '</div>';
    }

    // Retention summary — narrative (skip for early users)
    if (!isEarlyUser && progress.retention && progress.retention.retention_pct != null) {
      const retPct = Math.round(progress.retention.retention_pct);
      const totalItems = progress.retention.total_items || 0;
      const retainedCount = Math.round(totalItems * retPct / 100);
      html += '<div class="complete-details"><h3>Memory</h3>';
      if (totalItems > 0) {
        html += '<div class="complete-row">';
        html += '<span>' + retainedCount + ' of ' + totalItems + ' items above recall threshold</span>';
        html += '<span>' + retPct + '%</span>';
        html += '</div>';
      } else {
        html += '<div class="complete-row">';
        html += '<span>Recall above threshold</span>';
        html += '<span>' + retPct + '%</span>';
        html += '</div>';
      }
      html += '</div>';
    }

    // Next session — concrete, answers "what happens next?"
    if (status.item_count) {
      var due = status.items_due || 0;
      if (due > 0) {
        html += '<div class="complete-next">' + due + ' items due for review.</div>';
      } else {
        html += '<div class="complete-next">Memory reshaping. Next session adjusts spacing.</div>';
      }
    }

    // Return hook — give the user a reason to come back (always show concrete preview)
    var previewItems = [];
    for (var ph = 0; ph < items.length && previewItems.length < 5; ph++) {
      var pStage = items[ph].stage;
      if (pStage === "passed_once" || pStage === "stabilizing" || pStage === "stable") {
        previewItems.push({hanzi: items[ph].hanzi, pinyin: items[ph].pinyin || "", english: items[ph].english || ""});
      }
    }
    if (previewItems.length > 0) {
      var newWordCount = Math.max(0, (status.items_due || 0) - previewItems.length);
      var hookClass = wasFirstSession ? 'complete-return-hook complete-first-session' : 'complete-return-hook';
      html += '<div class="' + hookClass + '">';
      html += '<div class="return-hook-label">Tomorrow: review</div>';
      html += '<div class="return-word-list">';
      for (var rw = 0; rw < previewItems.length; rw++) {
        var ri = previewItems[rw];
        html += '<span class="return-word">';
        html += '<span class="return-word-hanzi">' + escapeHtml(ri.hanzi) + '</span>';
        html += '<span class="return-word-gloss">' + escapeHtml(ri.pinyin) + (ri.english ? ' \u00b7 ' + escapeHtml(ri.english) : '') + '</span>';
        html += '</span>';
      }
      html += '</div>';
      if (newWordCount > 0) html += '<div class="return-hook-extra">+ ' + newWordCount + ' more to review</div>';
      html += '</div>';
    } else if (wasFirstSession) {
      html += '<div class="complete-return-hook complete-first-session">'
            + 'Your study plan is now personalized to these results. '
            + 'Come back tomorrow \u2014 the system adapts with each session.'
            + '</div>';
    } else {
      html += '<div class="complete-return-hook">'
            + 'Your next session adapts to today\u2019s results.'
            + '</div>';
    }

    // Subtle branding line after first session
    if (wasFirstSession) {
      html += '<div class="complete-brand-line">10 minutes. Real progress.</div>';
    }

    // "At this pace" projection — available from session 1
    if (status.simple_forecast && status.simple_forecast.sessions_to_milestone) {
      var sf = status.simple_forecast;
      var paceText = 'At this pace: ' + sf.words_long_term + ' word' + (sf.words_long_term !== 1 ? 's' : '') + ' in long-term memory.';
      if (sf.next_milestone && sf.sessions_to_milestone) {
        paceText += ' Next milestone (' + sf.next_milestone + ' words) in ~' + sf.sessions_to_milestone + ' session' + (sf.sessions_to_milestone !== 1 ? 's' : '') + '.';
      }
      html += '<div class="complete-pace">' + paceText + '</div>';
    }

    // Daily reminder prompt — shown on first session completion
    if (wasFirstSession) {
      var reminderShown = false;
      try { reminderShown = localStorage.getItem("reminder_prompt_shown") === "1"; } catch (e) {}
      if (!reminderShown) {
        html += '<div class="complete-reminder" id="complete-reminder">'
              + '<span>Get a daily reminder?</span>'
              + '<button class="btn-primary btn-sm" id="btn-enable-reminder">Enable</button>'
              + '</div>';
      }
    }

    // Weekly encounters summary if available (skip for early users)
    if (!isEarlyUser) {
      html += '<div id="complete-encounters" class="complete-encounters"></div>';
    }

    // Share / referral button
    html += '<div class="share-section">';
    html += '<button class="btn btn-outline share-btn" onclick="shareReferral()">Share with a friend</button>';
    html += '</div>';

    contentEl.innerHTML = html;
    contentEl.classList.add("content-enter");
    setTimeout(function() { contentEl.classList.remove("content-enter"); }, DURATION_FAST);

    // Wire reminder enable button
    var reminderBtn = document.getElementById("btn-enable-reminder");
    if (reminderBtn) {
      reminderBtn.addEventListener("click", function() {
        try { localStorage.setItem("reminder_prompt_shown", "1"); } catch (e) {}
        var reminderDiv = document.getElementById("complete-reminder");
        function showFallback() {
          if (reminderDiv) {
            reminderDiv.classList.add("reminder-fallback");
            reminderDiv.innerHTML = '<span>Bookmark this page for quick access.</span>';
          }
        }
        function showSuccess() {
          if (reminderDiv) {
            reminderDiv.classList.add("reminder-success");
            reminderDiv.innerHTML = '<span>Daily reminder enabled.</span>';
          }
          if (AeluSound.instance) AeluSound.instance.milestone();
        }
        if (!("Notification" in window) || !("serviceWorker" in navigator)) {
          showFallback();
          return;
        }
        // Show loading state
        reminderBtn.disabled = true;
        reminderBtn.textContent = "Enabling\u2026";
        Notification.requestPermission().then(function(perm) {
          if (perm === "granted") {
            navigator.serviceWorker.ready.then(function(reg) {
              fetch("/api/push/vapid-key").then(function(r) { return r.json(); }).then(function(kd) {
                if (!kd.vapid_public_key) { showSuccess(); return; }
                var rawKey = atob(kd.vapid_public_key.replace(/-/g, '+').replace(/_/g, '/'));
                var keyArray = new Uint8Array(rawKey.length);
                for (var k = 0; k < rawKey.length; k++) keyArray[k] = rawKey.charCodeAt(k);
                return reg.pushManager.subscribe({
                  userVisibleOnly: true,
                  applicationServerKey: keyArray,
                });
              }).then(function(sub) {
                if (!sub) return;
                var subJson = JSON.stringify(sub);
                apiFetch("/api/push/register", {
                  method: "POST",
                  headers: {"Content-Type": "application/json"},
                  body: JSON.stringify({platform: "web", token: subJson}),
                });
                showSuccess();
              }).catch(function() {
                showFallback();
              });
            });
          } else {
            showFallback();
          }
        });
      });
    }

    // Fetch weekly encounters for the completion screen (skip for early users)
    if (!isEarlyUser) {
    fetch("/api/encounters/summary").then(function(r) { return r.json(); }).then(function(enc) {
      var encEl = document.getElementById("complete-encounters");
      if (!encEl) return;
      var total = enc.total_lookups_7d || 0;
      var topWords = enc.top_words || [];
      if (total > 0 || topWords.length > 0) {
        var encHtml = '<div class="complete-details"><h3>This Week</h3>';
        encHtml += '<div class="complete-row"><span>Words encountered</span><span>' + total + '</span></div>';
        if (topWords.length > 0) {
          encHtml += '<div class="complete-row"><span>Most seen</span><span>';
          encHtml += topWords.slice(0, 5).map(function(w) { return w.hanzi; }).join(" \u00b7 ");
          encHtml += '</span></div>';
        }
        encHtml += '</div>';
        encEl.innerHTML = encHtml;
      }
    }).catch(function() {});
    }

    // Wire achievement sounds based on session results
    if (AeluSound.instance) {
      // Check for mastery gains
      var hadGain = false;
      if (progress.mastery && _preMastery) {
        for (var lvl in progress.mastery) {
          if (_preMastery[lvl] && progress.mastery[lvl].pct > _preMastery[lvl].pct) { hadGain = true; break; }
        }
      }
      if (hadGain) setTimeout(function() { if (AeluSound.instance) AeluSound.instance.milestone(); }, 600);
      // Check for streak
      if (status.days_since_last != null && status.days_since_last <= 1 && status.streak_days >= 7) {
        setTimeout(function() { if (AeluSound.instance) AeluSound.instance.streakMilestone(); }, hadGain ? 1200 : 600);
      }
    }

    // Milestone toasts — check after session completion
    if (status.milestones) {
      setTimeout(function() { MilestoneToast.checkMilestones(status.milestones); }, 1500);
    }
  });
}

function shareReferral() {
  var referralUrl = window.location.origin + "?ref=" + (window._userReferralCode || "aelu");
  if (navigator.share) {
    navigator.share({
      title: "Aelu \u2014 Learn Chinese",
      text: "I've been learning Chinese with Aelu. Try it!",
      url: referralUrl,
    }).catch(function() {});
  } else {
    navigator.clipboard.writeText(referralUrl).then(function() {
      var toast = document.createElement("div");
      toast.className = "competence-toast visible";
      toast.textContent = "Referral link copied!";
      document.body.appendChild(toast);
      setTimeout(function() { toast.remove(); }, 3000);
    });
  }
}

function updateProgress(current, total) {
  // Start session timer on first progress update (actual drills, not preview screen)
  if (!_sessionStartTime && total > 0) {
    _sessionStartTime = Date.now();
    _sessionTimerInterval = setInterval(updateSessionTimer, 1000);
    updateSessionTimer();
  }
  const pct = total > 0 ? (current / total * 100) : 0;
  const bar = document.getElementById("progress-bar");
  document.getElementById("progress-fill").style.width = pct + "%";
  document.getElementById("progress-label").textContent = "Drill " + current + " of " + total;
  // Update ARIA
  if (bar) {
    bar.setAttribute("aria-valuenow", Math.round(pct));
    bar.setAttribute("aria-valuetext", current + " of " + total + " items completed");
  }
  // Sky gradient warms as session progresses — very subtle
  var progress = total > 0 ? current / total : 0;
  document.documentElement.style.setProperty("--session-progress", progress.toFixed(3));
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Attach error handlers to img elements within a container.
 * Hides images that fail to load, or falls back to a given src.
 */
function handleImgErrors(container, fallbackSrc) {
  if (!container) return;
  var imgs = container.querySelectorAll ? container.querySelectorAll("img") : [];
  for (var i = 0; i < imgs.length; i++) {
    (function(img) {
      img.addEventListener("error", function() {
        // Try WebP → JPG fallback first
        if (img.src.match(/\.webp($|\?)/)) {
          img.src = img.src.replace(/\.webp($|\?)/, '.jpg$1');
        } else if (fallbackSrc && img.src !== fallbackSrc) {
          img.src = fallbackSrc;
        } else {
          img.style.display = "none";
        }
      });
    })(imgs[i]);
  }
}

/* ── Audio playback from server-generated files ────────────────────────── */

var currentAudio = null;

function playAudioFromServer(url) {
  // Stop any currently playing audio
  if (currentAudio) {
    try { currentAudio.pause(); currentAudio.currentTime = 0; } catch (e) {}
  }
  // Remove any previous audio error actions
  var oldErr = document.getElementById("audio-error-actions");
  if (oldErr) oldErr.remove();

  currentAudio = new Audio(url);
  updateAudioState("playing");
  currentAudio.addEventListener("ended", function() {
    updateAudioState("ready");
  });

  function showAudioError() {
    updateAudioState("error");
    // #2 — Show retry/skip buttons for audio errors
    var currentGroup = getCurrentDrillGroup();
    var container = currentGroup || document.getElementById("drill-area");
    if (!container) return;
    var errDiv = document.createElement("div");
    errDiv.id = "audio-error-actions";
    errDiv.className = "audio-error-actions";
    var retryBtn = document.createElement("button");
    retryBtn.textContent = "Retry audio";
    retryBtn.addEventListener("click", function() {
      errDiv.remove();
      playAudioFromServer(url);
    });
    var skipBtn = document.createElement("button");
    skipBtn.textContent = "Skip";
    skipBtn.addEventListener("click", function() {
      errDiv.remove();
      updateAudioState("ready");
      if (currentPromptId) quickAnswer("B");
    });
    errDiv.appendChild(retryBtn);
    errDiv.appendChild(skipBtn);
    container.appendChild(errDiv);
  }

  currentAudio.addEventListener("error", function(e) {
    _debugLog.warn("[audio] playback error:", e);
    showAudioError();
  });
  currentAudio.play().catch(function(err) {
    _debugLog.warn("[audio] play() rejected:", err);
    showAudioError();
  });
}

/* ── Browser microphone recording ────────────────────────── */

/* ── 4-state recording panel (idle → recording → review → analyzing) ── */

var _recState = null;       // current panel state
var _recRequestId = null;   // WebSocket request id
var _recMaxDuration = 30;   // max recording seconds
var _recAudioCtx = null;
var _recStream = null;
var _recProcessor = null;
var _recSource = null;
var _recAnalyser = null;
var _recChunks = [];
var _recRecognition = null;
var _recTranscript = null;
var _recElapsedTimer = null;
var _recElapsedSec = 0;
var _recAnimFrame = null;
var _recMaxTimer = null;
var _recFrozenBars = null;  // snapshot for review waveform

// iOS Safari: pause recording when app goes to background (screen lock, tab switch)
document.addEventListener("visibilitychange", function() {
  if (_recState !== "recording") return;
  if (document.hidden) {
    // Disable mic tracks to prevent iOS from killing the stream
    if (_recStream) {
      _recStream.getTracks().forEach(function(t) { t.enabled = false; });
    }
    var panel = document.getElementById("recording-panel");
    if (panel) {
      var notice = panel.querySelector(".rec-paused-notice");
      if (!notice) {
        notice = document.createElement("div");
        notice.className = "rec-paused-notice";
        notice.textContent = "Recording paused";
        panel.appendChild(notice);
      }
      notice.classList.remove("hidden");
    }
  } else {
    // Re-enable mic tracks
    if (_recStream) {
      _recStream.getTracks().forEach(function(t) { t.enabled = true; });
    }
    var panel = document.getElementById("recording-panel");
    if (panel) {
      var notice = panel.querySelector(".rec-paused-notice");
      if (notice) notice.classList.add("hidden");
    }
  }
});

function handleRecordRequest(maxDuration, id, allowSkip) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    _debugLog.warn("[mic] getUserMedia not available, auto-skipping");
    EventLog.record("audio", "unavailable");
    addMessage("  Microphone not supported in this browser. Skipping speaking drill.", "msg msg-dim");
    sendAudioData(id, null);
    return;
  }

  _recRequestId = id;
  _recMaxDuration = maxDuration || 30;

  // Hide normal input area while recording panel is active
  hideInput();

  // Build panel DOM
  var existing = document.getElementById("recording-panel");
  if (existing) existing.remove();

  // Safari speech detection: show notice if SpeechRecognition unavailable
  var hasSpeechApi = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  var speechNotice = "";
  if (!hasSpeechApi) {
    speechNotice = '<div class="rec-safari-notice">Speech recognition unavailable in this browser. Audio is still recorded for tone grading. For full transcription, use Chrome.</div>';
  }

  var panel = document.createElement("div");
  panel.id = "recording-panel";
  panel.className = "recording-panel rec-state-idle";
  panel.innerHTML = speechNotice +
    '<div class="rec-idle">' +
      '<button class="rec-mic-btn" aria-label="Tap to record">' +
        '<svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>' +
      '</button>' +
      '<div class="rec-hint">Tap to record</div>' +
    '</div>' +
    '<div class="rec-recording">' +
      '<canvas class="rec-waveform" width="280" height="64"></canvas>' +
      '<div class="rec-level-bar"><div class="rec-level-fill"></div></div>' +
      '<div class="rec-elapsed">0:00</div>' +
      '<button class="rec-stop-btn" aria-label="Stop recording">' +
        '<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>' +
      '</button>' +
    '</div>' +
    '<div class="rec-review">' +
      '<canvas class="rec-waveform-frozen" width="280" height="64"></canvas>' +
      '<div class="rec-duration"></div>' +
      '<div class="rec-review-actions">' +
        '<button class="rec-redo-btn">Redo</button>' +
        '<button class="rec-submit-btn">Submit</button>' +
      '</div>' +
    '</div>' +
    '<div class="rec-analyzing">' +
      '<div class="rec-spinner"></div>' +
      '<div class="rec-analyzing-label">Analyzing your pronunciation</div>' +
    '</div>' +
    (allowSkip !== false ? '<a href="#" class="rec-skip">Skip</a>' : '');

  // Insert into current drill group
  var currentGroup = getCurrentDrillGroup();
  var area = document.getElementById("drill-area");
  if (currentGroup) {
    currentGroup.appendChild(panel);
  } else {
    area.appendChild(panel);
  }
  area.scrollTop = area.scrollHeight;

  // Wire up events
  panel.querySelector(".rec-mic-btn").addEventListener("click", _recStartRecording);
  panel.querySelector(".rec-stop-btn").addEventListener("click", _recStopRecording);
  panel.querySelector(".rec-redo-btn").addEventListener("click", _recRedo);
  panel.querySelector(".rec-submit-btn").addEventListener("click", _recSubmit);
  var skipLink = panel.querySelector(".rec-skip");
  if (skipLink) {
    skipLink.addEventListener("click", function(e) { e.preventDefault(); _recSkip(); });
  }

  _recSetState("idle");
}

function _recSetState(state) {
  _recState = state;
  var panel = document.getElementById("recording-panel");
  if (!panel) return;
  panel.className = "recording-panel rec-state-" + state;
}

function _recStartRecording() {
  var targetSR = 16000;
  _recChunks = [];
  _recTranscript = null;
  _recElapsedSec = 0;
  _recFrozenBars = null;

  // Start SpeechRecognition in parallel if available
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    try {
      _recRecognition = new SpeechRecognition();
      _recRecognition.lang = "zh-CN";
      _recRecognition.continuous = false;
      _recRecognition.maxAlternatives = 3;
      _recRecognition.onresult = function(event) {
        if (event.results.length > 0 && event.results[0].length > 0) {
          _recTranscript = event.results[0][0].transcript;
          _debugLog.log("[speech] transcript:", _recTranscript);
        }
      };
      _recRecognition.onerror = function(e) {
        _debugLog.warn("[speech] recognition error:", e.error);
      };
      _recRecognition.start();
    } catch (e) {
      _debugLog.warn("[speech] could not start recognition:", e);
      _recRecognition = null;
    }
  }

  navigator.mediaDevices.getUserMedia({ audio: { sampleRate: targetSR, channelCount: 1 } })
    .then(function(stream) {
      _recStream = stream;
      _recAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: targetSR });
      _recSource = _recAudioCtx.createMediaStreamSource(stream);

      // AnalyserNode for waveform visualization
      _recAnalyser = _recAudioCtx.createAnalyser();
      _recAnalyser.fftSize = 256;
      _recAnalyser.smoothingTimeConstant = 0.7;

      // Try AudioWorklet (modern), fall back to ScriptProcessor (deprecated)
      function _recSetupScriptProcessor() {
        var bufferSize = 4096;
        _recProcessor = _recAudioCtx.createScriptProcessor(bufferSize, 1, 1);
        _recProcessor._isWorklet = false;
        _recProcessor.onaudioprocess = function(e) {
          var input = e.inputBuffer.getChannelData(0);
          _recChunks.push(new Float32Array(input));
        };
        _recSource.connect(_recAnalyser);
        _recAnalyser.connect(_recProcessor);
        _recProcessor.connect(_recAudioCtx.destination);
      }

      function _recFinishSetup() {
        _recSetState("recording");
      }

      if (_recAudioCtx.audioWorklet) {
        _recAudioCtx.audioWorklet.addModule('/static/recorder-worklet.js').then(function() {
          var workletNode = new AudioWorkletNode(_recAudioCtx, 'recorder-processor');
          workletNode._isWorklet = true;
          workletNode.port.onmessage = function(e) {
            _recChunks.push(e.data);
          };
          _recSource.connect(_recAnalyser);
          _recAnalyser.connect(workletNode);
          workletNode.connect(_recAudioCtx.destination);
          _recProcessor = workletNode;
          _recFinishSetup();
        }).catch(function(err) {
          _debugLog.warn("[rec] AudioWorklet failed, falling back to ScriptProcessor:", err);
          _recSetupScriptProcessor();
          _recFinishSetup();
        });
      } else {
        _recSetupScriptProcessor();
        _recFinishSetup();
      }

      // (setup continues after worklet/fallback resolves)
      _recSetState("recording");
      updateAudioState("recording");

      // Elapsed timer
      _recUpdateElapsed();
      _recElapsedTimer = setInterval(function() {
        _recElapsedSec++;
        _recUpdateElapsed();
      }, 1000);

      // Waveform animation
      _recDrawWaveform();

      // Auto-stop at max duration
      _recMaxTimer = setTimeout(function() {
        _debugLog.log("[rec] max duration reached, auto-stopping");
        _recStopRecording();
      }, _recMaxDuration * 1000);
    })
    .catch(function(err) {
      _debugLog.error("[mic] getUserMedia error:", err);
      EventLog.record("audio", "permission_error", {error: err.name});
      if (_recRecognition) { try { _recRecognition.stop(); } catch (e) {} }

      // Show error in panel instead of removing it
      var panel = document.getElementById("recording-panel");
      if (panel) {
        var errDiv = document.createElement("div");
        errDiv.className = "rec-error";
        if (err.name === "NotAllowedError") {
          errDiv.textContent = "Microphone access is required for speaking drills. Please allow microphone access in your browser settings.";
        } else if (err.name === "NotFoundError") {
          errDiv.textContent = "No microphone detected. Please connect a microphone to use speaking drills.";
        } else {
          errDiv.textContent = "Microphone unavailable (" + err.name + "). Check permissions and try again.";
        }
        var idle = panel.querySelector(".rec-idle");
        if (idle) idle.appendChild(errDiv);
      }

      // Auto-skip after showing error
      setTimeout(function() { _recSkip(); }, 2500);
    });
}

function _recStopRecording() {
  // Clear timers
  if (_recElapsedTimer) { clearInterval(_recElapsedTimer); _recElapsedTimer = null; }
  if (_recMaxTimer) { clearTimeout(_recMaxTimer); _recMaxTimer = null; }
  if (_recAnimFrame) { cancelAnimationFrame(_recAnimFrame); _recAnimFrame = null; }

  // Capture frozen waveform snapshot before disconnecting analyser
  if (_recAnalyser) {
    var freqData = new Uint8Array(_recAnalyser.frequencyBinCount);
    _recAnalyser.getByteFrequencyData(freqData);
    _recFrozenBars = freqData;
  }

  // Stop audio nodes — send 'stop' to worklet before disconnecting
  if (_recProcessor) {
    if (_recProcessor._isWorklet) {
      try { _recProcessor.port.postMessage('stop'); } catch (e) {}
    }
    try { _recProcessor.disconnect(); } catch (e) {}
  }
  if (_recSource) { try { _recSource.disconnect(); } catch (e) {} }
  if (_recAnalyser) { try { _recAnalyser.disconnect(); } catch (e) {} }
  if (_recStream) { _recStream.getTracks().forEach(function(t) { t.stop(); }); }
  if (_recRecognition) { try { _recRecognition.stop(); } catch (e) {} }

  // Draw frozen waveform on review canvas
  _recDrawFrozenWaveform();

  // Show duration
  var panel = document.getElementById("recording-panel");
  if (panel) {
    var durEl = panel.querySelector(".rec-duration");
    if (durEl) durEl.textContent = _recFormatTime(_recElapsedSec);
  }

  _recSetState("review");
}

function _recRedo() {
  // Close previous AudioContext
  if (_recAudioCtx) { try { _recAudioCtx.close(); } catch (e) {} _recAudioCtx = null; }
  _recChunks = [];
  _recTranscript = null;
  _recFrozenBars = null;

  // Remove any error messages
  var panel = document.getElementById("recording-panel");
  if (panel) {
    var errs = panel.querySelectorAll(".rec-error");
    for (var i = 0; i < errs.length; i++) errs[i].remove();
  }

  _recSetState("idle");
}

function _recSubmit() {
  _recSetState("analyzing");

  // Merge chunks
  var totalLen = 0;
  for (var i = 0; i < _recChunks.length; i++) totalLen += _recChunks[i].length;
  var merged = new Float32Array(totalLen);
  var offset = 0;
  for (var j = 0; j < _recChunks.length; j++) {
    merged.set(_recChunks[j], offset);
    offset += _recChunks[j].length;
  }

  // Encode as WAV
  var actualSR = _recAudioCtx ? _recAudioCtx.sampleRate : 16000;
  if (_recAudioCtx) { try { _recAudioCtx.close(); } catch (e) {} _recAudioCtx = null; }
  var wavBuffer = encodeWAV(merged, actualSR);
  var base64 = arrayBufferToBase64(wavBuffer);

  // Check WebSocket is open
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    _debugLog.warn("[rec] WebSocket not open, keeping review state");
    _recSetState("review");
    addMessage("  Connection lost. Reconnecting...", "msg msg-dim");
    return;
  }

  sendAudioData(_recRequestId, base64, _recTranscript);
  updateAudioState("ready");
  _recChunks = [];
}

function _recSkip() {
  // Clean up any active recording
  if (_recElapsedTimer) { clearInterval(_recElapsedTimer); _recElapsedTimer = null; }
  if (_recMaxTimer) { clearTimeout(_recMaxTimer); _recMaxTimer = null; }
  if (_recAnimFrame) { cancelAnimationFrame(_recAnimFrame); _recAnimFrame = null; }
  if (_recProcessor) { try { _recProcessor.disconnect(); } catch (e) {} }
  if (_recSource) { try { _recSource.disconnect(); } catch (e) {} }
  if (_recAnalyser) { try { _recAnalyser.disconnect(); } catch (e) {} }
  if (_recStream) { _recStream.getTracks().forEach(function(t) { t.stop(); }); }
  if (_recRecognition) { try { _recRecognition.stop(); } catch (e) {} }
  if (_recAudioCtx) { try { _recAudioCtx.close(); } catch (e) {} _recAudioCtx = null; }

  sendAudioData(_recRequestId, null);
  _recCleanupPanel();
}

function _recCleanupPanel() {
  _recState = null;
  var panel = document.getElementById("recording-panel");
  if (panel) panel.remove();
}

/* Waveform drawing — 28 bars from frequency data */
function _recDrawWaveform() {
  if (_recState !== "recording" || !_recAnalyser) return;

  var panel = document.getElementById("recording-panel");
  if (!panel) return;
  var canvas = panel.querySelector(".rec-waveform");
  if (!canvas) return;
  var ctx = canvas.getContext("2d");
  var w = canvas.width;
  var h = canvas.height;

  var freqData = new Uint8Array(_recAnalyser.frequencyBinCount);
  _recAnalyser.getByteFrequencyData(freqData);

  var barCount = 28;
  var barWidth = Math.floor(w / barCount) - 2;
  var gap = 2;

  // Get accent color from CSS
  var accentColor = getComputedStyle(document.documentElement).getPropertyValue("--color-accent").trim() || "#946070";

  ctx.clearRect(0, 0, w, h);

  for (var i = 0; i < barCount; i++) {
    // Map bar index to frequency bin range
    var binIdx = Math.floor(i * freqData.length / barCount);
    var val = freqData[binIdx] / 255;
    var barH = Math.max(2, val * (h - 4));
    var x = i * (barWidth + gap) + gap;
    var y = (h - barH) / 2;

    ctx.globalAlpha = 0.5 + val * 0.5;
    ctx.fillStyle = accentColor;
    ctx.fillRect(x, y, barWidth, barH);
  }
  ctx.globalAlpha = 1;

  // Update level bar fill from frequency data average
  var levelFill = panel.querySelector(".rec-level-fill");
  if (levelFill) {
    var sum = 0;
    for (var li = 0; li < freqData.length; li++) sum += freqData[li];
    var avg = sum / freqData.length / 255;
    levelFill.style.width = Math.round(avg * 100) + "%";
  }

  _recAnimFrame = requestAnimationFrame(_recDrawWaveform);
}

/* Frozen waveform for review state */
function _recDrawFrozenWaveform() {
  var panel = document.getElementById("recording-panel");
  if (!panel || !_recFrozenBars) return;
  var canvas = panel.querySelector(".rec-waveform-frozen");
  if (!canvas) return;
  var ctx = canvas.getContext("2d");
  var w = canvas.width;
  var h = canvas.height;

  var barCount = 28;
  var barWidth = Math.floor(w / barCount) - 2;
  var gap = 2;

  var accentColor = getComputedStyle(document.documentElement).getPropertyValue("--color-accent").trim() || "#946070";

  ctx.clearRect(0, 0, w, h);

  for (var i = 0; i < barCount; i++) {
    var binIdx = Math.floor(i * _recFrozenBars.length / barCount);
    var val = _recFrozenBars[binIdx] / 255;
    var barH = Math.max(2, val * (h - 4));
    var x = i * (barWidth + gap) + gap;
    var y = (h - barH) / 2;

    ctx.globalAlpha = 0.3 + val * 0.1;
    ctx.fillStyle = accentColor;
    ctx.fillRect(x, y, barWidth, barH);
  }
  ctx.globalAlpha = 1;
}

function _recUpdateElapsed() {
  var panel = document.getElementById("recording-panel");
  if (!panel) return;
  var el = panel.querySelector(".rec-elapsed");
  if (el) el.textContent = _recFormatTime(_recElapsedSec);
}

function _recFormatTime(sec) {
  var m = Math.floor(sec / 60);
  var s = sec % 60;
  return m + ":" + (s < 10 ? "0" : "") + s;
}

function sendAudioData(id, base64Data, transcript) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  var msg = { type: "audio_data", id: id, data: base64Data };
  if (transcript != null) msg.transcript = transcript;
  ws.send(JSON.stringify(msg));
}

function encodeWAV(samples, sampleRate) {
  var buffer = new ArrayBuffer(44 + samples.length * 2);
  var view = new DataView(buffer);

  // RIFF header
  writeWAVString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeWAVString(view, 8, "WAVE");

  // fmt chunk
  writeWAVString(view, 12, "fmt ");
  view.setUint32(16, 16, true);       // chunk size
  view.setUint16(20, 1, true);        // PCM format
  view.setUint16(22, 1, true);        // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true);        // block align
  view.setUint16(34, 16, true);       // bits per sample

  // data chunk
  writeWAVString(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);

  // PCM samples
  for (var i = 0; i < samples.length; i++) {
    var s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return buffer;
}

function writeWAVString(view, offset, str) {
  for (var i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

function arrayBufferToBase64(buffer) {
  var bytes = new Uint8Array(buffer);
  var binary = "";
  for (var i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/* ── Audio state indicator ────────────────────────── */

function updateAudioState(state) {
  let indicator = document.getElementById("audio-indicator");
  if (!indicator) {
    indicator = document.createElement("span");
    indicator.id = "audio-indicator";
    indicator.className = "audio-indicator";
    document.getElementById("status-bar").appendChild(indicator);
  }
  if (state === "playing") {
    indicator.textContent = "Playing";
    indicator.title = "Audio playing";
    indicator.setAttribute("aria-label", "Audio playing");
  } else if (state === "recording") {
    indicator.textContent = "Recording";
    indicator.title = "Microphone recording";
    indicator.setAttribute("aria-label", "Microphone recording");
  } else if (state === "error") {
    indicator.textContent = "Audio error";
    indicator.title = "Audio error";
    indicator.setAttribute("aria-label", "Audio error");
  } else {
    indicator.textContent = "";
    indicator.title = "";
    indicator.removeAttribute("aria-label");
  }
}

/* ── Disconnect banner ────────────────────────── */

function showDisconnectBanner() {
  let banner = document.getElementById("disconnect-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "disconnect-banner";
    banner.setAttribute("role", "alert");
    document.getElementById("app").prepend(banner);
  }
  // #23 — Include progress context in disconnect banner
  banner.textContent = "";
  var msgSpan = document.createTextNode("Connection interrupted. ");
  banner.appendChild(msgSpan);
  if (drillCount > 0 && drillTotal > 0) {
    var progressSpan = document.createElement("span");
    progressSpan.className = "banner-progress";
    progressSpan.textContent = "(" + drillCount + " of " + drillTotal + " completed) ";
    banner.appendChild(progressSpan);
  }
  var resumeBtn = document.createElement("button");
  resumeBtn.textContent = "Resume";
  resumeBtn.addEventListener("click", function() {
    hideDisconnectBanner();
    if (lastSessionType) connectWebSocket(lastSessionType);
  });
  banner.appendChild(resumeBtn);
  var reloadBtn = document.createElement("button");
  reloadBtn.textContent = "Reload";
  reloadBtn.addEventListener("click", function() { location.reload(); });
  banner.appendChild(reloadBtn);
  banner.classList.remove("hidden");
}

function showPermanentReloadBanner() {
  let banner = document.getElementById("disconnect-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "disconnect-banner";
    banner.setAttribute("role", "alert");
    document.getElementById("app").prepend(banner);
  }
  banner.textContent = "";
  banner.appendChild(document.createTextNode("Connection could not be restored. "));
  if (drillCount > 0 && drillTotal > 0) {
    var progressSpan = document.createElement("span");
    progressSpan.className = "banner-progress";
    progressSpan.textContent = "(" + drillCount + " of " + drillTotal + " completed) ";
    banner.appendChild(progressSpan);
  }
  var retryBtn = document.createElement("button");
  retryBtn.textContent = "Retry";
  retryBtn.addEventListener("click", function() {
    reconnectAttempts = 0;
    hideDisconnectBanner();
    if (lastSessionType) connectWebSocket(lastSessionType);
  });
  banner.appendChild(retryBtn);
  var reloadBtn2 = document.createElement("button");
  reloadBtn2.textContent = "Reload";
  reloadBtn2.addEventListener("click", function() { location.reload(); });
  banner.appendChild(reloadBtn2);
  banner.classList.remove("hidden");
}

/* ── Fetch error toast with retry ── */
function showFetchError(action, retryFn) {
  var existing = document.getElementById("fetch-error-toast");
  if (existing) existing.remove();
  var toast = document.createElement("div");
  toast.id = "fetch-error-toast";
  toast.setAttribute("role", "alert");
  toast.textContent = (action || "Request") + " failed. ";
  if (typeof retryFn === "function") {
    var btn = document.createElement("button");
    btn.textContent = "Retry";
    btn.addEventListener("click", function() {
      toast.remove();
      retryFn();
    });
    toast.appendChild(btn);
  }
  var dismiss = document.createElement("button");
  dismiss.textContent = "\u00d7";
  dismiss.className = "toast-dismiss";
  dismiss.addEventListener("click", function() { toast.remove(); });
  toast.appendChild(dismiss);
  (document.getElementById("app") || document.body).appendChild(toast);
  setTimeout(function() { if (toast.parentNode) toast.remove(); }, 8000);
}

function hideDisconnectBanner() {
  if (_reconnectCountdownTimer) { clearInterval(_reconnectCountdownTimer); _reconnectCountdownTimer = null; }
  var banner = document.getElementById("disconnect-banner");
  if (!banner || banner.classList.contains("hidden")) return;
  // Exit animation: fade + slide up, then hide
  banner.classList.add("banner-exit");
  setTimeout(function() {
    banner.classList.add("hidden");
    banner.classList.remove("banner-exit");
  }, DURATION_FAST);
}

/* ── Network change listener — early WS reconnect on WiFi↔cellular switch ── */
(function() {
  var conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  if (conn) {
    conn.addEventListener("change", function() {
      if (sessionActive && ws && ws.readyState !== WebSocket.OPEN && ws.readyState !== WebSocket.CONNECTING) {
        _debugLog.log("[net] connection changed, triggering early reconnect");
        reconnectAttempts = 0;
        if (lastSessionType) connectWebSocket(lastSessionType);
      }
    });
  }
})();

function getUserFriendlyError(type) {
  return {
    "timeout": "Server took too long. Try again.",
    "offline": "You're offline. Work saved for later.",
    "auth": "Session expired. Please log in.",
    "server": "Server problem \u2014 reported automatically.",
    "ws_closed": "Connection lost. Reconnecting\u2026"
  }[type] || "Something unexpected. Try refreshing.";
}

function showSessionError(message) {
  /* Show a fatal session error with a "Back to dashboard" button. */
  if (AeluSound.instance) AeluSound.instance.errorAlert();
  addMessage(message, "msg msg-wrong");
  var area = document.getElementById("drill-area");
  if (!area) return;
  var errDiv = document.createElement("div");
  errDiv.className = "session-error-actions";
  var backBtn = document.createElement("button");
  backBtn.className = "btn-primary";
  backBtn.textContent = "Back to dashboard";
  backBtn.addEventListener("click", function() {
    transitionTo("session", "dashboard", function() {
      loadDashboardPanels();
    });
  });
  errDiv.appendChild(backBtn);
  area.appendChild(errDiv);
}

// Keyboard shortcuts: Enter, Q, B, ?, N, R, M, 1-4
document.addEventListener("keydown", function(e) {
  // Escape — close modals, open panels, tooltips (works from any context)
  if (e.key === "Escape") {
    // Close shortcut overlay
    var shortcutOverlay = document.getElementById("shortcut-overlay");
    if (shortcutOverlay) { shortcutOverlay.remove(); e.preventDefault(); return; }
    // Close upgrade modal
    var upgradeModal = document.getElementById("upgrade-modal");
    if (upgradeModal) {
      var dismissBtn = upgradeModal.querySelector(".upgrade-dismiss");
      if (dismissBtn) dismissBtn.click();
      e.preventDefault();
      return;
    }
    // Close join-classroom modal
    var modal = document.getElementById("join-classroom-modal");
    if (modal && !modal.classList.contains("hidden")) {
      modal.classList.add("hidden");
      e.preventDefault();
      return;
    }
    // Close NPS survey modal
    var npsModal = document.getElementById("nps-modal");
    if (npsModal) {
      var npsDismiss = npsModal.querySelector(".nps-dismiss");
      if (npsDismiss) npsDismiss.click();
      e.preventDefault();
      return;
    }
    // Close mastery criteria modal
    var masteryModal = document.getElementById("mastery-modal");
    if (masteryModal) {
      masteryModal.remove();
      e.preventDefault();
      return;
    }
    // Close report-a-problem modal
    var reportModal = document.getElementById("report-modal");
    if (reportModal && !reportModal.classList.contains("hidden")) {
      var reportClose = reportModal.querySelector(".report-close");
      if (reportClose) reportClose.click();
      e.preventDefault();
      return;
    }
    // Dismiss onboarding checklist
    var onboarding = document.getElementById("onboarding-checklist");
    if (onboarding && !onboarding.classList.contains("hidden")) {
      var onbDismiss = document.getElementById("onboarding-dismiss");
      if (onbDismiss) onbDismiss.click();
      e.preventDefault();
      return;
    }
    // Close any open collapsible panel
    var openPanels = document.querySelectorAll(".panel-body:not(.panel-closed)");
    if (openPanels.length > 0) {
      var lastOpen = openPanels[openPanels.length - 1];
      var panelId = lastOpen.id;
      if (panelId && typeof togglePanel === "function") {
        togglePanel(panelId);
        e.preventDefault();
        return;
      }
    }
    // Close mastery tooltip
    var tooltip = document.getElementById("mastery-tooltip");
    if (tooltip && tooltip.classList.contains("visible")) {
      tooltip.classList.remove("visible");
      e.preventDefault();
      return;
    }
    return;
  }

  // Ignore when typing in input fields (except answer-input for Enter)
  var tag = (e.target.tagName || "").toLowerCase();
  var isTextInput = (tag === "textarea" || (tag === "input" && e.target.id !== "answer-input"));
  if (isTextInput) return;

  var isAnswerFocused = (tag === "input" && e.target.id === "answer-input");
  var onDashboard = !sessionActive && !document.getElementById("dashboard").classList.contains("hidden");

  if (e.key === "Enter") {
    if (currentPromptId) {
      e.preventDefault();
      submitAnswer();
    } else if (onDashboard) {
      e.preventDefault();
      startSession("standard");
    }
    return;
  }

  // Don't intercept letter/symbol keys while user is typing an answer
  if (isAnswerFocused) return;

  // #20 — M key starts mini session from dashboard
  if ((e.key === "m" || e.key === "M") && onDashboard && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    startSession("mini");
    return;
  }

  // ? key on dashboard — show keyboard shortcut overlay
  if (e.key === "?" && !sessionActive && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    toggleShortcutOverlay();
    return;
  }

  // Session-only shortcuts (only when prompt is active)
  if (!sessionActive || !currentPromptId) return;

  // #19 — Number keys 1-4 for MC options
  if (_currentMcMode && e.key >= "1" && e.key <= "9") {
    var optBtns = document.querySelectorAll("#option-buttons .btn-option:not(.btn-option-replay)");
    var idx = parseInt(e.key) - 1;
    if (idx < optBtns.length) {
      e.preventDefault();
      optBtns[idx].click();
    }
    return;
  }

  // Shortcut keys Q, B, ?, N — only in free-text mode (not MC)
  if (!_currentMcMode) {
    var shortcutMap = {"q": "Q", "b": "B", "?": "?", "n": "N"};
    var mapped = shortcutMap[e.key.toLowerCase()];
    if (mapped && !e.ctrlKey && !e.metaKey) {
      // #8 — Done confirmation for Q
      if (mapped === "Q") {
        e.preventDefault();
        handleDoneShortcut();
        return;
      }
      // #29 — Hint first-use disclosure
      if (mapped === "?") {
        e.preventDefault();
        handleHintShortcut();
        return;
      }
      e.preventDefault();
      quickAnswer(mapped);
    }
  }
});

/* ── #8 Done confirmation + #29 Hint first-use ────────────────────────── */

function handleDoneShortcut() {
  confirmEndSession();
}

function confirmEndSession() {
  var m = document.querySelector(".confirm-modal");
  if (m) m.remove();
  m = document.createElement("div");
  m.className = "confirm-modal";
  m.innerHTML = '<div class="confirm-modal-content">' +
    '<p style="font-weight:600">End this session?</p>' +
    '<p class="confirm-detail">Your progress is saved.</p>' +
    '<div style="display:flex;gap:0.5rem;justify-content:center">' +
    '<button class="btn btn-primary" id="cey">End session</button>' +
    '<button class="btn btn-secondary" id="cen">Keep going</button>' +
    '</div></div>';
  document.body.appendChild(m);
  document.getElementById("cey").onclick = function() { m.remove(); quickAnswer("Q"); };
  document.getElementById("cen").onclick = function() { m.remove(); };
  m.onclick = function(e) { if (e.target === m) m.remove(); };
}

function handleHintShortcut() {
  try {
    _hintUsedBefore = localStorage.getItem("hintUsedBefore") === "true";
  } catch (e) {}
  if (!_hintUsedBefore) {
    // #29 — Show tooltip on first hint use
    var hintBtn = document.querySelector('.btn-shortcut[data-quick="?"]');
    if (hintBtn) {
      hintBtn.style.position = "relative";
      var tip = document.createElement("div");
      tip.className = "hint-tooltip";
      tip.textContent = "Narrows the choices. You\u2019ll still get most of the credit.";
      hintBtn.appendChild(tip);
      setTimeout(function() { if (tip.parentNode) tip.remove(); }, 3000);
    }
    try { localStorage.setItem("hintUsedBefore", "true"); } catch (e) {}
    _hintUsedBefore = true;
  }
  if (AeluSound.instance) AeluSound.instance.hintReveal();
  quickAnswer("?");
}

/* ── Dark mode toggle ── */
function toggleDarkMode() {
  var t = document.documentElement.getAttribute("data-theme");
  var next = t === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  document.documentElement.style.backgroundColor = next === "dark" ? "#1C2028" : "#F2EBE0";
  var m = document.getElementById("meta-theme-color");
  if (m) m.setAttribute("content", next === "dark" ? "#1C2028" : "#F2EBE0");
  try { localStorage.setItem("aelu-theme", next); } catch (e) {}
  _updateDarkModeIcon();
}
function _updateDarkModeIcon() {
  var icon = document.getElementById("dark-mode-icon");
  if (!icon) return;
  var isDark = document.documentElement.getAttribute("data-theme") === "dark";
  icon.textContent = isDark ? "\u2600\uFE0F" : "\uD83C\uDF19";
}
document.addEventListener("DOMContentLoaded", function() { _updateDarkModeIcon(); });

/* ── Keyboard shortcut help overlay ── */
function toggleShortcutOverlay() {
  var existing = document.getElementById("shortcut-overlay");
  if (existing) { existing.remove(); return; }
  var overlay = document.createElement("div");
  overlay.id = "shortcut-overlay";
  overlay.innerHTML =
    '<div class="shortcut-overlay-inner">' +
    '<h3>Keyboard Shortcuts</h3>' +
    '<div class="shortcut-section"><h4>Dashboard</h4>' +
    '<dl>' +
    '<dt><kbd>Enter</kbd></dt><dd>Start review session</dd>' +
    '<dt><kbd>M</kbd></dt><dd>Start mini session</dd>' +
    '<dt><kbd>?</kbd></dt><dd>Toggle this overlay</dd>' +
    '</dl></div>' +
    '<div class="shortcut-section"><h4>During Session</h4>' +
    '<dl>' +
    '<dt><kbd>1</kbd>\u2013<kbd>4</kbd></dt><dd>Select MC option</dd>' +
    '<dt><kbd>Enter</kbd></dt><dd>Submit answer</dd>' +
    '<dt><kbd>N</kbd></dt><dd>Skip drill</dd>' +
    '<dt><kbd>B</kbd></dt><dd>Show breakdown</dd>' +
    '<dt><kbd>?</kbd></dt><dd>Get a hint</dd>' +
    '<dt><kbd>Q</kbd></dt><dd>End session</dd>' +
    '</dl></div>' +
    '<div class="shortcut-section"><h4>Anywhere</h4>' +
    '<dl>' +
    '<dt><kbd>Esc</kbd></dt><dd>Close modal / panel</dd>' +
    '</dl></div>' +
    '<button class="shortcut-overlay-close">\u00d7</button>' +
    '</div>';
  overlay.addEventListener("click", function(e) {
    if (e.target === overlay || e.target.classList.contains("shortcut-overlay-close"))
      overlay.remove();
  });
  (document.getElementById("app") || document.body).appendChild(overlay);
}

/* End session button is now inside the shortcuts bar with data-quick="Q",
   handled by the unified data-quick click handler below. */

/* ── Panel toggle with localStorage persistence ────────────────────────── */

function togglePanel(panelId) {
  var panel = document.getElementById(panelId);
  if (!panel) return;
  var body = panel.querySelector(".panel-body");
  var icon = panel.querySelector(".toggle-icon");
  var toggle = panel.querySelector(".panel-toggle") || panel.querySelector("h3");
  if (!body) return;

  if (body.classList.contains("panel-closed")) {
    // Opening: set max-height to 0 (current state), remove closed class,
    // reflow, then set max-height to actual content height for accurate timing.
    body.style.maxHeight = "0px";
    body.classList.remove("panel-closed");
    body.offsetHeight; // force reflow
    body.style.maxHeight = body.scrollHeight + "px";
    if (icon) icon.innerHTML = '<svg class="icon"><use href="#icon-minus"/></svg>';
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    savePanelState(panelId, true);
  } else {
    // Closing: capture current height, reflow, then animate to 0.
    body.style.maxHeight = body.scrollHeight + "px";
    body.offsetHeight; // force reflow
    body.style.maxHeight = "0px";
    body.style.opacity = "0";
    body.style.marginTop = "0";
    if (icon) icon.innerHTML = '<svg class="icon"><use href="#icon-plus"/></svg>';
    if (toggle) toggle.setAttribute("aria-expanded", "false");
    savePanelState(panelId, false);
    // After transition completes, apply closed class and clean up inline styles
    var onEnd = function(e) {
      if (e.propertyName !== "max-height") return;
      body.removeEventListener("transitionend", onEnd);
      body.classList.add("panel-closed");
      body.style.maxHeight = "";
      body.style.opacity = "";
      body.style.marginTop = "";
    };
    body.addEventListener("transitionend", onEnd);
  }
}

function panelKeyHandler(event, panelId) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    togglePanel(panelId);
  }
}

function savePanelState(panelId, open) {
  try {
    const states = JSON.parse(localStorage.getItem("panelStates") || "{}");
    states[panelId] = open;
    localStorage.setItem("panelStates", JSON.stringify(states));
  } catch (e) {
    // localStorage might be unavailable
  }
}

function restorePanelStates() {
  try {
    var states = JSON.parse(localStorage.getItem("panelStates") || "{}");
    for (var panelId in states) {
      if (states[panelId]) {
        openPanelImmediate(panelId);
      }
    }
  } catch (e) {
    // localStorage might be unavailable
  }
}

function updatePanelHeight(panelId) {
  /* After content changes (API fetch), update max-height so future close transitions are accurate. */
  var panel = document.getElementById(panelId);
  if (!panel) return;
  var body = panel.querySelector(".panel-body");
  if (body && !body.classList.contains("panel-closed") && body.style.maxHeight !== "none") {
    body.style.maxHeight = body.scrollHeight + "px";
  }
}

function openPanelImmediate(panelId) {
  /* Open a panel without transition — used on page load restore and auto-expand. */
  var panel = document.getElementById(panelId);
  if (!panel) return;
  var body = panel.querySelector(".panel-body");
  var icon = panel.querySelector(".toggle-icon");
  var toggle = panel.querySelector(".panel-toggle") || panel.querySelector("h3");
  if (!body) return;
  body.classList.remove("panel-closed");
  body.style.maxHeight = "none"; // natural height, no transition on initial render
  if (icon) icon.innerHTML = '<svg class="icon"><use href="#icon-minus"/></svg>';
  if (toggle) toggle.setAttribute("aria-expanded", "true");
}

/* ── Sparkline helper ────────────────────────── */

function makeSparkline(values) {
  /* Generate an inline SVG polyline sparkline from 0-100 values. */
  if (!values || values.length === 0) return "";
  var w = values.length * 8;
  var h = 20;
  var points = [];
  for (var i = 0; i < values.length; i++) {
    var x = i * 8 + 4;
    var y = h - (values[i] / 100) * (h - 2) - 1;
    points.push(x.toFixed(1) + "," + y.toFixed(1));
  }
  return '<svg viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h + '" ' +
    'style="vertical-align:middle" aria-hidden="true">' +
    '<polyline points="' + points.join(" ") + '" fill="none" stroke="var(--color-accent)" ' +
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}

/* ── Dashboard data panels ────────────────────────── */

function autoExpandOnDesktop() {
  // On desktop (>=768px), auto-expand panels if user has no saved preference
  if (window.innerWidth < 768) return;
  try {
    var states = JSON.parse(localStorage.getItem("panelStates") || "{}");
    if (Object.keys(states).length > 0) return; // user has preferences, respect them
  } catch (e) {}
  // No saved preferences on desktop — expand all panels
  ["forecast-panel", "retention-panel", "sessions-panel"].forEach(function(panelId) {
    openPanelImmediate(panelId);
  });
}

// #17 — Auto-expand forecast for returning users (any screen size)
function autoExpandForecastForReturning() {
  try {
    var states = JSON.parse(localStorage.getItem("panelStates") || "{}");
    // Only auto-expand if user hasn't explicitly closed it
    if (states["forecast-panel"] === false) return;
  } catch (e) {}
  // Check if user has sessions (returning user) — use stat from page
  var sessionsEl = document.querySelector('.stat-value');
  if (sessionsEl) {
    var sessions = parseInt(sessionsEl.textContent) || 0;
    // The second stat is total sessions
    var allStats = document.querySelectorAll('.stat-value');
    if (allStats.length >= 2) {
      var totalSessions = parseInt(allStats[1].textContent) || 0;
      if (totalSessions > 0) {
        openPanelImmediate("forecast-panel");
      }
    }
  }
}

function loadDashboardPanels() {
  // Restore saved panel states first, then auto-expand on desktop
  restorePanelStates();
  autoExpandOnDesktop();
  autoExpandForecastForReturning();
  // Fetch all panel data in parallel
  fetchSessionPreview();
  fetchForecast();
  fetchProgress();
  fetchDiagnostics();
  fetchSessions();
  fetchEncounterStats();
  // Highlight mastery bar changes after a session
  highlightMasteryDeltas();
  // Upgrade banner for free users (after session 2)
  showDashboardUpgradeBanner();
}

function fetchSessionPreview() {
  var el = document.getElementById("next-session-preview");
  if (!el) return;
  apiFetch("/api/session-preview").then(function(r) { return r.json(); }).then(function(data) {
    if (!data) { el.classList.add("hidden"); return; }
    var items = [];

    // Error focus
    if (data.error_focus_count) {
      var types = data.error_focus_types || {};
      var parts = [];
      for (var et in types) {
        var label = {tone: "tone", segment: "segmentation", ime_confusable: "typing",
                     vocab: "vocabulary", grammar: "grammar"}[et] || et;
        parts.push(types[et] + " " + label);
      }
      items.push("Targeting " + data.error_focus_count + " items you keep missing" + (parts.length ? " (" + parts.join(", ") + ")" : ""));
    }

    // Encounter boost
    if (data.encounter_boost_count) {
      items.push("Reinforcing " + data.encounter_boost_count + " words from your reading");
    }

    // Tone accuracy
    if (data.tone_accuracy != null && data.tone_accuracy < 65) {
      items.push("Extra speaking practice \u2014 tone accuracy at " + data.tone_accuracy + "%");
    }

    // Day mode
    if (data.day_note) {
      items.push(data.day_note);
    }

    // Days since last
    if (data.days_since_last != null && data.days_since_last >= 3) {
      items.push("Welcome back \u2014 starting with familiar items");
    }

    if (items.length === 0) {
      el.classList.add("hidden");
      return;
    }

    var html = '<div class="session-preview-header">Next session</div>';
    html += '<ul class="session-preview-list">';
    for (var i = 0; i < Math.min(items.length, 3); i++) {
      html += '<li>' + escapeHtml(items[i]) + '</li>';
    }
    html += '</ul>';
    el.innerHTML = html;
    el.classList.remove("hidden");
  }).catch(function() { if (el) el.classList.add("hidden"); });
}


function showDashboardUpgradeBanner() {
  var existing = document.getElementById("upgrade-banner");
  if (existing) existing.remove();
  var totalSessions = window._totalSessionsBefore;
  if (totalSessions == null || totalSessions < 2) return;
  isFreeTier().then(function(free) {
    if (!free) return;
    var banner = document.createElement("div");
    banner.id = "upgrade-banner";
    banner.className = "upgrade-banner";
    banner.innerHTML =
      '<span class="upgrade-banner-text">You\u2019re on HSK 1\u20132. Unlock HSK 3\u20139 + adaptive scheduling.</span>'
      + '<button class="upgrade-banner-cta">$' + ((window.AELU_PRICING && window.AELU_PRICING.annual) || '149') + '/year</button>';
    banner.querySelector(".upgrade-banner-cta").addEventListener("click", function() {
      showUpgradePrompt("hsk_3_plus");
    });
    var target = document.getElementById("hsk-progress-bars") || document.querySelector(".mastery-bars");
    if (target) {
      target.parentNode.insertBefore(banner, target.nextSibling);
    }
  });
}

function highlightMasteryDeltas() {
  if (!_preMastery || Object.keys(_preMastery).length === 0) return;
  fetch("/api/status").then(function(r) { return r.json(); }).then(function(st) {
    var mastery = st.mastery || {};
    document.querySelectorAll(".mastery-bar-row").forEach(function(row) {
      var level = row.getAttribute("data-hsk");
      if (!level || !_preMastery[level] || !mastery[level]) return;
      var prePct = Math.round(_preMastery[level].pct || 0);
      var nowPct = Math.round(mastery[level].pct || 0);
      var diff = nowPct - prePct;
      if (diff <= 0) return;
      // Add a delta badge
      var existing = row.querySelector(".mastery-delta");
      if (existing) existing.remove();
      var badge = document.createElement("span");
      badge.className = "mastery-delta";
      badge.textContent = "+" + diff + "%";
      row.appendChild(badge);
      // Add a subtle glow to the bar
      var bar = row.querySelector(".mastery-bar");
      if (bar) bar.classList.add("mastery-bar-glow");
    });
    // Clear pre-mastery so we don't re-highlight on subsequent panel loads
    _preMastery = null;
  }).catch(function() {});
}

function _renderSimpleForecast(forecastData) {
  // Show a simple first-week projection instead of "assessing"
  fetch("/api/status").then(function(r) { return r.json(); }).then(function(status) {
    var sf = status.simple_forecast;
    var html = "";

    // Current modality levels from forecast data (always computed)
    if (forecastData.modality_projections) {
      var modLabels = {reading: "Reading", listening: "Listening", speaking: "Speaking", ime: "Typing", recognition: "Recognition", production: "Production", tone: "Tone"};
      for (var mod in forecastData.modality_projections) {
        var proj = forecastData.modality_projections[mod];
        var cur = proj.current_level || 0;
        if (cur > 0) {
          var modLabel = modLabels[mod] || (mod.charAt(0).toUpperCase() + mod.slice(1));
          html += '<div class="panel-row"><span class="label">' + escapeHtml(modLabel) + '</span>';
          html += '<span class="value">Level ' + cur.toFixed(1) + '</span></div>';
        }
      }
    }

    // Simple projection from status
    if (sf) {
      var wordsLT = sf.words_long_term || 0;
      html += '<div class="panel-row"><span class="label">Words in long-term memory</span>';
      html += '<span class="value">' + wordsLT + '</span></div>';

      if (sf.next_milestone && sf.sessions_to_milestone) {
        html += '<div class="panel-row"><span class="label">Next: ' + sf.next_milestone + ' words</span>';
        html += '<span class="value">~' + sf.sessions_to_milestone + ' session' + (sf.sessions_to_milestone !== 1 ? 's' : '') + '</span></div>';
      }
    }

    // Progress toward full forecast unlock
    var totalSessions = status.total_sessions || 0;
    var unlockPct = Math.min(100, Math.round(totalSessions / 8 * 100));
    html += '<div class="panel-row panel-row-dim"><span class="label">' + totalSessions + ' of 8 sessions toward detailed forecasts</span></div>';
    html += '<div class="forecast-timeline" aria-label="Progress toward forecast unlock">';
    html += '<div class="forecast-bar">';
    html += '<div class="forecast-fill forecast-fill-animate" style="width:' + unlockPct + '%"></div>';
    html += '</div></div>';

    if (html) {
      replaceContent("forecast-content", html);
    } else {
      showPanelError("forecast-content", "Unlocks with more sessions.");
    }
  }).catch(function() {
    showPanelError("forecast-content", "Unlocks with more sessions.");
  });
}

function fetchForecast() {
  fetch("/api/forecast")
    .then(function(r) {
      if (r.status === 403) {
        showUpgradePrompt("forecast");
        showPanelError("forecast-content", "Upgrade for forecast access.");
        throw new Error("tier_gate");
      }
      return r.json();
    })
    .then(data => {
      if (data.error) {
        showPanelError("forecast-content", "Unlocks with more sessions.");
        return;
      }
      const content = document.getElementById("forecast-content");
      let html = "";

      // For early users (pace not yet reliable), show simple forecast from /api/status
      if (data.pace && data.pace.reliable === false) {
        _renderSimpleForecast(data);
        return;
      }

      // Pace display — narrative framing (strip parenthetical judgments)
      if (data.pace && data.pace.message) {
        var paceMsg = data.pace.message.replace(/\s*\((good|low|high|moderate)\)/gi, "");
        html += '<div class="panel-row"><span class="label">' + escapeHtml(paceMsg) + '</span></div>';
      } else if (data.pace_label) {
        var paceLabel = data.pace_label.replace(/\s*\((good|low|high|moderate)\)/gi, "");
        html += '<div class="panel-row"><span class="label">' + escapeHtml(paceLabel) + '</span></div>';
      }

      // Aspirational milestones — show only nearest 2 to avoid overwhelm
      if (data.aspirational && typeof data.aspirational === "object") {
        var aspOrder = ["casual_media", "professional", "advanced", "near_native"];
        var aspLabels = {casual_media: "HSK 4-5", professional: "HSK 6", advanced: "HSK 7-8", near_native: "HSK 9"};
        var aspShown = 0;
        var aspHtml = "";
        for (var ai = 0; ai < aspOrder.length && aspShown < 2; ai++) {
          var aspKey = aspOrder[ai];
          var milestone = data.aspirational[aspKey];
          if (!milestone || !milestone.calendar) continue;
          var calEst = milestone.calendar.expected || "";
          var targetLabel = aspLabels[aspKey] || ("HSK " + (milestone.hsk_target || "?"));

          aspHtml += '<div class="panel-row"><span class="label">' + escapeHtml(targetLabel) + '</span>';
          aspHtml += '<span class="value">' + (calEst || "computing\u2026") + '</span></div>';
          aspShown++;
        }
        if (aspHtml && html) {
          html += '<hr class="panel-section-divider">';
        }
        html += aspHtml;
      }

      // Modality projections — show current levels and milestone timelines
      var htmlBeforeMod = html;
      if (data.modality_projections) {
        var modLabels = {reading: "Reading", listening: "Listening", speaking: "Speaking", ime: "Typing", recognition: "Recognition", production: "Production", tone: "Tone"};
        for (const [mod, proj] of Object.entries(data.modality_projections)) {
          // Skip tone — it has a different structure (tone_error_rate, not current_level)
          if (mod === "tone") continue;
          var msCurrent = proj.current_level || 0;
          var modLabel = modLabels[mod] || (mod.charAt(0).toUpperCase() + mod.slice(1));

          if (proj.milestones && proj.milestones.length > 0) {
            var ms = proj.milestones[0];
            var calStr = (ms.calendar && ms.calendar.expected) || "";
            // Parse target HSK level from string like "HSK 3"
            var msTargetNum = 0;
            if (ms.target && typeof ms.target === "string") {
              var tMatch = ms.target.match(/\d+/);
              if (tMatch) msTargetNum = parseInt(tMatch[0]);
            }

            html += '<div class="panel-row"><span class="label">' + escapeHtml(modLabel) + '</span>';
            html += '<span class="value">' + escapeHtml(calStr || ("Level " + msCurrent.toFixed(1))) + '</span></div>';

            if (msTargetNum > 0) {
              var msPct = Math.min(100, Math.max(0, (msCurrent / msTargetNum) * 100));
              // Ensure tiny progress is still visible (min 1.5%)
              var barPctVis = (msCurrent > 0 && msPct < 1.5) ? 1.5 : msPct;
              html += '<div class="forecast-timeline">';
              html += '<div class="forecast-bar">';
              html += '<div class="forecast-fill" style="width:' + barPctVis.toFixed(1) + '%"></div>';
              html += '<div class="forecast-marker" style="left:' + barPctVis.toFixed(1) + '%"></div>';
              html += '</div>';
              html += '<div class="forecast-timeline-label">';
              html += '<span>' + msCurrent.toFixed(1) + '</span>';
              html += '<span>' + escapeHtml(ms.target) + '</span>';
              html += '</div>';
              html += '</div>';
            }
          } else if (msCurrent > 0) {
            // No milestone target (already at max or not enough data),
            // but still show current level
            html += '<div class="panel-row"><span class="label">' + escapeHtml(modLabel) + '</span>';
            html += '<span class="value">Level ' + msCurrent.toFixed(1) + '</span></div>';
          }
        }

        // Tone projection (separate structure)
        if (data.modality_projections.tone) {
          var tp = data.modality_projections.tone;
          if (tp.tone_error_rate != null) {
            var errPct = Math.round(tp.tone_error_rate * 100);
            var toneVal = errPct + "% error rate";
            if (tp.sessions_est && tp.sessions_est.expected) {
              toneVal += " (~" + tp.sessions_est.expected + " sessions to target)";
            }
            html += '<div class="panel-row"><span class="label">Tone accuracy</span>';
            html += '<span class="value">' + escapeHtml(toneVal) + '</span></div>';
          }
        }
      }
      // Insert divider only if modality section added content
      if (htmlBeforeMod && html !== htmlBeforeMod) {
        html = htmlBeforeMod + '<hr class="panel-section-divider">' + html.slice(htmlBeforeMod.length);
      }

      // Legacy fields (backward compat)
      if (!html && data.next_milestone) {
        html += '<div class="panel-row"><span class="label">Next milestone</span><span class="value">' + escapeHtml(data.next_milestone) + '</span></div>';
      }
      if (data.hsk_projections) {
        for (const [level, proj] of Object.entries(data.hsk_projections)) {
          if (proj.weeks_remaining != null) {
            html += '<div class="panel-row"><span class="label">HSK ' + level + '</span><span class="value">' + proj.weeks_remaining + ' weeks</span></div>';
          }
        }
      }

      if (html) {
        replaceContent("forecast-content", html);
      } else {
        showPanelError("forecast-content", "Unlocks with more sessions.");
      }
    })
    .catch(function() {
      showPanelError("forecast-content", "Unlocks with more sessions.");
    });
}

function fetchProgress() {
  fetch("/api/progress")
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        showPanelError("retention-content", "Practice builds the picture.");
        return;
      }
      const content = document.getElementById("retention-content");
      let html = "";
      if (data.retention && data.retention.retention_pct != null) {
        const pct = Math.round(data.retention.retention_pct);
        const totalItems = data.retention.total_items || 0;
        const retainedCount = Math.round(totalItems * pct / 100);
        // Narrative: "Roughly 185 of 220 words you would likely recall if tested now"
        if (totalItems > 0) {
          html += '<div class="panel-row"><span class="label">Estimated recall</span><span class="value">' + pct + '%</span></div>';
          html += '<div class="panel-row panel-row-dim"><span class="label">~' + retainedCount + ' of ' + totalItems + ' words you would likely recall if tested now</span></div>';
        } else {
          html += '<div class="panel-row"><span class="label">Estimated recall</span><span class="value">' + pct + '%</span></div>';
        }
      } else if (data.retention && data.retention.total_items != null) {
        html += '<div class="panel-row"><span class="label">' + data.retention.total_items + ' items tracked</span></div>';
      }
      if (html) {
        replaceContent("retention-content", html);
      } else {
        showPanelError("retention-content", "Practice builds the picture.");
      }
    })
    .catch(function() {
      showPanelError("retention-content", "Practice builds the picture.");
    });
}

function fetchSessions() {
  fetch("/api/sessions")
    .then(r => r.json())
    .then(data => {
      if (data.error || !data.sessions || data.sessions.length === 0) {
        showPanelError("sessions-content", "No sessions yet.");
        // Ensure the panel body is visible so users can see the message
        openPanelImmediate("sessions-panel");
        return;
      }
      const content = document.getElementById("sessions-content");
      let html = "";

      // ── Accuracy sparkline ──
      const recent = data.sessions.slice(0, 10);
      var accuracies = [];
      for (var i = recent.length - 1; i >= 0; i--) {
        var t = recent[i].items_completed || 0;
        var c = recent[i].items_correct || 0;
        accuracies.push(t > 0 ? Math.round(c / t * 100) : 0);
      }
      if (accuracies.length > 1) {
        var spark = makeSparkline(accuracies);
        var firstVal = accuracies[0];
        var lastVal = accuracies[accuracies.length - 1];
        html += '<div class="sparkline-row" aria-label="Accuracy trend sparkline">';
        html += '<span class="sparkline-label">Accuracy trend </span>';
        html += '<span class="sparkline-value">' + firstVal + '%</span> ' + spark + ' <span class="sparkline-value">' + lastVal + '%</span>';
        html += '</div>';
      }

      // ── 14-day study frequency dots ──
      if (data.study_streak_data && data.study_streak_data.length > 0) {
        html += '<div class="frequency-row" aria-label="14-day study frequency">';
        var todayStr = new Date().toISOString().slice(0, 10);
        for (var j = 0; j < data.study_streak_data.length; j++) {
          var day = data.study_streak_data[j];
          var dotClass = "freq-dot";
          if (day.sessions >= 2) dotClass += " active-2";
          else if (day.sessions === 1) dotClass += " active-1";
          else dotClass += " inactive";
          if (day.date === todayStr) dotClass += " today";
          var dotTitle = day.date + ": " + day.sessions + " session" + (day.sessions !== 1 ? "s" : "");
          html += '<span class="' + dotClass + '" title="' + dotTitle + '"></span>';
        }
        html += '<span class="freq-label">14 days</span>';
        html += '</div>';
      }

      // ── Session list (chronicle format) ──
      for (const s of recent) {
        const total = s.items_completed || 0;
        const correct = s.items_correct || 0;
        const pct = total > 0 ? Math.round(correct / total * 100) : 0;

        // Format date as "15 February 2026"
        var dateStr = "\u2014";
        if (s.started_at) {
          var d = new Date(s.started_at);
          if (!isNaN(d.getTime())) {
            var months = ["January","February","March","April","May","June","July","August","September","October","November","December"];
            dateStr = d.getDate() + " " + months[d.getMonth()] + " " + d.getFullYear();
          } else {
            dateStr = s.started_at.substring(0, 10);
          }
        }

        // Narrative score: "18 of 22 recalled"
        var narrative = correct + " of " + total + " recalled";

        // Assessment word based on accuracy
        var assessment = "";
        var assessHint = "";
        if (pct >= 90) { assessment = "Strong"; assessHint = "90%+ — solid recall"; }
        else if (pct >= 75) { assessment = "Steady"; assessHint = "75-89% — good progress"; }
        else if (pct >= 55) { assessment = "Building"; assessHint = "55-74% — working through harder material"; }
        else { assessment = "Stretching"; assessHint = "Challenging session — the system is pushing your edge"; }

        var badge = "";
        if (s.session_outcome === "interrupted") {
          badge = ' <span class="session-badge-early">Interrupted</span>';
        } else if (s.session_outcome === "abandoned" || (s.early_exit && !s.session_outcome)) {
          badge = ' <span class="session-badge-early">Ended early</span>';
        }

        html += '<div class="session-history-item" title="' + escapeHtml(assessHint) + '">';
        html += '<span class="session-date">' + dateStr + '</span>';
        html += '<span class="session-narrative">' + narrative + ' (' + pct + '%) \u2014 <span class="session-assessment">' + assessment + '</span>' + badge + '</span>';
        html += '</div>';
      }
      replaceContent("sessions-content", html);
    })
    .catch(function() {
      showPanelError("sessions-content", "No sessions yet.");
    });
}

function fetchDiagnostics() {
  fetch("/api/diagnostics")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        showPanelError("diagnostics-content", "Unlocks after a few sessions.");
        return;
      }
      if (!data.ready) {
        var msg = data.sessions_needed
          ? data.sessions_needed + " more sessions to unlock \u2014 each one sharpens the picture."
          : "Unlocks after a few sessions.";
        showPanelError("diagnostics-content", msg);
        return;
      }
      var levels = data.estimated_levels;
      if (!levels || Object.keys(levels).length === 0) {
        showPanelError("diagnostics-content", "Unlocks after a few sessions.");
        return;
      }

      var modLabels = {
        reading: "Reading",
        listening: "Listening",
        speaking: "Speaking",
        ime: "Typing"
      };

      // Find highest level for relative bar and gap detection
      var maxLevel = 0;
      var maxMod = "";
      for (var mod in levels) {
        if (levels[mod].level > maxLevel) {
          maxLevel = levels[mod].level;
          maxMod = mod;
        }
      }

      var html = "";
      var gaps = [];
      var modOrder = ["reading", "listening", "speaking", "ime"];
      for (var i = 0; i < modOrder.length; i++) {
        var m = modOrder[i];
        if (!levels[m]) continue;
        var lvl = levels[m].level;
        var label = modLabels[m] || m;
        var barPct = maxLevel > 0 ? Math.min(100, (lvl / maxLevel) * 100) : 0;
        var barPctVis2 = (lvl > 0 && barPct < 1.5) ? 1.5 : barPct;

        html += '<div class="panel-row">';
        html += '<span class="label">' + escapeHtml(label) + '</span>';
        html += '<span class="value">HSK ' + lvl.toFixed(1) + '</span>';
        html += '</div>';
        html += '<div class="forecast-timeline" aria-label="' + escapeHtml(label) + ' level">';
        html += '<div class="forecast-bar">';
        html += '<div class="forecast-fill" style="width:' + barPctVis2.toFixed(1) + '%"></div>';
        html += '</div>';
        html += '</div>';

        // Track gaps >= 1.5 levels behind the highest
        var gap = maxLevel - lvl;
        if (gap >= 1.5 && m !== maxMod) {
          gaps.push({
            mod: label,
            behind: Math.round(gap * 10) / 10,
            ahead: modLabels[maxMod] || maxMod
          });
        }
      }

      // Gap indicators (calm, dim)
      if (gaps.length > 0) {
        html += '<div class="diag-gaps">';
        for (var g = 0; g < gaps.length; g++) {
          html += '<div class="panel-row diag-gap-row">';
          html += '<span class="label dim">' + escapeHtml(gaps[g].mod) + ': ' + gaps[g].behind.toFixed(1) + ' levels below ' + escapeHtml(gaps[g].ahead) + ' \u2014 extra practice helps here</span>';
          html += '</div>';
        }
        html += '</div>';
      }

      if (html) {
        replaceContent("diagnostics-content", html);
      } else {
        showPanelError("diagnostics-content", "Unlocks after a few sessions.");
      }
    })
    .catch(function() {
      showPanelError("diagnostics-content", "Unlocks after a few sessions.");
    });
}

function showPanelError(contentId, message) {
  // #26 — Panel errors include a retry button with context
  var retryMap = {
    "forecast-content": fetchForecast,
    "retention-content": fetchProgress,
    "diagnostics-content": fetchDiagnostics,
    "sessions-content": fetchSessions
  };
  var panelNameMap = {
    "forecast-content": "forecast",
    "retention-content": "memory",
    "diagnostics-content": "diagnostics",
    "sessions-content": "sessions"
  };
  var retryFn = retryMap[contentId];
  var panelName = panelNameMap[contentId] || "panel";
  var retryLabel = "Retry loading " + panelName;
  var retryHtml = retryFn ? ' <button class="panel-retry-btn" data-retry="' + contentId + '">' + retryLabel + '</button>' : '';
  replaceContent(contentId, '<div class="empty-state"><img src="' + themedIllustration('/static/illustrations/empty-generic.webp') + '" alt="" class="empty-state-illustration">' + escapeHtml(message) + retryHtml + '</div>');
  var _pEl = document.getElementById(contentId);
  if (_pEl) handleImgErrors(_pEl);
  if (retryFn) {
    var btn = document.querySelector('[data-retry="' + contentId + '"]');
    if (btn) btn.addEventListener("click", function() {
      replaceContent(contentId, '<div class="panel-skeleton"><div class="skeleton-line"></div><div class="skeleton-line short"></div></div>');
      retryFn();
    });
  }
}

function replaceContent(contentId, html) {
  /* Replace innerHTML with a crossfade: content fades in after replacement.
     Also updates panel max-height so close transitions remain accurate. */
  var el = document.getElementById(contentId);
  if (!el) return;
  el.innerHTML = html;
  el.classList.add("content-enter");
  // Update panel height after content change
  var panel = el.closest(".panel");
  if (panel && panel.id) updatePanelHeight(panel.id);
  setTimeout(function() {
    el.classList.remove("content-enter");
  }, DURATION_FAST);
}

// Load dashboard panels on page load
document.addEventListener("DOMContentLoaded", loadDashboardPanels);
document.addEventListener("DOMContentLoaded", function() {
  // Graceful image fallback for static illustrations
  handleImgErrors(document.getElementById("dashboard"));

  // Dashboard hero dismiss
  var heroEl = document.getElementById("dashboard-hero");
  var heroDismiss = document.getElementById("dashboard-hero-dismiss");
  if (heroEl && heroDismiss) {
    // Check if previously dismissed
    try {
      if (localStorage.getItem("aelu-dashboard-hero-dismissed") === "1") {
        heroEl.remove();
      }
    } catch (e) {}
    heroDismiss.addEventListener("click", function() {
      heroEl.style.transition = "opacity 0.3s, transform 0.3s";
      heroEl.style.opacity = "0";
      heroEl.style.transform = "translateY(-8px)";
      setTimeout(function() { heroEl.remove(); }, 300);
      try { localStorage.setItem("aelu-dashboard-hero-dismissed", "1"); } catch (e) {}
    });
  }
});

/* ── Time-of-day theme switching ────────────────────────── */
/* Dark between 7pm and 7am local time. Checked on load and every 60s.
   Sets data-theme on <html> which overrides @media (prefers-color-scheme). */

var DARK_START_HOUR = 19;  // 7pm
var DARK_END_HOUR = 7;     // 7am

function applyTimeTheme() {
  var hour = new Date().getHours();
  var isDark = (hour >= DARK_START_HOUR || hour < DARK_END_HOUR);
  var theme = isDark ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", theme);
  // Sync root background to prevent flash when CSS hasn't loaded yet
  document.documentElement.style.backgroundColor = isDark ? "#1C2028" : "#F2EBE0";
  // Update single meta theme-color to match
  var meta = document.getElementById("meta-theme-color");
  if (meta) meta.setAttribute("content", isDark ? "#1C2028" : "#F2EBE0");
}

// Apply immediately (before DOMContentLoaded to minimize flash)
applyTimeTheme();
// Re-check every 60 seconds for hour boundary crossings
var _timeThemeInterval = setInterval(applyTimeTheme, 60000);

/* ── High-contrast mode ────────────────────────── */

function applyContrastMode() {
  var saved = null;
  try { saved = localStorage.getItem("contrastMode"); } catch (e) {}
  if (saved === "high") {
    document.documentElement.setAttribute("data-contrast", "high");
  } else {
    document.documentElement.removeAttribute("data-contrast");
  }
}

function toggleContrastMode() {
  var current = document.documentElement.getAttribute("data-contrast");
  var newMode = current === "high" ? "normal" : "high";
  try { localStorage.setItem("contrastMode", newMode); } catch (e) {}
  if (newMode === "high") {
    document.documentElement.setAttribute("data-contrast", "high");
  } else {
    document.documentElement.removeAttribute("data-contrast");
  }
  // Update button text if it exists
  var btn = document.getElementById("btn-contrast");
  if (btn) {
    btn.textContent = newMode === "high" ? "Standard contrast" : "High contrast";
  }
  return newMode;
}

// Apply immediately (before DOMContentLoaded to minimize flash)
applyContrastMode();

/* ── Exposure views: Reading, Media, Listening ────────────────────────── */

var _readingPassages = [];
var _readingIndex = 0;
var _readingWordsLookedUp = 0;
var _readingStartTime = null;
var _currentPassageId = null;
var _readingQuizScore = null;  // {correct, total} from MC questions

function backToDashboardFrom(viewId) {
  var viewEl = document.getElementById(viewId);
  var dashEl = document.getElementById("dashboard");
  if (viewEl) viewEl.classList.add("hidden");
  if (dashEl) dashEl.classList.remove("hidden");
  // Restore full header when returning to main dashboard
  document.getElementById("app").classList.remove("subview-active");
}

/* ── Reading View ──────────────────────────────── */

function showFeatureTooltip(featureKey, message) {
  var storageKey = "aelu_seen_" + featureKey;
  try { if (localStorage.getItem(storageKey)) return; } catch (e) { return; }
  var tip = document.createElement("div");
  tip.className = "feature-tooltip";
  tip.innerHTML = '<p>' + message + '</p><button class="btn-link btn-sm feature-tooltip-dismiss">Got it</button>';
  tip.querySelector(".feature-tooltip-dismiss").addEventListener("click", function() {
    tip.classList.add("feature-tooltip-exit");
    setTimeout(function() { tip.remove(); }, 300);
    try { localStorage.setItem(storageKey, "1"); } catch (e) {}
  });
  // Auto-dismiss after 8 seconds
  setTimeout(function() {
    if (tip.parentNode) {
      tip.classList.add("feature-tooltip-exit");
      setTimeout(function() { tip.remove(); }, 300);
      try { localStorage.setItem(storageKey, "1"); } catch (e) {}
    }
  }, 8000);
  var area = document.querySelector(".section-visible") || document.getElementById("app");
  area.appendChild(tip);
}

/* ── Display preference persistence ──────────── */
var _displayPrefs = { reading_show_pinyin: false, reading_show_translation: false };
var _displayPrefsSaveTimer = null;

function loadDisplayPrefs(callback) {
  apiFetch("/api/settings/display-prefs")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _displayPrefs.reading_show_pinyin = !!data.reading_show_pinyin;
      _displayPrefs.reading_show_translation = !!data.reading_show_translation;
      if (callback) callback();
    })
    .catch(function() { if (callback) callback(); });
}

function saveDisplayPrefs(field, value) {
  _displayPrefs[field] = value;
  if (_displayPrefsSaveTimer) clearTimeout(_displayPrefsSaveTimer);
  _displayPrefsSaveTimer = setTimeout(function() {
    var body = {};
    body[field] = value;
    apiFetch("/api/settings/display-prefs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }, 300);
}

function applyDisplayPrefsToToggles() {
  var pinyinCb = document.getElementById("reading-pinyin-toggle");
  var transCb = document.getElementById("reading-translation-toggle");
  if (pinyinCb) pinyinCb.checked = _displayPrefs.reading_show_pinyin;
  if (transCb) transCb.checked = _displayPrefs.reading_show_translation;
  // Apply visibility to passage elements if they exist
  var pinyinEl = document.getElementById("reading-pinyin");
  var transEl = document.getElementById("reading-translation");
  if (pinyinEl) pinyinEl.classList.toggle("hidden", !_displayPrefs.reading_show_pinyin);
  if (transEl) transEl.classList.toggle("hidden", !_displayPrefs.reading_show_translation);
}

function openReadingView() {
  EventLog.record("view", "reading");
  transitionTo("dashboard", "reading");
  _readingWordsLookedUp = 0;
  _readingStartTime = Date.now();
  loadPassageList();
  _fetchReadingStats();
  showFeatureTooltip("reading", "Tap any character to look it up. Words you look up become drills in your next session.");

  // Load saved display preferences and apply to toggles
  loadDisplayPrefs(function() {
    applyDisplayPrefsToToggles();
  });

  // Level filter
  var levelSelect = document.getElementById("reading-level");
  if (levelSelect) {
    levelSelect.removeEventListener("change", onReadingLevelChange);
    levelSelect.addEventListener("change", onReadingLevelChange);
  }
  // Pinyin toggle
  var pinyinToggle = document.getElementById("reading-pinyin-toggle");
  if (pinyinToggle) {
    pinyinToggle.removeEventListener("change", onPinyinToggle);
    pinyinToggle.addEventListener("change", onPinyinToggle);
  }
  // Translation toggle
  var transToggle = document.getElementById("reading-translation-toggle");
  if (transToggle) {
    transToggle.removeEventListener("change", onTranslationToggle);
    transToggle.addEventListener("change", onTranslationToggle);
  }
  // Nav buttons
  var prevBtn = document.getElementById("reading-prev");
  var nextBtn = document.getElementById("reading-next");
  if (prevBtn) { prevBtn.onclick = function() { navigatePassage(-1); }; }
  if (nextBtn) { nextBtn.onclick = function() { navigatePassage(1); }; }

  // Analyze Text panel
  var analyzeToggle = document.getElementById("reading-analyze-toggle");
  if (analyzeToggle) {
    analyzeToggle.onclick = function() {
      var panel = document.getElementById("reading-analyze-panel");
      var expanded = panel.classList.contains("hidden");
      panel.classList.toggle("hidden");
      analyzeToggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    };
  }
  var analyzeSubmit = document.getElementById("analyze-submit");
  if (analyzeSubmit) { analyzeSubmit.onclick = submitTextAnalysis; }
}

function onReadingLevelChange() {
  loadPassageList();
}

function onPinyinToggle() {
  var el = document.getElementById("reading-pinyin");
  var cb = document.getElementById("reading-pinyin-toggle");
  if (el) el.classList.toggle("hidden", !cb.checked);
  saveDisplayPrefs("reading_show_pinyin", cb.checked);
}

function onTranslationToggle() {
  var el = document.getElementById("reading-translation");
  var cb = document.getElementById("reading-translation-toggle");
  if (el) el.classList.toggle("hidden", !cb.checked);
  saveDisplayPrefs("reading_show_translation", cb.checked);
}

function loadPassageList() {
  var level = document.getElementById("reading-level").value;
  var url = "/api/reading/passages" + (level ? "?hsk_level=" + level : "");
  apiFetch(url).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error === "upgrade_required") {
      showUpgradePrompt("reading"); return;
    }
    _readingPassages = data.passages || [];
    var freeOnly = data.free_only || false;
    var listEl = document.getElementById("reading-list");
    var passageEl = document.getElementById("reading-passage");
    listEl.classList.remove("hidden");
    passageEl.classList.add("hidden");

    if (_readingPassages.length === 0) {
      listEl.textContent = "";
      { const _es = document.createElement("div"); _es.className = "empty-state"; _es.innerHTML = '<img src="' + themedIllustration('/static/illustrations/empty-passages.webp') + '" alt="" class="empty-state-illustration">No passages at this level.'; listEl.appendChild(_es); handleImgErrors(_es); }
      return;
    }
    var html = "";
    for (var i = 0; i < _readingPassages.length; i++) {
      var p = _readingPassages[i];
      var readBadge = "";
      if (p.times_read > 0) {
        if (p.best_total > 0 && p.best_correct / p.best_total >= 0.8) {
          readBadge = '<span class="reading-completion-badge completion-mastered">Mastered</span>';
        } else if (p.best_total > 0 && p.best_correct / p.best_total >= 0.5) {
          readBadge = '<span class="reading-completion-badge completion-read">Read</span>';
        } else {
          readBadge = '<span class="reading-completion-badge completion-started">Started</span>';
        }
      }
      html += '<button class="reading-list-item' + (p.times_read > 0 ? ' reading-list-read' : '') + '" data-idx="' + i + '">'
        + '<span class="reading-list-title">' + escapeHtml(p.title_zh || p.title) + '</span>'
        + '<span class="reading-list-meta">'
        + '<span class="reading-hsk-tag">HSK ' + p.hsk_level + '</span>'
        + readBadge
        + '</span>'
        + '</button>';
    }
    if (freeOnly) {
      html += '<div class="reading-upgrade-hint">More passages at every HSK level with <button class="link-btn" onclick="showUpgradePrompt(\'reading\')">Full Access</button></div>';
    }
    listEl.innerHTML = html; // Safe: all data vars escaped via escapeHtml()
    listEl.querySelectorAll(".reading-list-item").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var idx = parseInt(btn.dataset.idx);
        loadPassage(idx);
      });
    });
  }).catch(function() {
    { const _rl = document.getElementById("reading-list"); _rl.textContent = ""; const _es2 = document.createElement("div"); _es2.className = "empty-state"; _es2.innerHTML = '<img src="' + themedIllustration('/static/illustrations/empty-passages.webp') + '" alt="" class="empty-state-illustration">Failed to load passages.'; _rl.appendChild(_es2); handleImgErrors(_es2); }
  });
}

function loadPassage(idx) {
  if (idx < 0 || idx >= _readingPassages.length) return;
  _readingIndex = idx;
  var p = _readingPassages[idx];
  _currentPassageId = p.id;
  _readingWordsLookedUp = 0;
  _readingStartTime = Date.now();
  _readingQuizScore = null;

  fetch("/api/reading/passage/" + encodeURIComponent(p.id))
    .then(function(r) { return r.json(); })
    .then(function(passage) {
      var listEl = document.getElementById("reading-list");
      var passageEl = document.getElementById("reading-passage");
      listEl.classList.add("hidden");
      passageEl.classList.remove("hidden");

      // Render text with adaptive script: known=hanzi only, unknown=hanzi+pinyin ruby
      var textEl = document.getElementById("reading-text");
      var text = passage.text_zh || "";
      var charMastery = passage.char_mastery || {};
      var html = "";
      for (var i = 0; i < text.length; i++) {
        var ch = text[i];
        if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) {
          var meta = charMastery[ch];
          var known = meta && (meta.stage === "passed_once" || meta.stage === "stabilizing" || meta.stage === "stable" || meta.stage === "durable");
          var cls = known ? "reading-word known" : "reading-word unknown";
          if (!known && meta && meta.pinyin) {
            html += '<ruby><span class="' + cls + '" data-char="' + escapeHtml(ch) + '">'
                  + escapeHtml(ch) + '</span><rt>' + escapeHtml(meta.pinyin) + '</rt></ruby>';
          } else {
            html += '<span class="' + cls + '" data-char="' + escapeHtml(ch) + '">' + escapeHtml(ch) + '</span>';
          }
        } else {
          html += escapeHtml(ch);
        }
      }
      textEl.innerHTML = html; // Safe: all vars escaped via escapeHtml()

      // Add click handlers for word lookup
      textEl.querySelectorAll(".reading-word").forEach(function(span) {
        span.addEventListener("click", function(e) {
          span.classList.add("reading-word-looked-up");
          lookupWord(span.dataset.char, e);
        });
      });

      // Pinyin and translation
      var pinyinEl = document.getElementById("reading-pinyin");
      pinyinEl.textContent = passage.text_pinyin || "";
      var transEl = document.getElementById("reading-translation");
      transEl.textContent = passage.text_en || "";

      // Apply saved display preferences
      applyDisplayPrefsToToggles();

      // Render comprehension questions if available
      var rqEl = document.getElementById("reading-questions");
      if (passage.questions && passage.questions.length > 0) {
        renderMCQuestions(rqEl, passage.questions, passage.user_hsk || _quizUserHsk || 1, function(score) {
          _readingQuizScore = score;
          // Submit progress immediately when quiz is done
          _submitReadingProgress();
          _fetchReadingStats();
        });
        rqEl.classList.remove("hidden");
      } else {
        rqEl.innerHTML = "";
        rqEl.classList.add("hidden");
      }

      // Update nav buttons
      document.getElementById("reading-prev").disabled = (idx <= 0);
      document.getElementById("reading-next").disabled = (idx >= _readingPassages.length - 1);

      updateReadingStats();

      // Attach swipe gestures for passage navigation (mobile)
      SwipeHandler.attach(passageEl, {
        onSwipeLeft: function() {
          if (idx < _readingPassages.length - 1) navigatePassage(1);
        },
        onSwipeRight: function() {
          if (idx > 0) navigatePassage(-1);
        }
      });

      // Render passage comments section
      _loadPassageComments(passage.id || p.id);
    }).catch(function() {});
}

function lookupWord(hanzi, event) {
  if (AeluSound.instance) AeluSound.instance.readingLookup();
  apiFetch("/api/reading/lookup", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({hanzi: hanzi, passage_id: _currentPassageId})
  }).then(function(r) { return r.json(); }).then(function(data) {
    _readingWordsLookedUp++;
    updateReadingStats();

    // Glow the tapped word, then fade
    var tappedWord = event && event.target && event.target.closest ? event.target.closest(".reading-word") : null;
    if (tappedWord) {
      tappedWord.classList.remove("gloss-fading");
      tappedWord.classList.add("gloss-active");
      setTimeout(function() {
        tappedWord.classList.remove("gloss-active");
        tappedWord.classList.add("gloss-fading");
      }, 1000);
      setTimeout(function() {
        tappedWord.classList.remove("gloss-fading");
      }, 2000);
    }

    // Show gloss tooltip — pick the one whose parent section is visible,
    // falling back to the global gloss (works from any view including session)
    var gloss = null;
    var candidates = ["reading-gloss", "listening-gloss"];
    for (var gi = 0; gi < candidates.length; gi++) {
      var g = document.getElementById(candidates[gi]);
      if (g && g.parentElement && !g.parentElement.classList.contains("hidden")) { gloss = g; break; }
    }
    if (!gloss) gloss = document.getElementById("global-gloss");
    if (!gloss) return;
    var pinyin = data.pinyin || "";
    var english = data.english || "";
    // Max-two-of-three rule: hanzi is already visible in passage,
    // so show pinyin OR english (prefer pinyin if available)
    var content = pinyin || english;
    if (!data.found) content = hanzi + " (not in dictionary)";
    gloss.textContent = content;
    gloss.classList.remove("hidden");

    // Position near click
    var x = event.clientX;
    var y = event.clientY - 40;
    if (y < 10) y = event.clientY + 20;
    gloss.style.left = Math.max(8, Math.min(x - 40, window.innerWidth - 200)) + "px";
    gloss.style.top = y + "px";

    // Auto-hide after 3 seconds
    clearTimeout(gloss._hideTimer);
    gloss._hideTimer = setTimeout(function() {
      gloss.classList.add("hidden");
    }, 3000);
  });
}

function updateReadingStats() {
  var el = document.getElementById("reading-stats");
  if (!el) return;
  var elapsed = Math.round((Date.now() - (_readingStartTime || Date.now())) / 1000);
  var mins = Math.floor(elapsed / 60);
  var secs = elapsed % 60;
  el.textContent = _readingWordsLookedUp + " words looked up · " + mins + ":" + (secs < 10 ? "0" : "") + secs;
}

function _fetchReadingStats() {
  apiFetch("/api/reading/stats").then(function(r) { return r.json(); }).then(function(data) {
    var el = document.getElementById("reading-progress-dashboard");
    if (!el || data.error) return;
    var html = '';
    html += '<div class="reading-dashboard-item"><span class="reading-dashboard-value">' + (data.total_passages || 0) + '</span><span class="reading-dashboard-label">Passages Read</span></div>';
    html += '<div class="reading-dashboard-item"><span class="reading-dashboard-value">' + (data.comprehension_pct || 0) + '%</span><span class="reading-dashboard-label">Comprehension</span></div>';
    html += '<div class="reading-dashboard-item"><span class="reading-dashboard-value">' + (data.total_words_looked_up || 0) + '</span><span class="reading-dashboard-label">Words Looked Up</span></div>';
    el.innerHTML = html;
    el.classList.remove("hidden");
  }).catch(function() {});
}

function _submitReadingProgress() {
  if (!_currentPassageId) return;
  var elapsed = Math.round((Date.now() - (_readingStartTime || Date.now())) / 1000);
  var qCorrect = _readingQuizScore ? _readingQuizScore.correct : 0;
  var qTotal = _readingQuizScore ? _readingQuizScore.total : 0;
  apiFetch("/api/reading/progress", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      passage_id: _currentPassageId,
      words_looked_up: _readingWordsLookedUp,
      questions_correct: qCorrect,
      questions_total: qTotal,
      reading_time_seconds: elapsed
    })
  });
}

function navigatePassage(dir) {
  // Submit progress for current passage before navigating
  _submitReadingProgress();
  var newIdx = _readingIndex + dir;
  if (newIdx >= 0 && newIdx < _readingPassages.length) {
    loadPassage(newIdx);
  }
}

/* ── Passage Comments (Community) ──────────────────────────────── */

function _loadPassageComments(passageId) {
  var container = document.getElementById("reading-comments");
  if (!container) return;

  apiFetch("/api/reading/comments?passage_id=" + encodeURIComponent(passageId))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) { container.classList.add("hidden"); return; }
      var comments = data.comments || [];
      var html = '<div class="passage-comments-header">'
        + '<span class="comments-count">' + (data.total_count || 0) + ' comment' + (data.total_count !== 1 ? 's' : '') + '</span>'
        + '</div>';

      if (comments.length > 0) {
        html += '<div class="passage-comments-list">';
        for (var i = 0; i < comments.length; i++) {
          var c = comments[i];
          html += '<div class="passage-comment">'
            + '<span class="comment-author">' + escapeHtml(c.author) + '</span>'
            + '<span class="comment-text">' + escapeHtml(c.text) + '</span>'
            + '</div>';
        }
        html += '</div>';
      }

      html += '<div class="passage-comment-form">'
        + '<textarea id="comment-input" placeholder="Share a thought about this passage..." maxlength="500" rows="2"></textarea>'
        + '<button id="comment-submit" class="btn btn-small">Post</button>'
        + '</div>';

      container.innerHTML = html;
      container.classList.remove("hidden");

      var submitBtn = document.getElementById("comment-submit");
      if (submitBtn) {
        submitBtn.onclick = function() { _postPassageComment(passageId); };
      }
    })
    .catch(function() { container.classList.add("hidden"); });
}

function _postPassageComment(passageId) {
  var input = document.getElementById("comment-input");
  var text = (input && input.value || "").trim();
  if (!text) return;

  apiFetch("/api/reading/comment", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({passage_id: passageId, text: text})
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.status === "ok") {
      _loadPassageComments(passageId);  // Refresh
    }
  }).catch(function() {});
}


/* ── Vocab Import UI ──────────────────────────────── */

function submitVocabImport() {
  var input = document.getElementById("import-vocab-input");
  var resultsEl = document.getElementById("import-results");
  if (!input || !resultsEl) return;

  var text = input.value.trim();
  if (!text) return;

  // Split by newlines, commas, or spaces — each word is a hanzi
  var words = text.split(/[,\n\s]+/).filter(function(w) { return w.trim().length > 0; });
  if (words.length === 0) return;

  apiFetch("/api/content/import", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({words: words})
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) {
      resultsEl.innerHTML = '<p class="analyze-error">' + escapeHtml(data.error) + '</p>';
      resultsEl.classList.remove("hidden");
      return;
    }
    var html = '<div class="import-summary">'
      + '<div class="import-stat"><strong>' + data.matched + '</strong> words added to study queue</div>'
      + '<div class="import-stat"><strong>' + data.already_queued + '</strong> already in your queue</div>'
      + '<div class="import-stat"><strong>' + data.unmatched + '</strong> not found in dictionary</div>'
      + '</div>';
    if (data.unmatched_words && data.unmatched_words.length > 0) {
      html += '<div class="import-unmatched">Not found: ' + data.unmatched_words.map(escapeHtml).join(', ') + '</div>';
    }
    resultsEl.innerHTML = html;
    resultsEl.classList.remove("hidden");
  }).catch(function() {
    resultsEl.innerHTML = '<p class="analyze-error">Import failed. Please try again.</p>';
    resultsEl.classList.remove("hidden");
  });
}


/* ── Grammar Explanation on Incorrect ──────────────────── */

function showGrammarExplanation(grammarPointId) {
  if (!grammarPointId) return;
  apiFetch("/api/grammar/explanation/" + grammarPointId)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) return;
      var modal = document.getElementById("grammar-explanation-modal");
      if (!modal) {
        modal = document.createElement("div");
        modal.id = "grammar-explanation-modal";
        modal.className = "grammar-explanation-modal";
        document.body.appendChild(modal);
      }
      var html = '<div class="grammar-explanation-content">'
        + '<button class="grammar-explanation-close" onclick="this.parentElement.parentElement.classList.add(\'hidden\')">&times;</button>'
        + '<h3>' + escapeHtml(data.name || '') + (data.name_zh ? ' ' + escapeHtml(data.name_zh) : '') + '</h3>';
      if (data.pattern) html += '<div class="grammar-pattern">' + escapeHtml(data.pattern) + '</div>';
      if (data.explanation) html += '<p class="grammar-explanation-text">' + escapeHtml(data.explanation) + '</p>';
      if (data.related_vocab && data.related_vocab.length > 0) {
        html += '<div class="grammar-examples"><strong>Examples:</strong><ul>';
        for (var i = 0; i < data.related_vocab.length; i++) {
          var v = data.related_vocab[i];
          html += '<li>' + escapeHtml(v.hanzi) + ' (' + escapeHtml(v.pinyin) + ') — ' + escapeHtml(v.english) + '</li>';
        }
        html += '</ul></div>';
      }
      html += '</div>';
      modal.innerHTML = html;
      modal.classList.remove("hidden");
    })
    .catch(function() {});
}


/* ── Content Analysis (user-importable text) ──────────────────────────────── */

function submitTextAnalysis() {
  var input = document.getElementById("analyze-input");
  var resultsEl = document.getElementById("analyze-results");
  var submitBtn = document.getElementById("analyze-submit");
  if (!input || !resultsEl || !submitBtn) return;

  var text = input.value.trim();
  if (!text) return;
  if (text.length < 2) {
    resultsEl.innerHTML = '<p class="analyze-error">Please enter at least 2 characters.</p>';
    resultsEl.classList.remove("hidden");
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Analyzing...";
  resultsEl.classList.add("hidden");

  apiFetch("/api/content/analyze", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text: text})
  }).then(function(r) { return r.json(); }).then(function(data) {
    submitBtn.disabled = false;
    submitBtn.textContent = "Analyze";

    if (data.error) {
      resultsEl.innerHTML = '<p class="analyze-error">' + escapeHtml(data.error) + '</p>';
      resultsEl.classList.remove("hidden");
      return;
    }

    var html = '';

    // HSK level badge
    html += '<span class="analyze-level-badge">Estimated HSK ' + data.hsk_level + '</span>';

    // Difficulty metrics
    var d = data.difficulty || {};
    html += '<div class="analyze-metrics">';
    html += '<div class="analyze-metric"><div class="analyze-metric-value">' + (d.char_count || 0) + '</div><div class="analyze-metric-label">Characters</div></div>';
    html += '<div class="analyze-metric"><div class="analyze-metric-value">' + ((d.unique_ratio || 0) * 100).toFixed(0) + '%</div><div class="analyze-metric-label">Unique</div></div>';
    html += '<div class="analyze-metric"><div class="analyze-metric-value">' + (d.avg_sentence_length || 0) + '</div><div class="analyze-metric-label">Avg sentence</div></div>';
    html += '</div>';

    // Summary
    var s = data.summary || {};
    html += '<p style="margin-bottom:8px;font-size:14px;">'
      + '<strong>' + (s.known_words || 0) + '</strong> of <strong>' + (s.total_words || 0) + '</strong> words known'
      + ' (' + (s.known_pct || 0) + '% coverage)</p>';

    // Vocabulary list
    var vocab = data.vocabulary || [];
    if (vocab.length > 0) {
      html += '<ul class="analyze-vocab-list">';
      for (var i = 0; i < Math.min(vocab.length, 30); i++) {
        var v = vocab[i];
        var statusCls = v.known ? "analyze-vocab-known" : "analyze-vocab-unknown";
        var statusText = v.known ? "known" : (v.stage === "not_in_db" ? "new" : "learning");
        html += '<li class="analyze-vocab-item">'
          + '<span class="analyze-vocab-hanzi">' + escapeHtml(v.word) + '</span>'
          + '<span>' + escapeHtml(v.pinyin || "") + '</span>'
          + '<span>' + escapeHtml(v.english || "") + '</span>'
          + '<span class="' + statusCls + '">' + statusText + '</span>'
          + (v.hsk_level ? '<span style="font-size:11px;color:var(--color-text-dim)">HSK ' + v.hsk_level + '</span>' : '')
          + '</li>';
      }
      html += '</ul>';
      if (vocab.length > 30) {
        html += '<p style="font-size:12px;color:var(--color-text-dim);margin-top:4px;">+ ' + (vocab.length - 30) + ' more words</p>';
      }
    }

    resultsEl.innerHTML = html;
    resultsEl.classList.remove("hidden");
    EventLog.record("content", "analyze", {hsk: data.hsk_level, words: s.total_words});
  }).catch(function(err) {
    submitBtn.disabled = false;
    submitBtn.textContent = "Analyze";
    resultsEl.innerHTML = '<p class="analyze-error">Analysis failed. Please try again.</p>';
    resultsEl.classList.remove("hidden");
  });
}

/* ── Grammar View ──────────────────────────────── */

var _grammarCurrentLevel = 1;
var _grammarPoints = [];

var _grammarLevelsLoaded = false;

function openGrammarView() {
  EventLog.record("view", "grammar");
  transitionTo("dashboard", "grammar");
  showFeatureTooltip("grammar", "Study grammar patterns level by level. Tap a point to learn, then practice linked vocabulary.");

  // Set up lesson back button
  var lessonBack = document.getElementById("grammar-lesson-back");
  if (lessonBack) {
    lessonBack.onclick = function() {
      document.getElementById("grammar-lesson").classList.add("hidden");
      document.getElementById("grammar-list").classList.remove("hidden");
      document.getElementById("grammar-level-tabs").classList.remove("hidden");
      document.getElementById("grammar-mastery-summary").classList.remove("hidden");
    };
  }

  // Build tabs dynamically on first visit
  if (!_grammarLevelsLoaded) {
    apiFetch("/api/grammar/levels").then(function(r) { return r.json(); }).then(function(data) {
      var levels = data.levels || [];
      var tabsEl = document.getElementById("grammar-level-tabs");
      tabsEl.innerHTML = "";
      for (var i = 0; i < levels.length; i++) {
        var btn = document.createElement("button");
        btn.className = "grammar-level-tab" + (levels[i] === _grammarCurrentLevel ? " active" : "");
        btn.dataset.level = levels[i];
        btn.setAttribute("role", "tab");
        btn.setAttribute("aria-selected", levels[i] === _grammarCurrentLevel ? "true" : "false");
        btn.textContent = "HSK " + levels[i];
        btn.addEventListener("click", _onGrammarTabClick);
        tabsEl.appendChild(btn);
      }
      _grammarLevelsLoaded = true;
      loadGrammarList(_grammarCurrentLevel);
    }).catch(function() {
      // Fallback: load with current level even if levels endpoint fails
      loadGrammarList(_grammarCurrentLevel);
    });
  } else {
    // Tabs already built — just reload the list
    var tabs = document.querySelectorAll(".grammar-level-tab");
    tabs.forEach(function(tab) {
      tab.removeEventListener("click", _onGrammarTabClick);
      tab.addEventListener("click", _onGrammarTabClick);
    });
    loadGrammarList(_grammarCurrentLevel);
  }
}

function _onGrammarTabClick(e) {
  var level = parseInt(e.currentTarget.dataset.level);
  if (isNaN(level)) return;
  _grammarCurrentLevel = level;
  var tabs = document.querySelectorAll(".grammar-level-tab");
  tabs.forEach(function(t) {
    var isActive = parseInt(t.dataset.level) === level;
    t.classList.toggle("active", isActive);
    t.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  loadGrammarList(level);
}

var _grammarCategoryFilter = "";

function loadGrammarList(hsk) {
  var url = "/api/grammar/lesson/" + hsk;
  apiFetch(url).then(function(r) { return r.json(); }).then(function(data) {
    _grammarPoints = data.points || [];
    var listEl = document.getElementById("grammar-list");
    var lessonEl = document.getElementById("grammar-lesson");
    var summaryEl = document.getElementById("grammar-mastery-summary");
    listEl.classList.remove("hidden");
    lessonEl.classList.add("hidden");

    // Mastery summary
    var total = data.total || _grammarPoints.length;
    var studied = data.studied_count || 0;
    var pct = total > 0 ? Math.round(studied / total * 100) : 0;
    summaryEl.innerHTML = '<span class="grammar-mastery-text">' + studied + ' / ' + total + ' studied</span>'
      + '<div class="grammar-mastery-bar"><div class="grammar-mastery-fill" style="width:' + pct + '%"></div></div>';

    if (_grammarPoints.length === 0) {
      listEl.textContent = "";
      var emptyDiv = document.createElement("div");
      emptyDiv.className = "empty-state";
      emptyDiv.textContent = "No grammar points at this level.";
      listEl.appendChild(emptyDiv);
      return;
    }

    // Category filter chips
    var categories = {};
    for (var ci = 0; ci < _grammarPoints.length; ci++) {
      var cat = _grammarPoints[ci].category;
      if (cat) categories[cat] = (categories[cat] || 0) + 1;
    }
    var chipHtml = '<div class="grammar-category-chips">';
    chipHtml += '<button class="grammar-category-chip' + (!_grammarCategoryFilter ? ' active' : '') + '" data-cat="">All</button>';
    var catKeys = Object.keys(categories).sort();
    for (var ck = 0; ck < catKeys.length; ck++) {
      var isActive = _grammarCategoryFilter === catKeys[ck];
      chipHtml += '<button class="grammar-category-chip' + (isActive ? ' active' : '') + '" data-cat="' + escapeHtml(catKeys[ck]) + '">'
        + escapeHtml(catKeys[ck]) + ' <span class="grammar-chip-count">' + categories[catKeys[ck]] + '</span></button>';
    }
    chipHtml += '</div>';

    // Filter points by category
    var filtered = _grammarPoints;
    if (_grammarCategoryFilter) {
      filtered = [];
      for (var fi = 0; fi < _grammarPoints.length; fi++) {
        if (_grammarPoints[fi].category === _grammarCategoryFilter) filtered.push(_grammarPoints[fi]);
      }
    }

    var html = chipHtml;
    for (var i = 0; i < filtered.length; i++) {
      var p = filtered[i];
      var studiedClass = p.studied ? " grammar-card-studied" : "";
      // Mastery badge
      var masteryBadge = "";
      if (p.drill_attempts > 0) {
        var ms = p.mastery_score || 0;
        if (ms >= 0.8) {
          masteryBadge = '<span class="grammar-mastery-badge mastery-mastered">Mastered</span>';
        } else if (ms >= 0.5) {
          masteryBadge = '<span class="grammar-mastery-badge mastery-practiced">Practiced</span>';
        } else {
          masteryBadge = '<span class="grammar-mastery-badge mastery-learning">Learning</span>';
        }
      }
      html += '<button class="grammar-card' + studiedClass + '" data-id="' + p.id + '">'
        + '<div class="grammar-card-main">'
        + '<span class="grammar-card-name">' + escapeHtml(p.name) + '</span>'
        + (p.name_zh ? ' <span class="grammar-card-name-zh">' + escapeHtml(p.name_zh) + '</span>' : '')
        + '</div>'
        + '<div class="grammar-card-meta">'
        + (p.category ? '<span class="grammar-card-category">' + escapeHtml(p.category) + '</span>' : '')
        + masteryBadge
        + (p.studied && !masteryBadge ? '<span class="grammar-card-studied-badge">Studied</span>' : '')
        + '</div>'
        + '</button>';
    }
    listEl.innerHTML = html;

    // Bind category chip clicks
    listEl.querySelectorAll(".grammar-category-chip").forEach(function(chip) {
      chip.addEventListener("click", function() {
        _grammarCategoryFilter = chip.dataset.cat || "";
        loadGrammarList(hsk);
      });
    });

    listEl.querySelectorAll(".grammar-card").forEach(function(btn) {
      btn.addEventListener("click", function() {
        openGrammarPoint(parseInt(btn.dataset.id));
      });
    });
  }).catch(function() {
    var listEl = document.getElementById("grammar-list");
    listEl.textContent = "";
    var errDiv = document.createElement("div");
    errDiv.className = "empty-state";
    errDiv.textContent = "Couldn\u2019t load grammar points. Try again in a moment.";
    listEl.appendChild(errDiv);
  });
}

function openGrammarPoint(id) {
  EventLog.record("grammar", "open_point", {id: id});
  apiFetch("/api/grammar/point/" + id).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) return;

    var listEl = document.getElementById("grammar-list");
    var lessonEl = document.getElementById("grammar-lesson");
    var contentEl = document.getElementById("grammar-lesson-content");
    var tabsEl = document.getElementById("grammar-level-tabs");
    var summaryEl = document.getElementById("grammar-mastery-summary");

    listEl.classList.add("hidden");
    tabsEl.classList.add("hidden");
    summaryEl.classList.add("hidden");
    lessonEl.classList.remove("hidden");

    var html = '';

    // Title
    html += '<div class="grammar-lesson-title">';
    html += '<h3>' + escapeHtml(data.name) + '</h3>';
    if (data.name_zh) html += '<span class="grammar-lesson-name-zh">' + escapeHtml(data.name_zh) + '</span>';
    html += '</div>';

    // Category + level meta
    html += '<div class="grammar-lesson-meta">';
    html += '<span class="grammar-card-category">' + escapeHtml(data.category || "General") + '</span>';
    html += '<span class="grammar-lesson-level">HSK ' + data.hsk_level + '</span>';
    if (data.studied) html += '<span class="grammar-card-studied-badge">Studied</span>';
    html += '</div>';

    // Description
    if (data.description) {
      html += '<div class="grammar-lesson-description">' + escapeHtml(data.description) + '</div>';
    }

    // Examples
    if (data.examples && data.examples.length > 0) {
      html += '<div class="grammar-examples">';
      html += '<h4>Examples</h4>';
      for (var i = 0; i < data.examples.length; i++) {
        var ex = data.examples[i];
        html += '<div class="grammar-example">';
        if (ex.zh || ex.chinese) {
          var zhText = ex.zh || ex.chinese;
          html += '<div class="grammar-example-zh">'
            + '<span class="grammar-example-text">' + escapeHtml(zhText) + '</span>'
            + '<button class="grammar-audio-btn" data-text="' + escapeHtml(zhText) + '" aria-label="Play audio" title="Play audio">&#9654;</button>'
            + '</div>';
        }
        if (ex.pinyin) {
          html += '<div class="grammar-example-pinyin">' + escapeHtml(ex.pinyin) + '</div>';
        }
        if (ex.en || ex.english) {
          html += '<div class="grammar-example-en">' + escapeHtml(ex.en || ex.english) + '</div>';
        }
        if (ex.note) {
          html += '<div class="grammar-example-note">' + escapeHtml(ex.note) + '</div>';
        }
        html += '</div>';
      }
      html += '</div>';
    }

    // Linked vocab
    if (data.linked_items && data.linked_items.length > 0) {
      html += '<div class="grammar-linked-vocab">';
      html += '<h4>Related Vocabulary</h4>';
      html += '<div class="grammar-vocab-list">';
      for (var j = 0; j < data.linked_items.length; j++) {
        var item = data.linked_items[j];
        var stageClass = "grammar-vocab-stage-" + (item.mastery_stage || "unseen");
        html += '<div class="grammar-vocab-item ' + stageClass + '">'
          + '<span class="grammar-vocab-hanzi">' + escapeHtml(item.hanzi) + '</span>'
          + '<span class="grammar-vocab-pinyin">' + escapeHtml(item.pinyin) + '</span>'
          + '<span class="grammar-vocab-english">' + escapeHtml(item.english) + '</span>'
          + '<span class="grammar-vocab-mastery">' + escapeHtml(item.mastery_stage) + '</span>'
          + '</div>';
      }
      html += '</div>';
      html += '</div>';
    }

    // Actions: mark studied + practice
    html += '<div class="grammar-lesson-actions">';
    if (!data.studied) {
      html += '<button class="btn-primary grammar-mark-studied" data-id="' + data.id + '">Mark as Studied</button>';
    } else {
      html += '<div class="grammar-studied-confirmation">Studied on ' + escapeHtml((data.studied_at || "").split(" ")[0]) + '</div>';
    }
    if (data.linked_items && data.linked_items.length > 0) {
      html += '<button class="btn-secondary grammar-practice-btn" data-id="' + data.id + '">'
        + 'Practice (' + data.linked_items.length + ' items)</button>';
    }
    html += '</div>';

    contentEl.innerHTML = html;

    // Bind audio buttons
    contentEl.querySelectorAll(".grammar-audio-btn").forEach(function(btn) {
      btn.addEventListener("click", function(e) {
        e.stopPropagation();
        var text = btn.dataset.text;
        if (text) _playGrammarTTS(text);
      });
    });

    // Bind mark-studied button
    var studiedBtn = contentEl.querySelector(".grammar-mark-studied");
    if (studiedBtn) {
      studiedBtn.addEventListener("click", function() {
        markGrammarStudied(parseInt(studiedBtn.dataset.id));
      });
    }

    // Bind practice button — starts a mini drill session with linked vocab
    var practiceBtn = contentEl.querySelector(".grammar-practice-btn");
    if (practiceBtn) {
      practiceBtn.addEventListener("click", function() {
        _startGrammarPractice(data.id, data.name, data.linked_items, data.examples);
      });
    }

    // Scroll to top of lesson
    lessonEl.scrollTop = 0;
    window.scrollTo(0, 0);
  }).catch(function() {
    var contentEl = document.getElementById("grammar-lesson-content");
    contentEl.textContent = "Couldn\u2019t load this grammar point.";
  });
}

function _playGrammarTTS(text) {
  // Try server-side TTS first, fall back to browser
  apiFetch("/api/tts", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text: text})
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.url) {
      var audio = new Audio(data.url);
      audio.onerror = function() { _playWithBrowserTTS(text); };
      audio.play().catch(function() { _playWithBrowserTTS(text); });
    } else {
      _playWithBrowserTTS(text);
    }
  }).catch(function() {
    _playWithBrowserTTS(text);
  });
}

function markGrammarStudied(id) {
  EventLog.record("grammar", "mark_studied", {id: id});
  apiFetch("/api/grammar/progress", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({grammar_point_id: id})
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.status === "ok") {
      // Refresh the point view to show studied state
      openGrammarPoint(id);
      // Also update the cached list entry
      for (var i = 0; i < _grammarPoints.length; i++) {
        if (_grammarPoints[i].id === id) {
          _grammarPoints[i].studied = true;
          break;
        }
      }
    }
  }).catch(function() {
    // Silently fail — user can retry
  });
}

function _startGrammarPractice(grammarPointId, grammarName, linkedItems, examples) {
  // Build a mini-quiz from linked vocabulary items + example sentences
  if ((!linkedItems || linkedItems.length === 0) && (!examples || examples.length === 0)) return;

  EventLog.record("grammar", "practice_start", {id: grammarPointId, count: (linkedItems || []).length});

  var questions = [];
  // Vocab-based questions: "What does X mean?"
  for (var i = 0; i < (linkedItems || []).length; i++) {
    var item = linkedItems[i];
    questions.push({
      type: "vocab",
      hanzi: item.hanzi,
      pinyin: item.pinyin,
      english: item.english,
      mastery_stage: item.mastery_stage,
    });
  }
  // Example-based questions: "What does this sentence mean?"
  if (examples && examples.length > 0) {
    for (var ei = 0; ei < examples.length; ei++) {
      var ex = examples[ei];
      if (ex.zh && ex.en) {
        questions.push({
          type: "example",
          hanzi: ex.zh,
          pinyin: ex.pinyin || "",
          english: ex.en,
        });
      }
    }
  }

  // Shuffle
  for (var si = questions.length - 1; si > 0; si--) {
    var sj = Math.floor(Math.random() * (si + 1));
    var tmp = questions[si]; questions[si] = questions[sj]; questions[sj] = tmp;
  }

  // Limit to 10 items per practice session
  if (questions.length > 10) questions = questions.slice(0, 10);

  _grammarQuizState = {
    grammarPointId: grammarPointId,
    grammarName: grammarName,
    questions: questions,
    allItems: linkedItems,
    current: 0,
    correct: 0,
    total: questions.length,
  };

  // Switch to grammar lesson content area and render first question
  var contentEl = document.getElementById("grammar-lesson-content");
  _renderGrammarQuizQuestion(contentEl);
}

var _grammarQuizState = null;

function _renderGrammarQuizQuestion(contentEl) {
  var state = _grammarQuizState;
  if (!state || state.current >= state.total) {
    _renderGrammarQuizResult(contentEl);
    return;
  }

  var q = state.questions[state.current];
  var isExample = q.type === "example";
  var html = '<div class="grammar-quiz">';
  html += '<div class="grammar-quiz-progress">' + (state.current + 1) + ' / ' + state.total + '</div>';
  html += '<div class="grammar-quiz-prompt">';
  html += '<span class="grammar-quiz-hanzi">' + escapeHtml(q.hanzi) + '</span>';
  html += '</div>';
  html += '<div class="grammar-quiz-question">' + (isExample ? 'What does this sentence mean?' : 'What does this mean?') + '</div>';

  // Build 4 MC options (1 correct + 3 distractors)
  var options = [{text: q.english, correct: true}];
  var pool = [];
  // Draw distractors from all questions of the same type, then fall back to all
  for (var i = 0; i < state.questions.length; i++) {
    if (state.questions[i].english !== q.english) {
      pool.push(state.questions[i].english);
    }
  }
  if (pool.length < 3) {
    for (var i = 0; i < (state.allItems || []).length; i++) {
      if (state.allItems[i].english !== q.english && pool.indexOf(state.allItems[i].english) === -1) {
        pool.push(state.allItems[i].english);
      }
    }
  }
  // Shuffle pool
  for (var pi = pool.length - 1; pi > 0; pi--) {
    var pj = Math.floor(Math.random() * (pi + 1));
    var pt = pool[pi]; pool[pi] = pool[pj]; pool[pj] = pt;
  }
  for (var di = 0; di < Math.min(3, pool.length); di++) {
    options.push({text: pool[di], correct: false});
  }
  // Shuffle options
  for (var oi = options.length - 1; oi > 0; oi--) {
    var oj = Math.floor(Math.random() * (oi + 1));
    var ot = options[oi]; options[oi] = options[oj]; options[oj] = ot;
  }

  html += '<div class="grammar-quiz-options">';
  for (var k = 0; k < options.length; k++) {
    html += '<button class="grammar-quiz-option" data-correct="' + (options[k].correct ? "1" : "0") + '">'
      + escapeHtml(options[k].text) + '</button>';
  }
  html += '</div>';
  html += '</div>';

  contentEl.innerHTML = html;

  // Bind option clicks
  contentEl.querySelectorAll(".grammar-quiz-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var isCorrect = btn.dataset.correct === "1";
      // Highlight correct/wrong
      contentEl.querySelectorAll(".grammar-quiz-option").forEach(function(b) {
        b.disabled = true;
        if (b.dataset.correct === "1") b.classList.add("grammar-quiz-correct");
      });
      if (!isCorrect) {
        btn.classList.add("grammar-quiz-wrong");
        _hapticFeedback('incorrect');
        // Show grammar explanation link when wrong
        var explainBtn = document.createElement("button");
        explainBtn.className = "btn-grammar-explain";
        explainBtn.textContent = "Why?";
        explainBtn.addEventListener("click", function() {
          showGrammarExplanation(state.grammarPointId);
        });
        btn.parentNode.appendChild(explainBtn);
      } else {
        state.correct++;
        _hapticFeedback('correct');
      }

      // Show pinyin after answer
      var prompt = contentEl.querySelector(".grammar-quiz-prompt");
      if (prompt && q.pinyin) {
        prompt.innerHTML += '<div class="grammar-quiz-pinyin">' + escapeHtml(q.pinyin) + '</div>';
      }

      // Advance after brief delay (longer if wrong, to read explanation)
      var delay = isCorrect ? 1200 : 2500;
      setTimeout(function() {
        state.current++;
        _renderGrammarQuizQuestion(contentEl);
      }, delay);
    });
  });
}

function _renderGrammarQuizResult(contentEl) {
  var state = _grammarQuizState;
  var pct = state.total > 0 ? Math.round(state.correct / state.total * 100) : 0;

  EventLog.record("grammar", "practice_complete", {
    id: state.grammarPointId, correct: state.correct, total: state.total
  });

  var html = '<div class="grammar-quiz-result">';
  html += '<h3>Practice Complete</h3>';
  html += '<div class="grammar-quiz-score">' + state.correct + ' / ' + state.total + ' correct (' + pct + '%)</div>';
  html += '<div class="grammar-quiz-result-actions">';
  html += '<button class="btn-secondary grammar-quiz-review" data-id="' + state.grammarPointId + '">Review Point</button>';
  if (state.correct < state.total) {
    html += '<button class="btn-primary grammar-quiz-retry" data-id="' + state.grammarPointId + '">Try Again</button>';
  }
  html += '</div>';
  html += '</div>';

  contentEl.innerHTML = html;

  var reviewBtn = contentEl.querySelector(".grammar-quiz-review");
  if (reviewBtn) {
    reviewBtn.addEventListener("click", function() {
      openGrammarPoint(parseInt(reviewBtn.dataset.id));
    });
  }

  var retryBtn = contentEl.querySelector(".grammar-quiz-retry");
  if (retryBtn) {
    retryBtn.addEventListener("click", function() {
      _grammarQuizState.current = 0;
      _grammarQuizState.correct = 0;
      // Re-shuffle
      var qs = _grammarQuizState.questions;
      for (var ri = qs.length - 1; ri > 0; ri--) {
        var rj = Math.floor(Math.random() * (ri + 1));
        var rt = qs[ri]; qs[ri] = qs[rj]; qs[rj] = rt;
      }
      _renderGrammarQuizQuestion(contentEl);
    });
  }

  // Persist practice results to backend
  if (state.grammarPointId && state.total > 0) {
    apiFetch("/api/grammar/practice", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        grammar_point_id: state.grammarPointId,
        correct: state.correct,
        total: state.total
      })
    });
  }

  // If they got a good score, auto-mark as studied
  if (pct >= 70 && state.grammarPointId) {
    markGrammarStudied(state.grammarPointId);
  }
}

/* ── Media View ──────────────────────────────── */

var _mediaTypeFilter = "";

function openMediaView() {
  EventLog.record("view", "media");
  transitionTo("dashboard", "media");
  loadMediaRecommendations();
  loadMediaHistory();
  _fetchMediaStats();
  showFeatureTooltip("media", "Watch real Chinese media at your level. Answer comprehension questions afterward to track understanding.");
}

function _fetchMediaStats() {
  apiFetch("/api/media/stats").then(function(r) { return r.json(); }).then(function(data) {
    var el = document.getElementById("media-stats-dashboard");
    if (!el || data.error) return;
    if (!data.total_watched && !data.liked_count) return;  // Don't show if empty
    var html = '';
    html += '<div class="media-stats-item"><span class="media-stats-value">' + (data.total_watched || 0) + '</span><span class="media-stats-label">Watched</span></div>';
    html += '<div class="media-stats-item"><span class="media-stats-value">' + (data.avg_comprehension || 0) + '%</span><span class="media-stats-label">Avg Score</span></div>';
    html += '<div class="media-stats-item"><span class="media-stats-value">' + (data.liked_count || 0) + '</span><span class="media-stats-label">Liked</span></div>';
    el.innerHTML = html;
    el.classList.remove("hidden");
  }).catch(function() {});
}

function loadMediaRecommendations() {
  apiFetch("/api/media/recommendations?limit=12")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var grid = document.getElementById("media-grid");
      var allRecs = data.recommendations || [];
      var freeOnly = data.free_only || false;

      // Build type filter chips
      var types = {};
      var mediaTypeLabels = {
        documentary: "Documentary", movie: "Movie", tv_series: "TV Series",
        talk_show: "Talk Show", short_clip: "Short Clip", youtube: "YouTube",
        podcast: "Podcast", social_media: "Social Media"
      };
      for (var ti = 0; ti < allRecs.length; ti++) {
        var mt = allRecs[ti].media_type;
        if (mt) types[mt] = (types[mt] || 0) + 1;
      }
      var chipEl = document.getElementById("media-type-chips");
      if (chipEl && Object.keys(types).length > 1) {
        var chipHtml = '<button class="media-type-chip' + (!_mediaTypeFilter ? ' active' : '') + '" data-type="">All</button>';
        var typeKeys = Object.keys(types).sort();
        for (var tk = 0; tk < typeKeys.length; tk++) {
          var isActive = _mediaTypeFilter === typeKeys[tk];
          var chipLabel = mediaTypeLabels[typeKeys[tk]] || typeKeys[tk];
          chipHtml += '<button class="media-type-chip' + (isActive ? ' active' : '') + '" data-type="' + escapeHtml(typeKeys[tk]) + '">'
            + escapeHtml(chipLabel) + '</button>';
        }
        chipEl.innerHTML = chipHtml;
        chipEl.querySelectorAll(".media-type-chip").forEach(function(chip) {
          chip.addEventListener("click", function() {
            _mediaTypeFilter = chip.dataset.type || "";
            loadMediaRecommendations();
          });
        });
      }

      // Filter by type
      var recs = allRecs;
      if (_mediaTypeFilter) {
        recs = [];
        for (var fi = 0; fi < allRecs.length; fi++) {
          if (allRecs[fi].media_type === _mediaTypeFilter) recs.push(allRecs[fi]);
        }
      }

      if (recs.length === 0) {
        grid.textContent = "";
        { const _es3 = document.createElement("div"); _es3.className = "empty-state"; _es3.innerHTML = '<img src="' + themedIllustration('/static/illustrations/empty-recommendations.webp') + '" alt="" class="empty-state-illustration">No recommendations available.'; grid.appendChild(_es3); handleImgErrors(_es3); }
        return;
      }
      var html = "";
      for (var i = 0; i < recs.length; i++) {
        var m = recs[i];
        var costClass = m.cost === "free" ? "cost-free" : m.cost === "subscription" ? "cost-sub" : "cost-purchase";
        var watchedBadge = '';
        if (m.times_watched > 0 && m.avg_score != null) {
          var scorePct = Math.round((m.avg_score || 0) * 100);
          if (scorePct >= 80) {
            watchedBadge = '<span class="media-mastery-badge mastery-mastered">' + scorePct + '%</span>';
          } else if (scorePct >= 50) {
            watchedBadge = '<span class="media-mastery-badge mastery-practiced">' + scorePct + '%</span>';
          } else {
            watchedBadge = '<span class="media-mastery-badge mastery-learning">' + scorePct + '%</span>';
          }
        } else if (m.times_watched > 0) {
          watchedBadge = '<span class="media-watched-badge">Watched</span>';
        }
        var watchUrl = m.watch_url || "";
        var watchLabel = m.watch_label || "";
        var fallbackUrl = m.fallback_url || "";
        var fallbackLabel = m.fallback_label || "";
        var whereHtml = "";
        if (watchUrl && watchLabel) {
          whereHtml = '<div class="media-card-where"><a href="' + escapeHtml(watchUrl) + '" target="_blank" rel="noopener">' + escapeHtml(watchLabel) + ' &rarr;</a>';
          if (fallbackUrl && fallbackLabel) {
            whereHtml += ' <span class="media-card-alt">or <a href="' + escapeHtml(fallbackUrl) + '" target="_blank" rel="noopener">' + escapeHtml(fallbackLabel) + '</a></span>';
          }
          whereHtml += '</div>';
        } else if (watchUrl) {
          var ctaVerb = m.media_type === 'podcast' ? 'Listen' : m.media_type === 'social_media' ? 'Read' : 'Watch';
          whereHtml = '<div class="media-card-where"><a href="' + escapeHtml(watchUrl) + '" target="_blank" rel="noopener">' + ctaVerb + ' &rarr;</a></div>';
        }
        var quizBtn = m.has_quiz ? '<button class="btn-media-quiz" data-id="' + escapeHtml(m.id) + '">Quiz</button>' : '';
        html += '<div class="media-card" data-media-id="' + escapeHtml(m.id) + '">'
          + '<div class="media-card-header">'
          + '<span class="media-hsk-badge">HSK ' + m.hsk_level + '</span>'
          + '<span class="media-cost-badge ' + costClass + '">' + escapeHtml(m.cost) + '</span>'
          + watchedBadge
          + '</div>'
          + '<div class="media-card-title">' + escapeHtml(m.title) + '</div>'
          + (m.content_name ? '<div class="media-card-type">' + escapeHtml(m.content_name_en || m.content_name) + (m.year ? ' (' + m.year + ')' : '') + '</div>' : '<div class="media-card-type">' + escapeHtml(m.media_type) + '</div>')
          + whereHtml
          + '<div class="media-card-actions">'
          + quizBtn
          + '<button class="btn-media-watched" data-id="' + escapeHtml(m.id) + '">Watched</button>'
          + '<button class="btn-media-skip" data-id="' + escapeHtml(m.id) + '">Skip</button>'
          + '<button class="btn-media-like" data-id="' + escapeHtml(m.id) + '">Like</button>'
          + '</div>'
          + '</div>';
      }
      if (freeOnly) {
        html += '<div class="media-upgrade-hint">More media at every HSK level with <button class="link-btn" onclick="showUpgradePrompt(\'media\')">Full Access</button></div>';
      }
      grid.innerHTML = html; // Safe: all data vars escaped via escapeHtml()

      // Event handlers
      grid.querySelectorAll(".btn-media-quiz").forEach(function(btn) {
        btn.addEventListener("click", function() {
          openMediaQuiz(btn.dataset.id);
        });
      });
      grid.querySelectorAll(".btn-media-watched").forEach(function(btn) {
        btn.addEventListener("click", function() {
          mediaAction("/api/media/watched", {media_id: btn.dataset.id, score: 0.0});
        });
      });
      grid.querySelectorAll(".btn-media-skip").forEach(function(btn) {
        btn.addEventListener("click", function() {
          mediaAction("/api/media/skip", {media_id: btn.dataset.id});
        });
      });
      grid.querySelectorAll(".btn-media-like").forEach(function(btn) {
        btn.addEventListener("click", function() {
          mediaAction("/api/media/liked", {media_id: btn.dataset.id, liked: true});
        });
      });
    }).catch(function() {
      { const _mg = document.getElementById("media-grid"); _mg.textContent = ""; const _es4 = document.createElement("div"); _es4.className = "empty-state"; _es4.innerHTML = '<img src="' + themedIllustration('/static/illustrations/empty-recommendations.webp') + '" alt="" class="empty-state-illustration">Failed to load recommendations.'; _mg.appendChild(_es4); handleImgErrors(_es4); }
    });
}

function mediaAction(url, data) {
  apiFetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  }).then(function() {
    loadMediaRecommendations();
    loadMediaHistory();
  }).catch(function() {});
}

function loadMediaHistory() {
  apiFetch("/api/media/history")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var listEl = document.getElementById("media-history-list");
      var hist = data.history || [];
      var stats = data.stats || {};
      if (hist.length === 0) {
        listEl.textContent = "";
        { const _es5 = document.createElement("div"); _es5.className = "empty-state"; _es5.innerHTML = '<img src="' + themedIllustration('/static/illustrations/empty-history.webp') + '" alt="" class="empty-state-illustration">No watch history yet.'; listEl.appendChild(_es5); handleImgErrors(_es5); }
        return;
      }
      var html = '<div class="media-stats">'
        + (stats.watched || 0) + ' watched'
        + (stats.overall_avg != null ? ' · avg ' + Math.round((stats.overall_avg || 0) * 100) + '%' : '')
        + '</div>';
      for (var i = 0; i < hist.length; i++) {
        var h = hist[i];
        var avg = h.avg_score != null ? Math.round(h.avg_score * 100) + '%' : '—';
        html += '<div class="media-history-item">'
          + '<span class="media-history-title">' + escapeHtml(h.title) + '</span>'
          + '<span class="media-history-score">' + avg + '</span>'
          + '</div>';
      }
      listEl.innerHTML = html; // Safe: all data vars escaped via escapeHtml()
    }).catch(function() {});
}

/* ── Media Comprehension Quiz ──────────────────── */

var _quizData = null;
var _quizAnswers = [];
var _quizCurrentQ = 0;
var _quizUserHsk = 1;

function openMediaQuiz(mediaId) {
  transitionTo("media", "media-quiz");
  _quizData = null;
  _quizAnswers = [];
  _quizCurrentQ = 0;
  _quizUserHsk = 1;

  document.getElementById("media-quiz-title").textContent = "Loading\u2026";
  document.getElementById("media-quiz-source").textContent = "";
  document.getElementById("media-quiz-source").classList.add("hidden");
  document.getElementById("media-quiz-vocab").textContent = "";
  document.getElementById("media-quiz-passage").textContent = "";
  document.getElementById("media-quiz-passage").classList.add("hidden");
  document.getElementById("media-quiz-questions").textContent = "";
  document.getElementById("media-quiz-result").classList.add("hidden");
  document.getElementById("media-quiz-cultural").classList.add("hidden");

  fetch("/api/media/comprehension/" + encodeURIComponent(mediaId))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        document.getElementById("media-quiz-title").textContent = "Quiz unavailable";
        return;
      }
      _quizData = data;
      _quizUserHsk = data.user_hsk || 1;
      document.getElementById("media-quiz-title").textContent = data.title || "Comprehension Quiz";

      // Media source info — show a clickable link with correct platform label
      var segment = data.segment || {};
      var quizWatchUrl = data.watch_url || "";
      var quizWatchLabel = data.watch_label || "";
      if (quizWatchUrl && quizWatchLabel) {
        var srcEl = document.getElementById("media-quiz-source");
        var srcHtml = '<a href="' + escapeHtml(quizWatchUrl) + '" target="_blank" rel="noopener">' + escapeHtml(quizWatchLabel) + ' &rarr;</a>';
        if (data.fallback_url && data.fallback_label) {
          srcHtml += ' <span class="media-card-alt">or <a href="' + escapeHtml(data.fallback_url) + '" target="_blank" rel="noopener">' + escapeHtml(data.fallback_label) + '</a></span>';
        }
        if (segment.start && segment.end) {
          srcHtml += ' &middot; ' + escapeHtml(segment.start) + '\u2013' + escapeHtml(segment.end);
        } else if (segment.start) {
          srcHtml += ' &middot; from ' + escapeHtml(segment.start);
        }
        srcEl.innerHTML = srcHtml; // Safe: all data vars escaped via escapeHtml()
        srcEl.classList.remove("hidden");
      } else {
        // Fallback to raw where_to_find.primary if no resolved links
        var source = data.where_to_find || {};
        if (source.primary) {
          var srcEl2 = document.getElementById("media-quiz-source");
          srcEl2.textContent = source.primary;
          srcEl2.classList.remove("hidden");
        }
      }

      // Vocab preview
      var vocab = data.vocab_preview || [];
      if (vocab.length > 0) {
        var vhtml = '<div class="quiz-vocab-label">Vocab preview</div>';
        for (var i = 0; i < vocab.length; i++) {
          vhtml += '<div class="quiz-vocab-item">'
            + '<span class="quiz-vocab-hanzi">' + escapeHtml(vocab[i].hanzi) + '</span>'
            + '<span class="quiz-vocab-pinyin">' + escapeHtml(vocab[i].pinyin || "") + '</span>'
            + '<span class="quiz-vocab-english">' + escapeHtml(vocab[i].english || "") + '</span>'
            + '</div>';
        }
        document.getElementById("media-quiz-vocab").innerHTML = vhtml; // Safe: all data vars escaped via escapeHtml()
      }

      // Passage context
      var passageZh = data.passage_zh || "";
      var passageEn = data.passage_en || "";
      if (passageZh) {
        var pEl = document.getElementById("media-quiz-passage");
        var phtml = '<div class="quiz-passage-label">Passage</div>'
          + '<div class="quiz-passage-zh">' + escapeHtml(passageZh) + '</div>';
        if (passageEn) {
          phtml += '<div class="quiz-passage-en">' + escapeHtml(passageEn) + '</div>';
        }
        pEl.innerHTML = phtml; // Safe: all data vars escaped via escapeHtml()
        pEl.classList.remove("hidden");
      }

      // Render first question
      renderQuizQuestion(0);
    })
    .catch(function() {
      document.getElementById("media-quiz-title").textContent = "Couldn\u2019t load quiz";
    });
}

function renderQuizQuestion(idx) {
  var questions = _quizData.questions || [];
  if (idx >= questions.length) {
    finishQuiz();
    return;
  }
  var q = questions[idx];
  // Skip questions with blank text
  if (!q || (!q.q_zh && !q.q_en)) {
    renderQuizQuestion(idx + 1);
    return;
  }
  // Skip mc questions with no options or no correct answer
  var qType = q.type || "mc";
  if (qType === "mc") {
    var opts = q.options || [];
    if (opts.length < 2 || !opts.some(function(o) { return o.correct; })) {
      renderQuizQuestion(idx + 1);
      return;
    }
  }
  _quizCurrentQ = idx;
  var container = document.getElementById("media-quiz-questions");

  // Scaffolding rules by user HSK level:
  // HSK 1-2: show q_en primary, q_zh secondary; options show hanzi + pinyin + text_en
  // HSK 3-4: show q_en primary, q_zh secondary; options show hanzi + text_en (no pinyin)
  // HSK 5-6: show q_zh primary, q_en secondary; options show hanzi only
  // HSK 7+:  show q_zh only; options show hanzi only
  var showQEn = _quizUserHsk <= 6 && q.q_en;
  var showQZh = _quizUserHsk >= 1;
  var showOptPinyin = _quizUserHsk <= 2;
  var showOptEn = _quizUserHsk <= 4;
  var qEnFirst = _quizUserHsk <= 4;

  var html = '<div class="quiz-question">'
    + '<div class="quiz-q-number">Q' + (idx + 1) + ' of ' + questions.length + '</div>';
  if (qEnFirst && showQEn) {
    html += '<div class="quiz-q-en">' + escapeHtml(q.q_en) + '</div>';
    if (showQZh) html += '<div class="quiz-q-text quiz-q-secondary">' + escapeHtml(q.q_zh || "") + '</div>';
  } else {
    if (showQZh) html += '<div class="quiz-q-text">' + escapeHtml(q.q_zh || "") + '</div>';
    if (showQEn) html += '<div class="quiz-q-en">' + escapeHtml(q.q_en) + '</div>';
  }

  var options = [];
  if (qType === "mc") {
    options = shuffleArray(q.options || []);
    for (var i = 0; i < options.length; i++) {
      var optHtml = escapeHtml(options[i].text || "");
      if (showOptPinyin && options[i].pinyin) {
        optHtml += ' <span class="quiz-option-pinyin">' + escapeHtml(options[i].pinyin) + '</span>';
      }
      if (showOptEn && options[i].text_en) {
        optHtml += ' <span class="quiz-option-en">(' + escapeHtml(options[i].text_en) + ')</span>';
      }
      html += '<button class="quiz-option" data-idx="' + i + '">' + optHtml + '</button>';
    }
  } else if (qType === "vocab_check") {
    var allOpts = shuffleArray([q.answer].concat(q.distractors || []));
    options = allOpts.map(function(o) { return {text: o, correct: o === q.answer}; });
    for (var i = 0; i < options.length; i++) {
      html += '<button class="quiz-option" data-idx="' + i + '">'
        + escapeHtml(options[i].text)
        + '</button>';
    }
  }

  // Explanation area (hidden until answered)
  var explanation = q.explanation || '';
  html += '<div class="mc-feedback hidden" data-explanation="' + escapeHtml(explanation) + '"></div>';

  html += '</div>';
  container.innerHTML = html; // Safe: all data vars escaped via escapeHtml()

  // Store shuffled options for answer checking
  container._options = options;
  container._qType = qType;

  container.querySelectorAll(".quiz-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      handleQuizAnswer(parseInt(btn.dataset.idx));
    });
  });
}

function handleQuizAnswer(optIdx) {
  var container = document.getElementById("media-quiz-questions");
  var options = container._options;
  var qType = container._qType;
  var isCorrect = false;

  if (qType === "mc") {
    isCorrect = !!(options[optIdx] && options[optIdx].correct);
  } else {
    isCorrect = !!(options[optIdx] && options[optIdx].correct);
  }

  _quizAnswers.push(isCorrect);

  // Highlight correct/incorrect
  var buttons = container.querySelectorAll(".quiz-option");
  buttons.forEach(function(btn, i) {
    btn.disabled = true;
    var opt = options[i];
    if (opt && opt.correct) {
      btn.classList.add("quiz-option-correct");
    } else if (i === optIdx && !isCorrect) {
      btn.classList.add("quiz-option-incorrect");
    }
  });

  // Show explanation if available
  var feedbackEl = container.querySelector(".mc-feedback");
  if (feedbackEl && feedbackEl.dataset.explanation) {
    feedbackEl.textContent = feedbackEl.dataset.explanation;
    feedbackEl.classList.remove("hidden");
  }

  // Show "Next" button so learner can read explanation
  var nextBtn = document.createElement("button");
  nextBtn.className = "btn-secondary quiz-next-btn";
  nextBtn.textContent = (_quizCurrentQ + 1 < (_quizData.questions || []).length) ? "Next" : "See results";
  nextBtn.style.marginTop = "var(--space-4)";
  container.querySelector(".quiz-question").appendChild(nextBtn);
  nextBtn.addEventListener("click", function() {
    renderQuizQuestion(_quizCurrentQ + 1);
  });
}

function finishQuiz() {
  var correct = _quizAnswers.filter(function(a) { return a; }).length;
  var total = _quizAnswers.length;
  var score = total > 0 ? correct / total : 0;

  // Show result
  var resultEl = document.getElementById("media-quiz-result");
  // Safe: correct, total, score are all locally-computed numbers
  resultEl.innerHTML = '<div class="quiz-score">' + correct + ' of ' + total
    + ' (' + Math.round(score * 100) + '%)</div>';
  resultEl.classList.remove("hidden");
  document.getElementById("media-quiz-questions").textContent = "";

  // Show cultural note + follow-up
  if (_quizData.cultural_note || _quizData.follow_up) {
    var chtml = "";
    if (_quizData.cultural_note) {
      chtml += '<div class="quiz-cultural-note">' + escapeHtml(_quizData.cultural_note) + '</div>';
    }
    if (_quizData.follow_up) {
      chtml += '<div class="quiz-follow-up">' + escapeHtml(_quizData.follow_up) + '</div>';
    }
    var culturalEl = document.getElementById("media-quiz-cultural");
    culturalEl.innerHTML = chtml; // Safe: all data vars escaped via escapeHtml()
    culturalEl.classList.remove("hidden");
  }

  // Submit results
  apiFetch("/api/media/comprehension/submit", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      media_id: _quizData.id,
      score: score,
      total: total,
      correct: correct
    })
  }).then(function() {
    _fetchMediaStats();
  });
}

function shuffleArray(arr) {
  var a = arr.slice();
  for (var i = a.length - 1; i > 0; i--) {
    var j = Math.floor(Math.random() * (i + 1));
    var tmp = a[i]; a[i] = a[j]; a[j] = tmp;
  }
  return a;
}

/* ── Listening View ──────────────────────────── */

var _listeningPassage = null;
var _listeningWordsLookedUp = [];
var _listeningPlayed = false;

var _listeningMode = "listen"; // "listen" or "dictation"

function openListeningView() {
  EventLog.record("view", "listening");
  transitionTo("dashboard", "listening");
  _listeningWordsLookedUp = [];
  _listeningPlayed = false;
  _listeningMode = "listen";
  loadListeningPassage();
  showFeatureTooltip("listening", "Listen to a passage, then reveal the text. Tap unfamiliar words to look them up.");

  // Load display preferences so transcript reveal respects them
  loadDisplayPrefs();

  var levelSelect = document.getElementById("listening-level");
  if (levelSelect) {
    levelSelect.removeEventListener("change", loadListeningPassage);
    levelSelect.addEventListener("change", loadListeningPassage);
  }
  var playBtn = document.getElementById("listening-play");
  if (playBtn) { playBtn.onclick = playListeningPassage; }
  var replayBtn = document.getElementById("listening-replay");
  if (replayBtn) { replayBtn.onclick = playListeningPassage; }
  var revealBtn = document.getElementById("listening-reveal");
  if (revealBtn) { revealBtn.onclick = revealTranscript; }
  var newBtn = document.getElementById("listening-new");
  if (newBtn) { newBtn.onclick = function() { loadListeningPassage(); _resetDictationUI(); }; }

  // Mode tabs (Listen vs Dictation)
  document.querySelectorAll(".listening-mode-tab").forEach(function(tab) {
    tab.addEventListener("click", function() {
      var mode = tab.dataset.mode;
      _listeningMode = mode;
      document.querySelectorAll(".listening-mode-tab").forEach(function(t) { t.classList.remove("active"); });
      tab.classList.add("active");
      _updateListeningModeUI();
      EventLog.record("listening", "mode_switch", {mode: mode});
    });
  });

  // Dictation check button
  var dictCheckBtn = document.getElementById("dictation-check");
  if (dictCheckBtn) { dictCheckBtn.onclick = checkDictation; }

  _updateListeningModeUI();
}

function _updateListeningModeUI() {
  var dictArea = document.getElementById("listening-dictation-area");
  var revealBtn = document.getElementById("listening-reveal");
  var transcriptEl = document.getElementById("listening-transcript");
  var questionsEl = document.getElementById("listening-questions");

  if (_listeningMode === "dictation") {
    // Show dictation area, hide reveal/transcript/questions
    if (dictArea) dictArea.classList.remove("hidden");
    if (revealBtn) revealBtn.classList.add("hidden");
    if (transcriptEl) transcriptEl.classList.add("hidden");
    if (questionsEl) questionsEl.classList.add("hidden");
  } else {
    // Normal listen mode
    if (dictArea) dictArea.classList.add("hidden");
    // Reveal button shown after play
    if (_listeningPlayed && revealBtn) revealBtn.classList.remove("hidden");
  }
}

function _resetDictationUI() {
  var input = document.getElementById("dictation-input");
  var result = document.getElementById("dictation-result");
  if (input) input.value = "";
  if (result) { result.innerHTML = ""; result.classList.add("hidden"); }
}

function checkDictation() {
  if (!_listeningPassage) return;

  var input = document.getElementById("dictation-input");
  var resultEl = document.getElementById("dictation-result");
  if (!input || !resultEl) return;

  var userText = input.value.trim();
  if (!userText) return;

  var expected = (_listeningPassage.text_zh || "").trim();
  // Normalize: remove spaces and some punctuation for comparison
  var normExpected = expected.replace(/[\s。，！？、；：""''（）\u3000]/g, "");
  var normUser = userText.replace(/[\s。，！？、；：""''（）\u3000]/g, "");

  // Character-by-character comparison
  var html = '<div class="dictation-diff">';
  var correct = 0;
  var total = Math.max(normExpected.length, normUser.length);

  for (var i = 0; i < Math.max(normExpected.length, normUser.length); i++) {
    if (i < normExpected.length && i < normUser.length) {
      if (normExpected[i] === normUser[i]) {
        html += '<span class="char-correct">' + escapeHtml(normExpected[i]) + '</span>';
        correct++;
      } else {
        html += '<span class="char-wrong" title="Expected: ' + escapeHtml(normExpected[i]) + '">' + escapeHtml(normUser[i]) + '</span>';
      }
    } else if (i < normExpected.length) {
      html += '<span class="char-missing">' + escapeHtml(normExpected[i]) + '</span>';
    } else {
      html += '<span class="char-wrong">' + escapeHtml(normUser[i]) + '</span>';
    }
  }
  html += '</div>';

  var pct = total > 0 ? Math.round(correct / total * 100) : 0;
  var scoreHtml = '<div class="dictation-score">' + pct + '% accurate</div>';

  // Show expected text
  var expectedHtml = '<div style="margin-top:8px;font-size:13px;color:var(--color-text-dim);">'
    + '<strong>Expected:</strong> ' + escapeHtml(expected) + '</div>';

  resultEl.innerHTML = scoreHtml + html + expectedHtml;
  resultEl.classList.remove("hidden");

  EventLog.record("listening", "dictation_check", {score: pct, chars: total});
}

function loadListeningPassage() {
  var level = document.getElementById("listening-level").value;
  var url = "/api/listening/passage" + (level ? "?hsk_level=" + level : "");
  fetch(url).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) {
      document.getElementById("listening-title").textContent = data.error;
      return;
    }
    _listeningPassage = data;
    _listeningWordsLookedUp = [];
    _listeningPlayed = false;

    document.getElementById("listening-title").textContent = data.title_zh || data.title || "Passage";
    document.getElementById("listening-play").classList.remove("hidden");
    document.getElementById("listening-replay").classList.add("hidden");
    document.getElementById("listening-reveal").classList.add("hidden");
    document.getElementById("listening-transcript").classList.add("hidden");
    document.getElementById("listening-questions").classList.add("hidden");
  }).catch(function() {
    document.getElementById("listening-title").textContent = "Couldn\u2019t load passage.";
  });
}

function _showListeningPlaying() {
  var playingIndicator = document.getElementById("listening-playing-indicator");
  if (!playingIndicator) {
    playingIndicator = document.createElement("span");
    playingIndicator.id = "listening-playing-indicator";
    playingIndicator.className = "listening-playing-indicator";
    playingIndicator.textContent = "Playing...";
    var titleEl = document.getElementById("listening-title");
    if (titleEl) titleEl.parentNode.insertBefore(playingIndicator, titleEl.nextSibling);
  }
  playingIndicator.classList.remove("hidden");
  return playingIndicator;
}

function _playWithBrowserTTS(text) {
  if (!window.speechSynthesis) return false;
  var utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  var speedSelect = document.getElementById("listening-speed");
  utterance.rate = parseFloat(speedSelect.value) || 1.0;
  var zhVoice = _cachedZhVoice || speechSynthesis.getVoices().find(function(v) { return v.lang.startsWith("zh"); });
  if (zhVoice) utterance.voice = zhVoice;

  var indicator = _showListeningPlaying();
  var _ttsTimeout = null;
  function _clear() { if (_ttsTimeout) { clearTimeout(_ttsTimeout); _ttsTimeout = null; } }
  utterance.onend = function() { _clear(); if (indicator) indicator.classList.add("hidden"); };
  utterance.onerror = function() { _clear(); if (indicator) indicator.classList.add("hidden"); };
  speechSynthesis.cancel();
  speechSynthesis.speak(utterance);
  _ttsTimeout = setTimeout(function() { _ttsTimeout = null; speechSynthesis.cancel(); if (indicator) indicator.classList.add("hidden"); }, 30000);
  return true;
}

function playListeningPassage() {
  if (!_listeningPassage) return;
  var text = _listeningPassage.text_zh || "";
  if (!text) return;

  // Get playback speed from the speed selector
  var speedSelect = document.getElementById("listening-speed");
  var playbackRate = parseFloat(speedSelect ? speedSelect.value : "1.0") || 1.0;

  // Try server-side TTS first (higher quality macOS voices)
  var indicator = _showListeningPlaying();
  apiFetch("/api/tts", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text: text})
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.url) {
      // Play server-generated audio with speed control
      var audio = new Audio(data.url);
      audio.playbackRate = playbackRate;
      audio.onended = function() { if (indicator) indicator.classList.add("hidden"); };
      audio.onerror = function() {
        if (indicator) indicator.classList.add("hidden");
        _playWithBrowserTTS(text);  // Fallback
      };
      audio.play().catch(function() { _playWithBrowserTTS(text); });
    } else {
      _playWithBrowserTTS(text);  // Server TTS unavailable, use browser
    }
  }).catch(function() {
    _playWithBrowserTTS(text);  // Network error, use browser
  });

  _listeningPlayed = true;
  document.getElementById("listening-play").classList.add("hidden");
  document.getElementById("listening-replay").classList.remove("hidden");
  // Update mode-specific UI
  _updateListeningModeUI();
}

function revealTranscript() {
  if (!_listeningPassage) return;
  var transcriptEl = document.getElementById("listening-transcript");
  var textEl = document.getElementById("listening-text");
  transcriptEl.classList.remove("hidden");
  document.getElementById("listening-reveal").classList.add("hidden");

  // Render clickable text (same as reading view)
  var text = _listeningPassage.text_zh || "";
  var html = "";
  for (var i = 0; i < text.length; i++) {
    var ch = text[i];
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) {
      html += '<span class="reading-word" data-char="' + escapeHtml(ch) + '">' + escapeHtml(ch) + '</span>';
    } else {
      html += escapeHtml(ch);
    }
  }

  // Add pinyin and translation if available, respecting display prefs
  var pinyinText = _listeningPassage.text_pinyin || "";
  var transText = _listeningPassage.text_en || "";
  if (pinyinText) {
    var pinyinHidden = _displayPrefs.reading_show_pinyin ? "" : " hidden";
    html += '<div id="listening-pinyin" class="reading-pinyin' + pinyinHidden + '">'
          + escapeHtml(pinyinText) + '</div>';
  }
  if (transText) {
    var transHidden = _displayPrefs.reading_show_translation ? "" : " hidden";
    html += '<div id="listening-translation" class="reading-translation' + transHidden + '">'
          + escapeHtml(transText) + '</div>';
  }

  textEl.innerHTML = html; // Safe: all vars escaped via escapeHtml()

  textEl.querySelectorAll(".reading-word").forEach(function(span) {
    span.addEventListener("click", function(e) {
      _listeningWordsLookedUp.push(span.dataset.char);
      span.classList.add("listening-word-looked-up");
      lookupWord(span.dataset.char, e);
    });
  });

  // Show comprehension questions if available
  showListeningQuestions();
}

/**
 * Reusable MC question renderer for reading and listening comprehension.
 * Renders proper multiple-choice questions with HSK-based language scaffolding.
 * @param {HTMLElement} container - DOM element to render into
 * @param {Array} questions - Array of MC question objects
 * @param {number} userHsk - User's HSK level for scaffolding
 * @param {Function} [onComplete] - Optional callback when all questions answered
 */
function renderMCQuestions(container, questions, userHsk, onComplete) {
  if (!questions || questions.length === 0) return;

  var score = {correct: 0, total: 0};
  // Scaffolding rules (same as media quiz):
  var showQEn = userHsk <= 6;
  var showOptPinyin = userHsk <= 2;
  var showOptEn = userHsk <= 4;
  var qEnFirst = userHsk <= 4;

  var html = '<h3>Comprehension</h3>';
  for (var qi = 0; qi < questions.length; qi++) {
    var q = questions[qi];
    var opts = q.options || [];
    // Shuffle options for this render
    var shuffled = [];
    for (var si = 0; si < opts.length; si++) shuffled.push(opts[si]);
    for (var si = shuffled.length - 1; si > 0; si--) {
      var j = Math.floor(Math.random() * (si + 1));
      var tmp = shuffled[si]; shuffled[si] = shuffled[j]; shuffled[j] = tmp;
    }

    html += '<div class="mc-question" data-q-idx="' + qi + '">';
    html += '<div class="mc-q-number">Q' + (qi + 1) + ' of ' + questions.length + '</div>';

    // Question text with scaffolding
    if (qEnFirst && showQEn && q.q_en) {
      html += '<div class="mc-q-en">' + escapeHtml(q.q_en) + '</div>';
      if (q.q_zh) html += '<div class="mc-q-zh mc-q-secondary">' + escapeHtml(q.q_zh) + '</div>';
    } else {
      if (q.q_zh) html += '<div class="mc-q-zh">' + escapeHtml(q.q_zh) + '</div>';
      if (showQEn && q.q_en) html += '<div class="mc-q-en">' + escapeHtml(q.q_en) + '</div>';
    }

    // Options
    html += '<div class="mc-options">';
    for (var oi = 0; oi < shuffled.length; oi++) {
      var opt = shuffled[oi];
      var optLabel = escapeHtml(opt.text || "");
      if (showOptPinyin && opt.pinyin) {
        optLabel += ' <span class="mc-opt-pinyin">' + escapeHtml(opt.pinyin) + '</span>';
      }
      if (showOptEn && opt.text_en) {
        optLabel += ' <span class="mc-opt-en">(' + escapeHtml(opt.text_en) + ')</span>';
      }
      html += '<button class="mc-option btn-secondary" data-q="' + qi + '" data-o="' + oi + '" data-correct="' + (opt.correct ? '1' : '0') + '">'
        + optLabel + '</button>';
    }
    html += '</div>';
    // Store explanation for reveal after answering
    var explanation = q.explanation || '';
    html += '<div class="mc-feedback hidden" data-explanation="' + escapeHtml(explanation) + '"></div>';
    html += '</div>';
  }
  html += '<div class="mc-score hidden"></div>';
  container.innerHTML = html; // Safe: all data vars escaped via escapeHtml()

  // Click handlers
  container.querySelectorAll(".mc-option").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var qIdx = parseInt(btn.dataset.q);
      var questionEl = btn.closest(".mc-question");
      // Prevent double-answering
      if (questionEl.classList.contains("mc-answered")) return;
      questionEl.classList.add("mc-answered");

      var isCorrect = btn.dataset.correct === "1";
      score.total++;
      if (isCorrect) score.correct++;

      // Highlight correct/incorrect
      btn.classList.add(isCorrect ? "mc-correct" : "mc-incorrect");
      if (!isCorrect) {
        // Show correct answer
        questionEl.querySelectorAll(".mc-option").forEach(function(ob) {
          if (ob.dataset.correct === "1") ob.classList.add("mc-correct");
        });
      }
      // Disable all options
      questionEl.querySelectorAll(".mc-option").forEach(function(ob) {
        ob.disabled = true;
      });

      // Show explanation if available
      var feedbackEl = questionEl.querySelector(".mc-feedback");
      if (feedbackEl && feedbackEl.dataset.explanation) {
        feedbackEl.textContent = feedbackEl.dataset.explanation;
        feedbackEl.classList.remove("hidden");
      }

      // Show score when all answered
      if (score.total === questions.length) {
        var pct = Math.round(score.correct / score.total * 100);
        var scoreEl = container.querySelector(".mc-score");
        scoreEl.textContent = 'Comprehension: ' + score.correct + '/' + score.total + ' (' + pct + '%)';
        scoreEl.classList.remove("hidden");
        if (onComplete) onComplete(score);
      }
    });
  });
}

function showListeningQuestions() {
  if (!_listeningPassage || !_listeningPassage.questions || _listeningPassage.questions.length === 0) {
    // No questions — still post completion with looked-up words
    _postListeningComplete(0, 0);
    return;
  }
  var qEl = document.getElementById("listening-questions");
  qEl.classList.remove("hidden");

  renderMCQuestions(qEl, _listeningPassage.questions, _quizUserHsk || 1, function(score) {
    var compScore = score.total > 0 ? score.correct / score.total : 0;
    _postListeningComplete(score.correct, score.total);
    _fetchListeningStats();
  });
}

function _postListeningComplete(questionsCorrect, questionsTotal) {
  if (!_listeningPassage) return;
  var compScore = questionsTotal > 0 ? questionsCorrect / questionsTotal : 0;
  var wordsEncountered = [];
  for (var i = 0; i < _listeningWordsLookedUp.length; i++) {
    wordsEncountered.push({hanzi: _listeningWordsLookedUp[i], looked_up: true});
  }
  apiFetch("/api/listening/complete", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      passage_id: _listeningPassage.id,
      comprehension_score: compScore,
      questions_correct: questionsCorrect,
      questions_total: questionsTotal,
      hsk_level: _listeningPassage.hsk_level || 1,
      words_encountered: wordsEncountered
    })
  });
}

function _fetchListeningStats() {
  apiFetch("/api/listening/stats").then(function(r) { return r.json(); }).then(function(data) {
    var statsEl = document.getElementById("listening-stats");
    if (!statsEl || data.error) return;
    var html = '';
    html += '<div class="listening-stats-item"><span class="listening-stats-value">' + (data.total_completed || 0) + '</span><span class="listening-stats-label">Passages</span></div>';
    html += '<div class="listening-stats-item"><span class="listening-stats-value">' + (data.avg_comprehension || 0) + '%</span><span class="listening-stats-label">Avg Comprehension</span></div>';
    html += '<div class="listening-stats-item"><span class="listening-stats-value">' + (data.total_words_looked_up || 0) + '</span><span class="listening-stats-label">Words Looked Up</span></div>';
    statsEl.innerHTML = html;
    statsEl.classList.remove("hidden");
  }).catch(function() {});
}

/* ── Encounter stats on dashboard ──────────────────────── */

function fetchEncounterStats() {
  fetch("/api/encounters/summary")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error || !data.total_lookups_7d) return;
      // Show encounter count near the exposure buttons
      var actionsEl = document.querySelector(".actions-exposure");
      if (!actionsEl) return;
      var existing = document.getElementById("encounter-badge");
      if (existing) existing.remove();
      var badge = document.createElement("div");
      badge.id = "encounter-badge";
      badge.className = "encounter-badge";
      var badgeText = data.total_lookups_7d + " words looked up this week";
      // Show top looked-up word if available
      var top_words = data.top_words || [];
      if (top_words.length > 0) {
        badgeText += " \u00b7 most looked up: " + top_words[0].hanzi;
      }
      // Show source breakdown if available
      var sources = data.sources || {};
      var sourceKeys = Object.keys(sources);
      if (sourceKeys.length > 0) {
        var sourceParts = [];
        for (var si = 0; si < sourceKeys.length; si++) {
          sourceParts.push(sourceKeys[si] + ": " + sources[sourceKeys[si]]);
        }
        badgeText += " (" + sourceParts.join(", ") + ")";
      }
      badge.textContent = badgeText;
      actionsEl.parentNode.insertBefore(badge, actionsEl.nextSibling);
    }).catch(function() {});
}

/* ── Event listeners (CSP-safe, no inline handlers) ────────────────────────── */

/* ── Onboarding wizard ───────────────────────────── */
function checkOnboarding() {
  fetch("/api/onboarding/wizard").then(function(r) { return r.json(); }).then(function(data) {
    if (data.complete) return;
    showOnboardingWizard();
  }).catch(function() {});
}

function _refreshDashboardAfterOnboarding() {
  // Re-fetch status and update dashboard buttons/panels without full reload
  var btnStart = document.getElementById("btn-start");
  var btnMini = document.getElementById("btn-mini");
  fetch("/api/status").then(function(r) { return r.json(); }).then(function(data) {
    var count = data.item_count || 0;
    var totalSessions = data.total_sessions || 0;
    var sessionLength = data.session_length || 12;
    var fullMins = Math.round(sessionLength * 35 / 60);
    var miniMins = Math.round(5 * 35 / 60);
    if (btnStart) {
      btnStart.disabled = count === 0;
      btnStart.textContent = totalSessions === 0
        ? "Start Your First Session (~" + fullMins + " min)"
        : "Begin (~" + fullMins + " min)";
    }
    if (btnMini) {
      btnMini.disabled = count === 0;
      btnMini.textContent = "Quick session (~" + miniMins + " min)";
    }
    window._totalSessionsBefore = totalSessions;
    // Show/hide panels for new users
    if (totalSessions < 3) {
      ["forecast-panel", "retention-panel", "diagnostics-panel"].forEach(function(id) {
        var panel = document.getElementById(id);
        if (panel) panel.style.display = "none";
      });
    }
  }).catch(function() {
    if (btnStart) { btnStart.disabled = false; btnStart.textContent = "Begin"; }
  });
  // Reload dashboard panels
  if (typeof loadDashboardPanels === "function") loadDashboardPanels();
}

function showOnboardingWizard() {
  var dashboard = document.getElementById("dashboard");
  if (!dashboard) return;
  // Build wizard overlay
  var overlay = document.createElement("div");
  overlay.id = "onboarding-wizard";
  overlay.className = "onboarding-wizard";
  overlay.innerHTML =
    '<div class="onboarding-wizard-card">' +
      '<div class="auth-logo"><div class="logo-mark" aria-hidden="true">\u6F2B</div>' +
      '<div class="logo-text">Aelu</div></div>' +

      // Intro slides — shown before the level/goal picker
      '<div id="onboarding-intro-0" class="onboarding-step onboarding-intro-slide">' +
        '<img class="onboarding-intro-img" src="' + themedIllustration('/static/illustrations/onboarding-1.webp') + '" alt="" />' +
        '<div class="onboarding-intro-body">' +
          '<p class="onboarding-intro-heading">Every language lives in memory</p>' +
          '<p class="onboarding-intro-text">When you learn a new word, your brain begins forgetting it almost immediately. ' +
            'This is not a flaw \u2014 it\u2019s how memory works. ' +
            'Aelu brings words back at the moment you\u2019re about to forget them, ' +
            'so each review strengthens the connection a little more.</p>' +
        '</div>' +
        '<button class="btn-primary onboarding-next-btn" id="onboarding-next-0">Continue</button>' +
        '<button class="btn-link btn-sm onboarding-skip-btn" id="onboarding-skip-0">Skip intro</button>' +
      '</div>' +

      '<div id="onboarding-intro-1" class="onboarding-step onboarding-intro-slide hidden">' +
        '<img class="onboarding-intro-img" src="' + themedIllustration('/static/illustrations/onboarding-2.webp') + '" alt="" />' +
        '<div class="onboarding-intro-body">' +
          '<p class="onboarding-intro-heading">Short sessions, real progress</p>' +
          '<p class="onboarding-intro-text">Each session is a few minutes of focused practice \u2014 ' +
            'characters, tones, meanings, recall. ' +
            'Aelu adapts to your strengths and where you need more practice, ' +
            'so your time is spent where it matters most.</p>' +
        '</div>' +
        '<button class="btn-primary onboarding-next-btn" id="onboarding-next-1">Continue</button>' +
        '<button class="btn-link btn-sm onboarding-skip-btn" id="onboarding-skip-1">Skip intro</button>' +
      '</div>' +

      '<div id="onboarding-intro-2" class="onboarding-step onboarding-intro-slide hidden">' +
        '<img class="onboarding-intro-img" src="' + themedIllustration('/static/illustrations/onboarding-3.webp') + '" alt="" />' +
        '<div class="onboarding-intro-body">' +
          '<p class="onboarding-intro-heading">Be patient with yourself</p>' +
          '<p class="onboarding-intro-text">Learning Mandarin is a long journey, and some days will feel slower than others. ' +
            'That\u2019s okay. Aelu tracks what you actually remember \u2014 not points or streaks \u2014 ' +
            'so you always know where you truly stand.</p>' +
        '</div>' +
        '<button class="btn-primary onboarding-next-btn" id="onboarding-next-2">Let\u2019s begin</button>' +
      '</div>' +

      // Step 1: level picker
      '<div id="onboarding-step-1" class="onboarding-step hidden">' +
        '<p>What HSK level are you starting from?</p>' +
        '<div class="onboarding-options" id="onboarding-levels">' +
          '<button class="btn-secondary onboarding-opt" data-level="1">HSK 1 \u2014 Beginner<br><small>New to Mandarin. ~150 core words.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-level="2">HSK 2 \u2014 Elementary<br><small>Basic conversations. ~300 words.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-level="3">HSK 3 \u2014 Intermediate<br><small>Daily topics. ~600 words.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-level="4">HSK 4 \u2014 Upper-Intermediate<br><small>Fluent on familiar topics. ~1200 words.</small></button>' +
        '</div>' +
        '<div style="margin-top:var(--space-3);text-align:center">' +
          '<button class="btn-link btn-sm" id="onboarding-placement-btn">Not sure? Take a placement quiz</button>' +
        '</div>' +
      '</div>' +

      // Step 2: session length
      '<div id="onboarding-step-2" class="onboarding-step hidden">' +
        '<p>How much time per session?</p>' +
        '<div class="onboarding-options" id="onboarding-goals">' +
          '<button class="btn-secondary onboarding-opt" data-goal="quick">Quick \u2014 5 min<br><small>A few drills. Good for daily habit.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-goal="standard">Standard \u2014 10 min<br><small>Balanced review and new material.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-goal="deep">Deep \u2014 20 min<br><small>Thorough practice. Best for retention.</small></button>' +
        '</div>' +
        '<button class="btn-secondary onboarding-back-btn" id="onboarding-back" style="margin-top:var(--space-3);width:100%">&larr; Back</button>' +
      '</div>' +
    '</div>';
  document.getElementById("app").appendChild(overlay);
  handleImgErrors(overlay, '/static/illustrations/onboarding-1.png');

  // Intro slide navigation
  var introSteps = [
    document.getElementById("onboarding-intro-0"),
    document.getElementById("onboarding-intro-1"),
    document.getElementById("onboarding-intro-2")
  ];

  var _introTransitioning = false;
  function goToIntroSlide(idx) {
    if (_introTransitioning) return;
    // Find currently visible slide
    var current = null;
    introSteps.forEach(function(el) {
      if (!el.classList.contains("hidden")) current = el;
    });
    var nextEl = idx < introSteps.length ? introSteps[idx] : document.getElementById("onboarding-step-1");

    if (current && current !== nextEl) {
      _introTransitioning = true;
      current.classList.add("slide-out");
      current.addEventListener("animationend", function handler() {
        current.removeEventListener("animationend", handler);
        current.classList.add("hidden");
        current.classList.remove("slide-out");
        nextEl.classList.remove("hidden");
        _introTransitioning = false;
      }, { once: true });
      // Fallback if animationend doesn't fire
      setTimeout(function() {
        if (_introTransitioning) {
          current.classList.add("hidden");
          current.classList.remove("slide-out");
          nextEl.classList.remove("hidden");
          _introTransitioning = false;
        }
      }, 400);
    } else {
      introSteps.forEach(function(el) { el.classList.add("hidden"); });
      nextEl.classList.remove("hidden");
    }
  }

  function skipToLevelPicker() {
    introSteps.forEach(function(el) { el.classList.add("hidden"); el.classList.remove("slide-out"); });
    document.getElementById("onboarding-step-1").classList.remove("hidden");
    _introTransitioning = false;
    EventLog.queueClientEvent("onboarding", "step_view", {step_name: "level_picker"});
  }

  // Wire Continue / Skip buttons on each intro slide
  for (var _si = 0; _si < introSteps.length; _si++) {
    (function(idx) {
      var nextBtn = document.getElementById("onboarding-next-" + idx);
      var skipBtn = document.getElementById("onboarding-skip-" + idx);
      if (nextBtn) nextBtn.addEventListener("click", function() {
        AeluSound.onboardingStep();
        EventLog.queueClientEvent("onboarding", "step_complete", {step_name: "intro_" + idx});
        goToIntroSlide(idx + 1);
      });
      if (skipBtn) skipBtn.addEventListener("click", function() {
        EventLog.queueClientEvent("onboarding", "step_skip", {step_name: "intro_" + idx});
        skipToLevelPicker();
      });
    })(_si);
  }

  // Placement quiz option
  var placementBtn = document.getElementById("onboarding-placement-btn");
  if (placementBtn) {
    placementBtn.addEventListener("click", function() {
      showPlacementQuiz(overlay);
    });
  }

  // Step 1: level
  overlay.querySelectorAll("[data-level]").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var level = parseInt(btn.getAttribute("data-level"));
      apiFetch("/api/onboarding/level", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({level: level})
      }).then(function() {
        EventLog.queueClientEvent("onboarding", "step_complete", {step_name: "level_picker", level: level});
        document.getElementById("onboarding-step-1").classList.add("hidden");
        document.getElementById("onboarding-step-2").classList.remove("hidden");
        EventLog.queueClientEvent("onboarding", "step_view", {step_name: "session_length"});
      });
    });
  });

  // Back button in step 2
  var backBtn = document.getElementById("onboarding-back");
  if (backBtn) {
    backBtn.addEventListener("click", function() {
      document.getElementById("onboarding-step-2").classList.add("hidden");
      document.getElementById("onboarding-step-1").classList.remove("hidden");
    });
  }

  // Step 2: goal
  overlay.querySelectorAll("[data-goal]").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var goal = btn.getAttribute("data-goal");
      apiFetch("/api/onboarding/goal", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({goal: goal})
      }).then(function() {
        return apiFetch("/api/onboarding/complete", {method: "POST"});
      }).then(function() {
        // Smooth CSS fade instead of full page reload
        overlay.classList.add("onboarding-exit");
        overlay.addEventListener("transitionend", function() {
          overlay.remove();
        });
        // Fallback removal if transitionend doesn't fire
        setTimeout(function() { if (overlay.parentNode) overlay.remove(); }, 500);
        // Re-run dashboard init from status, then auto-start first session
        _refreshDashboardAfterOnboarding();
        // Auto-bridge into first session after onboarding
        if (window._totalSessionsBefore === 0 || window._totalSessionsBefore == null) {
          var bridge = document.createElement("div");
          bridge.className = "onboarding-bridge";
          bridge.innerHTML = '<div class="onboarding-bridge-inner">'
            + '<div class="onboarding-bridge-logo">\u6F2B</div>'
            + '<div class="onboarding-bridge-text">Starting your first session\u2026</div>'
            + '</div>';
          document.body.appendChild(bridge);
          requestAnimationFrame(function() { bridge.classList.add("onboarding-bridge-visible"); });
          setTimeout(function() {
            bridge.classList.remove("onboarding-bridge-visible");
            bridge.classList.add("onboarding-bridge-exit");
            setTimeout(function() { if (bridge.parentNode) bridge.remove(); }, 500);
            startSession("standard");
          }, 1200);
        }
      });
    });
  });
}

document.addEventListener("DOMContentLoaded", function() {
  // Force WebKit re-composite to fix stale hit-test geometry after splash→app navigation
  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      document.body.style.transform = 'translateZ(0)';
      requestAnimationFrame(function() { document.body.style.transform = ''; });
    });
  });

  // HTTPS check for iOS — microphone requires secure context
  if (location.protocol === "http:" && /iPad|iPhone|iPod/.test(navigator.userAgent)) {
    var httpsBanner = document.createElement("div");
    httpsBanner.className = "https-warning";
    httpsBanner.textContent = "HTTPS required for microphone on iOS. Speaking drills may not work.";
    document.body.prepend(httpsBanner);
  }

  // CSS :has() fallback for Safari < 15.4 — apply .has-illustration class via JS
  if (!CSS.supports || !CSS.supports("selector(:has(*))")) {
    var _hasObserver = new MutationObserver(function() {
      document.querySelectorAll(".empty-state").forEach(function(el) {
        if (el.querySelector(".empty-state-illustration")) {
          el.classList.add("has-illustration");
        }
      });
    });
    _hasObserver.observe(document.getElementById("app") || document.body, {childList: true, subtree: true});
  }

  // Check for resumable session checkpoint
  (function checkResumeBanner() {
    var cp = SessionCheckpoint.load();
    if (!cp) return;
    fetch("/api/session/checkpoint/" + cp.sessionId)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.resumable) {
          SessionCheckpoint.clear();
          return;
        }
        showResumeBanner(cp, data);
      })
      .catch(function() { SessionCheckpoint.clear(); });
  })();

  // Check onboarding status for new users
  checkOnboarding();

  // Check NPS survey eligibility (day 28-45)
  checkNPSSurvey();

  // Report a Problem modal
  initReportProblem();

  // Collapsible panel headers (click + keyboard) — register first
  document.querySelectorAll("[data-panel]").forEach(function(btn) {
    var panelId = btn.getAttribute("data-panel");
    btn.addEventListener("click", function() { togglePanel(panelId); });
    btn.addEventListener("keydown", function(e) { panelKeyHandler(e, panelId); });
  });

  // Session start buttons (debounced to prevent rage-click double-start)
  var btnStart = document.getElementById("btn-start");
  var btnMini = document.getElementById("btn-mini");
  var _sessionStarting = false;
  if (btnStart) btnStart.addEventListener("click", function() {
    if (_sessionStarting) return;
    _sessionStarting = true;
    btnStart.disabled = true;
    if (btnMini) btnMini.disabled = true;
    startSession("standard");
    setTimeout(function() { _sessionStarting = false; }, 2000);
  });
  if (btnMini) btnMini.addEventListener("click", function() {
    if (_sessionStarting) return;
    _sessionStarting = true;
    if (btnStart) btnStart.disabled = true;
    btnMini.disabled = true;
    startSession("mini");
    setTimeout(function() { _sessionStarting = false; }, 2000);
  });

  // #13 — Disable Begin until items confirmed via status check
  // Also uses status response to show role-based UI + new-user progressive disclosure
  if (btnStart) {
    btnStart.disabled = true;
    btnStart.textContent = "Checking...";
    if (btnMini) { btnMini.disabled = true; }
    fetch("/api/status").then(function(r) { return r.json(); }).then(function(data) {
      var count = data.item_count || 0;
      var totalSessions = data.total_sessions || 0;
      var sessionLength = data.session_length || 12;
      var isNewUser = totalSessions === 0;

      // Compute time estimates from session length
      var fullMins = Math.round(sessionLength * 35 / 60);
      var miniMins = Math.round(5 * 35 / 60);

      btnStart.disabled = false;
      if (btnMini) { btnMini.disabled = false; }

      if (count === 0) {
        // No content — disable both buttons
        btnStart.disabled = true;
        btnStart.textContent = "Setting up vocabulary\u2026";
        if (btnMini) { btnMini.disabled = true; }
      } else if (isNewUser) {
        // First session — prominent single CTA with time estimate
        btnStart.textContent = "Start Your First Session (~" + fullMins + " min)";
        if (btnMini) {
          btnMini.textContent = "Quick session (~" + miniMins + " min)";
        }
      } else {
        // Returning user — show time estimates
        btnStart.textContent = "Begin (~" + fullMins + " min)";
        if (btnMini) {
          btnMini.textContent = "Quick session (~" + miniMins + " min)";
        }
      }

      // Pre-fetch session preview to warm the scheduler cache and reduce
      // first-drill latency — helps reduce bounce rate by making session
      // start feel instant. Uses low-priority fetch to avoid blocking UI.
      if (count > 0) {
        try {
          fetch("/api/session-preview", {priority: "low"}).catch(function() {});
        } catch (e) {}
      }

      // Progressive disclosure: hide advanced panels for new users, group for all
      if (totalSessions < 3) {
        var advancedPanels = ["forecast-panel", "retention-panel", "diagnostics-panel"];
        advancedPanels.forEach(function(id) {
          var panel = document.getElementById(id);
          if (panel) panel.style.display = "none";
        });
      } else if (!document.getElementById("details-wrapper")) {
        // Wrap technical panels in a <details> for progressive disclosure
        var detailIds = ["forecast-panel", "retention-panel", "diagnostics-panel"];
        var firstPanel = document.getElementById(detailIds[0]);
        if (firstPanel && firstPanel.parentNode) {
          var details = document.createElement("details");
          details.id = "details-wrapper";
          details.className = "details-wrapper";
          var summary = document.createElement("summary");
          summary.className = "details-summary";
          summary.textContent = "Details";
          details.appendChild(summary);
          firstPanel.parentNode.insertBefore(details, firstPanel);
          detailIds.forEach(function(id) {
            var p = document.getElementById(id);
            if (p) details.appendChild(p);
          });
        }
      }

      // Hide exposure buttons for brand-new users (no content context yet)
      if (isNewUser) {
        var exposureRow = document.querySelector(".actions-exposure");
        if (exposureRow) exposureRow.style.display = "none";
      }

      // Show teacher nav if user is a teacher
      var userRole = data.user_role || "student";
      var isAdmin = data.is_admin || false;
      _isAdminTeacher = isAdmin;
      if (userRole === "teacher" || isAdmin) {
        var teacherNav = document.getElementById("teacher-nav");
        if (teacherNav) teacherNav.classList.remove("hidden");
      }
      // Show "Join Classroom" for students
      if (userRole === "student") {
        var joinBtn = document.getElementById("btn-join-classroom");
        var joinSep = document.getElementById("join-classroom-sep");
        if (joinBtn) joinBtn.classList.remove("hidden");
        if (joinSep) joinSep.classList.remove("hidden");
      }

      // Store session count for use by completion screen
      window._totalSessionsBefore = totalSessions;

      // Cache upgrade context for smart paywall
      if (data.upgrade_context) {
        window._upgradeContext = data.upgrade_context;
      }

      // Streak recovery banner: show when user broke their streak
      if (data.streak_broken && data.previous_streak > 0) {
        showStreakRecoveryBanner(data.previous_streak, data.streak_freezes);
      }

      // First-session modal: explain what the first session does
      if (totalSessions === 0) {
        window._showFirstSessionModal = true;
      }

      // HSK mastery bars are rendered server-side in the template (mastery-bars).
      // No JS duplicate needed.

      initSessionExplain();
    }).catch(function() {
      // On error, enable anyway — don't block the user
      btnStart.disabled = false;
      btnStart.textContent = "Begin";
      if (btnMini) { btnMini.disabled = false; }
      initSessionExplain();
    });
  }

  // Fetch streak + study calendar for dashboard
  (function loadStreakCalendar() {
    Promise.all([
      fetch("/api/status").then(function(r) { return r.json(); }).catch(function() { return {}; }),
      fetch("/api/sessions").then(function(r) { return r.json(); }).catch(function() { return {}; }),
    ]).then(function(res) {
      var status = res[0];
      var sessions = res[1];
      var el = document.getElementById("streak-calendar");
      if (!el) return;
      var streakDays = status.streak_days || 0;
      var calData = (sessions && sessions.study_streak_data) || [];
      if (streakDays === 0 && calData.length === 0) return;

      var html = '<div class="streak-header">';
      // Rhythm pattern: "X of 7 this week" instead of fragile counter
      var daysThisWeek = Math.min(streakDays, 7);
      if (streakDays > 0) {
        // 7-dot rhythm indicator
        html += '<span class="streak-rhythm">';
        for (var di = 0; di < 7; di++) {
          html += '<span class="rhythm-dot' + (di < daysThisWeek ? ' rhythm-active' : '') + '"></span>';
        }
        html += '</span>';
        html += '<span class="streak-label">' + daysThisWeek + ' of 7 this week</span>';
      } else {
        html += '<span class="streak-label">This week</span>';
      }
      html += '</div>';

      // 4-week calendar heatmap (7 cols)
      if (calData.length > 0) {
        var dayLabels = ["S", "M", "T", "W", "T", "F", "S"];
        html += '<div class="cal-heatmap">';
        html += '<div class="cal-labels">';
        for (var dl = 0; dl < 7; dl++) html += '<span>' + dayLabels[dl] + '</span>';
        html += '</div><div class="cal-grid">';
        // Pad to start on Sunday
        var firstDate = calData.length > 0 ? new Date(calData[0].date + "T12:00:00") : new Date();
        var startDow = firstDate.getDay();
        for (var pad = 0; pad < startDow; pad++) html += '<span class="cal-cell cal-empty"></span>';
        for (var ci = 0; ci < calData.length; ci++) {
          var cnt = calData[ci].sessions || 0;
          var cls = cnt === 0 ? "cal-0" : cnt === 1 ? "cal-1" : cnt >= 2 ? "cal-2" : "cal-0";
          var items = calData[ci].items_completed || 0;
          var tip = calData[ci].date + ": " + cnt + " session" + (cnt !== 1 ? "s" : "");
          if (items > 0) tip += ", " + items + " items reviewed";
          html += '<span class="cal-cell ' + cls + '" title="' + tip + '"></span>';
        }
        html += '</div></div>';
      }

      el.innerHTML = html;
      el.classList.remove("hidden");
    });
  })();

  // Next session preview (shown after first session)
  (function loadNextSessionPreview() {
    fetch("/api/status").then(function(r) { return r.json(); }).then(function(data) {
      var el = document.getElementById("next-session-preview");
      if (!el) return;
      var totalSessions = data.total_sessions || 0;
      var itemsDue = data.items_due || 0;
      var mins = data.next_session_mins || 0;
      if (totalSessions >= 1 && itemsDue > 0) {
        el.textContent = "Next session: ~" + mins + " min" + (itemsDue > 20 ? " \u00b7 review + new material" : " \u00b7 " + itemsDue + " items");
        el.classList.remove("hidden");
      }
    }).catch(function() {});
  })();

  // Fetch weekly summary — combines session progress + encounter data
  (function loadWeeklySummary() {
    Promise.all([
      fetch("/api/encounters/summary").then(function(r) { return r.json(); }).catch(function() { return {}; }),
      fetch("/api/status").then(function(r) { return r.json(); }).catch(function() { return {}; }),
    ]).then(function(results) {
      var enc = results[0];
      var status = results[1];
      var el = document.getElementById("weekly-summary");
      if (!el) return;

      var sessionsWeek = status.sessions_this_week || 0;
      var itemsWeek = status.items_reviewed_week || 0;
      var wordsLT = status.words_long_term || 0;
      var total = enc.total_lookups_7d || 0;
      var sources = enc.sources || {};
      var topWords = enc.top_words || [];

      // Show if there's any weekly activity
      if (sessionsWeek === 0 && total === 0 && topWords.length === 0) return;

      var html = '<div class="weekly-summary-label">This week</div>';

      // Session progress line
      var progressParts = [];
      if (sessionsWeek > 0) progressParts.push(sessionsWeek + " session" + (sessionsWeek !== 1 ? "s" : ""));
      if (itemsWeek > 0) progressParts.push(itemsWeek + " items reviewed");
      if (wordsLT > 0) progressParts.push(wordsLT + " words in long-term memory");
      if (status.accuracy_this_week != null) progressParts.push(Math.round(status.accuracy_this_week) + "% accuracy");
      if (progressParts.length > 0) {
        html += '<div class="weekly-summary-stats">' + progressParts.join(" \u00b7 ") + '</div>';
      }

      // Encounter data
      var encParts = [];
      if (total > 0) encParts.push(total + " words encountered");
      if (sources.reading) encParts.push(sources.reading + " from reading");
      if (sources.listening) encParts.push(sources.listening + " from listening");
      if (encParts.length > 0) {
        html += '<div class="weekly-summary-stats">' + encParts.join(" \u00b7 ") + '</div>';
      }

      if (topWords.length > 0) {
        html += '<div class="weekly-summary-words">';
        html += topWords.slice(0, 5).map(function(w) { return '<span class="weekly-word">' + w.hanzi + '<sub>' + w.count + '</sub></span>'; }).join(" ");
        html += '</div>';
      }
      el.innerHTML = html;
      el.classList.remove("hidden");
      // If weekly-summary is inside a collapsible panel, auto-expand it
      var panel = el.closest && el.closest(".panel.collapsible");
      if (panel) {
        el.classList.remove("panel-closed");
        var toggle = panel.querySelector(".panel-toggle");
        if (toggle) toggle.setAttribute("aria-expanded", "true");
        var icon = panel.querySelector(".toggle-icon .icon use");
        if (icon) icon.setAttribute("href", "#icon-minus");
      }
    });
  })();

  // Exposure view buttons — gated for free users
  var btnRead = document.getElementById("btn-read");
  var btnWatch = document.getElementById("btn-watch");
  var btnListen = document.getElementById("btn-listen");
  if (btnRead) btnRead.addEventListener("click", function() {
    if (AeluSound.instance) AeluSound.instance.navigate(); openReadingView();
  });
  if (btnWatch) btnWatch.addEventListener("click", function() {
    isFreeTier().then(function(free) {
      if (free) { showUpgradePrompt("media"); return; }
      if (AeluSound.instance) AeluSound.instance.navigate(); openMediaView();
    });
  });
  if (btnListen) btnListen.addEventListener("click", function() {
    isFreeTier().then(function(free) {
      if (free) { showUpgradePrompt("listening"); return; }
      if (AeluSound.instance) AeluSound.instance.navigate(); openListeningView();
    });
  });
  var btnGrammar = document.getElementById("btn-grammar");
  if (btnGrammar) btnGrammar.addEventListener("click", function() {
    if (AeluSound.instance) AeluSound.instance.navigate(); openGrammarView();
  });

  // Back buttons for exposure views
  var readingBack = document.getElementById("reading-back");
  var mediaBack = document.getElementById("media-back");
  var listeningBack = document.getElementById("listening-back");
  var grammarBack = document.getElementById("grammar-back");
  if (readingBack) readingBack.addEventListener("click", function() { _submitReadingProgress(); backToDashboardFrom("reading"); });
  if (mediaBack) mediaBack.addEventListener("click", function() { backToDashboardFrom("media"); });
  if (listeningBack) listeningBack.addEventListener("click", function() { backToDashboardFrom("listening"); });
  if (grammarBack) grammarBack.addEventListener("click", function() { backToDashboardFrom("grammar"); });
  var mediaQuizBack = document.getElementById("media-quiz-back");
  if (mediaQuizBack) mediaQuizBack.addEventListener("click", function() { transitionTo("media-quiz", "media"); loadMediaRecommendations(); loadMediaHistory(); });

  // Teacher dashboard buttons
  var btnMyClasses = document.getElementById("btn-my-classes");
  if (btnMyClasses) btnMyClasses.addEventListener("click", function() { openTeacherDashboard(); });
  var teacherBack = document.getElementById("teacher-back");
  if (teacherBack) teacherBack.addEventListener("click", function() { backToDashboardFrom("teacher-dashboard"); });
  var teacherCreateClass = document.getElementById("teacher-create-class");
  if (teacherCreateClass) teacherCreateClass.addEventListener("click", function() {
    var form = document.getElementById("teacher-create-form");
    if (form) { form.classList.toggle("hidden"); if (!form.classList.contains("hidden")) document.getElementById("new-class-name").focus(); }
  });
  var teacherCreateSubmit = document.getElementById("teacher-create-submit");
  if (teacherCreateSubmit) teacherCreateSubmit.addEventListener("click", createClassroom);
  var teacherCreateCancel = document.getElementById("teacher-create-cancel");
  if (teacherCreateCancel) teacherCreateCancel.addEventListener("click", function() {
    document.getElementById("teacher-create-form").classList.add("hidden");
  });
  var classDetailBack = document.getElementById("class-detail-back");
  if (classDetailBack) classDetailBack.addEventListener("click", function() {
    document.getElementById("teacher-class-detail").classList.add("hidden");
    document.getElementById("teacher-class-list").classList.remove("hidden");
    loadTeacherClasses();
  });
  document.querySelectorAll(".class-tab").forEach(function(btn) {
    btn.addEventListener("click", function() { switchClassTab(btn.getAttribute("data-tab")); });
  });
  var inviteCodeCopy = document.getElementById("invite-code-copy");
  if (inviteCodeCopy) inviteCodeCopy.addEventListener("click", function() {
    var code = document.getElementById("invite-code-display").textContent;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(code).then(function() { inviteCodeCopy.textContent = "Copied"; setTimeout(function() { inviteCodeCopy.textContent = "Copy"; }, 2000); });
    }
  });
  var inviteBulkSend = document.getElementById("invite-bulk-send");
  if (inviteBulkSend) inviteBulkSend.addEventListener("click", sendBulkInvites);
  var studentDetailClose = document.getElementById("student-detail-close");
  if (studentDetailClose) studentDetailClose.addEventListener("click", function() {
    document.getElementById("student-detail-panel").classList.add("hidden");
  });

  // Join classroom buttons (student)
  var btnJoinClassroom = document.getElementById("btn-join-classroom");
  if (btnJoinClassroom) btnJoinClassroom.addEventListener("click", showJoinClassroom);
  var joinClassSubmit = document.getElementById("join-class-submit");
  if (joinClassSubmit) joinClassSubmit.addEventListener("click", submitJoinClassroom);
  var joinClassCancel = document.getElementById("join-class-cancel");
  if (joinClassCancel) joinClassCancel.addEventListener("click", hideJoinClassroom);
  // Allow Enter key to submit join code
  var joinCodeInput = document.getElementById("join-class-code");
  if (joinCodeInput) joinCodeInput.addEventListener("keydown", function(e) {
    if (e.key === "Enter") submitJoinClassroom();
  });

  // Submit button
  var btnSubmit = document.getElementById("btn-submit");
  if (btnSubmit) btnSubmit.addEventListener("click", submitAnswer);

  // Quick-answer shortcut buttons (#8 — done uses confirmation, #29 — hint uses disclosure)
  document.querySelectorAll("[data-quick]").forEach(function(btn) {
    var val = btn.getAttribute("data-quick");
    if (val === "Q") {
      btn.addEventListener("click", function() { handleDoneShortcut(); });
    } else if (val === "?") {
      btn.addEventListener("click", function() { handleHintShortcut(); });
    } else {
      btn.addEventListener("click", function() { quickAnswer(val); });
    }
  });

  // #10 — Back to dashboard without full reload
  var btnBack = document.getElementById("btn-back");
  if (btnBack) btnBack.addEventListener("click", function() {
    transitionTo("complete", "dashboard", function() {
      // Refresh dashboard data
      loadDashboardPanels();
    });
  });

  // Sound toggle
  var soundToggle = document.getElementById("sound-toggle");
  if (soundToggle) {
    // Sync initial state
    if (!AeluSound.isEnabled()) soundToggle.classList.add("sound-off");
    soundToggle.addEventListener("click", function() {
      var on = AeluSound.toggle();
      soundToggle.classList.toggle("sound-off", !on);
      soundToggle.setAttribute("aria-label", on ? "Sound on" : "Sound off");
    });
  }

  // Hydrate sound preference from DB (single source of truth)
  AeluSound.syncFromServer();

  // Contrast toggle
  var contrastBtn = document.getElementById("btn-contrast");
  if (contrastBtn) {
    contrastBtn.addEventListener("click", function() {
      var mode = toggleContrastMode();
    });
  }

  // ── Mastery bar tooltip ──────────────────────────
  var tooltip = document.getElementById("mastery-tooltip");
  if (tooltip) {
    var stageColors = {
      durable: "var(--color-mastery-durable)",
      stable: "var(--color-mastery-stable)",
      stabilizing: "var(--color-mastery-stabilizing)",
      passed: "var(--color-secondary)",
      seen: "var(--color-divider)",
      unseen: "var(--color-surface-alt)"
    };
    var stageLabels = {
      durable: "Mastered",
      stable: "Strong",
      stabilizing: "Building",
      passed: "Introduced",
      seen: "Encountered",
      unseen: "New"
    };
    var _stageDefinitions = {
      durable: "Mastered 3+ months ago — very unlikely to forget.",
      stable: "Mastered 1-3 months ago — solid long-term memory.",
      stabilizing: "Improving — correct 3+ times in the last week.",
      passed: "Correct at least once — still being practiced.",
      seen: "Encountered but not yet answered correctly.",
      unseen: "Not yet presented in a session."
    };
    var stageKeys = ["durable", "stable", "stabilizing", "passed", "seen", "unseen"];

    function showMasteryTooltip(e) {
      var row = e.currentTarget;
      var total = parseInt(row.dataset.total) || 1;
      var hsk = row.dataset.hsk;

      var html = '<div class="tooltip-title">HSK ' + hsk + '</div>';
      stageKeys.forEach(function(key) {
        var count = parseInt(row.dataset[key]) || 0;
        if (count > 0) {
          var pct = (count / total * 100).toFixed(0);
          var def = _stageDefinitions[key] || "";
          html += '<div class="tooltip-row">'
            + '<span class="tooltip-label">'
            + '<span class="tooltip-dot" style="background:' + stageColors[key] + '"></span>'
            + stageLabels[key] + '</span>'
            + '<span class="tooltip-value">' + count + ' (' + pct + '%)</span>'
            + '</div>';
          if (def) {
            html += '<div class="tooltip-row tooltip-def" style="padding-left:14px;font-size:0.8em;opacity:0.75;margin-top:-2px">'
              + def + '</div>';
          }
        }
      });
      html += '<div class="tooltip-row" style="margin-top:4px;border-top:1px solid var(--color-divider);padding-top:4px">'
        + '<span class="tooltip-label">Total</span>'
        + '<span class="tooltip-value">' + total + '</span></div>';

      // Safe: hsk/count/pct/total are parsed numbers; stageColors/stageLabels are hardcoded
      tooltip.innerHTML = html;
      tooltip.classList.add("visible");
      positionTooltip(e);
    }

    function positionTooltip(e) {
      var x = e.clientX + 12;
      var y = e.clientY + 12;
      var rect = tooltip.getBoundingClientRect();
      // Keep within viewport — all four edges
      if (x + rect.width > window.innerWidth - 8) x = e.clientX - rect.width - 12;
      if (y + rect.height > window.innerHeight - 8) y = e.clientY - rect.height - 12;
      if (x < 8) x = 8;
      if (y < 8) y = 8;
      tooltip.style.left = x + "px";
      tooltip.style.top = y + "px";
    }

    function hideMasteryTooltip() {
      tooltip.classList.remove("visible");
    }

    document.querySelectorAll(".mastery-bar-row").forEach(function(row) {
      row.addEventListener("mouseenter", showMasteryTooltip);
      row.addEventListener("mousemove", positionTooltip);
      row.addEventListener("mouseleave", hideMasteryTooltip);
    });
  }

  // ── Stat row HSK tooltips ──────────────────────────
  if (tooltip) {
    function showStatTooltip(e) {
      var el = e.currentTarget;
      var hsk = el.dataset.hsk;
      var total = parseInt(el.dataset.total) || 0;
      var mastered = parseInt(el.dataset.mastered) || 0;
      var seen = parseInt(el.dataset.seen) || 0;
      var durable = parseInt(el.dataset.durable) || 0;
      var stable = parseInt(el.dataset.stable) || 0;
      var stabilizing = parseInt(el.dataset.stabilizing) || 0;
      var passed = parseInt(el.dataset.passed) || 0;

      var html = '<div class="tooltip-title">HSK ' + hsk + '</div>';
      if (durable > 0) {
        html += '<div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background:var(--color-mastery-durable)"></span>Mastered</span><span class="tooltip-value">' + durable + '</span></div>';
      }
      if (stable > 0) {
        html += '<div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background:var(--color-mastery-stable)"></span>Strong</span><span class="tooltip-value">' + stable + '</span></div>';
      }
      if (stabilizing > 0) {
        html += '<div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background:var(--color-mastery-stabilizing)"></span>Building</span><span class="tooltip-value">' + stabilizing + '</span></div>';
      }
      if (passed > 0) {
        html += '<div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background:var(--color-secondary)"></span>Introduced</span><span class="tooltip-value">' + passed + '</span></div>';
      }
      var unseenCount = total - seen;
      if (unseenCount > 0) {
        html += '<div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background:var(--color-surface-alt)"></span>Not yet seen</span><span class="tooltip-value">' + unseenCount + '</span></div>';
      }
      html += '<div class="tooltip-row" style="margin-top:4px;border-top:1px solid var(--color-divider);padding-top:4px"><span class="tooltip-label">' + seen + ' of ' + total + ' encountered</span></div>';

      tooltip.innerHTML = html;
      tooltip.classList.add("visible");
      positionTooltip(e);
    }

    document.querySelectorAll(".stat-hsk").forEach(function(el) {
      el.style.cursor = "help";
      el.addEventListener("mouseenter", showStatTooltip);
      el.addEventListener("mousemove", positionTooltip);
      el.addEventListener("mouseleave", hideMasteryTooltip);
    });
  }

  // ── Feature: Onboarding Checklist ──────────────────────────
  loadOnboardingChecklist();

  // ── Feature: Account Settings ──────────────────────────
  initAccountPanel();

  // ── Feature: Referral UI ──────────────────────────
  loadReferralData();

  // ── Feature: Feedback / NPS ──────────────────────────
  initFeedbackBar();

  // ── Push unregister on logout ──────────────────────────
  var logoutForm = document.querySelector(".logout-form");
  if (logoutForm) {
    logoutForm.addEventListener("submit", function(e) {
      e.preventDefault();
      // Fire-and-forget push unregister, then submit the form
      apiFetch("/api/push/unregister", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({})
      }).catch(function() {}).finally(function() {
        logoutForm.submit();
      });
    });
  }
});

/* ═══════════════════════════════════════════════════════════════════
   Account Settings Panel
   ═══════════════════════════════════════════════════════════════════ */

var _accountLoaded = false;

function initAccountPanel() {
  var panel = document.getElementById("account-panel");
  if (!panel) return;

  // Lazy-load account data on first expand
  var toggle = panel.querySelector(".panel-toggle");
  if (toggle) {
    toggle.addEventListener("click", function() {
      if (!_accountLoaded) loadAccountPanel();
    });
  }

  // If panel was restored open from localStorage, load immediately
  var body = panel.querySelector(".panel-body");
  if (body && !body.classList.contains("panel-closed")) {
    loadAccountPanel();
  }

  // Password change toggle
  var cpToggle = document.getElementById("change-password-toggle");
  var cpForm = document.getElementById("change-password-form");
  var cpCancel = document.getElementById("cp-cancel");
  if (cpToggle && cpForm) {
    cpToggle.addEventListener("click", function() {
      cpForm.classList.toggle("hidden");
      if (!cpForm.classList.contains("hidden")) {
        document.getElementById("cp-old").focus();
      }
    });
  }
  if (cpCancel && cpForm) {
    cpCancel.addEventListener("click", function() {
      cpForm.classList.add("hidden");
      clearPasswordForm();
    });
  }

  var cpSubmit = document.getElementById("cp-submit");
  if (cpSubmit) cpSubmit.addEventListener("click", changePassword);

  // Billing
  var billingBtn = document.getElementById("manage-billing-btn");
  if (billingBtn) billingBtn.addEventListener("click", openBillingPortal);

  // Toggles
  var streakToggle = document.getElementById("toggle-streak-reminders");
  if (streakToggle) streakToggle.addEventListener("change", function() {
    toggleStreakReminders(streakToggle.checked);
  });

  var marketingToggle = document.getElementById("toggle-marketing-emails");
  if (marketingToggle) marketingToggle.addEventListener("change", function() {
    toggleMarketingOptOut(!marketingToggle.checked);
  });

  // Delete account
  var deleteBtn = document.getElementById("delete-account-btn");
  if (deleteBtn) deleteBtn.addEventListener("click", deleteAccount);
}

function loadAccountPanel() {
  if (_accountLoaded) return;
  _accountLoaded = true;

  // Fetch settings, subscription, and MFA status in parallel
  Promise.all([
    apiFetch("/api/settings").then(function(r) { return r.json(); }).catch(function() { return {}; }),
    apiFetch("/api/subscription/status").then(function(r) { return r.json(); }).catch(function() { return {}; }),
    apiFetch("/api/mfa/status").then(function(r) { return r.json(); }).catch(function() { return {}; }),
  ]).then(function(results) {
    var settings = results[0];
    var sub = results[1];
    var mfa = results[2];

    // Subscription
    var tierEl = document.getElementById("account-tier");
    if (tierEl) {
      var tier = sub.tier || "free";
      var status = sub.status || "active";
      tierEl.textContent = tier.charAt(0).toUpperCase() + tier.slice(1) + (status !== "active" ? " (" + status + ")" : "");
    }

    // Billing button — show only if has Stripe
    if (sub.has_stripe) {
      var billingRow = document.getElementById("account-billing-row");
      if (billingRow) billingRow.classList.remove("hidden");
    }

    // MFA status
    renderMfaStatus(mfa.enabled);

    // Toggles
    var streakToggle = document.getElementById("toggle-streak-reminders");
    if (streakToggle) streakToggle.checked = settings.streak_reminders !== false;

    var marketingToggle = document.getElementById("toggle-marketing-emails");
    if (marketingToggle) marketingToggle.checked = !settings.marketing_opt_out;

    // Subscription cancel/pause actions
    initSubscriptionActions(sub);
    // Personalization interests
    initPersonalization();

    updatePanelHeight("account-panel");
  });
}

function renderMfaStatus(enabled) {
  var statusEl = document.getElementById("account-mfa-status");
  var setupSection = document.getElementById("mfa-setup-section");
  var disableSection = document.getElementById("mfa-disable-section");
  if (!statusEl) return;

  if (enabled) {
    statusEl.innerHTML = '<span style="color:var(--color-correct)">Enabled</span> '
      + '<button id="mfa-disable-toggle" class="btn-secondary btn-sm" type="button">Disable</button>';
    var disableToggle = document.getElementById("mfa-disable-toggle");
    if (disableToggle && disableSection) {
      disableToggle.addEventListener("click", function() {
        disableSection.classList.toggle("hidden");
        if (!disableSection.classList.contains("hidden")) {
          document.getElementById("mfa-disable-code").focus();
        }
        updatePanelHeight("account-panel");
      });
    }
    // Wire disable confirm
    var disableConfirmBtn = document.getElementById("mfa-disable-confirm-btn");
    if (disableConfirmBtn) disableConfirmBtn.addEventListener("click", disableMfa);
    var disableCancelBtn = document.getElementById("mfa-disable-cancel-btn");
    if (disableCancelBtn) disableCancelBtn.addEventListener("click", function() {
      disableSection.classList.add("hidden");
      updatePanelHeight("account-panel");
    });
  } else {
    statusEl.innerHTML = '<span style="color:var(--color-text-dim)">Not enabled</span> '
      + '<button id="mfa-enable-toggle" class="btn-secondary btn-sm" type="button">Set up</button>';
    var enableToggle = document.getElementById("mfa-enable-toggle");
    if (enableToggle && setupSection) {
      enableToggle.addEventListener("click", startMfaSetup);
    }
    // Wire setup verify & cancel
    var verifyBtn = document.getElementById("mfa-verify-btn");
    if (verifyBtn) verifyBtn.addEventListener("click", verifyMfaSetup);
    var cancelBtn = document.getElementById("mfa-cancel-btn");
    if (cancelBtn) cancelBtn.addEventListener("click", function() {
      setupSection.classList.add("hidden");
      updatePanelHeight("account-panel");
    });
  }
}

function startMfaSetup() {
  var setupSection = document.getElementById("mfa-setup-section");
  var instructions = document.getElementById("mfa-setup-instructions");
  var secretDisplay = document.getElementById("mfa-secret-display");
  var backupSection = document.getElementById("mfa-backup-codes");
  var backupList = document.getElementById("mfa-backup-list");
  var msgEl = document.getElementById("mfa-message");

  apiFetch("/api/mfa/setup", { method: "POST" })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        showSettingsMessage(msgEl, data.error, "error");
        return;
      }
      if (instructions) instructions.textContent = "Scan this QR code with your authenticator app, then enter the 6-digit code below:";
      var qrContainer = document.getElementById("mfa-qr-container");
      if (qrContainer && data.qr_code) {
        var img = document.createElement("img");
        img.src = data.qr_code;
        img.alt = "MFA QR Code — scan with authenticator app";
        img.style.cssText = "max-width:200px;border-radius:var(--radius);background:#fff;padding:8px;";
        qrContainer.innerHTML = "";
        qrContainer.appendChild(img);
      }
      if (secretDisplay) secretDisplay.textContent = data.secret || "";
      if (data.backup_codes && backupList && backupSection) {
        backupList.textContent = data.backup_codes.join("\n");
        backupSection.classList.remove("hidden");
      }
      if (setupSection) setupSection.classList.remove("hidden");
      updatePanelHeight("account-panel");
      var codeInput = document.getElementById("mfa-verify-code");
      if (codeInput) codeInput.focus();
    })
    .catch(function() {
      showSettingsMessage(msgEl, "Could not start MFA setup.", "error");
    });
}

function verifyMfaSetup() {
  var code = (document.getElementById("mfa-verify-code").value || "").trim();
  var msgEl = document.getElementById("mfa-message");
  if (!code) {
    showSettingsMessage(msgEl, "Enter the 6-digit code from your authenticator.", "error");
    return;
  }

  apiFetch("/api/mfa/verify-setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code }),
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        showSettingsMessage(msgEl, data.error, "error");
        return;
      }
      showSettingsMessage(msgEl, "MFA enabled successfully.", "success");
      document.getElementById("mfa-setup-section").classList.add("hidden");
      _accountLoaded = false;
      loadAccountPanel();
    })
    .catch(function() {
      showSettingsMessage(msgEl, "Verification failed.", "error");
    });
}

function disableMfa() {
  var code = (document.getElementById("mfa-disable-code").value || "").trim();
  var msgEl = document.getElementById("mfa-disable-message");
  if (!code) {
    showSettingsMessage(msgEl, "Enter your 6-digit code to disable MFA.", "error");
    return;
  }

  apiFetch("/api/mfa/disable", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: code }),
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        showSettingsMessage(msgEl, data.error, "error");
        return;
      }
      showSettingsMessage(msgEl, "MFA disabled.", "success");
      document.getElementById("mfa-disable-section").classList.add("hidden");
      _accountLoaded = false;
      loadAccountPanel();
    })
    .catch(function() {
      showSettingsMessage(msgEl, "Could not disable MFA.", "error");
    });
}

function changePassword() {
  var oldPw = document.getElementById("cp-old").value;
  var newPw = document.getElementById("cp-new").value;
  var confirmPw = document.getElementById("cp-confirm").value;
  var msgEl = document.getElementById("cp-message");

  if (!oldPw || !newPw) {
    showSettingsMessage(msgEl, "All fields are required.", "error");
    return;
  }
  if (newPw !== confirmPw) {
    showSettingsMessage(msgEl, "New passwords do not match.", "error");
    return;
  }

  apiFetch("/auth/api/account/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_password: oldPw, new_password: newPw }),
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        showSettingsMessage(msgEl, data.error, "error");
        return;
      }
      showSettingsMessage(msgEl, "Password updated.", "success");
      clearPasswordForm();
      setTimeout(function() {
        document.getElementById("change-password-form").classList.add("hidden");
        msgEl.classList.add("hidden");
      }, 2000);
    })
    .catch(function() {
      showSettingsMessage(msgEl, "Could not update password.", "error");
    });
}

function clearPasswordForm() {
  var ids = ["cp-old", "cp-new", "cp-confirm"];
  for (var i = 0; i < ids.length; i++) {
    var el = document.getElementById(ids[i]);
    if (el) el.value = "";
  }
  var msgEl = document.getElementById("cp-message");
  if (msgEl) msgEl.classList.add("hidden");
}

function openBillingPortal() {
  apiFetch("/api/billing-portal", { method: "POST" })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.url) {
        window.location.href = data.url;
      } else {
        alert(data.error || "Could not open billing portal.");
      }
    })
    .catch(function() {
      alert("Could not open billing portal.");
    });
}

function toggleStreakReminders(enabled) {
  apiFetch("/api/settings/streak-reminders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: enabled }),
  }).catch(function() {});
}

function toggleMarketingOptOut(optedOut) {
  apiFetch("/api/settings/marketing-opt-out", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ opted_out: optedOut }),
  }).catch(function() {});
}

function deleteAccount() {
  if (!confirm("Are you sure you want to delete your account? This action cannot be undone.")) return;
  if (!confirm("This will permanently delete all your data. Type OK to confirm.")) return;

  var msgEl = document.getElementById("delete-account-message");
  apiFetch("/api/account/delete", { method: "POST" })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.deleted) {
        window.location.href = "/auth/login";
      } else {
        showSettingsMessage(msgEl, data.error || "Deletion failed.", "error");
      }
    })
    .catch(function() {
      showSettingsMessage(msgEl, "Could not delete account.", "error");
    });
}

function showSettingsMessage(el, text, type) {
  if (!el) return;
  el.textContent = text;
  el.className = "settings-message " + type;
  el.classList.remove("hidden");
}

/* ═══════════════════════════════════════════════════════════════════
   Feature 1: In-App Referral UI
   ═══════════════════════════════════════════════════════════════════ */

function loadReferralData() {
  var linkInput = document.getElementById("referral-link-input");
  var copyBtn = document.getElementById("referral-copy-btn");
  var statsEl = document.getElementById("referral-stats");
  if (!linkInput || !copyBtn) return;

  // Fetch the referral link
  fetch("/api/referral/link")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        linkInput.value = "Unavailable";
        return;
      }
      linkInput.value = data.link || "";
    })
    .catch(function() {
      linkInput.value = "Unavailable";
    });

  // Fetch referral stats
  fetch("/api/referral/stats")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error || !statsEl) return;
      var count = data.referral_count || 0;
      if (count > 0) {
        statsEl.textContent = count + (count === 1 ? " friend" : " friends") + " signed up through your link.";
      } else {
        statsEl.textContent = "No referrals yet.";
      }
    })
    .catch(function() {});

  // Copy button
  copyBtn.addEventListener("click", function() {
    var link = linkInput.value;
    if (!link || link === "Unavailable") return;

    var statusEl = document.getElementById("referral-copy-status");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link).then(function() {
        if (statusEl) {
          statusEl.classList.remove("hidden");
          setTimeout(function() { statusEl.classList.add("hidden"); }, 2000);
        }
      }).catch(function() {
        fallbackCopyInput(linkInput, statusEl);
      });
    } else {
      fallbackCopyInput(linkInput, statusEl);
    }
  });
}

function fallbackCopyInput(inputEl, statusEl) {
  inputEl.select();
  inputEl.setSelectionRange(0, 99999);
  try {
    document.execCommand("copy");
    if (statusEl) {
      statusEl.classList.remove("hidden");
      setTimeout(function() { statusEl.classList.add("hidden"); }, 2000);
    }
  } catch (e) {
    // Fail silently
  }
}

/* ═══════════════════════════════════════════════════════════════════
   Feature 2: Onboarding Nudges
   ═══════════════════════════════════════════════════════════════════ */

var ONBOARDING_MILESTONES = [
  { key: "first_session", label: "First session", description: "Complete at least one study session." },
  { key: "first_week", label: "First week", description: "Study on 3 different days in your first 7 days." },
  { key: "first_reading", label: "First reading", description: "Use the graded reader at least once." },
  { key: "drill_variety", label: "Drill variety", description: "Try 3 or more different drill types." },
  { key: "first_streak", label: "First streak", description: "Achieve a 3-day study streak." }
];

function loadOnboardingChecklist() {
  // Check if dismissed
  try {
    if (localStorage.getItem("onboarding_dismissed") === "true") return;
  } catch (e) {}

  fetch("/api/onboarding/status")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) return;
      // If all complete, auto-dismiss permanently
      if (data.all_complete) {
        try {
          localStorage.setItem("onboarding_dismissed", "true");
        } catch (e) {}
        return;
      }
      renderOnboardingChecklist(data);
    })
    .catch(function() {});
}

function renderOnboardingChecklist(data) {
  var container = document.getElementById("onboarding-checklist");
  var itemsEl = document.getElementById("onboarding-items");
  var completeMsg = document.getElementById("onboarding-complete-msg");
  if (!container || !itemsEl) return;

  var html = "";
  var allDone = true;
  for (var i = 0; i < ONBOARDING_MILESTONES.length; i++) {
    var m = ONBOARDING_MILESTONES[i];
    var done = !!data[m.key];
    if (!done) allDone = false;
    html += '<li class="onboarding-item' + (done ? " onboarding-done" : "") + '">'
      + '<span class="onboarding-check" aria-hidden="true">' + (done ? '<svg class="icon icon-sm"><use href="#icon-check"/></svg>' : "") + '</span>'
      + '<span class="onboarding-label">' + escapeHtml(m.label) + '</span>'
      + '<span class="onboarding-desc">' + escapeHtml(m.description) + '</span>'
      + '</li>';
  }
  itemsEl.innerHTML = html; // Safe: all data vars escaped via escapeHtml(); milestones are hardcoded

  if (allDone) {
    completeMsg.classList.remove("hidden");
    // Auto-hide after showing for 5 seconds
    try { localStorage.setItem("onboarding_complete_shown", "true"); } catch (e) {}
    setTimeout(function() {
      container.classList.add("onboarding-fade-out");
      setTimeout(function() { container.classList.add("hidden"); }, 500);
    }, 5000);
  }

  container.classList.remove("hidden");

  // Dismiss button
  var dismissBtn = document.getElementById("onboarding-dismiss");
  if (dismissBtn) {
    dismissBtn.addEventListener("click", function() {
      try { localStorage.setItem("onboarding_dismissed", "true"); } catch (e) {}
      container.classList.add("onboarding-fade-out");
      setTimeout(function() { container.classList.add("hidden"); }, 500);
    });
  }
}

/* ═══════════════════════════════════════════════════════════════════
   Feature 3: Feedback / NPS Form
   ═══════════════════════════════════════════════════════════════════ */

/* ── NPS Survey (Day 30) + Sharing ────────────────────────────────── */

function checkNPSSurvey() {
  apiFetch("/api/nps/check")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.show) showNPSModal();
    })
    .catch(function() {}); // silent fail
}

function showNPSModal() {
  var existing = document.getElementById("nps-modal");
  if (existing) existing.remove();

  var overlay = document.createElement("div");
  overlay.id = "nps-modal";
  overlay.className = "nps-modal";

  var btnsHtml = '';
  for (var i = 0; i <= 10; i++) {
    btnsHtml += '<button class="nps-score-btn" data-score="' + i + '">' + i + '</button>';
  }

  overlay.innerHTML =
    '<div class="nps-modal-inner">'
    + '<div class="nps-title">How likely are you to recommend Aelu to a friend?</div>'
    + '<div class="nps-scale">'
    + '<div class="nps-scores">' + btnsHtml + '</div>'
    + '<div class="nps-labels"><span>Not likely</span><span>Very likely</span></div>'
    + '</div>'
    + '<div class="nps-followup hidden" id="nps-followup"></div>'
    + '<button class="nps-dismiss">Not now</button>'
    + '</div>';

  document.body.appendChild(overlay);

  // Score selection
  overlay.querySelectorAll(".nps-score-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var score = parseInt(btn.dataset.score, 10);
      overlay.querySelectorAll(".nps-score-btn").forEach(function(b) { b.classList.remove("nps-score-selected"); });
      btn.classList.add("nps-score-selected");
      showNPSFollowup(overlay, score);
    });
  });

  // Dismiss
  overlay.querySelector(".nps-dismiss").addEventListener("click", function() {
    apiFetch("/api/nps/prompted", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({})
    }).catch(function() {});
    overlay.remove();
  });
}

function showNPSFollowup(overlay, score) {
  var followup = document.getElementById("nps-followup");
  followup.classList.remove("hidden");

  if (score >= 9) {
    // Promoter — share overlay + interview opt-in
    followup.innerHTML =
      '<div class="nps-thanks">Thank you! Would you mind sharing?</div>'
      + '<div class="share-overlay">'
      + '<button class="share-btn share-twitter" data-channel="twitter">Share on X</button>'
      + '<button class="share-btn share-whatsapp" data-channel="whatsapp">Share on WhatsApp</button>'
      + (navigator.share ? '<button class="share-btn share-native" data-channel="native">Share\u2026</button>' : '')
      + '<button class="share-btn share-copy" data-channel="copy">Copy Link</button>'
      + '</div>'
      + '<div class="nps-interview" style="margin-top:16px;padding:12px;border-top:1px solid rgba(0,0,0,0.1);">'
      + '<p style="font-size:14px;margin-bottom:8px;">Would you be open to a 15-minute chat about your experience? We\u2019ll send you a free month.</p>'
      + '<button class="share-btn nps-interview-btn" style="background:var(--color-secondary,#6A7A5A);color:#fff;">Yes, I\u2019m interested</button>'
      + '</div>'
      + '<button class="nps-submit-btn">Done</button>';

    var shareText = "I\u2019ve been learning Mandarin with Aelu \u2014 adaptive drills, graded reading, no engagement tricks. Worth checking out.";
    var shareUrl = (window.AELU_CANONICAL_URL || location.origin) + "/?ref=nps";

    followup.querySelectorAll(".share-btn").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var ch = btn.dataset.channel;
        EventLog.queueClientEvent("nps", "share", {score: score, channel: ch});
        if (ch === "twitter") {
          window.open("https://x.com/intent/tweet?text=" + encodeURIComponent(shareText + " " + shareUrl), "_blank");
        } else if (ch === "whatsapp") {
          window.open("https://wa.me/?text=" + encodeURIComponent(shareText + " " + shareUrl), "_blank");
        } else if (ch === "native" && navigator.share) {
          navigator.share({title: "Aelu", text: shareText, url: shareUrl}).catch(function() {});
        } else if (ch === "copy") {
          navigator.clipboard.writeText(shareUrl).then(function() {
            btn.textContent = "Copied!";
          }).catch(function() {});
        }
      });
    });

    // Interview opt-in button
    var interviewBtn = followup.querySelector(".nps-interview-btn");
    if (interviewBtn) {
      interviewBtn.addEventListener("click", function() {
        apiFetch("/api/nps/interview-opt-in", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({score: score})
        }).catch(function() {});
        interviewBtn.textContent = "Thank you! We\u2019ll be in touch.";
        interviewBtn.disabled = true;
        interviewBtn.style.opacity = "0.7";
        EventLog.queueClientEvent("nps", "interview_optin", {score: score});
      });
    }
  } else if (score >= 7) {
    // Passive — what would make it a 10?
    followup.innerHTML =
      '<div class="nps-question">What would make it a 10?</div>'
      + '<textarea class="nps-comment" id="nps-comment" rows="3" maxlength="1000" placeholder="Your thoughts\u2026"></textarea>'
      + '<button class="nps-submit-btn">Submit</button>';
  } else {
    // Detractor — what can we improve?
    followup.innerHTML =
      '<div class="nps-question">What can we improve?</div>'
      + '<textarea class="nps-comment" id="nps-comment" rows="3" maxlength="1000" placeholder="We read every response."></textarea>'
      + '<button class="nps-submit-btn">Submit</button>';
  }

  followup.querySelector(".nps-submit-btn").addEventListener("click", function() {
    var comment = "";
    var commentEl = document.getElementById("nps-comment");
    if (commentEl) comment = commentEl.value.trim();
    apiFetch("/api/nps/prompted", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({score: score, comment: comment})
    }).catch(function() {});
    EventLog.queueClientEvent("nps", "submitted", {score: score});
    overlay.querySelector(".nps-modal-inner").innerHTML =
      '<div class="nps-thanks">Thank you for your feedback.</div>';
    setTimeout(function() { overlay.remove(); }, 2000);
  });
}


var _feedbackSelectedRating = null;

function initFeedbackBar() {
  // Generate 1-10 rating buttons
  var ratingsContainer = document.getElementById("feedback-ratings");
  if (!ratingsContainer) return;

  for (var i = 1; i <= 10; i++) {
    var btn = document.createElement("button");
    btn.className = "feedback-rating-btn";
    btn.textContent = i;
    btn.setAttribute("aria-label", "Rate " + i + " out of 10");
    btn.addEventListener("click", (function(val) {
      return function() { selectFeedbackRating(val); };
    })(i));
    ratingsContainer.appendChild(btn);
  }

  // Submit button
  var submitBtn = document.getElementById("feedback-submit-btn");
  if (submitBtn) {
    submitBtn.addEventListener("click", submitFeedback);
  }

  // Close button
  var closeBtn = document.getElementById("feedback-close");
  if (closeBtn) {
    closeBtn.addEventListener("click", closeFeedbackBar);
  }

  // "Give Feedback" link in footer
  var feedbackLink = document.getElementById("btn-give-feedback");
  if (feedbackLink) {
    feedbackLink.addEventListener("click", function() {
      showFeedbackBar();
    });
  }

  // Check if we should auto-show after 10th session
  checkFeedbackTrigger();
}

function checkFeedbackTrigger() {
  // Don't show if recently shown (within 30 days)
  try {
    var lastShown = localStorage.getItem("feedback_last_shown");
    if (lastShown) {
      var elapsed = Date.now() - parseInt(lastShown);
      if (elapsed < 30 * 24 * 60 * 60 * 1000) return;
    }
  } catch (e) {}

  // Check total sessions from the page data (use API)
  fetch("/api/status")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var total = data.total_sessions || 0;
      // Show every 10th session
      if (total > 0 && total % 10 === 0) {
        showFeedbackBar();
      }
    })
    .catch(function() {});
}

function showFeedbackBar() {
  var bar = document.getElementById("feedback-bar");
  if (!bar) return;
  // Reset state
  _feedbackSelectedRating = null;
  var prompt = document.getElementById("feedback-prompt");
  var commentArea = document.getElementById("feedback-comment-area");
  var thanks = document.getElementById("feedback-thanks");
  if (prompt) prompt.classList.remove("hidden");
  if (commentArea) commentArea.classList.add("hidden");
  if (thanks) thanks.classList.add("hidden");

  // Clear previous selection
  var btns = bar.querySelectorAll(".feedback-rating-btn");
  for (var i = 0; i < btns.length; i++) {
    btns[i].classList.remove("feedback-rating-selected");
  }
  var commentInput = document.getElementById("feedback-comment");
  if (commentInput) commentInput.value = "";

  bar.classList.remove("hidden");
}

function closeFeedbackBar() {
  var bar = document.getElementById("feedback-bar");
  if (bar) bar.classList.add("hidden");
}

function selectFeedbackRating(rating) {
  _feedbackSelectedRating = rating;

  // Highlight selected button
  var btns = document.querySelectorAll(".feedback-rating-btn");
  for (var i = 0; i < btns.length; i++) {
    btns[i].classList.toggle("feedback-rating-selected", parseInt(btns[i].textContent) === rating);
  }

  // Show comment area
  var commentArea = document.getElementById("feedback-comment-area");
  if (commentArea) commentArea.classList.remove("hidden");
}

function submitFeedback() {
  if (!_feedbackSelectedRating) return;

  var comment = "";
  var commentInput = document.getElementById("feedback-comment");
  if (commentInput) comment = commentInput.value.trim();

  var submitBtn = document.getElementById("feedback-submit-btn");
  if (submitBtn) submitBtn.disabled = true;

  apiFetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rating: _feedbackSelectedRating,
      comment: comment,
      type: "nps"
    })
  }).then(function(r) { return r.json(); })
    .then(function(data) {
      // Show thank you
      var prompt = document.getElementById("feedback-prompt");
      var commentArea = document.getElementById("feedback-comment-area");
      var thanks = document.getElementById("feedback-thanks");
      if (prompt) prompt.classList.add("hidden");
      if (commentArea) commentArea.classList.add("hidden");
      if (thanks) thanks.classList.remove("hidden");

      // Record timestamp to prevent re-showing
      try { localStorage.setItem("feedback_last_shown", String(Date.now())); } catch (e) {}

      // Fade out after 3 seconds
      setTimeout(function() {
        closeFeedbackBar();
      }, 3000);
    })
    .catch(function() {
      // Fail gracefully — just close
      closeFeedbackBar();
    })
    .finally(function() {
      if (submitBtn) submitBtn.disabled = false;
    });
}

/* ── Capacitor Bridge + Offline Queue Init ────────────── */

(function() {
  // Init Capacitor bridge (no-ops in browser)
  if (typeof CapacitorBridge !== 'undefined') {
    CapacitorBridge.init();
  }

  // Init offline queue auto-flush
  if (typeof OfflineQueue !== 'undefined') {
    OfflineQueue.setupAutoFlush();

    // Flush any pending items on page load (reconnect scenario)
    OfflineQueue.getQueueSize().then(function(size) {
      if (size > 0) {
        _debugLog.log('[offline] ' + size + ' queued items, attempting flush');
        OfflineQueue.flush().then(function(count) {
          if (count > 0) _debugLog.log('[offline] flushed ' + count + ' items');
        }).catch(function(e) {
          _debugLog.warn('[offline] flush on load failed:', e);
        });
      }
    }).catch(function() {});
  }

  // Offline indicator
  var _offlineIndicator = null;
  function showOfflineIndicator() {
    if (!_offlineIndicator) {
      _offlineIndicator = document.createElement('div');
      _offlineIndicator.className = 'offline-indicator';
      _offlineIndicator.textContent = 'Offline — results will sync when reconnected';
      document.body.appendChild(_offlineIndicator);
    }
    requestAnimationFrame(function() { _offlineIndicator.classList.add('visible'); });
  }
  function hideOfflineIndicator() {
    if (_offlineIndicator) _offlineIndicator.classList.remove('visible');
  }

  window.addEventListener('offline', showOfflineIndicator);
  window.addEventListener('online', hideOfflineIndicator);

  // Capacitor native network events (more reliable than browser events on native)
  if (typeof CapacitorBridge !== 'undefined' && CapacitorBridge.onNetworkChange) {
    CapacitorBridge.onNetworkChange(function(connected) {
      if (connected) { hideOfflineIndicator(); }
      else { showOfflineIndicator(); }
    });
  }

  // Check initial state — use Capacitor API if available, else navigator.onLine
  if (typeof CapacitorBridge !== 'undefined' && CapacitorBridge.isOnline) {
    CapacitorBridge.isOnline().then(function(online) {
      if (!online) showOfflineIndicator();
    });
  } else if (!navigator.onLine) {
    showOfflineIndicator();
  }

  // Push notification registration (after login / on load if already authed)
  if (typeof CapacitorBridge !== 'undefined' && CapacitorBridge.isCapacitor) {
    CapacitorBridge.registerPush().then(function(token) {
      if (token) {
        var platform = /android/i.test(navigator.userAgent) ? 'android' : 'ios';
        var headers = { 'Content-Type': 'application/json' };
        var jwt = null;
        try { jwt = sessionStorage.getItem('jwt_token'); } catch (e) {}
        if (jwt) headers['Authorization'] = 'Bearer ' + jwt;
        headers['X-Requested-With'] = 'XMLHttpRequest';
        fetch('/api/push/register', {
          method: 'POST',
          headers: headers,
          credentials: 'include',
          body: JSON.stringify({ platform: platform, token: token }),
        }).catch(function(e) {
          _debugLog.warn('[push] registration failed:', e);
        });
      }
    }).catch(function() {});
  }
})();

/* ═══════════════════════════════════════════════════════════════════
   Feature 4: Report a Problem
   ═══════════════════════════════════════════════════════════════════ */

function initReportProblem() {
  // Create modal (hidden until triggered)
  var modal = document.createElement("div");
  modal.id = "report-modal";
  modal.className = "report-modal hidden";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-label", "Report a problem");
  modal.innerHTML =
    '<div class="report-modal-backdrop"></div>' +
    '<div class="report-modal-card">' +
      '<div class="report-modal-header">' +
        '<h3>Report a Problem</h3>' +
        '<button class="report-close" aria-label="Close">&times;</button>' +
      '</div>' +
      '<p class="report-modal-desc">Describe what went wrong. Your report will be sent to Aelu so we can investigate — it includes your recent event log and app state, no personal data beyond study progress.</p>' +
      '<label for="report-description" class="report-label">What happened?</label>' +
      '<textarea id="report-description" class="report-textarea" rows="3" maxlength="1000" placeholder="e.g. Session froze after answering a tone drill..."></textarea>' +
      '<div class="report-actions">' +
        '<button id="report-send" class="btn-primary report-btn">Send Report</button>' +
        '<button id="report-download" class="btn-secondary report-btn">Download Copy</button>' +
      '</div>' +
      '<div id="report-status" class="report-status hidden" aria-live="polite"></div>' +
    '</div>';
  document.body.appendChild(modal);

  // Close handlers
  modal.querySelector(".report-modal-backdrop").addEventListener("click", closeReportModal);
  modal.querySelector(".report-close").addEventListener("click", closeReportModal);
  modal.addEventListener("keydown", function(e) {
    if (e.key === "Escape") closeReportModal();
  });

  // Send Report handler (primary action)
  document.getElementById("report-send").addEventListener("click", function() {
    var btn = this;
    btn.disabled = true;
    btn.textContent = "Sending\u2026";
    var payload = buildReportPayload();
    _sendUserReport(payload).then(function() {
      showReportStatus("Report sent. Thank you \u2014 we\u2019ll look into it.");
      btn.textContent = "Sent";
      EventLog.record("report", "sent");
      setTimeout(closeReportModal, 2000);
    }).catch(function() {
      showReportStatus("Couldn\u2019t reach the server. Your report has been downloaded instead.");
      _downloadReport(payload);
      btn.disabled = false;
      btn.textContent = "Send Report";
    });
  });

  // Download handler (secondary — local copy)
  document.getElementById("report-download").addEventListener("click", function() {
    var payload = buildReportPayload();
    _downloadReport(payload);
    showReportStatus("Report downloaded.");
    EventLog.record("report", "downloaded");
  });

  // Wire footer link
  var reportLink = document.getElementById("btn-report-problem");
  if (reportLink) {
    reportLink.addEventListener("click", function() {
      openReportModal();
    });
  }
}

function _sendUserReport(payload) {
  return apiFetch("/api/error-report", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      error_type: "user_report",
      message: (payload.description || "").substring(0, 2000),
      page_url: payload.url || location.href,
      snapshot: payload,
    }),
  });
}

function _downloadReport(payload) {
  var blob = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"});
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = "mandarin-report-" + new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19) + ".json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function buildReportPayload() {
  var snapshot = EventLog.getSnapshot();
  var desc = "";
  var textarea = document.getElementById("report-description");
  if (textarea) desc = textarea.value.trim();
  snapshot.description = desc;
  return snapshot;
}

function openReportModal() {
  var modal = document.getElementById("report-modal");
  if (!modal) return;
  // Reset
  var textarea = document.getElementById("report-description");
  if (textarea) textarea.value = "";
  var status = document.getElementById("report-status");
  if (status) status.classList.add("hidden");
  modal.classList.remove("hidden");
  if (textarea) textarea.focus();
  EventLog.record("report", "opened");
}

function closeReportModal() {
  var modal = document.getElementById("report-modal");
  if (modal) modal.classList.add("hidden");
}

function showReportStatus(text) {
  var el = document.getElementById("report-status");
  if (!el) return;
  el.textContent = text;
  el.classList.remove("hidden");
  setTimeout(function() { el.classList.add("hidden"); }, 3000);
}

function fallbackCopy(text) {
  var ta = document.createElement("textarea");
  ta.value = text;
  ta.style.cssText = "position:fixed;left:-9999px";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); showReportStatus("Copied to clipboard."); }
  catch (e) { showReportStatus("Copy failed — please download instead."); }
  document.body.removeChild(ta);
}

/* ── Teacher Dashboard ────────────────────────────────── */

var _teacherCurrentClassId = null;
var _teacherStudentSortField = "name";
var _teacherStudentSortAsc = true;
var _isAdminTeacher = false;
var _teacherStudentsData = [];

function openTeacherDashboard() {
  transitionTo("dashboard", "teacher-dashboard");
  // Compact the global header in sub-views
  document.getElementById("app").classList.add("subview-active");

  if (_isAdminTeacher) {
    // Admin mode: skip classroom list, show students directly
    var classList = document.getElementById("teacher-class-list");
    var classDetail = document.getElementById("teacher-class-detail");
    var createBtn = document.getElementById("teacher-create-class");
    var header = document.querySelector("#teacher-dashboard .teacher-header h2");
    if (classList) classList.classList.add("hidden");
    if (classDetail) classDetail.classList.remove("hidden");
    if (createBtn) createBtn.classList.add("hidden");
    if (header) header.textContent = "My Students";
    // Hide classroom-specific UI in detail view
    var backBtn = document.getElementById("class-detail-back");
    var codeDisplay = document.getElementById("class-detail-code");
    if (backBtn) backBtn.classList.add("hidden");
    if (codeDisplay) codeDisplay.classList.add("hidden");
    document.getElementById("class-detail-name").textContent = "";
    // Hide all tabs in admin mode (no need for tab bar with single tab)
    var tabBar = document.querySelector(".class-detail-tabs");
    if (tabBar) tabBar.classList.add("hidden");
    switchClassTab("students");
    loadAdminStudents();
    return;
  }

  loadTeacherClasses();
  // Reset to class list view
  var classList = document.getElementById("teacher-class-list");
  var classDetail = document.getElementById("teacher-class-detail");
  if (classList) classList.classList.remove("hidden");
  if (classDetail) classDetail.classList.add("hidden");
}

function loadAdminStudents() {
  var tableEl = document.getElementById("class-student-table");
  if (!tableEl) return;
  tableEl.innerHTML = '<div class="panel-skeleton"><div class="skeleton-line"></div></div>';

  apiFetch("/api/admin/students")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _teacherStudentsData = data.students || [];
      renderStudentTable();
    })
    .catch(function() {
      tableEl.innerHTML = '<p>Failed to load students.</p>';
    });
}

function loadTeacherClasses() {
  var listEl = document.getElementById("teacher-class-list");
  if (!listEl) return;
  listEl.innerHTML = '<div class="panel-skeleton"><div class="skeleton-line"></div></div>';

  apiFetch("/api/classroom/list")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var classes = data.classrooms || [];
      if (classes.length === 0) {
        listEl.innerHTML = '<div class="empty-state"><img src="' + themedIllustration('/static/illustrations/empty-classes.webp') + '" alt="" class="empty-state-illustration"><p>No classes yet. Create one to get started.</p></div>';
        handleImgErrors(listEl);
        return;
      }
      var html = "";
      for (var i = 0; i < classes.length; i++) {
        var c = classes[i];
        html += '<div class="class-card" data-class-id="' + c.id + '">'
          + '<div class="class-card-header">'
          + '<span class="class-card-name">' + escapeHtml(c.name) + '</span>'
          + '<span class="class-card-code">' + escapeHtml(c.invite_code) + '</span>'
          + '</div>'
          + '<div class="class-card-stats">'
          + '<span>' + (c.student_count || 0) + ' students</span>'
          + '<span>' + (c.avg_accuracy != null ? Math.round(c.avg_accuracy) + '% avg accuracy' : 'No data yet') + '</span>'
          + '</div>'
          + '</div>';
      }
      listEl.innerHTML = html;
      // Attach click handlers
      listEl.querySelectorAll(".class-card").forEach(function(card) {
        card.addEventListener("click", function() {
          var classId = card.getAttribute("data-class-id");
          openClassDetail(classId, card.querySelector(".class-card-name").textContent,
            card.querySelector(".class-card-code").textContent);
        });
      });
    })
    .catch(function() {
      listEl.innerHTML = '<div class="empty-state"><img src="' + themedIllustration('/static/illustrations/empty-classes.webp') + '" alt="" class="empty-state-illustration"><p>Failed to load classes.</p></div>';
      handleImgErrors(listEl);
    });
}

function openClassDetail(classId, className, inviteCode) {
  _teacherCurrentClassId = classId;
  var classList = document.getElementById("teacher-class-list");
  var classDetail = document.getElementById("teacher-class-detail");
  var createForm = document.getElementById("teacher-create-form");
  if (classList) classList.classList.add("hidden");
  if (createForm) createForm.classList.add("hidden");
  if (classDetail) classDetail.classList.remove("hidden");

  document.getElementById("class-detail-name").textContent = className;
  document.getElementById("class-detail-code").textContent = "Code: " + inviteCode;
  document.getElementById("invite-code-display").textContent = inviteCode;

  // Hide student detail, show students tab
  var detailPanel = document.getElementById("student-detail-panel");
  if (detailPanel) detailPanel.classList.add("hidden");

  // Activate students tab
  switchClassTab("students");
  loadClassStudents(classId);
}

function switchClassTab(tabName) {
  document.querySelectorAll(".class-tab").forEach(function(btn) {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tabName);
  });
  ["students", "analytics", "invite"].forEach(function(t) {
    var el = document.getElementById("class-tab-" + t);
    if (el) el.classList.toggle("hidden", t !== tabName);
  });
  if (tabName === "analytics" && _teacherCurrentClassId) {
    loadClassAnalytics(_teacherCurrentClassId);
  }
}

function loadClassStudents(classId) {
  var tableEl = document.getElementById("class-student-table");
  if (!tableEl) return;
  tableEl.innerHTML = '<div class="panel-skeleton"><div class="skeleton-line"></div></div>';

  apiFetch("/api/classroom/" + classId + "/students")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _teacherStudentsData = data.students || [];
      renderStudentTable();
    })
    .catch(function() {
      tableEl.innerHTML = '<p>Failed to load students.</p>';
    });
}

function _studentSummaryCards(students) {
  var totalSessions = 0, accSum = 0, accCount = 0, activeCount = 0, atRiskCount = 0;
  var now = new Date();
  for (var i = 0; i < students.length; i++) {
    var s = students[i];
    totalSessions += (s.total_sessions || 0);
    if (s.avg_accuracy != null) { accSum += s.avg_accuracy; accCount++; }
    if (s.last_session) {
      var diff = Math.floor((now - new Date(s.last_session)) / 86400000);
      if (diff <= 7) activeCount++;
    }
    if (s.churn_risk_level === "high" || s.churn_risk_level === "critical") atRiskCount++;
  }
  var avgAcc = accCount > 0 ? Math.round(accSum / accCount) : null;

  var html = '<div class="teacher-summary-cards">';
  html += '<div class="teacher-summary-card"><div class="teacher-summary-value">' + students.length + '</div><div class="teacher-summary-label">Students</div></div>';
  html += '<div class="teacher-summary-card"><div class="teacher-summary-value">' + activeCount + '</div><div class="teacher-summary-label">Active this week</div></div>';
  html += '<div class="teacher-summary-card"><div class="teacher-summary-value">' + (avgAcc != null ? avgAcc + '%' : '—') + '</div><div class="teacher-summary-label">Avg accuracy</div></div>';
  html += '<div class="teacher-summary-card"><div class="teacher-summary-value">' + totalSessions + '</div><div class="teacher-summary-label">Total sessions</div></div>';
  if (atRiskCount > 0) {
    html += '<div class="teacher-summary-card teacher-summary-alert"><div class="teacher-summary-value">' + atRiskCount + '</div><div class="teacher-summary-label">At risk</div></div>';
  }
  html += '</div>';
  return html;
}

function renderStudentTable() {
  var tableEl = document.getElementById("class-student-table");
  if (!tableEl) return;

  var students = _teacherStudentsData.slice();
  if (students.length === 0) {
    tableEl.innerHTML = '<div class="empty-state"><img src="' + themedIllustration('/static/illustrations/empty-students.webp') + '" alt="" class="empty-state-illustration"><p>No students have joined yet. Share the invite code above.</p></div>';
    handleImgErrors(tableEl);
    return;
  }

  // Sort
  students.sort(function(a, b) {
    var aVal, bVal;
    switch (_teacherStudentSortField) {
      case "name": aVal = (a.display_name || a.email || "").toLowerCase(); bVal = (b.display_name || b.email || "").toLowerCase(); break;
      case "last_active": aVal = a.last_session || ""; bVal = b.last_session || ""; break;
      case "accuracy": aVal = a.avg_accuracy || 0; bVal = b.avg_accuracy || 0; break;
      case "sessions": aVal = a.total_sessions || 0; bVal = b.total_sessions || 0; break;
      default: aVal = 0; bVal = 0;
    }
    if (aVal < bVal) return _teacherStudentSortAsc ? -1 : 1;
    if (aVal > bVal) return _teacherStudentSortAsc ? 1 : -1;
    return 0;
  });

  var arrow = function(field) {
    if (_teacherStudentSortField !== field) return "";
    return '<span class="sort-arrow"><svg class="icon icon-sm"><use href="' + (_teacherStudentSortAsc ? "#icon-chart-up" : "#icon-chart-down") + '"/></svg></span>';
  };

  // Summary cards
  var html = _studentSummaryCards(students);

  // Table
  html += '<table><thead><tr>'
    + '<th data-sort="name">Name' + arrow("name") + '</th>'
    + '<th data-sort="last_active">Last Active' + arrow("last_active") + '</th>'
    + '<th data-sort="accuracy">Accuracy' + arrow("accuracy") + '</th>'
    + '<th data-sort="sessions">Sessions' + arrow("sessions") + '</th>'
    + '<th>Status</th>'
    + '</tr></thead><tbody>';

  for (var i = 0; i < students.length; i++) {
    var s = students[i];
    var name = escapeHtml(s.display_name || s.email || "Student " + s.id);
    var lastActive = s.last_session ? formatRelativeDate(s.last_session) : "Never";
    var accuracy = s.avg_accuracy != null ? Math.round(s.avg_accuracy) + "%" : "—";
    var status = "";
    if (s.churn_risk_level === "critical" || s.churn_risk_level === "high") {
      status = '<span class="student-status student-status-risk">At risk</span>';
    } else if (s.last_session) {
      var daysSince = Math.floor((new Date() - new Date(s.last_session)) / 86400000);
      if (daysSince <= 2) status = '<span class="student-status student-status-active">Active</span>';
      else if (daysSince <= 7) status = '<span class="student-status student-status-ok">This week</span>';
      else status = '<span class="student-status student-status-idle">Idle</span>';
    } else {
      status = '<span class="student-status student-status-idle">New</span>';
    }
    html += '<tr data-student-id="' + s.id + '">'
      + '<td>' + name + '</td>'
      + '<td>' + lastActive + '</td>'
      + '<td>' + accuracy + '</td>'
      + '<td>' + (s.total_sessions || 0) + '</td>'
      + '<td>' + status + '</td>'
      + '</tr>';
  }
  html += '</tbody></table>';

  // #4: Contextual tip for small rosters
  if (students.length <= 2) {
    html += '<div class="teacher-tip">';
    html += '<p>Click a student row to see detailed progress, drill accuracy, and learning trajectory.</p>';
    html += '</div>';
  }

  tableEl.innerHTML = html;

  // Sort handlers on headers
  tableEl.querySelectorAll("th[data-sort]").forEach(function(th) {
    th.addEventListener("click", function() {
      var field = th.getAttribute("data-sort");
      if (_teacherStudentSortField === field) {
        _teacherStudentSortAsc = !_teacherStudentSortAsc;
      } else {
        _teacherStudentSortField = field;
        _teacherStudentSortAsc = true;
      }
      renderStudentTable();
    });
  });

  // Row click → student detail
  tableEl.querySelectorAll("tr[data-student-id]").forEach(function(row) {
    row.addEventListener("click", function() {
      var studentId = row.getAttribute("data-student-id");
      openStudentDetail(studentId);
    });
  });
}

function formatRelativeDate(dateStr) {
  if (!dateStr) return "—";
  var d = new Date(dateStr);
  var now = new Date();
  var diff = Math.floor((now - d) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 7) return diff + "d ago";
  if (diff < 30) return Math.floor(diff / 7) + "w ago";
  return Math.floor(diff / 30) + "mo ago";
}

function openStudentDetail(studentId) {
  var panel = document.getElementById("student-detail-panel");
  var content = document.getElementById("student-detail-content");
  if (!panel || !content) return;
  panel.classList.remove("hidden");
  content.innerHTML = '<div class="panel-skeleton"><div class="skeleton-line"></div></div>';

  var detailUrl = _isAdminTeacher
    ? "/api/admin/student/" + studentId
    : "/api/classroom/" + _teacherCurrentClassId + "/student/" + studentId;
  apiFetch(detailUrl)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var html = '<h4>Student Detail</h4>';

      // Summary stats row
      html += '<div class="student-stat-row">'
        + '<div class="student-stat-card"><div class="stat-value">' + (data.items_mastered || 0) + '</div><div class="stat-label">Mastered</div></div>'
        + '</div>';

      // Drill accuracy breakdown (API returns [{drill_type, total, errors}])
      var drillRows = data.drill_accuracy || [];
      if (drillRows.length > 0) {
        html += '<div class="analytics-card"><h4>Accuracy by Drill Type</h4><div class="drill-accuracy-bars">';
        for (var i = 0; i < drillRows.length; i++) {
          var dr = drillRows[i];
          var drTotal = dr.total || 1;
          var drErrors = dr.errors || 0;
          var pct = Math.round((drTotal - drErrors) / drTotal * 100);
          html += '<div class="drill-accuracy-row">'
            + '<span class="label">' + escapeHtml(dr.drill_type) + '</span>'
            + '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>'
            + '<span class="value">' + pct + '%</span>'
            + '</div>';
        }
        html += '</div></div>';
      }

      // HSK progress (API returns [{hsk_level, total, mastered}])
      var hskRows = data.hsk_progress || [];
      if (hskRows.length > 0) {
        html += '<div class="analytics-card"><h4>HSK Mastery</h4>';
        for (var j = 0; j < hskRows.length; j++) {
          var hr = hskRows[j];
          var mastPct = hr.total > 0 ? Math.round(hr.mastered / hr.total * 100) : 0;
          html += '<div class="hsk-dist-bar">'
            + '<span style="width:50px">HSK ' + hr.hsk_level + '</span>'
            + '<div style="flex:1;height:8px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:4px">'
            + '<div class="bar-fill" style="width:' + mastPct + '%;height:100%;border-radius:4px"></div></div>'
            + '<span style="width:60px;text-align:right">' + hr.mastered + '/' + hr.total + '</span>'
            + '</div>';
        }
        html += '</div>';
      }

      // Session frequency (API returns [{day, count}] — group by week)
      var sessionDays = data.session_frequency || [];
      if (sessionDays.length > 0) {
        // Group into weeks
        var weekCounts = {};
        for (var k = 0; k < sessionDays.length; k++) {
          var d = new Date(sessionDays[k].day);
          var weekStart = new Date(d);
          weekStart.setDate(d.getDate() - d.getDay());
          var key = weekStart.toISOString().slice(0, 10);
          weekCounts[key] = (weekCounts[key] || 0) + sessionDays[k].count;
        }
        var weekKeys = Object.keys(weekCounts).sort();
        var weekVals = weekKeys.map(function(wk) { return weekCounts[wk]; });
        var maxF = Math.max.apply(null, weekVals) || 1;
        html += '<div class="analytics-card"><h4>Session Activity (last 30 days)</h4><div class="weekly-trend-row">';
        for (var m = 0; m < weekVals.length; m++) {
          var h = Math.round(weekVals[m] / maxF * 100);
          html += '<div class="weekly-trend-bar" style="height:' + Math.max(h, 4) + '%"></div>';
        }
        html += '</div></div>';
      }

      // Levels
      if (data.levels) {
        html += '<div class="analytics-card"><h4>Skill Levels</h4>';
        var lvlKeys = ["reading", "listening", "speaking", "ime"];
        var lvlLabels = {reading: "Reading", listening: "Listening", speaking: "Speaking", ime: "Typing"};
        for (var n = 0; n < lvlKeys.length; n++) {
          var lk = lvlKeys[n];
          var lv = data.levels[lk] || 1.0;
          var lvPct = Math.min(100, Math.round(lv / 6 * 100));
          html += '<div class="drill-accuracy-row">'
            + '<span class="label">' + lvlLabels[lk] + '</span>'
            + '<div class="bar-track"><div class="bar-fill" style="width:' + lvPct + '%"></div></div>'
            + '<span class="value">' + lv.toFixed(1) + '</span>'
            + '</div>';
        }
        html += '</div>';
      }

      content.innerHTML = html;
    })
    .catch(function() {
      content.innerHTML = '<p>Failed to load student details.</p>';
    });
}

function loadClassAnalytics(classId) {
  var el = document.getElementById("class-analytics");
  if (!el) return;
  el.innerHTML = '<div class="panel-skeleton"><div class="skeleton-line"></div></div>';

  apiFetch("/api/classroom/" + classId + "/analytics")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var html = '';

      // Summary row
      html += '<div class="analytics-row">'
        + '<div class="analytics-card"><h4>Avg Accuracy</h4><div class="analytics-value">' + (data.avg_accuracy != null ? Math.round(data.avg_accuracy) + '%' : '—') + '</div></div>'
        + '</div>';

      // HSK distribution (API: [{hsk_level, count}])
      var hskDist = data.hsk_distribution || [];
      if (hskDist.length > 0) {
        var maxCount = 1;
        for (var i = 0; i < hskDist.length; i++) {
          if (hskDist[i].count > maxCount) maxCount = hskDist[i].count;
        }
        html += '<div class="analytics-card"><h4>HSK Level Distribution</h4>';
        for (var j = 0; j < hskDist.length; j++) {
          var item = hskDist[j];
          var pct = Math.round(item.count / maxCount * 100);
          html += '<div class="hsk-dist-bar">'
            + '<span style="width:50px">HSK ' + item.hsk_level + '</span>'
            + '<div style="flex:1;height:8px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:4px">'
            + '<div class="bar-fill" style="width:' + pct + '%;height:100%;border-radius:4px"></div></div>'
            + '<span style="width:30px;text-align:right">' + item.count + '</span>'
            + '</div>';
        }
        html += '</div>';
      }

      // Weekly engagement trend (API: [{week, sessions, active_students}])
      var weeklyTrend = data.weekly_trend || [];
      if (weeklyTrend.length > 0) {
        var weekSessions = weeklyTrend.map(function(w) { return w.sessions; });
        var maxW = Math.max.apply(null, weekSessions) || 1;
        html += '<div class="analytics-card"><h4>Weekly Sessions (class total)</h4><div class="weekly-trend-row">';
        for (var k = 0; k < weekSessions.length; k++) {
          var h = Math.round(weekSessions[k] / maxW * 100);
          html += '<div class="weekly-trend-bar" style="height:' + Math.max(h, 4) + '%"></div>';
        }
        html += '</div></div>';
      }

      // Struggle areas
      if (data.struggle_areas && data.struggle_areas.length > 0) {
        var strugHtml = '<div class="analytics-card"><h4>Struggle Areas</h4>';
        strugHtml += '<div class="struggle-list">';
        data.struggle_areas.forEach(function(item) {
          strugHtml += '<div class="struggle-item">';
          strugHtml += '<span class="struggle-hanzi">' + escapeHtml(item.hanzi) + '</span>';
          strugHtml += '<span class="struggle-pinyin">' + escapeHtml(item.pinyin) + '</span>';
          strugHtml += '<span class="struggle-english">' + escapeHtml(item.english) + '</span>';
          strugHtml += '<span class="struggle-errors">' + item.error_count + ' errors</span>';
          strugHtml += '<span class="struggle-drill">' + escapeHtml(item.drill_type || '') + '</span>';
          strugHtml += '</div>';
        });
        strugHtml += '</div></div>';
        html += strugHtml;
      }

      el.innerHTML = html;
    })
    .catch(function() {
      el.innerHTML = '<p>Failed to load analytics.</p>';
    });
}

function createClassroom() {
  var nameInput = document.getElementById("new-class-name");
  var descInput = document.getElementById("new-class-desc");
  var name = (nameInput.value || "").trim();
  if (!name) { nameInput.focus(); return; }

  apiFetch("/api/classroom/create", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    body: JSON.stringify({name: name, description: (descInput.value || "").trim()})
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) { alert(data.error); return; }
      nameInput.value = "";
      descInput.value = "";
      document.getElementById("teacher-create-form").classList.add("hidden");
      loadTeacherClasses();
    })
    .catch(function() { alert("Couldn\u2019t create class. Try again."); });
}

function sendBulkInvites() {
  var emailsEl = document.getElementById("invite-emails");
  var statusEl = document.getElementById("invite-bulk-status");
  var raw = (emailsEl.value || "").trim();
  if (!raw) return;

  var emails = raw.split(/[\n,]+/).map(function(e) { return e.trim(); }).filter(Boolean);
  if (emails.length === 0) return;

  statusEl.textContent = "Sending...";
  statusEl.className = "";
  statusEl.classList.remove("hidden");

  apiFetch("/api/classroom/" + _teacherCurrentClassId + "/invite/bulk", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    body: JSON.stringify({emails: emails})
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        statusEl.textContent = data.error;
        statusEl.className = "error";
      } else {
        statusEl.textContent = "Sent " + (data.invited || 0) + " invitation(s).";
        statusEl.className = "success";
        emailsEl.value = "";
      }
      statusEl.classList.remove("hidden");
    })
    .catch(function() {
      statusEl.textContent = "Couldn\u2019t send invitations. Try again.";
      statusEl.className = "error";
      statusEl.classList.remove("hidden");
    });
}

/* ── Join Classroom (Student) ─────────────────────────── */

function showJoinClassroom() {
  var modal = document.getElementById("join-classroom-modal");
  var input = document.getElementById("join-class-code");
  var status = document.getElementById("join-class-status");
  if (modal) modal.classList.remove("hidden");
  if (input) { input.value = ""; input.focus(); }
  if (status) status.classList.add("hidden");
}

function hideJoinClassroom() {
  var modal = document.getElementById("join-classroom-modal");
  if (modal) modal.classList.add("hidden");
}

function submitJoinClassroom() {
  var input = document.getElementById("join-class-code");
  var status = document.getElementById("join-class-status");
  var code = (input.value || "").trim();
  if (!code) { input.focus(); return; }

  status.textContent = "Joining...";
  status.className = "";
  status.classList.remove("hidden");

  apiFetch("/api/classroom/join", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    body: JSON.stringify({code: code})
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        status.textContent = data.error;
        status.className = "error";
      } else {
        var msg = "Joined " + escapeHtml(data.classroom_name || "classroom");
        if (data.teacher_name) msg += " (taught by " + escapeHtml(data.teacher_name) + ")";
        status.textContent = msg + ".";
        status.className = "success";
        setTimeout(function() { hideJoinClassroom(); }, 2000);
      }
      status.classList.remove("hidden");
    })
    .catch(function() {
      status.textContent = "Couldn\u2019t join classroom. Try again.";
      status.className = "error";
      status.classList.remove("hidden");
    });
}

/* ═══════════════════════════════════════════════════════════════════
   Feature 7: Session Explainability
   ═══════════════════════════════════════════════════════════════════ */

function initSessionExplain() {
  var container = document.getElementById("session-explain");
  var btn = document.getElementById("btn-explain");
  var content = document.getElementById("session-explain-content");
  if (!btn || !content || !container) return;
  container.classList.remove("hidden");

  btn.addEventListener("click", function() {
    var expanded = btn.getAttribute("aria-expanded") === "true";
    if (expanded) {
      content.classList.add("hidden");
      btn.setAttribute("aria-expanded", "false");
      return;
    }
    content.innerHTML = '<span class="settings-hint">Loading…</span>';
    content.classList.remove("hidden");
    btn.setAttribute("aria-expanded", "true");

    fetch("/api/session/explain")
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error) {
          content.innerHTML = '<span class="settings-hint">' + escapeHtml(data.error) + '</span>';
          return;
        }
        var html = '<ul class="explain-list">';
        // Session type
        if (data.is_long_gap) {
          html += '<li>Focus: reviewing what you already know (it\u2019s been a while)</li>';
        } else {
          html += '<li>Focus: regular practice with review and new material</li>';
        }
        // Session length
        html += '<li>' + (data.final_session_length || "?") + ' items this session</li>';
        // Gap context
        if (data.gap_days != null && data.gap_days > 1) {
          html += '<li>' + data.gap_days + ' days since your last session</li>';
        }
        // New items
        if (data.new_item_budget > 0) {
          html += '<li>Up to ' + data.new_item_budget + ' new word' + (data.new_item_budget !== 1 ? 's' : '') + ' will be introduced</li>';
        } else if (!data.is_long_gap) {
          html += '<li>No new words today \u2014 focusing on review</li>';
        }
        // Bounce levels (struggling HSK levels)
        if (data.bounce_levels && data.bounce_levels.length > 0) {
          html += '<li>Extra practice on HSK ' + data.bounce_levels.join(', ') + ' (needs reinforcement)</li>';
        }
        html += '</ul>';
        content.innerHTML = html;
      })
      .catch(function() {
        content.innerHTML = '<span class="settings-hint">Could not load explanation.</span>';
      });
  });
}

/* ═══════════════════════════════════════════════════════════════════
   Feature 8: Mastery Criteria Modal
   ═══════════════════════════════════════════════════════════════════ */

function showMasteryCriteria(itemId) {
  // Remove existing modal
  var existing = document.getElementById("mastery-modal");
  if (existing) existing.remove();

  var overlay = document.createElement("div");
  overlay.id = "mastery-modal";
  overlay.className = "mastery-modal-overlay";
  overlay.innerHTML =
    '<div class="mastery-modal-card">' +
      '<div class="mastery-modal-header">' +
        '<span class="mastery-modal-title">Mastery Progress</span>' +
        '<button class="mastery-modal-close" aria-label="Close">&times;</button>' +
      '</div>' +
      '<div class="mastery-modal-body"><span class="settings-hint">Loading…</span></div>' +
    '</div>';
  document.getElementById("app").appendChild(overlay);

  overlay.querySelector(".mastery-modal-close").addEventListener("click", function() { overlay.remove(); });
  overlay.addEventListener("click", function(e) { if (e.target === overlay) overlay.remove(); });

  apiFetch("/api/mastery/" + itemId + "/criteria")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        overlay.querySelector(".mastery-modal-body").innerHTML =
          '<p class="settings-hint">' + escapeHtml(data.error) + '</p>';
        return;
      }
      var html = '<p class="mastery-stage">' + escapeHtml(data.summary || "") + '</p>';
      html += '<div class="mastery-gates">';
      var gateLabels = {streak: "Correct streak", attempts: "Total attempts", diversity: "Drill types", days: "Review days"};
      var gates = data.gates || {};
      for (var key in gateLabels) {
        if (!gates[key]) continue;
        var g = gates[key];
        var pct = g.needed > 0 ? Math.min(100, Math.round(g.current / g.needed * 100)) : 0;
        html += '<div class="mastery-gate">';
        html += '<div class="mastery-gate-label">' + gateLabels[key] + '</div>';
        html += '<div class="mastery-gate-bar"><div class="mastery-gate-fill' + (g.met ? ' met' : '') + '" style="width:' + pct + '%"></div></div>';
        html += '<div class="mastery-gate-values">' + g.current + ' / ' + g.needed + (g.met ? ' ✓' : '') + '</div>';
        html += '</div>';
      }
      html += '</div>';
      overlay.querySelector(".mastery-modal-body").innerHTML = html;
    })
    .catch(function() {
      overlay.querySelector(".mastery-modal-body").innerHTML =
        '<p class="settings-hint">Could not load mastery data.</p>';
    });
}

/* ═══════════════════════════════════════════════════════════════════
   Feature 9: Subscription Cancel / Pause
   ═══════════════════════════════════════════════════════════════════ */

function initSubscriptionActions(sub) {
  var actionsRow = document.getElementById("subscription-actions-row");
  if (!actionsRow) return;
  // Only show for paid users with Stripe
  if (!sub.has_stripe || sub.tier === "free") return;
  actionsRow.classList.remove("hidden");

  var pauseBtn = document.getElementById("btn-pause-sub");
  var cancelBtn = document.getElementById("btn-cancel-sub");
  var pauseSection = document.getElementById("pause-sub-section");
  var cancelSection = document.getElementById("cancel-sub-section");

  if (pauseBtn) pauseBtn.addEventListener("click", function() {
    cancelSection.classList.add("hidden");
    pauseSection.classList.toggle("hidden");
    updatePanelHeight("account-panel");
  });

  if (cancelBtn) cancelBtn.addEventListener("click", function() {
    pauseSection.classList.add("hidden");
    cancelSection.classList.toggle("hidden");
    updatePanelHeight("account-panel");
  });

  // Pause duration buttons
  document.querySelectorAll("[data-pause]").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var months = parseInt(btn.getAttribute("data-pause"));
      var msgEl = document.getElementById("pause-sub-message");
      btn.disabled = true;
      apiFetch("/api/subscription/pause", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({duration_months: months})
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          btn.disabled = false;
          if (data.error) {
            showSettingsMessage(msgEl, data.error, "error");
          } else {
            showSettingsMessage(msgEl, "Paused until " + data.resume_date + ".", "success");
            setTimeout(function() { pauseSection.classList.add("hidden"); updatePanelHeight("account-panel"); }, 3000);
          }
        })
        .catch(function() {
          btn.disabled = false;
          showSettingsMessage(msgEl, "Could not pause subscription.", "error");
        });
    });
  });

  var pauseCancelBtn = document.getElementById("pause-cancel-btn");
  if (pauseCancelBtn) pauseCancelBtn.addEventListener("click", function() {
    pauseSection.classList.add("hidden");
    updatePanelHeight("account-panel");
  });

  // Cancel confirmation
  var cancelConfirmBtn = document.getElementById("cancel-confirm-btn");
  if (cancelConfirmBtn) cancelConfirmBtn.addEventListener("click", function() {
    var reason = document.getElementById("cancel-reason").value;
    var details = (document.getElementById("cancel-details").value || "").trim();
    var msgEl = document.getElementById("cancel-sub-message");
    if (!reason) {
      showSettingsMessage(msgEl, "Please select a reason.", "error");
      return;
    }
    cancelConfirmBtn.disabled = true;
    apiFetch("/api/subscription/cancel", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({reason: reason, details: details})
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        cancelConfirmBtn.disabled = false;
        if (data.error) {
          showSettingsMessage(msgEl, data.error, "error");
        } else {
          showSettingsMessage(msgEl, "Subscription cancelled. Access continues until " + data.access_until + ".", "success");
          setTimeout(function() { cancelSection.classList.add("hidden"); updatePanelHeight("account-panel"); }, 4000);
        }
      })
      .catch(function() {
        cancelConfirmBtn.disabled = false;
        showSettingsMessage(msgEl, "Could not cancel subscription.", "error");
      });
  });

  var cancelBackBtn = document.getElementById("cancel-back-btn");
  if (cancelBackBtn) cancelBackBtn.addEventListener("click", function() {
    cancelSection.classList.add("hidden");
    updatePanelHeight("account-panel");
  });
}

/* ═══════════════════════════════════════════════════════════════════
   Feature 10: Personalization Interests
   ═══════════════════════════════════════════════════════════════════ */

function initPersonalization() {
  var toggleBtn = document.getElementById("personalization-toggle");
  var section = document.getElementById("personalization-section");
  if (!toggleBtn || !section) return;

  toggleBtn.addEventListener("click", function() {
    if (!section.classList.contains("hidden")) {
      section.classList.add("hidden");
      updatePanelHeight("account-panel");
      return;
    }
    section.classList.remove("hidden");
    updatePanelHeight("account-panel");
    loadPersonalizationDomains();
  });

  var saveBtn = document.getElementById("personalization-save");
  if (saveBtn) saveBtn.addEventListener("click", savePersonalization);

  var cancelBtn = document.getElementById("personalization-cancel");
  if (cancelBtn) cancelBtn.addEventListener("click", function() {
    section.classList.add("hidden");
    updatePanelHeight("account-panel");
  });
}

function loadPersonalizationDomains() {
  var container = document.getElementById("personalization-domains");
  if (!container) return;
  container.innerHTML = '<span class="settings-hint">Loading…</span>';

  fetch("/api/personalization")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        container.innerHTML = '<span class="settings-hint">' + escapeHtml(data.error) + '</span>';
        return;
      }
      var domains = data.domains || {};
      var html = '';
      for (var key in domains) {
        var d = domains[key];
        if (!d.available) continue;
        html += '<label class="personalization-domain-label">';
        html += '<input type="checkbox" value="' + escapeHtml(key) + '"' + (d.active ? ' checked' : '') + '> ';
        html += '<span class="personalization-domain-name">' + escapeHtml(d.label) + '</span>';
        if (d.description) html += '<span class="personalization-domain-desc"> — ' + escapeHtml(d.description) + '</span>';
        html += '</label>';
      }
      if (!html) html = '<span class="settings-hint">No interest domains available yet.</span>';
      container.innerHTML = html;
    })
    .catch(function() {
      container.innerHTML = '<span class="settings-hint">Could not load interests.</span>';
    });
}

function savePersonalization() {
  var container = document.getElementById("personalization-domains");
  var msgEl = document.getElementById("personalization-message");
  if (!container) return;

  var selected = [];
  container.querySelectorAll("input[type=checkbox]:checked").forEach(function(cb) {
    selected.push(cb.value);
  });

  apiFetch("/api/personalization", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({domains: selected.join(",")})
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        showSettingsMessage(msgEl, data.error, "error");
      } else {
        showSettingsMessage(msgEl, "Interests saved.", "success");
        setTimeout(function() {
          document.getElementById("personalization-section").classList.add("hidden");
          msgEl.classList.add("hidden");
          updatePanelHeight("account-panel");
        }, 2000);
      }
    })
    .catch(function() {
      showSettingsMessage(msgEl, "Could not save interests.", "error");
    });
}

/* ═══════════════════════════════════════════════════════════════════
   Feature 11: Placement Quiz in Onboarding
   ═══════════════════════════════════════════════════════════════════ */

function showPlacementQuiz(wizardOverlay) {
  var card = wizardOverlay.querySelector(".onboarding-wizard-card");
  if (!card) return;

  // Replace step 1 content with quiz loading state
  card.innerHTML =
    '<div class="auth-logo"><div class="logo-mark" aria-hidden="true">\u6F2B</div>' +
    '<div class="logo-text">Placement Quiz</div></div>' +
    '<div class="onboarding-wizard-intro">Answer these questions so we can find your level. Don\'t worry about getting them all right.</div>' +
    '<div id="placement-quiz-body"><span class="settings-hint">Loading questions…</span></div>';

  apiFetch("/api/onboarding/placement/start")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        document.getElementById("placement-quiz-body").innerHTML =
          '<p class="settings-hint">' + escapeHtml(data.error) + '</p>' +
          '<button class="btn-secondary" id="placement-back-btn">Choose level manually</button>';
        document.getElementById("placement-back-btn").addEventListener("click", function() {
          wizardOverlay.remove();
          showOnboardingWizard();
        });
        return;
      }
      renderPlacementQuestions(wizardOverlay, data.questions, data._answers);
    })
    .catch(function() {
      document.getElementById("placement-quiz-body").innerHTML =
        '<p class="settings-hint">Could not load placement quiz.</p>' +
        '<button class="btn-secondary" id="placement-back-btn">Choose level manually</button>';
      document.getElementById("placement-back-btn").addEventListener("click", function() {
        wizardOverlay.remove();
        showOnboardingWizard();
      });
    });
}

var _placementAnswers = [];

function renderPlacementQuestions(wizardOverlay, questions, correctAnswers) {
  _placementAnswers = [];
  var body = document.getElementById("placement-quiz-body");
  if (!body || !questions || questions.length === 0) return;

  var currentQ = 0;

  function showQuestion(idx) {
    if (idx >= questions.length) {
      submitPlacementQuiz(wizardOverlay);
      return;
    }
    var q = questions[idx];
    var html = '<div class="placement-progress">' + (idx + 1) + ' / ' + questions.length + '</div>';
    html += '<div class="placement-question">';
    html += '<div class="placement-hanzi">' + escapeHtml(q.hanzi) + '</div>';
    if (q.pinyin) html += '<div class="placement-pinyin">' + escapeHtml(q.pinyin) + '</div>';
    html += '<p>What does this mean?</p>';
    html += '<div class="onboarding-options">';
    for (var i = 0; i < q.options.length; i++) {
      html += '<button class="btn-secondary onboarding-opt" data-answer="' + escapeHtml(q.options[i]) + '">' + escapeHtml(q.options[i]) + '</button>';
    }
    html += '</div></div>';
    body.innerHTML = html;

    body.querySelectorAll("[data-answer]").forEach(function(btn) {
      btn.addEventListener("click", function() {
        _placementAnswers.push(btn.getAttribute("data-answer"));
        showQuestion(idx + 1);
      });
    });
  }

  showQuestion(0);
}

function submitPlacementQuiz(wizardOverlay) {
  var body = document.getElementById("placement-quiz-body");
  if (body) body.innerHTML = '<span class="settings-hint">Calculating your level…</span>';

  apiFetch("/api/onboarding/placement/submit", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({answers: _placementAnswers})
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        if (body) body.innerHTML = '<p class="settings-hint">' + escapeHtml(data.error) + '</p>';
        return;
      }
      var level = data.estimated_level || 1;
      if (body) {
        body.innerHTML =
          '<div class="placement-result">' +
            '<p>Your estimated level: <strong>HSK ' + level + '</strong></p>' +
            '<p class="settings-hint">' + (data.correct || 0) + ' of ' + (data.total || 0) + ' correct</p>' +
          '</div>';
      }
      // Go to goal step after a brief pause
      setTimeout(function() {
        var card = wizardOverlay.querySelector(".onboarding-wizard-card");
        if (!card) return;
        card.innerHTML =
          '<div class="auth-logo"><div class="logo-mark" aria-hidden="true">\u6F2B</div>' +
          '<div class="logo-text">Almost done</div></div>' +
          '<p>How much time per session?</p>' +
          '<div class="onboarding-options" id="placement-goals">' +
            '<button class="btn-secondary onboarding-opt" data-goal="quick">Quick \u2014 5 min<br><small>A few drills. Good for daily habit.</small></button>' +
            '<button class="btn-secondary onboarding-opt" data-goal="standard">Standard \u2014 10 min<br><small>Balanced review and new material.</small></button>' +
            '<button class="btn-secondary onboarding-opt" data-goal="deep">Deep \u2014 20 min<br><small>Thorough practice. Best for retention.</small></button>' +
          '</div>';
        card.querySelectorAll("[data-goal]").forEach(function(btn) {
          btn.addEventListener("click", function() {
            var goal = btn.getAttribute("data-goal");
            apiFetch("/api/onboarding/goal", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({goal: goal})
            }).then(function() {
              return apiFetch("/api/onboarding/complete", {method: "POST"});
            }).then(function() {
              wizardOverlay.remove();
              location.reload();
            });
          });
        });
      }, 2000);
    })
    .catch(function() {
      if (body) body.innerHTML = '<p class="settings-hint">Could not submit quiz.</p>';
    });
}

/* ── Mobile viewport — scroll input into view when keyboard appears ── */
(function() {
  function scrollActiveInput() {
    var active = document.activeElement;
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) {
      setTimeout(function() { active.scrollIntoView({block: "center", behavior: "smooth"}); }, 100);
    }
  }
  // visualViewport resize covers iOS Safari PWA
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", scrollActiveInput);
  }
  // Capacitor Keyboard plugin fires earlier and more reliably on native
  if (typeof CapacitorBridge !== 'undefined' && CapacitorBridge.isCapacitor) {
    try {
      var Keyboard = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Keyboard;
      if (Keyboard) {
        Keyboard.addListener('keyboardDidShow', scrollActiveInput);
      }
    } catch (e) { /* plugin not available */ }
  }
})();

/* ── Touch gesture handling for mobile drills ─────────── */

(function() {
  var touchStartX = 0;
  var touchStartY = 0;
  var SWIPE_THRESHOLD = 80;
  var MAX_Y_DRIFT = 60;

  document.addEventListener('touchstart', function(e) {
    touchStartX = e.changedTouches[0].screenX;
    touchStartY = e.changedTouches[0].screenY;
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    if (!sessionActive) return;
    var dx = e.changedTouches[0].screenX - touchStartX;
    var dy = Math.abs(e.changedTouches[0].screenY - touchStartY);

    // Only register horizontal swipes with minimal vertical drift
    if (dy > MAX_Y_DRIFT) return;

    if (dx < -SWIPE_THRESHOLD) {
      // Swipe left → skip
      var skipBtn = document.querySelector('.btn-shortcut[onclick*="skip"], .btn-shortcut[data-action="skip"]');
      if (skipBtn) skipBtn.click();
    } else if (dx > SWIPE_THRESHOLD) {
      // Swipe right → submit/confirm
      var submitBtn = document.getElementById('btn-submit');
      if (submitBtn && !submitBtn.disabled) submitBtn.click();
    }
  }, { passive: true });
})();

/* ── First Session Modal ──────────────────────────────────────────── */

function showFirstSessionModal(onStart) {
  var existing = document.getElementById("first-session-modal");
  if (existing) existing.remove();

  var overlay = document.createElement("div");
  overlay.id = "first-session-modal";
  overlay.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;";

  overlay.innerHTML =
    '<div style="background:var(--color-surface,#fff);max-width:400px;width:100%;padding:32px 28px;text-align:center;font-family:var(--font-body);">'
    + '<h2 style="font-family:var(--font-heading);font-size:1.5rem;margin-bottom:16px;color:var(--color-text);">Your First Session</h2>'
    + '<p style="font-size:15px;line-height:1.6;color:var(--color-text);margin-bottom:12px;">'
    + 'Your first session uses recognition drills \u2014 matching, listening, multiple choice \u2014 to build familiarity with new words.</p>'
    + '<p style="font-size:15px;line-height:1.6;color:var(--color-text);margin-bottom:24px;">'
    + 'Production drills (typing, speaking) come later, once you\u2019ve seen the words a few times.</p>'
    + '<button id="first-session-start" style="padding:12px 32px;font-family:var(--font-body);font-size:16px;background:var(--color-accent);color:var(--color-on-accent,#fff);border:none;cursor:pointer;">Let\u2019s go</button>'
    + '</div>';

  document.body.appendChild(overlay);

  document.getElementById("first-session-start").addEventListener("click", function() {
    overlay.remove();
    if (onStart) onStart();
  });

  // Also dismiss on overlay click
  overlay.addEventListener("click", function(e) {
    if (e.target === overlay) {
      overlay.remove();
      if (onStart) onStart();
    }
  });
}

/* ── Streak Recovery Banner ───────────────────────────────────────── */

function showStreakRecoveryBanner(previousStreak, freezesAvailable) {
  var existing = document.getElementById("streak-recovery-banner");
  if (existing) existing.remove();

  var banner = document.createElement("div");
  banner.id = "streak-recovery-banner";
  banner.style.cssText = "padding:16px 20px;margin:0 0 16px;background:var(--color-surface);border-left:4px solid var(--color-secondary,#6A7A5A);font-family:var(--font-body);font-size:14px;line-height:1.5;";

  var msg = '<strong>Welcome back.</strong> Your previous streak was <strong>' + previousStreak + ' day' + (previousStreak !== 1 ? 's' : '') + '</strong>.';

  if (freezesAvailable > 0) {
    msg += ' You have ' + freezesAvailable + ' streak freeze' + (freezesAvailable > 1 ? 's' : '') + ' available.';
    msg += ' <button id="use-streak-freeze" style="margin-left:8px;padding:4px 12px;font-size:13px;background:var(--color-secondary,#6A7A5A);color:#fff;border:none;cursor:pointer;">Use freeze</button>';
  } else {
    msg += ' Complete 7 consecutive days to earn a streak freeze.';
  }

  msg += ' <button id="dismiss-streak-banner" style="margin-left:8px;padding:4px 8px;font-size:12px;background:none;border:1px solid var(--color-text-dim);color:var(--color-text-dim);cursor:pointer;">Dismiss</button>';

  banner.innerHTML = msg;

  var dashboard = document.getElementById("dashboard");
  if (dashboard) {
    dashboard.insertBefore(banner, dashboard.firstChild);
  }

  // Dismiss handler
  var dismissBtn = document.getElementById("dismiss-streak-banner");
  if (dismissBtn) {
    dismissBtn.addEventListener("click", function() { banner.remove(); });
  }

  // Use freeze handler
  var freezeBtn = document.getElementById("use-streak-freeze");
  if (freezeBtn) {
    freezeBtn.addEventListener("click", function() {
      apiFetch("/api/streak/use-freeze", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({})
      }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.applied) {
          banner.innerHTML = '<strong>Streak freeze applied!</strong> Your streak has been restored.';
          setTimeout(function() { banner.remove(); loadDashboard(); }, 3000);
        }
      }).catch(function() {
        freezeBtn.textContent = "Failed";
      });
    });
  }
}

/* ═══════════════════════════════════════════════════════════════════
   F0 Contour Overlay Visualization
   Draws user vs target pitch contours on a Canvas element.
   Colors: target = teal (--color-accent), user = terracotta (--color-secondary)
   ═══════════════════════════════════════════════════════════════════ */

function renderF0Contour(canvas, userF0, targetF0, options) {
  if (!canvas || !canvas.getContext) return canvas;
  var ctx = canvas.getContext("2d");
  var w = canvas.width;
  var h = canvas.height;
  var opt = options || {};

  // Color defaults: teal for target, terracotta for user
  var targetColor = opt.targetColor || getComputedStyle(document.documentElement).getPropertyValue("--color-accent").trim() || "#4A7A6F";
  var userColor = opt.userColor || getComputedStyle(document.documentElement).getPropertyValue("--color-secondary").trim() || "#B85C3A";
  var bgColor = opt.bgColor || getComputedStyle(document.documentElement).getPropertyValue("--color-surface").trim() || "#F8F5EF";
  var textColor = opt.textColor || getComputedStyle(document.documentElement).getPropertyValue("--color-text-dim").trim() || "#666";

  // Tone numbers (optional)
  var toneNumbers = opt.toneNumbers || [];
  var toneBoundaries = opt.toneBoundaries || [];

  // Clear canvas
  ctx.fillStyle = bgColor;
  ctx.fillRect(0, 0, w, h);

  // Compute F0 range across both arrays
  var allF0 = (targetF0 || []).concat(userF0 || []).filter(function(v) { return v > 0; });
  if (allF0.length === 0) {
    ctx.fillStyle = textColor;
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No F0 data available", w / 2, h / 2);
    return canvas;
  }

  var minF0 = Math.min.apply(null, allF0);
  var maxF0 = Math.max.apply(null, allF0);
  var range = maxF0 - minF0 || 1;

  // Padding
  var padTop = 28;    // room for tone numbers
  var padBottom = 16;
  var padLeft = 36;
  var padRight = 12;
  var plotW = w - padLeft - padRight;
  var plotH = h - padTop - padBottom;

  // Y axis labels
  ctx.fillStyle = textColor;
  ctx.font = "10px sans-serif";
  ctx.textAlign = "right";
  ctx.fillText(Math.round(maxF0) + " Hz", padLeft - 4, padTop + 10);
  ctx.fillText(Math.round(minF0) + " Hz", padLeft - 4, h - padBottom);

  // Helper: map F0 value to canvas y
  function f0ToY(f0) {
    if (f0 <= 0) return null;
    return padTop + plotH - ((f0 - minF0) / range) * plotH;
  }

  // Helper: draw a contour line
  function drawContour(f0Array, color, lineWidth) {
    if (!f0Array || f0Array.length === 0) return;
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth || 2.5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    var step = plotW / Math.max(f0Array.length - 1, 1);
    var started = false;
    for (var i = 0; i < f0Array.length; i++) {
      var y = f0ToY(f0Array[i]);
      var x = padLeft + i * step;
      if (y === null) {
        started = false;
        continue;
      }
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
  }

  // Draw target first (behind), then user on top
  drawContour(targetF0, targetColor, 3);
  drawContour(userF0, userColor, 2.5);

  // Draw tone boundaries (vertical dashed lines)
  if (toneBoundaries.length > 0) {
    var maxIdx = Math.max((targetF0 || []).length, (userF0 || []).length, 1);
    var stepPx = plotW / Math.max(maxIdx - 1, 1);
    ctx.strokeStyle = textColor;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    for (var bi = 0; bi < toneBoundaries.length; bi++) {
      var bx = padLeft + toneBoundaries[bi] * stepPx;
      ctx.beginPath();
      ctx.moveTo(bx, padTop);
      ctx.lineTo(bx, h - padBottom);
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  // Draw tone numbers at top
  if (toneNumbers.length > 0) {
    ctx.fillStyle = textColor;
    ctx.font = "bold 12px sans-serif";
    ctx.textAlign = "center";
    // Compute center of each tone segment
    var boundaries = [0].concat(toneBoundaries || []);
    var maxLen = Math.max((targetF0 || []).length, (userF0 || []).length, 1);
    boundaries.push(maxLen);
    var segStep = plotW / Math.max(maxLen - 1, 1);
    for (var ti = 0; ti < toneNumbers.length && ti < boundaries.length - 1; ti++) {
      var segCenter = (boundaries[ti] + boundaries[ti + 1]) / 2;
      var tx = padLeft + segCenter * segStep;
      ctx.fillText("T" + toneNumbers[ti], tx, padTop - 8);
    }
  }

  // Legend
  ctx.font = "10px sans-serif";
  ctx.textAlign = "left";
  var legendY = h - 4;
  ctx.fillStyle = targetColor;
  ctx.fillRect(padLeft, legendY - 6, 14, 3);
  ctx.fillStyle = textColor;
  ctx.fillText("Target", padLeft + 18, legendY);
  ctx.fillStyle = userColor;
  ctx.fillRect(padLeft + 68, legendY - 6, 14, 3);
  ctx.fillStyle = textColor;
  ctx.fillText("You", padLeft + 86, legendY);

  return canvas;
}

/* ═══════════════════════════════════════════════════════════════════
   PodcastPlayer — In-app audio player with subtitle synchronization
   ═══════════════════════════════════════════════════════════════════ */

var PodcastPlayer = (function() {
  'use strict';

  function PodcastPlayer(containerEl, options) {
    this.container = containerEl;
    this.options = options || {};
    this.audio = null;
    this.subtitles = options.subtitles || [];  // [{start: seconds, end: seconds, text: "...", pinyin: "..."}]
    this.passageId = options.passageId || "";
    this.playbackRate = 1.0;
    this.isPlaying = false;
    this.currentSubIndex = -1;
    this._syncInterval = null;
    this._startTime = null;
    this._totalListened = 0;
    this._wordsLookedUp = 0;

    this._buildUI();
    this._bindEvents();
  }

  PodcastPlayer.prototype._buildUI = function() {
    var html = '<div class="podcast-player">';
    html += '<div class="podcast-controls">';
    html += '  <button class="podcast-play-btn" aria-label="Play">';
    html += '    <svg class="podcast-icon-play" viewBox="0 0 24 24" width="28" height="28"><polygon points="5,3 19,12 5,21"/></svg>';
    html += '    <svg class="podcast-icon-pause hidden" viewBox="0 0 24 24" width="28" height="28"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
    html += '  </button>';
    html += '  <div class="podcast-seek-wrap">';
    html += '    <input type="range" class="podcast-seek" min="0" max="100" value="0" step="0.1">';
    html += '    <div class="podcast-time"><span class="podcast-current">0:00</span> / <span class="podcast-duration">0:00</span></div>';
    html += '  </div>';
    html += '  <div class="podcast-speed">';
    html += '    <button class="podcast-speed-btn" title="Playback speed">1.0x</button>';
    html += '  </div>';
    html += '</div>';
    html += '<div class="podcast-subtitle-display">';
    html += '  <div class="podcast-subtitle-text"></div>';
    html += '  <div class="podcast-subtitle-pinyin"></div>';
    html += '</div>';
    html += '</div>';
    this.container.innerHTML = html;
  };

  PodcastPlayer.prototype._bindEvents = function() {
    var self = this;
    var playBtn = this.container.querySelector(".podcast-play-btn");
    var seekBar = this.container.querySelector(".podcast-seek");
    var speedBtn = this.container.querySelector(".podcast-speed-btn");

    playBtn.addEventListener("click", function() {
      if (self.isPlaying) { self.pause(); } else { self.play(); }
    });

    seekBar.addEventListener("input", function() {
      if (self.audio && self.audio.duration) {
        self.audio.currentTime = (parseFloat(seekBar.value) / 100) * self.audio.duration;
        self._syncSubtitle();
      }
    });

    var speeds = [0.75, 1.0, 1.25, 1.5];
    var speedIdx = 1;
    speedBtn.addEventListener("click", function() {
      speedIdx = (speedIdx + 1) % speeds.length;
      self.playbackRate = speeds[speedIdx];
      if (self.audio) self.audio.playbackRate = self.playbackRate;
      speedBtn.textContent = self.playbackRate + "x";
    });

    // Vocabulary lookup on subtitle tap
    var subText = this.container.querySelector(".podcast-subtitle-text");
    subText.addEventListener("click", function(e) {
      var text = subText.textContent.trim();
      if (text && typeof showInlineDictionary === "function") {
        showInlineDictionary(text, e);
        self._wordsLookedUp++;
      }
    });
  };

  PodcastPlayer.prototype.loadAudio = function(url) {
    var self = this;
    this.audio = new Audio(url);
    this.audio.playbackRate = this.playbackRate;
    this.audio.preload = "metadata";

    this.audio.addEventListener("loadedmetadata", function() {
      var dur = self.container.querySelector(".podcast-duration");
      if (dur) dur.textContent = self._formatTime(self.audio.duration);
      var seekBar = self.container.querySelector(".podcast-seek");
      if (seekBar) seekBar.max = "100";
    });

    this.audio.addEventListener("ended", function() {
      self.pause();
      self._onComplete();
    });
  };

  PodcastPlayer.prototype.play = function() {
    if (!this.audio) return;
    var self = this;
    this.audio.play().then(function() {
      self.isPlaying = true;
      self._startTime = Date.now();
      self.container.querySelector(".podcast-icon-play").classList.add("hidden");
      self.container.querySelector(".podcast-icon-pause").classList.remove("hidden");
      self._startSync();
    }).catch(function(err) {
      _debugLog.warn("[podcast] play rejected:", err);
    });
  };

  PodcastPlayer.prototype.pause = function() {
    if (!this.audio) return;
    this.audio.pause();
    this.isPlaying = false;
    if (this._startTime) {
      this._totalListened += (Date.now() - this._startTime) / 1000;
      this._startTime = null;
    }
    this.container.querySelector(".podcast-icon-play").classList.remove("hidden");
    this.container.querySelector(".podcast-icon-pause").classList.add("hidden");
    this._stopSync();
  };

  PodcastPlayer.prototype.seek = function(seconds) {
    if (!this.audio) return;
    this.audio.currentTime = Math.max(0, Math.min(seconds, this.audio.duration || 0));
    this._syncSubtitle();
  };

  PodcastPlayer.prototype._startSync = function() {
    var self = this;
    this._syncInterval = setInterval(function() {
      self._updateProgress();
      self._syncSubtitle();
    }, 100);
  };

  PodcastPlayer.prototype._stopSync = function() {
    if (this._syncInterval) {
      clearInterval(this._syncInterval);
      this._syncInterval = null;
    }
  };

  PodcastPlayer.prototype._updateProgress = function() {
    if (!this.audio) return;
    var cur = this.audio.currentTime;
    var dur = this.audio.duration || 1;
    var seekBar = this.container.querySelector(".podcast-seek");
    if (seekBar) seekBar.value = (cur / dur * 100).toString();
    var curEl = this.container.querySelector(".podcast-current");
    if (curEl) curEl.textContent = this._formatTime(cur);
  };

  PodcastPlayer.prototype._syncSubtitle = function() {
    if (!this.audio || !this.subtitles.length) return;
    var t = this.audio.currentTime;
    var found = -1;
    for (var i = 0; i < this.subtitles.length; i++) {
      if (t >= this.subtitles[i].start && t < this.subtitles[i].end) {
        found = i;
        break;
      }
    }
    if (found !== this.currentSubIndex) {
      this.currentSubIndex = found;
      var textEl = this.container.querySelector(".podcast-subtitle-text");
      var pinyinEl = this.container.querySelector(".podcast-subtitle-pinyin");
      if (found >= 0) {
        textEl.textContent = this.subtitles[found].text || "";
        pinyinEl.textContent = this.subtitles[found].pinyin || "";
      } else {
        textEl.textContent = "";
        pinyinEl.textContent = "";
      }
    }
  };

  PodcastPlayer.prototype._formatTime = function(seconds) {
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
  };

  PodcastPlayer.prototype._onComplete = function() {
    // Report listening progress to server
    if (!this.passageId) return;
    var payload = {
      passage_id: this.passageId,
      duration_s: Math.round(this._totalListened),
      words_looked_up: this._wordsLookedUp,
      playback_rate: this.playbackRate,
    };
    apiFetch("/api/listening/complete", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    }).catch(function() {
      _debugLog.warn("[podcast] progress report failed");
    });
  };

  PodcastPlayer.prototype.destroy = function() {
    this._stopSync();
    if (this.audio) {
      this.audio.pause();
      this.audio = null;
    }
    this.container.innerHTML = "";
  };

  return PodcastPlayer;
})();

/* ── Mobile swipe handler for drill navigation ────────────────────────── */
/* Swipe left on a drill to submit/advance. Only activates on touch devices.
   Does not interfere with text inputs, select elements, or horizontal scrolling.
   Calls CapacitorBridge.hapticFeedback if available. */
(function() {
  if (!('ontouchstart' in window)) return;

  var drillArea = document.getElementById("drill-area");
  if (!drillArea) return;

  var startX = 0, startY = 0, startTime = 0;
  var MIN_SWIPE = 50;   // px
  var MAX_TIME = 300;    // ms
  var MAX_Y_RATIO = 0.8; // reject diagonal swipes

  drillArea.addEventListener("touchstart", function(e) {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
    if (e.target.isContentEditable) return;
    var t = e.changedTouches[0];
    startX = t.clientX;
    startY = t.clientY;
    startTime = Date.now();
  }, { passive: true });

  drillArea.addEventListener("touchmove", function(e) {
    if (startTime === 0) return;
    var t = e.changedTouches[0];
    var dx = t.clientX - startX;
    var group = drillArea.querySelector(".drill-group:not(.past)");
    if (!group) return;
    if (Math.abs(dx) > 10) {
      group.classList.remove("swipe-settle");
      group.style.transform = "translateX(" + Math.max(-40, Math.min(40, dx * 0.3)) + "px)";
    }
  }, { passive: true });

  drillArea.addEventListener("touchend", function(e) {
    if (startTime === 0) return;
    var t = e.changedTouches[0];
    var dx = t.clientX - startX;
    var dy = t.clientY - startY;
    var elapsed = Date.now() - startTime;
    startTime = 0;

    var group = drillArea.querySelector(".drill-group:not(.past)");
    if (group) {
      group.style.transform = "";
      group.classList.add("swipe-settle");
      setTimeout(function() { group.classList.remove("swipe-settle"); }, 400);
    }

    // Reject: too slow, too short, too diagonal, or upward swipe
    if (elapsed > MAX_TIME) return;
    if (Math.abs(dx) < MIN_SWIPE) return;
    if (Math.abs(dy) / Math.abs(dx) > MAX_Y_RATIO) return;

    // Swipe left = advance/submit
    if (dx < -MIN_SWIPE) {
      if (typeof CapacitorBridge !== "undefined" && CapacitorBridge.hapticFeedback) {
        CapacitorBridge.hapticFeedback("light");
      }
      // Find and click the current submit/continue button
      var submitBtn = document.querySelector("#input-area .btn-primary:not([disabled])");
      if (submitBtn) {
        submitBtn.click();
      } else {
        // If no submit button visible, try sending empty answer (continue/skip)
        var continueBtn = drillArea.querySelector(".btn-primary:not([disabled])");
        if (continueBtn) continueBtn.click();
      }
    }
  }, { passive: true });
})();

/* ══════════════════════════════════════════════════════════════════
   2026 Visual Design Modernization — JavaScript
   View transitions, animated counters, parallax, color shifts,
   panel stagger, pull-to-refresh
   ══════════════════════════════════════════════════════════════════ */

/* ── 1b. View Transitions wrapper ────────────────────────── */
/* Wraps screen transitions in the View Transitions API when supported.
   Falls back to immediate swap in older browsers. */
function viewTransition(callback) {
  if (document.startViewTransition && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.startViewTransition(callback);
  } else {
    callback();
  }
}

/* ── 1c. Animated number counters ────────────────────────── */
/* Counts up stat values from 0 on dashboard load. Spring-decelerated. */
function animateCounter(el, target, duration) {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    el.textContent = target;
    return;
  }
  duration = duration || 800;
  var isPercent = el.textContent.indexOf('%') >= 0;
  el.setAttribute('data-animate', '1');
  var startTime = null;
  function step(ts) {
    if (!startTime) startTime = ts;
    var p = Math.min((ts - startTime) / duration, 1);
    var ease = 1 - Math.pow(1 - p, 3);  // cubic deceleration
    var val = Math.round(target * ease);
    el.textContent = val + (isPercent ? '%' : '');
    if (p < 1) requestAnimationFrame(step);
    else el.textContent = target + (isPercent ? '%' : '');
  }
  requestAnimationFrame(step);
}

/* Auto-animate stat values on page load */
document.addEventListener('DOMContentLoaded', function() {
  var statValues = document.querySelectorAll('.stat-value');
  statValues.forEach(function(el, i) {
    var text = el.textContent.trim();
    var num = parseInt(text, 10);
    if (isNaN(num) || num <= 0) return;
    el.textContent = '0' + (text.indexOf('%') >= 0 ? '%' : '');
    setTimeout(function() {
      animateCounter(el, num, 800 + i * 100);
    }, 200 + i * 80);  // stagger start
  });

  /* ── Panel stagger entrance ────────────────────────── */
  var panels = document.querySelectorAll('.panel');
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    panels.forEach(function(p) { p.classList.add('panel-stagger-enter'); });
  }
});

/* ── 1e. Parallax depth on scroll ────────────────────────── */
/* Sky gradient and horizon line respond to scroll for depth perception. */
(function() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var horizon = document.querySelector('.horizon');
  var sky = document.querySelector('.sky-bg');
  if (!horizon && !sky) return;

  var ticking = false;
  window.addEventListener('scroll', function() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function() {
      var y = window.scrollY;
      if (sky) sky.style.transform = 'translateY(' + (y * 0.3) + 'px)';
      if (horizon) horizon.style.transform = 'translateY(' + (y * 0.15) + 'px)';
      ticking = false;
    });
  }, { passive: true });
})();

/* ── 1g. Contextual color temperature ────────────────────────── */
/* Sets data-session-state on <html> so CSS shifts the background color. */
function setSessionColorState(state) {
  if (state === 'active' || state === 'complete' || state === 'idle') {
    document.documentElement.setAttribute('data-session-state', state);
  } else {
    document.documentElement.removeAttribute('data-session-state');
  }
}

/* ── Move 5: Pull-to-refresh (mobile) ────────────────────────── */
(function() {
  if (!('ontouchstart' in window)) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var indicator = document.createElement('div');
  indicator.className = 'ptr-indicator';
  document.body.prepend(indicator);

  var startY = 0, pulling = false;
  var THRESHOLD = 80;

  document.addEventListener('touchstart', function(e) {
    if (window.scrollY > 5) return;
    if (typeof sessionActive !== 'undefined' && sessionActive) return;
    startY = e.touches[0].clientY;
    pulling = true;
  }, { passive: true });

  document.addEventListener('touchmove', function(e) {
    if (!pulling) return;
    var dy = e.touches[0].clientY - startY;
    if (dy < 0) { pulling = false; return; }
    var progress = Math.min(dy / THRESHOLD, 1);
    indicator.classList.add('ptr-active');
    indicator.style.setProperty('--ptr-progress', progress);
  }, { passive: true });

  document.addEventListener('touchend', function() {
    if (!pulling) return;
    pulling = false;
    var progress = parseFloat(indicator.style.getPropertyValue('--ptr-progress') || '0');
    indicator.classList.remove('ptr-active');
    if (progress >= 1) {
      indicator.classList.add('ptr-refreshing');
      if (typeof fetchDashboardData === 'function') {
        fetchDashboardData().then(function() {
          indicator.classList.remove('ptr-refreshing');
        }).catch(function() {
          indicator.classList.remove('ptr-refreshing');
        });
      } else {
        setTimeout(function() {
          indicator.classList.remove('ptr-refreshing');
          location.reload();
        }, 800);
      }
    }
  }, { passive: true });
})();

/* ── Move 2: Learner Intelligence Panel ────────────────────────── */
(function() {
  var panel = document.getElementById('intelligence-content');
  if (!panel) return;

  function fetchIntelligence() {
    apiFetch('/api/learner-intelligence').then(function(r) { return r.json(); }).then(function(data) {
      if (!data || data.error) {
        panel.innerHTML = '<p class="intelligence-note">Not enough data yet. Complete a few sessions first.</p>';
        return;
      }
      var html = '';
      if (data.optimal_zone_count != null) {
        html += '<div class="intelligence-stat"><span class="intelligence-stat-label">Items in optimal learning zone</span><span class="intelligence-stat-value">' + data.optimal_zone_count + '</span></div>';
      }
      if (data.velocity != null) {
        html += '<div class="intelligence-stat"><span class="intelligence-stat-label">Items mastered per session</span><span class="intelligence-stat-value">' + data.velocity.toFixed(1) + '</span></div>';
      }
      if (data.total_items_learning) {
        html += '<div class="intelligence-stat"><span class="intelligence-stat-label">Items being tracked</span><span class="intelligence-stat-value">' + data.total_items_learning + '</span></div>';
      }
      if (data.top_errors && data.top_errors.length > 0) {
        html += '<div class="intelligence-stat"><span class="intelligence-stat-label">Top challenge this week</span><span class="intelligence-stat-value">' + esc(data.top_errors[0].type) + ' (' + data.top_errors[0].count + ')</span></div>';
      }
      if (data.forecast) html += '<p class="intelligence-note">' + esc(data.forecast) + '</p>';
      if (data.difficulty_note) html += '<p class="intelligence-note">' + esc(data.difficulty_note) + '</p>';
      panel.innerHTML = html || '<p class="intelligence-note">Complete a few sessions to see learning insights.</p>';
    }).catch(function() {
      panel.innerHTML = '<p class="intelligence-note">Insights will appear after your first few sessions.</p>';
    });
  }

  setTimeout(fetchIntelligence, 1500);
})();

/* ── Move 4: Onboarding walkthrough ────────────────────────── */
(function() {
  var WALKTHROUGH_KEY = 'aelu_walkthrough_done';
  if (localStorage.getItem(WALKTHROUGH_KEY)) return;

  var steps = [
    { title: 'Your dashboard', text: 'This shows what you know. The numbers update after each session.' },
    { title: 'Start studying', text: 'Press Begin for a full session, or Quick for a shorter one. Drills adapt to what you need.' },
    { title: 'Read, listen, practice', text: 'Beyond drills, you can read Chinese texts, listen to audio, and study grammar.' },
    { title: 'Track your memory', text: 'The mastery bars show how securely each word lives in your long-term memory.' }
  ];

  var overlay = document.getElementById('onboarding-walkthrough');
  var titleEl = document.getElementById('walkthrough-title');
  var textEl = document.getElementById('walkthrough-text');
  var dotsEl = document.getElementById('walkthrough-dots');
  var nextBtn = document.getElementById('walkthrough-next');
  var skipBtn = document.getElementById('walkthrough-skip');
  if (!overlay || !titleEl) return;

  var currentStep = 0;

  function renderStep() {
    titleEl.textContent = steps[currentStep].title;
    textEl.textContent = steps[currentStep].text;
    nextBtn.textContent = currentStep === steps.length - 1 ? 'Got it' : 'Next';
    dotsEl.innerHTML = '';
    for (var i = 0; i < steps.length; i++) {
      var dot = document.createElement('div');
      dot.className = 'walkthrough-dot' + (i === currentStep ? ' active' : '');
      dotsEl.appendChild(dot);
    }
  }

  function dismiss() {
    overlay.classList.add('hidden');
    localStorage.setItem(WALKTHROUGH_KEY, '1');
  }

  nextBtn.addEventListener('click', function() {
    currentStep++;
    if (currentStep >= steps.length) { dismiss(); return; }
    renderStep();
  });

  skipBtn.addEventListener('click', dismiss);

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && !overlay.classList.contains('hidden')) dismiss();
  });

  setTimeout(function() {
    renderStep();
    overlay.classList.remove('hidden');
  }, 1200);
})();

/* ── Move 3: Streaming session analysis ────────────────────────── */
function showSessionAnalysis(sessionId) {
  var container = document.getElementById('session-analysis');
  var content = document.getElementById('analysis-typing');
  var closeBtn = document.getElementById('analysis-close');
  if (!container || !content) return;

  container.classList.remove('hidden');
  content.textContent = '';
  content.classList.remove('done');

  if (typeof EventSource !== 'undefined' && sessionId) {
    var es = new EventSource('/api/session/' + sessionId + '/analyze-stream');
    es.onmessage = function(e) {
      var data = JSON.parse(e.data);
      if (data.text) content.textContent += data.text;
      if (data.done) { content.classList.add('done'); es.close(); }
    };
    es.onerror = function() {
      es.close();
      if (!content.textContent) {
        content.textContent = 'Session analysis will be available after more sessions.';
      }
      content.classList.add('done');
    };
  } else {
    content.textContent = 'Session analysis will be available after more sessions.';
    content.classList.add('done');
  }

  closeBtn.addEventListener('click', function() { container.classList.add('hidden'); });
}
