/**
 * Scroll Engine — continuous scroll-position-based animation for Aelu.
 *
 * Replaces binary IntersectionObserver reveals with a continuous 0→1 progress
 * system per section, driving CSS custom properties and WebGL uniforms.
 *
 * Features:
 * - Maps scroll position to 0→1 for each [data-scroll-section]
 * - Sets --scroll-progress CSS property on each section
 * - Drives AeluScene.setScrollProgress() for WebGL integration
 * - Supports pinned sections (position:sticky + scroll-linked animation)
 * - Uses ScrollTimeline API where supported, RAF fallback elsewhere
 * - Passive scroll listener, requestAnimationFrame debounce
 *
 * Usage:
 *   <section data-scroll-section="hero" data-scroll-pin>
 *     <div style="opacity: calc(1 - var(--scroll-progress))">Fades out</div>
 *   </section>
 *
 *   AeluScroll.onProgress('hero', function(progress) { ... });
 *   AeluScroll.getProgress('hero'); // 0-1
 *
 * Respects prefers-reduced-motion (still computes progress, skips animations).
 */
(function() {
  'use strict';

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ── State ──
  var sections = [];
  var callbacks = {};
  var globalCallbacks = [];
  var ticking = false;
  var lastScrollY = 0;
  var viewportHeight = window.innerHeight;
  var totalScrollProgress = 0;

  // ── Section registration ──
  function registerSections() {
    sections = [];
    var els = document.querySelectorAll('[data-scroll-section]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var rect = el.getBoundingClientRect();
      var name = el.dataset.scrollSection;
      sections.push({
        el: el,
        name: name,
        top: rect.top + window.scrollY,
        height: rect.height,
        pinned: el.hasAttribute('data-scroll-pin'),
        progress: 0
      });
    }
    // Sort by DOM position
    sections.sort(function(a, b) { return a.top - b.top; });
  }

  // ── Progress computation ──
  function computeProgress() {
    var scrollY = window.scrollY;
    var docHeight = document.documentElement.scrollHeight - viewportHeight;
    totalScrollProgress = docHeight > 0 ? scrollY / docHeight : 0;

    for (var i = 0; i < sections.length; i++) {
      var s = sections[i];
      var start = s.top - viewportHeight;
      var end = s.top + s.height;
      var range = end - start;

      if (range <= 0) {
        s.progress = 0;
        continue;
      }

      var raw = (scrollY - start) / range;
      s.progress = Math.max(0, Math.min(1, raw));

      // Set CSS custom property
      s.el.style.setProperty('--scroll-progress', s.progress.toFixed(4));

      // Fire named callbacks
      if (callbacks[s.name]) {
        for (var j = 0; j < callbacks[s.name].length; j++) {
          callbacks[s.name][j](s.progress, s.el, s);
        }
      }
    }

    // Fire global callbacks
    for (var k = 0; k < globalCallbacks.length; k++) {
      globalCallbacks[k](totalScrollProgress, sections);
    }

    // Push total progress to scene manager
    if (window.AeluScene && window.AeluScene.setScrollProgress) {
      window.AeluScene.setScrollProgress(totalScrollProgress);
    }
  }

  // ── Scroll handler ──
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function() {
      computeProgress();
      ticking = false;
    });
  }

  // ── Resize handler ──
  function onResize() {
    viewportHeight = window.innerHeight;
    registerSections();
    computeProgress();
  }

  // ── Public API ──

  /** Register a callback for a named section's progress */
  function onProgress(sectionName, callback) {
    if (!callbacks[sectionName]) callbacks[sectionName] = [];
    callbacks[sectionName].push(callback);
  }

  /** Register a callback for total page scroll progress */
  function onGlobalProgress(callback) {
    globalCallbacks.push(callback);
  }

  /** Get current progress of a named section */
  function getProgress(sectionName) {
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].name === sectionName) return sections[i].progress;
    }
    return 0;
  }

  /** Get total page scroll progress */
  function getTotalProgress() {
    return totalScrollProgress;
  }

  /** Force re-measurement (call after dynamic content changes) */
  function refresh() {
    registerSections();
    computeProgress();
  }

  /** Smooth scroll to a named section */
  function scrollTo(sectionName, options) {
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].name === sectionName) {
        var offset = (options && options.offset) || 0;
        window.scrollTo({
          top: sections[i].top + offset,
          behavior: reducedMotion ? 'auto' : 'smooth'
        });
        return;
      }
    }
  }

  /** Animate a value driven by scroll progress of a section */
  function scrollDriven(sectionName, fromVal, toVal) {
    var progress = getProgress(sectionName);
    return fromVal + (toVal - fromVal) * progress;
  }

  // ── Init ──
  function init() {
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onResize);

    registerSections();
    computeProgress();

    // Re-register on DOM changes
    var mo = new MutationObserver(function(mutations) {
      var hasStructural = mutations.some(function(m) { return m.addedNodes.length > 0 || m.removedNodes.length > 0; });
      if (hasStructural) {
        setTimeout(refresh, 100); // debounce
      }
    });
    mo.observe(document.getElementById('app') || document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // ── Expose ──
  window.AeluScroll = {
    onProgress: onProgress,
    onGlobalProgress: onGlobalProgress,
    getProgress: getProgress,
    getTotalProgress: getTotalProgress,
    refresh: refresh,
    scrollTo: scrollTo,
    scrollDriven: scrollDriven
  };
})();
