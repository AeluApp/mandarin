/* Mandarin web — WebSocket client for drill sessions */

/* Debug logging — suppressed in production */
var _debugLog = (function() {
  var isDebug = !window.IS_PRODUCTION && (location.hostname === 'localhost' || location.hostname === '127.0.0.1');
  return {
    log: function() { if (isDebug) console.log.apply(console, arguments); },
    warn: function() { if (isDebug) console.warn.apply(console, arguments); },
    error: function() { console.error.apply(console, arguments); },  // always log errors
  };
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
    ["dashboard", "session", "complete", "reading", "media", "media-quiz", "listening"].forEach(function(id) {
      var el = document.getElementById(id);
      if (el && !el.classList.contains("hidden")) visibleSection = id;
    });

    return {
      install_id: installId,
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

  // Capture unhandled errors
  window.addEventListener("error", function(e) {
    record("error", "unhandled", {
      msg: (e.message || "").substring(0, 200),
      src: (e.filename || "").split("/").pop(),
      line: e.lineno,
    });
  });

  window.addEventListener("unhandledrejection", function(e) {
    record("error", "promise", {
      msg: String(e.reason || "").substring(0, 200),
    });
  });

  return {
    record: record,
    getEntries: getEntries,
    getInstallId: getInstallId,
    getSnapshot: getSnapshot,
  };
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

let ws = null;
let currentPromptId = null;
let drillCount = 0;
let drillTotal = 0;
let sessionActive = false;

/* ── Nielsen fix state ── */
var _sessionTimerInterval = null;
var _sessionStartTime = null;
var _lastSubmitTime = 0;           // #7 debounce
var _doneConfirmPending = false;   // #8 done confirmation
var _doneConfirmTimer = null;
var _hintUsedBefore = false;       // #29 hint first-use
var _preMastery = null;            // #22 session delta
var _currentMcMode = false;        // #21 MC shortcut hiding

/* ── Timing constants — mirror CSS custom property values ── */
/* These MUST match :root { --duration-fast, --duration-base } in style.css */
var DURATION_FAST = 200;     // ms — matches --duration-fast: 0.2s
var DURATION_BASE = 400;     // ms — matches --duration-base: 0.4s
var FLASH_DURATION = 1500;   // ms — how long a temporary status message stays visible
var FOCUS_DELAY = 50;        // ms — brief delay before focusing MC options (DOM needs to settle)
var OPTION_STAGGER = 0.04;   // seconds — animation-delay increment per MC option button

/* ── Reconnect state ────────────────────────── */
var _hideInputTimer = null;

let reconnectAttempts = 0;
let maxReconnectAttempts = 5;
let reconnectDelay = 1000;
let lastSessionType = null;
let resumeToken = null;

/* ── Sound synthesis ────────────────────────── */
/*
 * Design principles:
 *
 * 1. All UI frequencies stay ABOVE the vocal F0 range (75–500Hz) to avoid
 *    interfering with Mandarin tone perception. Session tones use 800–1600Hz.
 *    Feedback textures use filtered noise (no pitch center at all).
 *
 * 2. Oscillators route through a lowpass filter (BiquadFilterNode) and a
 *    short delay (early reflections) to avoid the raw-digital-sine quality
 *    and place sounds in a subtle room.
 *
 * 3. Gain hierarchy: TTS content audio > silence > UI sounds. UI sounds
 *    should be felt more than heard. Master gain: 0.06–0.10.
 *
 * 4. Timing contracts: session start fires when the session section is fully
 *    visible. Session complete fires when the complete section enters.
 *    Feedback sounds fire on message render, not on WS receive.
 */

var MandarinSound = (function() {
  var ctx = null;
  var enabled = true;
  // Persist user preference
  try {
    var saved = localStorage.getItem("soundEnabled");
    if (saved !== null) enabled = saved !== "false";
  } catch (e) {}

  function getContext() {
    if (!ctx) {
      try {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
      } catch (e) {
        enabled = false;
      }
    }
    return ctx;
  }

  // Shared signal chain: oscillators → filter → delay → master gain → destination
  // The filter warms the tone; the delay adds early reflections (subtle room).
  function createOutputChain(ac, gain, startTime, duration) {
    var masterGain = ac.createGain();

    // Lowpass filter: removes digital harshness from sine harmonics
    var filter = ac.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 2200;
    filter.Q.value = 0.7;

    // Early reflections: 22ms delay at 6% wet creates sense of a small room
    var dry = ac.createGain();
    var wet = ac.createGain();
    var delay = ac.createDelay(0.1);
    dry.gain.value = 0.94;
    wet.gain.value = 0.06;
    delay.delayTime.value = 0.022;

    filter.connect(dry);
    filter.connect(delay);
    delay.connect(wet);
    dry.connect(masterGain);
    wet.connect(masterGain);
    masterGain.connect(ac.destination);

    // Shaped envelope: 50ms exponential attack, sustained body, gentle release
    var t = startTime;
    masterGain.gain.setValueAtTime(0.001, t);
    masterGain.gain.exponentialRampToValueAtTime(gain, t + 0.05);
    masterGain.gain.exponentialRampToValueAtTime(gain * 0.5, t + duration * 0.6);
    masterGain.gain.exponentialRampToValueAtTime(0.001, t + duration);

    return { input: filter, masterGain: masterGain };
  }

  function playTone(freq, startTime, duration, gain) {
    var ac = getContext();
    if (!ac || !enabled) return;

    var chain = createOutputChain(ac, gain, startTime, duration);

    // Sine fundamental + 2nd harmonic (octave) + 3rd harmonic (octave+fifth)
    var osc1 = ac.createOscillator();
    var osc2 = ac.createOscillator();
    var osc3 = ac.createOscillator();

    osc1.type = "sine";
    osc1.frequency.value = freq;
    osc2.type = "sine";
    osc2.frequency.value = freq * 2.0;  // 2nd harmonic
    osc3.type = "sine";
    osc3.frequency.value = freq * 3.0;  // 3rd harmonic (adds warmth via fifth)

    var mix1 = ac.createGain();
    var mix2 = ac.createGain();
    var mix3 = ac.createGain();
    mix1.gain.value = 1.0;
    mix2.gain.value = 0.12;
    mix3.gain.value = 0.03;

    osc1.connect(mix1); mix1.connect(chain.input);
    osc2.connect(mix2); mix2.connect(chain.input);
    osc3.connect(mix3); mix3.connect(chain.input);

    osc1.start(startTime);
    osc2.start(startTime);
    osc3.start(startTime);
    osc1.stop(startTime + duration);
    osc2.stop(startTime + duration);
    osc3.stop(startTime + duration);
  }

  function playNoiseBurst(startTime, duration, gain, filterFreq) {
    /* Filtered noise burst — no pitch center, safe for tonal language context.
       Used for feedback textures (correct/wrong acknowledgments). */
    var ac = getContext();
    if (!ac || !enabled) return;

    // Generate white noise buffer
    var bufferSize = Math.ceil(ac.sampleRate * duration);
    var buffer = ac.createBuffer(1, bufferSize, ac.sampleRate);
    var data = buffer.getChannelData(0);
    for (var i = 0; i < bufferSize; i++) {
      data[i] = Math.random() * 2 - 1;
    }

    var source = ac.createBufferSource();
    source.buffer = buffer;

    // Bandpass filter shapes the noise texture
    var bp = ac.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = filterFreq;
    bp.Q.value = 1.2;

    var envGain = ac.createGain();

    source.connect(bp);
    bp.connect(envGain);
    envGain.connect(ac.destination);

    // Very short envelope: fast attack, immediate decay
    envGain.gain.setValueAtTime(0.001, startTime);
    envGain.gain.exponentialRampToValueAtTime(gain, startTime + 0.008);
    envGain.gain.exponentialRampToValueAtTime(0.001, startTime + duration);

    source.start(startTime);
    source.stop(startTime + duration);
  }

  // All UI frequencies above the vocal F0 range (75-500Hz used by tone_grading).
  // Mandarin tone perception operates in that band — UI sounds must not compete.
  // Session tones: 554-880Hz — above speech, below harshness, through lowpass filter.
  var A5 = 880.0, E5 = 659.26, Cs5 = 554.37;

  return {
    // Session start: A5 → E5 — a descending fifth.
    // "Arriving at a place." Plays when session section is fully visible.
    sessionStart: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      var now = ac.currentTime + 0.05;
      playTone(A5, now, 0.5, 0.08);
      playTone(E5, now + 0.3, 0.6, 0.07);
    },

    // Session complete: A5 → E5 → C#5 — descending A major triad.
    // Settles on the major third (554Hz, above F0 range) rather than
    // dropping an octave into vocal territory. Final C#5 lingers.
    sessionComplete: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      var now = ac.currentTime + 0.05;
      playTone(A5, now, 0.4, 0.07);
      playTone(E5, now + 0.25, 0.4, 0.06);
      playTone(Cs5, now + 0.5, 1.2, 0.06);
    },

    // Correct answer: brief high filtered noise — a soft "registered" click.
    // No pitch center, so it cannot interfere with tonal memory.
    correct: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      playNoiseBurst(ac.currentTime + 0.02, 0.06, 0.04, 3200);
    },

    // Wrong answer: lower, slightly longer filtered noise — neutral, not punishing.
    // The Tingting correction that follows provides the content.
    wrong: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      playNoiseBurst(ac.currentTime + 0.02, 0.09, 0.035, 800);
    },

    // Navigate: soft click for page/section transitions.
    // Single very short noise burst at 4000Hz — even softer than correct feedback.
    // High center frequency keeps it well above vocal F0 range. 30ms duration
    // makes it feel like a tactile detent rather than a sound. Gain 0.025 keeps
    // it at the threshold of awareness: you notice its absence more than its presence.
    navigate: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      playNoiseBurst(ac.currentTime + 0.02, 0.03, 0.025, 4000);
    },

    // Hint reveal: single gentle tone at E5 (659Hz), 200ms.
    // Like a quiet "here you go" — the dominant of A major, implying there is
    // more to come (the answer). E5 at 659Hz sits comfortably above the vocal
    // F0 ceiling. Gain 0.05 — slightly louder than a click, quieter than session tones.
    hintReveal: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      var now = ac.currentTime + 0.05;
      playTone(E5, now, 0.2, 0.05);
    },

    // Level up: ascending three-note figure Cs5 → E5 → A5 (reverse of sessionComplete).
    // Where sessionComplete settles downward, levelUp lifts upward — same pitches,
    // opposite emotional vector. Each note 300ms, staggered 200ms apart so they
    // overlap briefly for warmth. Gain 0.07 — celebratory but restrained.
    // All three pitches (554, 659, 880Hz) are above the 500Hz F0 ceiling.
    levelUp: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      var now = ac.currentTime + 0.05;
      playTone(Cs5, now, 0.3, 0.07);
      playTone(E5, now + 0.2, 0.3, 0.07);
      playTone(A5, now + 0.4, 0.3, 0.07);
    },

    // Milestone: streak or mastery milestone reached. Two notes: A5 → A6 (octave).
    // The octave jump (880 → 1760Hz) is the purest interval — recognition without
    // complexity. First note 250ms, second 400ms (lingers to let the moment land).
    // Both frequencies well above vocal range. Gain 0.06 — a gentle "ding-ding."
    milestone: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      var now = ac.currentTime + 0.05;
      playTone(A5, now, 0.25, 0.06);
      playTone(1760, now + 0.25, 0.4, 0.06);
    },

    // Timer tick: for timed drills. Nearly subliminal single tick — 20ms noise burst
    // at 5000Hz. The high center frequency and extreme brevity make it register as
    // a physical sensation rather than a sound. Gain 0.015 is the quietest event
    // in the system — just enough to create temporal awareness without distraction.
    timerTick: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      playNoiseBurst(ac.currentTime + 0.02, 0.02, 0.015, 5000);
    },

    // Transition in: section entering. Rising filtered noise sweep at 2000Hz, 150ms.
    // A soft whoosh that accompanies visual section entry. 2000Hz center gives it
    // an airy quality above the vocal range. Gain 0.03 — present but not announcing.
    transitionIn: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      playNoiseBurst(ac.currentTime + 0.02, 0.15, 0.03, 2000);
    },

    // Transition out: section leaving. Falling filtered noise at 1200Hz, 150ms.
    // Lower center frequency than transitionIn creates a "settling" sensation.
    // Gain 0.025 — slightly quieter than in, because departures need less emphasis
    // than arrivals. 1200Hz still well above the 500Hz vocal F0 ceiling.
    transitionOut: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      playNoiseBurst(ac.currentTime + 0.02, 0.15, 0.025, 1200);
    },

    // Streak milestone: weekly/monthly streak celebration.
    // Four-note ascending figure: Cs5 → E5 → A5 → A6 (1760Hz). Fuller version
    // of levelUp — same first three notes, plus the octave A6 as a capstone.
    // Each 200ms, staggered by 150ms for tighter overlap than levelUp, creating
    // a richer texture. Gain 0.065. All pitches 554–1760Hz, safely above vocal F0.
    streakMilestone: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      var now = ac.currentTime + 0.05;
      playTone(Cs5, now, 0.2, 0.065);
      playTone(E5, now + 0.15, 0.2, 0.065);
      playTone(A5, now + 0.3, 0.2, 0.065);
      playTone(1760, now + 0.45, 0.2, 0.065);
    },

    // Error alert: system error (not a wrong answer — that is wrong()).
    // Two quick low-ish noise bursts at 600Hz, 60ms each, 80ms apart.
    // 600Hz is above the 500Hz F0 ceiling but lower than other UI sounds,
    // giving it a distinct "something went wrong" character without entering
    // vocal territory. Gain 0.04. The double-tap rhythm distinguishes it
    // from the single-burst correct/wrong feedback sounds.
    errorAlert: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      var now = ac.currentTime + 0.02;
      playNoiseBurst(now, 0.06, 0.04, 600);
      playNoiseBurst(now + 0.08, 0.06, 0.04, 600);
    },

    // Achievement unlock: new achievement earned. Single sustained tone at A5,
    // 800ms, gain 0.06. Longer than any other single tone in the system — the
    // duration itself communicates significance. Uses playTone which routes through
    // createOutputChain's envelope (50ms attack, shaped body, gentle release).
    // At 800ms the natural envelope creates a swell-and-fade arc that feels earned.
    // A5 (880Hz) is the tonal anchor of the system, safely above vocal F0 range.
    achievementUnlock: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      var now = ac.currentTime + 0.05;
      playTone(A5, now, 0.8, 0.06);
    },

    // Reading lookup: word looked up in reading view. Extremely quiet single tone
    // at E5 (659Hz), 120ms. The gentlest possible acknowledgment — confirms the
    // system registered the tap without pulling attention from the reading flow.
    // Gain 0.03 is near the bottom of the system's range. E5 is the same pitch
    // as hintReveal but shorter and quieter — a whisper of recognition.
    readingLookup: function() {
      var ac = getContext();
      if (!ac || !enabled) return;
      if (ac.state === "suspended") ac.resume();
      var now = ac.currentTime + 0.05;
      playTone(E5, now, 0.12, 0.03);
    },

    // Toggle sound on/off
    toggle: function() {
      enabled = !enabled;
      try { localStorage.setItem("soundEnabled", enabled ? "true" : "false"); } catch (e) {}
      return enabled;
    },

    isEnabled: function() { return enabled; }
  };
})();

/* ── State visibility ────────────────────────── */

function setStatus(state, text) {
  const dot = document.getElementById("status-dot");
  const label = document.getElementById("status-text");
  dot.className = "dot-" + state;
  label.textContent = text;
}

function transitionTo(hideId, showId, callback) {
  EventLog.record("nav", "transition", {from: hideId, to: showId});
  var hideEl = document.getElementById(hideId);
  var showEl = document.getElementById(showId);
  hideEl.classList.add("section-exit");
  setTimeout(function() {
    hideEl.classList.add("hidden");
    hideEl.classList.remove("section-exit");
    showEl.classList.remove("hidden");
    showEl.classList.add("section-enter");
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
  const drillArea = document.getElementById("drill-area");
  drillArea.textContent = "";
  sessionActive = true;
  document.body.classList.add('in-session');
  EventLog.record("session", "start", {type: type});
  lastSessionType = type;
  reconnectAttempts = 0;
  resumeToken = null;
  _doneConfirmPending = false;
  _currentMcMode = false;
  try { sessionStorage.removeItem("resumeToken"); } catch (e) {}
  try { sessionStorage.removeItem("sessionType"); } catch (e) {}
  hideDisconnectBanner();
  setStatus("loading", "Preparing session");

  // #3 — Start session timer
  _sessionStartTime = Date.now();
  if (_sessionTimerInterval) clearInterval(_sessionTimerInterval);
  _sessionTimerInterval = setInterval(updateSessionTimer, 1000);
  updateSessionTimer();

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

function updateSessionTimer() {
  var timerEl = document.getElementById("session-timer");
  if (!timerEl || !_sessionStartTime) return;
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
      MandarinSound.sessionStart();
    }
  };

  ws.onmessage = function(event) {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (e) {
      _debugLog.error("[ws] invalid JSON from server:", e);
      setStatus("disconnected", "Something went wrong");
      addMessage("Something went wrong. Please reload the page.", "msg msg-wrong");
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
      setStatus("disconnected", "Disconnected");
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

  setTimeout(function() {
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
      EventLog.record("session", "complete", {drills: drillTotal});
      sessionActive = false;
      document.body.classList.remove('in-session');
      resumeToken = null;
      try { sessionStorage.removeItem("resumeToken"); } catch (e) {}
      try { sessionStorage.removeItem("sessionType"); } catch (e) {}
      // Sound fires when the complete section enters (200ms into transition),
      // not immediately on message receive. showComplete handles this.
      if (typeof CapacitorBridge !== 'undefined') CapacitorBridge.hapticFeedback('success');
      showComplete(data.summary);
      break;
    case "audio_play":
      playAudioFromServer(data.url);
      break;
    case "record_request":
      handleRecordRequest(data.duration, data.id);
      break;
    case "audio_state":
      updateAudioState(data.state);
      break;
    case "error":
      EventLog.record("ws", "server_error", {msg: (data.message || "").substring(0, 100)});
      addMessage(data.message, "msg-wrong");
      showDisconnectBanner();
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

function displayShow(data) {
  const html = data.html || escapeHtml(data.text);
  const text = data.text || "";

  // Detect hanzi display (large centered characters with Rich markup)
  if (text.match(/^\n?\[bold bright_magenta\]\s+.+\[\/bold bright_magenta\]\n?$/)) {
    const hanzi = text.replace(/\[.*?\]/g, "").trim();
    addMessage(hanzi, "msg-hanzi");
    return;
  }

  // Detect progress indicator like [3/12]
  const progressMatch = text.match(/\[(\d+)\/(\d+)\]/);
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
  const labels = ["Reading", "Recognition", "IME", "Tone", "Listening", "Listening (detail)",
                  "Tone ID", "Dictation", "Intuition", "Pinyin recall", "Pinyin reading",
                  "Hanzi recall", "Dialogue", "Register", "Pragmatic", "Slang", "Speaking",
                  "Transfer", "Measure word", "Word order", "Sentence build", "Particle",
                  "Homophone", "Translation", "Confusable", "Cloze", "Synonym",
                  "Passage", "Sentence dictation"];
  const trimmed = text.trim().replace(/\[.*?\]/g, "").trim();
  if (labels.some(l => trimmed.startsWith(l)) && trimmed.length < 50) {
    cls = "msg msg-label";
    // #1 — Update persistent drill-type label in session header
    var dtLabel = document.getElementById("drill-type-label");
    if (dtLabel) dtLabel.textContent = trimmed;
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
    MandarinSound.correct();
    if (typeof CapacitorBridge !== 'undefined') CapacitorBridge.hapticFeedback('correct');
  } else if (cls.indexOf("msg-wrong") !== -1) {
    MandarinSound.wrong();
    if (typeof CapacitorBridge !== 'undefined') CapacitorBridge.hapticFeedback('incorrect');
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
    optDiv.setAttribute("role", "group");
    optDiv.setAttribute("aria-label", "Answer options");

    for (var i = 0; i < options.length; i++) {
      var btn = document.createElement("button");
      btn.className = "btn-option";
      btn.textContent = options[i].text;
      btn.style.animationDelay = (i * OPTION_STAGGER) + "s";
      btn.addEventListener("click", (function(val) {
        return function() { quickAnswer(val); };
      })(options[i].value));
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

    // Arrow key navigation for MC options
    optDiv.addEventListener("keydown", function(e) {
      var btns = optDiv.querySelectorAll(".btn-option");
      var idx = Array.prototype.indexOf.call(btns, document.activeElement);
      if (e.key === "ArrowDown" || e.key === "ArrowRight") {
        e.preventDefault();
        var next = (idx + 1) % btns.length;
        btns[next].focus();
      } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
        e.preventDefault();
        var prev = (idx - 1 + btns.length) % btns.length;
        btns[prev].focus();
      }
    });

    inputArea.insertBefore(optDiv, inputArea.querySelector(".shortcuts"));
    inputArea.classList.remove("hidden");
    // #21 — Hide hint/unsure shortcuts during MC
    _currentMcMode = true;
    var shortcuts = inputArea.querySelector(".shortcuts");
    if (shortcuts) shortcuts.classList.add("mc-mode");
    // Focus first option for keyboard accessibility
    var firstBtn = optDiv.querySelector(".btn-option");
    if (firstBtn) setTimeout(function() { firstBtn.focus(); }, FOCUS_DELAY);
  } else if (actions) {
    // Action prompt (Press Enter to begin, etc.) — show action buttons
    _currentMcMode = false;
    var shortcuts2 = inputArea.querySelector(".shortcuts");
    if (shortcuts2) shortcuts2.classList.remove("mc-mode");
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
  } else {
    // Free-text input — show text box (pinyin, IME, etc.)
    _currentMcMode = false;
    var shortcuts3 = inputArea.querySelector(".shortcuts");
    if (shortcuts3) shortcuts3.classList.remove("mc-mode");
    promptText.textContent = prompt;
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
  /* Check if current drill group indicates audio was played (listening drill). */
  var area = document.getElementById("drill-area");
  if (!area) return false;
  var currentGroup = getCurrentDrillGroup();
  var container = currentGroup || area;
  var msgs = container.querySelectorAll(".msg");
  for (var i = msgs.length - 1; i >= 0; i--) {
    var text = msgs[i].textContent;
    if (text.indexOf("Listen:") !== -1 || text.indexOf("replaying") !== -1) return true;
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

function quickAnswer(value) {
  sendAnswer(value);
}

function sendAnswer(value) {
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

  // Show what user typed — append to current drill group to preserve grouping
  if (value && value !== "") {
    const div = document.createElement("div");
    div.className = "msg msg-user-echo";
    div.textContent = "  > " + value;
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
  setTimeout(function() { MandarinSound.sessionComplete(); }, DURATION_FAST);

  const total = summary.items_completed || 0;
  const correct = summary.items_correct || 0;
  const pct = total > 0 ? Math.round(correct / total * 100) : 0;

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
  const scoreLabel = pct >= 80 ? "above average" : pct >= 50 ? "average" : "below average";

  let html = '<h2>Session complete.</h2>';
  html += '<div class="complete-score ' + scoreClass + '">' + correct + ' of ' + total + '<span class="sr-only"> — ' + scoreLabel + '</span></div>';
  html += '<div class="complete-pct">' + pct + '% recalled';
  if (elapsedStr) html += ' &middot; ' + elapsedStr;
  html += '</div>';

  if (summary.early_exit) {
    html += '<div class="complete-message">Short session recorded.</div>';
  }

  // Performance band message — structural, calm, grounded
  if (pct >= 90) {
    html += '<div class="complete-message">Solid ground. Intervals stretch.</div>';
  } else if (pct >= 70) {
    html += '<div class="complete-message">Missed items resurface sooner.</div>';
  } else if (pct >= 50) {
    html += '<div class="complete-message">Difficult material. Spacing adjusts.</div>';
  } else if (total > 0) {
    html += '<div class="complete-message">These items return in the next session.</div>';
  }

  // #4 — Show loading skeleton while fetching details
  content.innerHTML = html + '<div class="complete-skeleton"><div class="skeleton-line"></div><div class="skeleton-line short"></div><div class="skeleton-line"></div></div>';

  // Fetch additional session data for the complete screen
  fetchCompleteDetails(content, html);
}

function fetchCompleteDetails(contentEl, baseHtml) {
  // Fetch progress and streak data for the complete screen
  Promise.all([
    fetch("/api/progress").then(r => r.json()).catch(() => ({})),
    fetch("/api/status").then(r => r.json()).catch(() => ({})),
  ]).then(function(results) {
    const progress = results[0];
    const status = results[1];
    let html = baseHtml;

    // Streak display — quiet, no celebration
    if (status.days_since_last != null && status.days_since_last <= 1) {
      html += '<div class="complete-streak">Returning.</div>';
    }

    // Mastery summary — narrative with delta (#22)
    if (progress.mastery && Object.keys(progress.mastery).length > 0) {
      html += '<div class="complete-details"><h3>Mastery</h3>';
      for (const [level, data] of Object.entries(progress.mastery).sort()) {
        const masteryPct = data.pct != null ? Math.round(data.pct) : 0;
        const totalItems = data.total || 0;
        const masteredCount = Math.round(totalItems * masteryPct / 100);
        // #22 — Show delta from pre-session mastery
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
      }
      html += '</div>';
    }

    // Retention summary — narrative
    if (progress.retention && progress.retention.retention_pct != null) {
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

    contentEl.innerHTML = html;
    contentEl.classList.add("content-enter");
    setTimeout(function() { contentEl.classList.remove("content-enter"); }, DURATION_FAST);
  });
}

function updateProgress(current, total) {
  const pct = total > 0 ? (current / total * 100) : 0;
  const bar = document.getElementById("progress-bar");
  document.getElementById("progress-fill").style.width = pct + "%";
  document.getElementById("progress-label").textContent = current + " of " + total;
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

function showRecordingOverlay(duration) {
  var overlay = document.getElementById("recording-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "recording-overlay";
    overlay.innerHTML =
      '<div class="recording-dot"></div>' +
      '<div class="recording-label">Listening</div>' +
      '<div class="recording-countdown"></div>';
    document.getElementById("drill").appendChild(overlay);
  }
  overlay.classList.remove("hidden");
  overlay.classList.add("recording-active");

  var countdownEl = overlay.querySelector(".recording-countdown");
  var remaining = duration;
  countdownEl.textContent = remaining;

  var interval = setInterval(function() {
    remaining--;
    if (remaining > 0) {
      countdownEl.textContent = remaining;
    } else {
      clearInterval(interval);
    }
  }, 1000);
  overlay._interval = interval;
  return overlay;
}

function hideRecordingOverlay() {
  var overlay = document.getElementById("recording-overlay");
  if (overlay) {
    if (overlay._interval) clearInterval(overlay._interval);
    overlay.classList.remove("recording-active");
    overlay.classList.add("hidden");
  }
}

function handleRecordRequest(duration, id) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    _debugLog.warn("[mic] getUserMedia not available, auto-skipping");
    addMessage("  Microphone not supported in this browser. Skipping speaking drill.", "msg msg-dim");
    sendAudioData(id, null);
    return;
  }

  var targetSR = 16000;
  var overlay = showRecordingOverlay(duration);
  updateAudioState("recording");

  // Start SpeechRecognition in parallel if available
  var transcript = null;
  var recognition = null;
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    try {
      recognition = new SpeechRecognition();
      recognition.lang = "zh-CN";
      recognition.continuous = false;
      recognition.maxAlternatives = 3;
      recognition.onresult = function(event) {
        if (event.results.length > 0 && event.results[0].length > 0) {
          transcript = event.results[0][0].transcript;
          _debugLog.log("[speech] transcript:", transcript);
        }
      };
      recognition.onerror = function(e) {
        _debugLog.warn("[speech] recognition error:", e.error);
      };
      recognition.start();
    } catch (e) {
      _debugLog.warn("[speech] could not start recognition:", e);
      recognition = null;
    }
  }

  navigator.mediaDevices.getUserMedia({ audio: { sampleRate: targetSR, channelCount: 1 } })
    .then(function(stream) {
      var audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: targetSR });
      var source = audioCtx.createMediaStreamSource(stream);
      var bufferSize = 4096;
      var processor = audioCtx.createScriptProcessor(bufferSize, 1, 1);
      var chunks = [];

      processor.onaudioprocess = function(e) {
        var input = e.inputBuffer.getChannelData(0);
        chunks.push(new Float32Array(input));
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

      setTimeout(function() {
        processor.disconnect();
        source.disconnect();
        stream.getTracks().forEach(function(t) { t.stop(); });
        hideRecordingOverlay();

        // Stop speech recognition
        if (recognition) {
          try { recognition.stop(); } catch (e) {}
        }

        // Merge chunks
        var totalLen = 0;
        for (var i = 0; i < chunks.length; i++) totalLen += chunks[i].length;
        var merged = new Float32Array(totalLen);
        var offset = 0;
        for (var j = 0; j < chunks.length; j++) {
          merged.set(chunks[j], offset);
          offset += chunks[j].length;
        }

        // Encode as WAV
        var actualSR = audioCtx.sampleRate;
        audioCtx.close();
        var wavBuffer = encodeWAV(merged, actualSR);
        var base64 = arrayBufferToBase64(wavBuffer);
        sendAudioData(id, base64, transcript);
        updateAudioState("ready");
        addMessage("  Analyzing...", "msg msg-dim");
      }, duration * 1000);
    })
    .catch(function(err) {
      _debugLog.error("[mic] getUserMedia error:", err);
      hideRecordingOverlay();
      if (recognition) { try { recognition.stop(); } catch (e) {} }
      addMessage("  Microphone unavailable. Check browser permissions and try again. Skipping this drill.", "msg msg-wrong");
      sendAudioData(id, null);
      updateAudioState("error");
    });
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
  var reloadBtn2 = document.createElement("button");
  reloadBtn2.textContent = "Reload to continue";
  reloadBtn2.addEventListener("click", function() { location.reload(); });
  banner.appendChild(reloadBtn2);
  banner.classList.remove("hidden");
}

function hideDisconnectBanner() {
  var banner = document.getElementById("disconnect-banner");
  if (!banner || banner.classList.contains("hidden")) return;
  // Exit animation: fade + slide up, then hide
  banner.classList.add("banner-exit");
  setTimeout(function() {
    banner.classList.add("hidden");
    banner.classList.remove("banner-exit");
  }, DURATION_FAST);
}

// Keyboard shortcuts: Enter, Q, B, ?, N, R, M, 1-4
document.addEventListener("keydown", function(e) {
  // Ignore when typing in input fields (except answer-input for Enter)
  var tag = (e.target.tagName || "").toLowerCase();
  var isTextInput = (tag === "textarea" || (tag === "input" && e.target.id !== "answer-input"));
  if (isTextInput) return;

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

  // #20 — M key starts mini session from dashboard
  if ((e.key === "m" || e.key === "M") && onDashboard && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    startSession("mini");
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

  // #18 — R key replays audio
  if ((e.key === "r" || e.key === "R") && !e.ctrlKey && !e.metaKey) {
    var replayBtn = document.querySelector(".btn-option-replay");
    if (replayBtn) {
      e.preventDefault();
      replayBtn.click();
      return;
    }
    // Also replay if there's a current audio
    if (currentAudio && currentAudio.src) {
      e.preventDefault();
      quickAnswer("R");
      return;
    }
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
  var doneBtn = document.querySelector('.btn-shortcut[data-quick="Q"]');
  if (_doneConfirmPending) {
    // Second tap — actually quit
    _doneConfirmPending = false;
    if (_doneConfirmTimer) { clearTimeout(_doneConfirmTimer); _doneConfirmTimer = null; }
    if (doneBtn) { doneBtn.classList.remove("confirm-tap"); doneBtn.innerHTML = 'done <kbd>Q</kbd>'; }
    quickAnswer("Q");
    return;
  }
  // First tap — show confirmation
  _doneConfirmPending = true;
  if (doneBtn) { doneBtn.classList.add("confirm-tap"); doneBtn.innerHTML = 'end session? <kbd>Q</kbd>'; }
  _doneConfirmTimer = setTimeout(function() {
    _doneConfirmPending = false;
    if (doneBtn) { doneBtn.classList.remove("confirm-tap"); doneBtn.innerHTML = 'done <kbd>Q</kbd>'; }
  }, 3000);
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
      tip.textContent = "Eliminates wrong options. Counts as partial.";
      hintBtn.appendChild(tip);
      setTimeout(function() { if (tip.parentNode) tip.remove(); }, 3000);
    }
    try { localStorage.setItem("hintUsedBefore", "true"); } catch (e) {}
    _hintUsedBefore = true;
  }
  quickAnswer("?");
}

/* ── Panel toggle with localStorage persistence ────────────────────────── */

function togglePanel(panelId) {
  var panel = document.getElementById(panelId);
  if (!panel) return;
  var body = panel.querySelector(".panel-body");
  var icon = panel.querySelector(".toggle-icon");
  var h3 = panel.querySelector("h3");
  if (!body) return;

  if (body.classList.contains("panel-closed")) {
    // Opening: set max-height to 0 (current state), remove closed class,
    // reflow, then set max-height to actual content height for accurate timing.
    body.style.maxHeight = "0px";
    body.classList.remove("panel-closed");
    body.offsetHeight; // force reflow
    body.style.maxHeight = body.scrollHeight + "px";
    if (icon) icon.textContent = "\u2212";
    if (h3) h3.setAttribute("aria-expanded", "true");
    savePanelState(panelId, true);
  } else {
    // Closing: capture current height, reflow, then animate to 0.
    body.style.maxHeight = body.scrollHeight + "px";
    body.offsetHeight; // force reflow
    body.style.maxHeight = "0px";
    body.style.opacity = "0";
    body.style.marginTop = "0";
    if (icon) icon.textContent = "+";
    if (h3) h3.setAttribute("aria-expanded", "false");
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
  var h3 = panel.querySelector("h3");
  if (!body) return;
  body.classList.remove("panel-closed");
  body.style.maxHeight = "none"; // natural height, no transition on initial render
  if (icon) icon.textContent = "\u2212";
  if (h3) h3.setAttribute("aria-expanded", "true");
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
  fetchForecast();
  fetchProgress();
  fetchSessions();
  fetchEncounterStats();
}

function fetchForecast() {
  fetch("/api/forecast")
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        showPanelError("forecast-content", "Not enough data yet.");
        return;
      }
      const content = document.getElementById("forecast-content");
      let html = "";

      // Pace display — narrative framing
      if (data.pace && data.pace.message) {
        html += '<div class="panel-row"><span class="label">' + escapeHtml(data.pace.message) + '</span></div>';
      } else if (data.pace_label) {
        html += '<div class="panel-row"><span class="label">' + escapeHtml(data.pace_label) + '</span></div>';
      }

      // Aspirational milestones with timeline bars
      if (data.aspirational && data.aspirational.length > 0) {
        for (var i = 0; i < data.aspirational.length; i++) {
          var milestone = data.aspirational[i];
          var target = milestone.target || 0;
          var current = milestone.current || 0;
          var weeksNum = milestone.weeks_remaining;
          var weeksStr = weeksNum != null ? (weeksNum === 1 ? "~1 week" : "~" + weeksNum + " weeks") : "";
          var targetLabel = "HSK " + (milestone.target_int || Math.ceil(target));

          html += '<div class="panel-row"><span class="label">' + targetLabel + '</span>';
          html += '<span class="value">' + (weeksStr || "assessing") + '</span></div>';

          // Timeline bar: show progress from current level toward target
          if (target > 0) {
            var pct = Math.min(100, Math.max(0, (current / target) * 100));
            html += '<div class="forecast-timeline" aria-label="Progress toward ' + targetLabel + '">';
            html += '<div class="forecast-bar">';
            html += '<div class="forecast-fill" style="width:' + pct.toFixed(1) + '%"></div>';
            html += '<div class="forecast-marker" style="left:' + pct.toFixed(1) + '%"></div>';
            html += '</div>';
            html += '<div class="forecast-timeline-label">';
            html += '<span>Now: ' + current.toFixed(1) + ' (' + Math.round(pct) + '%)</span>';
            html += '<span>' + targetLabel + '</span>';
            html += '</div>';
            html += '</div>';
          }
        }
      }

      // Modality projections with timeline bars
      if (data.modality_projections) {
        for (const [mod, proj] of Object.entries(data.modality_projections)) {
          if (proj.milestones && proj.milestones.length > 0) {
            var msCurrent = proj.current_level || 0;
            var ms = proj.milestones[0]; // next milestone
            var msTarget = ms.target || 0;
            var msWeeks = ms.weeks != null ? (ms.weeks === 1 ? "~1 week" : "~" + ms.weeks + " weeks") : "";
            var modLabel = mod.charAt(0).toUpperCase() + mod.slice(1);

            html += '<div class="panel-row"><span class="label">' + escapeHtml(modLabel) + '</span>';
            html += '<span class="value">' + (msWeeks || "assessing") + '</span></div>';

            if (msTarget > 0) {
              var msPct = Math.min(100, Math.max(0, (msCurrent / msTarget) * 100));
              html += '<div class="forecast-timeline">';
              html += '<div class="forecast-bar">';
              html += '<div class="forecast-marker" style="left:' + msPct.toFixed(1) + '%"></div>';
              html += '</div>';
              html += '<div class="forecast-timeline-label">';
              html += '<span>' + msCurrent.toFixed(1) + '</span>';
              html += '<span>HSK ' + Math.ceil(msTarget) + '</span>';
              html += '</div>';
              html += '</div>';
            }
          }
        }
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
        showPanelError("forecast-content", "Not enough data yet.");
      }
    })
    .catch(function() {
      showPanelError("forecast-content", "Not enough data yet.");
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
        // Narrative: "Roughly 185 of 220 items above recall threshold"
        if (totalItems > 0) {
          html += '<div class="panel-row"><span class="label">' + retainedCount + ' of ' + totalItems + ' items above recall threshold</span><span class="value">' + pct + '%</span></div>';
        } else {
          html += '<div class="panel-row"><span class="label">Recall above threshold</span><span class="value">' + pct + '%</span></div>';
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
        html += '<div class="sparkline-row" aria-label="Accuracy trend sparkline">';
        html += '<span class="sparkline-label">Accuracy trend </span> ' + spark;
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
        if (pct >= 90) assessment = "Strong";
        else if (pct >= 75) assessment = "Steady";
        else if (pct >= 55) assessment = "Building";
        else assessment = "Difficult";

        html += '<div class="session-history-item">';
        html += '<span class="session-date">' + dateStr + '</span>';
        html += '<span class="session-narrative">' + narrative + ' \u2014 <span class="session-assessment">' + assessment + '</span></span>';
        html += '</div>';
      }
      replaceContent("sessions-content", html);
    })
    .catch(function() {
      showPanelError("sessions-content", "No sessions yet.");
    });
}

function showPanelError(contentId, message) {
  // #26 — Panel errors include a retry button
  var retryMap = {
    "forecast-content": fetchForecast,
    "retention-content": fetchProgress,
    "sessions-content": fetchSessions
  };
  var retryFn = retryMap[contentId];
  var retryHtml = retryFn ? ' <button class="panel-retry-btn" data-retry="' + contentId + '">Retry</button>' : '';
  replaceContent(contentId, '<div class="empty-state">' + escapeHtml(message) + retryHtml + '</div>');
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
  // Update meta theme-color to match
  var metaLight = document.querySelector('meta[name="theme-color"][media*="light"]');
  var metaDark = document.querySelector('meta[name="theme-color"][media*="dark"]');
  if (isDark) {
    if (metaLight) metaLight.setAttribute("content", "#1C2028");
    if (metaDark) metaDark.setAttribute("content", "#1C2028");
  } else {
    if (metaLight) metaLight.setAttribute("content", "#946070");
    if (metaDark) metaDark.setAttribute("content", "#946070");
  }
}

// Apply immediately (before DOMContentLoaded to minimize flash)
applyTimeTheme();
// Re-check every 60 seconds for hour boundary crossings
setInterval(applyTimeTheme, 60000);

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

function backToDashboardFrom(viewId) {
  var viewEl = document.getElementById(viewId);
  var dashEl = document.getElementById("dashboard");
  if (viewEl) viewEl.classList.add("hidden");
  if (dashEl) dashEl.classList.remove("hidden");
}

/* ── Reading View ──────────────────────────────── */

function openReadingView() {
  transitionTo("dashboard", "reading");
  _readingWordsLookedUp = 0;
  _readingStartTime = Date.now();
  loadPassageList();

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
}

function onReadingLevelChange() {
  loadPassageList();
}

function onPinyinToggle() {
  var el = document.getElementById("reading-pinyin");
  var cb = document.getElementById("reading-pinyin-toggle");
  if (el) el.classList.toggle("hidden", !cb.checked);
}

function onTranslationToggle() {
  var el = document.getElementById("reading-translation");
  var cb = document.getElementById("reading-translation-toggle");
  if (el) el.classList.toggle("hidden", !cb.checked);
}

function loadPassageList() {
  var level = document.getElementById("reading-level").value;
  var url = "/api/reading/passages" + (level ? "?hsk_level=" + level : "");
  fetch(url).then(function(r) { return r.json(); }).then(function(data) {
    _readingPassages = data.passages || [];
    var listEl = document.getElementById("reading-list");
    var passageEl = document.getElementById("reading-passage");
    listEl.classList.remove("hidden");
    passageEl.classList.add("hidden");

    if (_readingPassages.length === 0) {
      listEl.textContent = "";
      { const _es = document.createElement("div"); _es.className = "empty-state"; _es.textContent = "No passages at this level."; listEl.appendChild(_es); }
      return;
    }
    var html = "";
    for (var i = 0; i < _readingPassages.length; i++) {
      var p = _readingPassages[i];
      html += '<button class="reading-list-item" data-idx="' + i + '">'
        + '<span class="reading-list-title">' + escapeHtml(p.title_zh || p.title) + '</span>'
        + '<span class="reading-list-meta">HSK ' + p.hsk_level + '</span>'
        + '</button>';
    }
    listEl.innerHTML = html; // Safe: all data vars escaped via escapeHtml()
    listEl.querySelectorAll(".reading-list-item").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var idx = parseInt(btn.dataset.idx);
        loadPassage(idx);
      });
    });
  }).catch(function() {
    { const _rl = document.getElementById("reading-list"); _rl.textContent = ""; const _es2 = document.createElement("div"); _es2.className = "empty-state"; _es2.textContent = "Failed to load passages."; _rl.appendChild(_es2); }
  });
}

function loadPassage(idx) {
  if (idx < 0 || idx >= _readingPassages.length) return;
  _readingIndex = idx;
  var p = _readingPassages[idx];
  _currentPassageId = p.id;
  _readingWordsLookedUp = 0;
  _readingStartTime = Date.now();

  fetch("/api/reading/passage/" + encodeURIComponent(p.id))
    .then(function(r) { return r.json(); })
    .then(function(passage) {
      var listEl = document.getElementById("reading-list");
      var passageEl = document.getElementById("reading-passage");
      listEl.classList.add("hidden");
      passageEl.classList.remove("hidden");

      // Render text character-by-character with clickable words
      var textEl = document.getElementById("reading-text");
      var text = passage.text_zh || "";
      var html = "";
      // Split into characters, make each clickable
      for (var i = 0; i < text.length; i++) {
        var ch = text[i];
        if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) {
          html += '<span class="reading-word" data-char="' + escapeHtml(ch) + '">' + escapeHtml(ch) + '</span>';
        } else {
          html += escapeHtml(ch);
        }
      }
      textEl.innerHTML = html; // Safe: all chars escaped via escapeHtml()

      // Add click handlers for word lookup
      textEl.querySelectorAll(".reading-word").forEach(function(span) {
        span.addEventListener("click", function(e) {
          lookupWord(span.dataset.char, e);
        });
      });

      // Pinyin and translation
      var pinyinEl = document.getElementById("reading-pinyin");
      pinyinEl.textContent = passage.text_pinyin || "";
      var transEl = document.getElementById("reading-translation");
      transEl.textContent = passage.text_en || "";

      // Update nav buttons
      document.getElementById("reading-prev").disabled = (idx <= 0);
      document.getElementById("reading-next").disabled = (idx >= _readingPassages.length - 1);

      updateReadingStats();
    });
}

function lookupWord(hanzi, event) {
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

    // Show gloss tooltip
    var gloss = document.getElementById("reading-gloss") || document.getElementById("listening-gloss");
    if (!gloss) return;
    var pinyin = data.pinyin || "";
    var english = data.english || "";
    var content = pinyin;
    if (english) content += (content ? " — " : "") + english;
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

function navigatePassage(dir) {
  var newIdx = _readingIndex + dir;
  if (newIdx >= 0 && newIdx < _readingPassages.length) {
    loadPassage(newIdx);
  }
}

/* ── Media View ──────────────────────────────── */

function openMediaView() {
  transitionTo("dashboard", "media");
  loadMediaRecommendations();
  loadMediaHistory();
}

function loadMediaRecommendations() {
  fetch("/api/media/recommendations?limit=6")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var grid = document.getElementById("media-grid");
      var recs = data.recommendations || [];
      if (recs.length === 0) {
        grid.textContent = "";
        { const _es3 = document.createElement("div"); _es3.className = "empty-state"; _es3.textContent = "No recommendations available."; grid.appendChild(_es3); }
        return;
      }
      var html = "";
      for (var i = 0; i < recs.length; i++) {
        var m = recs[i];
        var costClass = m.cost === "free" ? "cost-free" : m.cost === "subscription" ? "cost-sub" : "cost-purchase";
        var watchedBadge = m.times_watched > 0 ? '<span class="media-watched-badge">Watched</span>' : '';
        var whereText = typeof m.where_to_find === "object" ? (m.where_to_find.primary || "") : (m.where_to_find || "");
        var quizBtn = m.has_quiz ? '<button class="btn-media-quiz" data-id="' + escapeHtml(m.id) + '">Quiz</button>' : '';
        html += '<div class="media-card" data-media-id="' + escapeHtml(m.id) + '">'
          + '<div class="media-card-header">'
          + '<span class="media-hsk-badge">HSK ' + m.hsk_level + '</span>'
          + '<span class="media-cost-badge ' + costClass + '">' + escapeHtml(m.cost) + '</span>'
          + watchedBadge
          + '</div>'
          + '<div class="media-card-title">' + escapeHtml(m.title) + '</div>'
          + '<div class="media-card-type">' + escapeHtml(m.media_type) + '</div>'
          + (whereText ? '<div class="media-card-where">' + escapeHtml(whereText) + '</div>' : '')
          + '<div class="media-card-actions">'
          + quizBtn
          + '<button class="btn-media-watched" data-id="' + escapeHtml(m.id) + '">Watched</button>'
          + '<button class="btn-media-skip" data-id="' + escapeHtml(m.id) + '">Skip</button>'
          + '<button class="btn-media-like" data-id="' + escapeHtml(m.id) + '">Like</button>'
          + '</div>'
          + '</div>';
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
      { const _mg = document.getElementById("media-grid"); _mg.textContent = ""; const _es4 = document.createElement("div"); _es4.className = "empty-state"; _es4.textContent = "Failed to load recommendations."; _mg.appendChild(_es4); }
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
  });
}

function loadMediaHistory() {
  fetch("/api/media/history")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var listEl = document.getElementById("media-history-list");
      var hist = data.history || [];
      var stats = data.stats || {};
      if (hist.length === 0) {
        listEl.textContent = "";
        { const _es5 = document.createElement("div"); _es5.className = "empty-state"; _es5.textContent = "No watch history yet."; listEl.appendChild(_es5); }
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
    });
}

/* ── Media Comprehension Quiz ──────────────────── */

var _quizData = null;
var _quizAnswers = [];
var _quizCurrentQ = 0;

function openMediaQuiz(mediaId) {
  transitionTo("media", "media-quiz");
  _quizData = null;
  _quizAnswers = [];
  _quizCurrentQ = 0;

  document.getElementById("media-quiz-title").textContent = "Loading…";
  document.getElementById("media-quiz-vocab").textContent = "";
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
      document.getElementById("media-quiz-title").textContent = data.title || "Comprehension Quiz";

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

      // Render first question
      renderQuizQuestion(0);
    })
    .catch(function() {
      document.getElementById("media-quiz-title").textContent = "Failed to load quiz";
    });
}

function renderQuizQuestion(idx) {
  var questions = _quizData.questions || [];
  if (idx >= questions.length) {
    finishQuiz();
    return;
  }
  _quizCurrentQ = idx;
  var q = questions[idx];
  var qType = q.type || "mc";
  var container = document.getElementById("media-quiz-questions");

  var html = '<div class="quiz-question">'
    + '<div class="quiz-q-number">Q' + (idx + 1) + ' of ' + questions.length + '</div>'
    + '<div class="quiz-q-text">' + escapeHtml(q.q_zh || "") + '</div>';
  if (q.q_en) {
    html += '<div class="quiz-q-en">' + escapeHtml(q.q_en) + '</div>';
  }

  var options = [];
  if (qType === "mc") {
    options = shuffleArray(q.options || []);
    for (var i = 0; i < options.length; i++) {
      html += '<button class="quiz-option" data-idx="' + i + '">'
        + escapeHtml(options[i].text || "")
        + ' <span class="quiz-option-en">(' + escapeHtml(options[i].text_en || "") + ')</span>'
        + '</button>';
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

  // Advance after brief delay
  setTimeout(function() {
    renderQuizQuestion(_quizCurrentQ + 1);
  }, 1200);
}

function finishQuiz() {
  var correct = _quizAnswers.filter(function(a) { return a; }).length;
  var total = _quizAnswers.length;
  var score = total > 0 ? correct / total : 0;

  // Show result
  var resultEl = document.getElementById("media-quiz-result");
  // Safe: correct, total, score are all locally-computed numbers
  resultEl.innerHTML = '<div class="quiz-score">Score: ' + correct + '/' + total
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

function openListeningView() {
  transitionTo("dashboard", "listening");
  _listeningWordsLookedUp = [];
  _listeningPlayed = false;
  loadListeningPassage();

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
  if (newBtn) { newBtn.onclick = loadListeningPassage; }
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
    document.getElementById("listening-title").textContent = "Failed to load passage.";
  });
}

function playListeningPassage() {
  if (!_listeningPassage) return;

  // Check for zh-CN voice
  var text = _listeningPassage.text_zh || "";
  if (!text) return;

  if (!window.speechSynthesis) {
    document.getElementById("listening-title").textContent += " (TTS not available in this browser)";
    return;
  }

  var utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  var speedSelect = document.getElementById("listening-speed");
  utterance.rate = parseFloat(speedSelect.value) || 1.0;

  // Try to find a zh-CN voice
  var voices = speechSynthesis.getVoices();
  var zhVoice = voices.find(function(v) { return v.lang.startsWith("zh"); });
  if (zhVoice) utterance.voice = zhVoice;

  // #30 — Show TTS playing indicator
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

  utterance.onend = function() {
    if (playingIndicator) playingIndicator.classList.add("hidden");
  };
  utterance.onerror = function() {
    if (playingIndicator) playingIndicator.classList.add("hidden");
  };

  speechSynthesis.cancel();
  speechSynthesis.speak(utterance);
  _listeningPlayed = true;

  document.getElementById("listening-play").classList.add("hidden");
  document.getElementById("listening-replay").classList.remove("hidden");
  document.getElementById("listening-reveal").classList.remove("hidden");
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
  textEl.innerHTML = html; // Safe: all chars escaped via escapeHtml()

  textEl.querySelectorAll(".reading-word").forEach(function(span) {
    span.addEventListener("click", function(e) {
      _listeningWordsLookedUp.push(span.dataset.char);
      lookupWord(span.dataset.char, e);
    });
  });

  // Show comprehension questions if available
  showListeningQuestions();
}

function showListeningQuestions() {
  if (!_listeningPassage || !_listeningPassage.questions || _listeningPassage.questions.length === 0) return;
  var qEl = document.getElementById("listening-questions");
  qEl.classList.remove("hidden");

  var html = '<h3>Comprehension</h3>';
  var questions = _listeningPassage.questions;
  for (var i = 0; i < questions.length; i++) {
    var q = questions[i];
    html += '<div class="listening-question">'
      + '<div class="listening-q-text">' + escapeHtml(q.q_zh || "") + '</div>';
    if (q.q_en) html += '<div class="listening-q-en">' + escapeHtml(q.q_en) + '</div>';
    html += '<button class="btn-secondary btn-show-answer" data-answer="' + escapeHtml(q.answer || "") + '">Show Answer</button>';
    html += '<div class="listening-answer hidden"></div>';
    html += '</div>';
  }
  qEl.innerHTML = html; // Safe: all data vars escaped via escapeHtml()

  // Show answer buttons
  qEl.querySelectorAll(".btn-show-answer").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var answerEl = btn.nextElementSibling;
      answerEl.textContent = btn.dataset.answer;
      answerEl.classList.remove("hidden");
      btn.classList.add("hidden");
    });
  });

  // Log encounters on complete
  if (_listeningWordsLookedUp.length > 0) {
    apiFetch("/api/listening/complete", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        passage_id: _listeningPassage.id,
        words_looked_up: _listeningWordsLookedUp
      })
    });
  }
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
      badge.textContent = data.total_lookups_7d + " words looked up this week";
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

function showOnboardingWizard() {
  var dashboard = document.getElementById("dashboard");
  if (!dashboard) return;
  // Inject wizard styles
  var style = document.createElement("style");
  style.textContent = [
    ".onboarding-wizard { position:fixed; inset:0; z-index:1000; display:flex; align-items:center; justify-content:center; background:rgba(0,0,0,0.4); padding:var(--space-4); }",
    ".onboarding-wizard-card { background:var(--color-base); border-radius:12px; padding:var(--space-6); max-width:420px; width:100%; }",
    ".onboarding-wizard p { font-family:var(--font-body); font-size:var(--text-lg); color:var(--color-text); margin-bottom:var(--space-4); text-align:center; }",
    ".onboarding-options { display:flex; flex-direction:column; gap:var(--space-2); }",
    ".onboarding-opt { text-align:left !important; padding:12px 16px !important; }",
    ".onboarding-step.hidden { display:none; }",
  ].join("\n");
  document.head.appendChild(style);
  // Build wizard overlay
  var overlay = document.createElement("div");
  overlay.id = "onboarding-wizard";
  overlay.className = "onboarding-wizard";
  overlay.innerHTML =
    '<div class="onboarding-wizard-card">' +
      '<div class="auth-logo"><div class="logo-mark" aria-hidden="true">\u6F2B</div>' +
      '<div class="logo-text">Welcome</div></div>' +
      // #27 — Intro text
      '<div class="onboarding-wizard-intro">Patient Mandarin study. Honest data, no theatrics. Set your starting level and session length to begin.</div>' +
      '<div id="onboarding-step-1" class="onboarding-step">' +
        '<p>What HSK level are you starting from?</p>' +
        '<div class="onboarding-options" id="onboarding-levels">' +
          // #6 — HSK level descriptions
          '<button class="btn-secondary onboarding-opt" data-level="1">HSK 1 \u2014 Beginner<br><small>New to Mandarin. ~150 core words.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-level="2">HSK 2 \u2014 Elementary<br><small>Basic conversations. ~300 words.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-level="3">HSK 3 \u2014 Intermediate<br><small>Daily topics. ~600 words.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-level="4">HSK 4 \u2014 Upper-Intermediate<br><small>Fluent on familiar topics. ~1200 words.</small></button>' +
        '</div>' +
      '</div>' +
      '<div id="onboarding-step-2" class="onboarding-step hidden">' +
        '<p>How much time per session?</p>' +
        '<div class="onboarding-options" id="onboarding-goals">' +
          // #15 — Goal descriptions
          '<button class="btn-secondary onboarding-opt" data-goal="quick">Quick \u2014 5 min<br><small>A few drills. Good for daily habit.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-goal="standard">Standard \u2014 10 min<br><small>Balanced review and new material.</small></button>' +
          '<button class="btn-secondary onboarding-opt" data-goal="deep">Deep \u2014 20 min<br><small>Thorough practice. Best for retention.</small></button>' +
        '</div>' +
        // #9 — Back button
        '<button class="btn-secondary onboarding-back-btn" id="onboarding-back" style="margin-top:var(--space-3);width:100%">&larr; Back</button>' +
      '</div>' +
    '</div>';
  document.getElementById("app").appendChild(overlay);

  // Step 1: level
  overlay.querySelectorAll("[data-level]").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var level = parseInt(btn.getAttribute("data-level"));
      apiFetch("/api/onboarding/level", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({level: level})
      }).then(function() {
        document.getElementById("onboarding-step-1").classList.add("hidden");
        document.getElementById("onboarding-step-2").classList.remove("hidden");
      });
    });
  });

  // #9 — Back button in step 2
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
        overlay.remove();
        location.reload();
      });
    });
  });
}

document.addEventListener("DOMContentLoaded", function() {
  // Check onboarding status for new users
  checkOnboarding();

  // Report a Problem modal
  initReportProblem();

  // Collapsible panel headers (click + keyboard) — register first
  document.querySelectorAll("[data-panel]").forEach(function(h3) {
    var panelId = h3.getAttribute("data-panel");
    h3.addEventListener("click", function() { togglePanel(panelId); });
    h3.addEventListener("keydown", function(e) { panelKeyHandler(e, panelId); });
  });

  // Session start buttons
  var btnStart = document.getElementById("btn-start");
  var btnMini = document.getElementById("btn-mini");
  if (btnStart) btnStart.addEventListener("click", function() { startSession("standard"); });
  if (btnMini) btnMini.addEventListener("click", function() { startSession("mini"); });

  // #13 — Disable Begin until items confirmed via status check
  if (btnStart) {
    btnStart.disabled = true;
    btnStart.textContent = "Checking...";
    fetch("/api/status").then(function(r) { return r.json(); }).then(function(data) {
      var count = data.item_count || 0;
      btnStart.disabled = false;
      btnStart.textContent = "Begin";
      if (count === 0) {
        btnStart.disabled = true;
        btnStart.textContent = "No items yet";
      }
    }).catch(function() {
      // On error, enable anyway — don't block the user
      btnStart.disabled = false;
      btnStart.textContent = "Begin";
    });
  }

  // Exposure view buttons
  var btnRead = document.getElementById("btn-read");
  var btnWatch = document.getElementById("btn-watch");
  var btnListen = document.getElementById("btn-listen");
  if (btnRead) btnRead.addEventListener("click", function() { openReadingView(); });
  if (btnWatch) btnWatch.addEventListener("click", function() { openMediaView(); });
  if (btnListen) btnListen.addEventListener("click", function() { openListeningView(); });

  // Back buttons for exposure views
  var readingBack = document.getElementById("reading-back");
  var mediaBack = document.getElementById("media-back");
  var listeningBack = document.getElementById("listening-back");
  if (readingBack) readingBack.addEventListener("click", function() { backToDashboardFrom("reading"); });
  if (mediaBack) mediaBack.addEventListener("click", function() { backToDashboardFrom("media"); });
  if (listeningBack) listeningBack.addEventListener("click", function() { backToDashboardFrom("listening"); });
  var mediaQuizBack = document.getElementById("media-quiz-back");
  if (mediaQuizBack) mediaQuizBack.addEventListener("click", function() { transitionTo("media-quiz", "media"); loadMediaRecommendations(); loadMediaHistory(); });

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
    if (!MandarinSound.isEnabled()) soundToggle.classList.add("sound-off");
    soundToggle.addEventListener("click", function() {
      var on = MandarinSound.toggle();
      soundToggle.classList.toggle("sound-off", !on);
      soundToggle.setAttribute("aria-label", on ? "Sound on" : "Sound off");
    });
  }

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
          html += '<div class="tooltip-row">'
            + '<span class="tooltip-label">'
            + '<span class="tooltip-dot" style="background:' + stageColors[key] + '"></span>'
            + stageLabels[key] + '</span>'
            + '<span class="tooltip-value">' + count + ' (' + pct + '%)</span>'
            + '</div>';
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
      // Keep within viewport
      if (x + rect.width > window.innerWidth - 8) x = e.clientX - rect.width - 12;
      if (y + rect.height > window.innerHeight - 8) y = e.clientY - rect.height - 12;
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

  // ── Feature: Onboarding Checklist ──────────────────────────
  loadOnboardingChecklist();

  // ── Feature: Referral UI ──────────────────────────
  loadReferralData();

  // ── Feature: Feedback / NPS ──────────────────────────
  initFeedbackBar();
});

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
        fallbackCopy(linkInput, statusEl);
      });
    } else {
      fallbackCopy(linkInput, statusEl);
    }
  });
}

function fallbackCopy(inputEl, statusEl) {
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
      // If all complete, check if we already showed the final message
      if (data.all_complete) {
        try {
          if (localStorage.getItem("onboarding_complete_shown") === "true") return;
        } catch (e) {}
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
      + '<span class="onboarding-check" aria-hidden="true">' + (done ? "\u2713" : "") + '</span>'
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
  if (!navigator.onLine) showOfflineIndicator();

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
      '<p class="report-modal-desc">Describe what went wrong. The download includes your recent event log and app state — no personal data beyond study progress.</p>' +
      '<label for="report-description" class="report-label">What happened?</label>' +
      '<textarea id="report-description" class="report-textarea" rows="3" maxlength="1000" placeholder="e.g. Session froze after answering a tone drill..."></textarea>' +
      '<div class="report-actions">' +
        '<button id="report-download" class="btn-primary report-btn">Download Report</button>' +
        '<button id="report-copy" class="btn-secondary report-btn">Copy to Clipboard</button>' +
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

  // Download handler
  document.getElementById("report-download").addEventListener("click", function() {
    var payload = buildReportPayload();
    var blob = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"});
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "mandarin-report-" + new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19) + ".json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showReportStatus("Report downloaded.");
    EventLog.record("report", "downloaded");
  });

  // Copy handler
  document.getElementById("report-copy").addEventListener("click", function() {
    var payload = buildReportPayload();
    var text = JSON.stringify(payload, null, 2);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function() {
        showReportStatus("Copied to clipboard.");
      }).catch(function() {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }
    EventLog.record("report", "copied");
  });

  // Wire footer link
  var reportLink = document.getElementById("btn-report-problem");
  if (reportLink) {
    reportLink.addEventListener("click", function() {
      openReportModal();
    });
  }
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
