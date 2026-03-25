/**
 * Hanzi Stroke Animation — stroke-order character reveals for Aelu.
 *
 * When a Chinese character appears in a drill, it draws itself on screen
 * stroke by stroke — the way you'd write it with a brush. This is both
 * beautiful and pedagogically powerful: stroke order is a real part of
 * learning Chinese.
 *
 * Uses HanziWriter (MIT license) loaded from CDN.
 * Falls back to instant display if HanziWriter unavailable or reduced motion.
 *
 * Usage:
 *   // Animate a character into a container
 *   AeluStroke.animate('你', document.getElementById('target'), {
 *     size: 200,
 *     onComplete: function() { console.log('done'); }
 *   });
 *
 *   // Quiz mode — user draws strokes
 *   AeluStroke.quiz('好', document.getElementById('target'));
 *
 * Respects prefers-reduced-motion (shows character instantly).
 */
(function() {
  'use strict';

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var writerInstances = new Map();

  // ── Color helpers ──
  function getCSSColor(prop) {
    return getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
  }

  // ── Load HanziWriter from CDN ──
  var HW = null;
  var hwReady = false;
  var hwCallbacks = [];

  function loadHanziWriter(cb) {
    if (hwReady && HW) { cb(HW); return; }
    hwCallbacks.push(cb);

    if (document.querySelector('script[data-hanzi-writer]')) return; // already loading

    var script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/hanzi-writer@3/dist/hanzi-writer.min.js';
    script.dataset.hanziWriter = 'true';
    script.async = true;
    script.onload = function() {
      HW = window.HanziWriter;
      hwReady = true;
      hwCallbacks.forEach(function(fn) { fn(HW); });
      hwCallbacks = [];
    };
    script.onerror = function() {
      // Fallback: HanziWriter unavailable
      hwCallbacks.forEach(function(fn) { fn(null); });
      hwCallbacks = [];
    };
    document.head.appendChild(script);
  }

  // ── Animate a character stroke-by-stroke ──
  function animate(char, container, opts) {
    if (!char || !container) return;
    opts = opts || {};

    // Reduced motion: just show the character immediately
    if (reducedMotion) {
      showFallback(char, container, opts);
      return;
    }

    loadHanziWriter(function(Writer) {
      if (!Writer) {
        showFallback(char, container, opts);
        return;
      }

      // Clear previous instance
      var existingId = container.dataset.hwId;
      if (existingId && writerInstances.has(existingId)) {
        writerInstances.get(existingId).hideCharacter();
        writerInstances.delete(existingId);
      }
      container.innerHTML = '';

      var id = 'hw-' + Date.now();
      container.dataset.hwId = id;

      var strokeColor = opts.strokeColor || getCSSColor('--color-text') || '#2A3650';
      var accentColor = getCSSColor('--color-accent') || '#946070';
      var size = opts.size || 200;

      try {
        var writer = Writer.create(char, container, {
          width: size,
          height: size,
          padding: 10,
          strokeColor: strokeColor,
          radicalColor: accentColor,
          strokeAnimationSpeed: 1.2,
          delayBetweenStrokes: 80,
          drawingWidth: size < 120 ? 4 : 6,
          showOutline: true,
          outlineColor: getCSSColor('--color-divider') || '#D8D0C4',
          showCharacter: false
        });

        writerInstances.set(id, writer);

        // Animate with callback
        writer.animateCharacter({
          onComplete: function() {
            // Subtle resonance when character finishes drawing — felt more than heard
            if (window.AeluSound) AeluSound.hintReveal();
            if (opts.onComplete) opts.onComplete();
          }
        });
      } catch (e) {
        // Character not in HanziWriter dataset — show fallback
        showFallback(char, container, opts);
      }
    });
  }

  // ── Quiz mode — user traces strokes ──
  function quiz(char, container, opts) {
    if (!char || !container) return;
    opts = opts || {};

    if (reducedMotion) {
      showFallback(char, container, opts);
      return;
    }

    loadHanziWriter(function(Writer) {
      if (!Writer) {
        showFallback(char, container, opts);
        return;
      }

      container.innerHTML = '';

      var strokeColor = opts.strokeColor || getCSSColor('--color-text') || '#2A3650';
      var correctColor = getCSSColor('--color-correct') || '#5A7A5A';
      var incorrectColor = getCSSColor('--color-incorrect') || '#806058';
      var size = opts.size || 200;

      try {
        var writer = Writer.create(char, container, {
          width: size,
          height: size,
          padding: 10,
          strokeColor: strokeColor,
          showOutline: true,
          outlineColor: getCSSColor('--color-divider') || '#D8D0C4',
          drawingColor: getCSSColor('--color-accent') || '#946070',
          drawingWidth: 6,
          showHintAfterMisses: 2,
          highlightColor: correctColor,
          highlightOnComplete: true,
          showCharacter: false
        });

        writer.quiz({
          onCorrectStroke: function(data) {
            if (opts.onCorrectStroke) opts.onCorrectStroke(data);
          },
          onMistake: function(data) {
            if (opts.onMistake) opts.onMistake(data);
          },
          onComplete: function(data) {
            if (opts.onComplete) opts.onComplete(data);
          }
        });
      } catch (e) {
        showFallback(char, container, opts);
      }
    });
  }

  // ── Fallback: just show the character as text ──
  function showFallback(char, container, opts) {
    var size = (opts && opts.size) || 200;
    container.innerHTML = '<span style="font-family:var(--font-hanzi);font-size:' +
      Math.round(size * 0.7) + 'px;color:var(--color-text);display:flex;align-items:center;' +
      'justify-content:center;width:' + size + 'px;height:' + size + 'px;line-height:1">' +
      char + '</span>';
    if (opts && opts.onComplete) {
      setTimeout(opts.onComplete, 50);
    }
  }

  // ── Cleanup ──
  function destroy(container) {
    if (!container) return;
    var id = container.dataset.hwId;
    if (id && writerInstances.has(id)) {
      writerInstances.delete(id);
    }
    container.innerHTML = '';
  }

  // ── Expose ──
  window.AeluStroke = {
    animate: animate,
    quiz: quiz,
    destroy: destroy
  };
})();
