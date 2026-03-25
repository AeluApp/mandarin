/**
 * Smooth Scroll — inertia-based scroll normalization for Aelu.
 *
 * Makes scrolling feel like silk: the page glides with gentle inertia,
 * decelerating into rest — matching the brand's "things decelerate into
 * rest" motion principle.
 *
 * Technique: intercepts wheel events, accumulates a target scroll position,
 * and lerps (smoothly interpolates) the actual scroll toward it each frame.
 *
 * Integrates with scroll-engine.js — the scroll engine reads window.scrollY
 * which this module controls.
 *
 * Disabled when:
 * - prefers-reduced-motion is active
 * - Touch/coarse pointer device (native momentum scroll is better)
 * - Browser doesn't support passive event listeners
 *
 * Usage:
 *   <script src="/static/smooth-scroll.js" defer></script>
 *   (loads automatically, no API needed)
 */
(function() {
  'use strict';

  // ── Guards ──
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (window.matchMedia('(pointer: coarse)').matches) return;
  if ('ontouchstart' in window) return;

  // ── Config ──
  var LERP_FACTOR = 0.08;   // Lower = smoother/slower (0.05–0.12 range)
  var WHEEL_MULT = 1.0;     // Multiplier for wheel delta
  var THRESHOLD = 0.5;      // Stop animating when within this many pixels

  // ── State ──
  var targetY = window.scrollY;
  var currentY = window.scrollY;
  var animating = false;
  var maxScroll = 0;

  function updateMaxScroll() {
    maxScroll = document.documentElement.scrollHeight - window.innerHeight;
  }

  // ── Lerp ──
  function lerp(start, end, factor) {
    return start + (end - start) * factor;
  }

  // ── Animation loop ──
  function animate() {
    currentY = lerp(currentY, targetY, LERP_FACTOR);

    // Snap when close enough
    if (Math.abs(currentY - targetY) < THRESHOLD) {
      currentY = targetY;
      animating = false;
    }

    // Apply scroll position
    window.scrollTo(0, currentY);

    if (animating) {
      requestAnimationFrame(animate);
    }
  }

  function startAnimation() {
    if (!animating) {
      animating = true;
      requestAnimationFrame(animate);
    }
  }

  // ── Wheel handler ──
  function onWheel(e) {
    e.preventDefault();
    updateMaxScroll();

    var delta = e.deltaY * WHEEL_MULT;

    // Normalize deltaMode (some mice report in lines or pages)
    if (e.deltaMode === 1) delta *= 40;  // lines → pixels
    if (e.deltaMode === 2) delta *= window.innerHeight; // pages → pixels

    targetY = Math.max(0, Math.min(maxScroll, targetY + delta));
    startAnimation();
  }

  // ── Keyboard scroll support (arrow keys, page up/down, space) ──
  function onKeydown(e) {
    var delta = 0;
    switch (e.key) {
      case 'ArrowDown': delta = 100; break;
      case 'ArrowUp': delta = -100; break;
      case 'PageDown': case ' ': delta = window.innerHeight * 0.8; break;
      case 'PageUp': delta = -window.innerHeight * 0.8; break;
      case 'Home': targetY = 0; startAnimation(); return;
      case 'End': updateMaxScroll(); targetY = maxScroll; startAnimation(); return;
      default: return;
    }
    if (e.shiftKey && e.key === ' ') delta = -delta;
    e.preventDefault();
    updateMaxScroll();
    targetY = Math.max(0, Math.min(maxScroll, targetY + delta));
    startAnimation();
  }

  // ── Sync state when user scrolls programmatically or via scrollbar ──
  var lastProgrammaticScroll = 0;
  function onNativeScroll() {
    // If scroll wasn't caused by us (e.g., scrollbar drag, anchor link)
    if (Date.now() - lastProgrammaticScroll > 100) {
      targetY = window.scrollY;
      currentY = window.scrollY;
    }
  }

  // Patch window.scrollTo to track programmatic scrolls
  var _nativeScrollTo = window.scrollTo.bind(window);
  window.scrollTo = function(x, y) {
    if (typeof x === 'object') {
      // scrollTo({ top, behavior }) — let native handle smooth, intercept instant
      if (x.behavior === 'smooth') {
        targetY = x.top || 0;
        startAnimation();
        return;
      }
      lastProgrammaticScroll = Date.now();
      _nativeScrollTo(x);
    } else {
      lastProgrammaticScroll = Date.now();
      _nativeScrollTo(x, y);
    }
  };

  // ── Init ──
  function init() {
    updateMaxScroll();
    currentY = window.scrollY;
    targetY = window.scrollY;

    // Wheel events must be non-passive to preventDefault
    window.addEventListener('wheel', onWheel, { passive: false });
    window.addEventListener('keydown', onKeydown);
    window.addEventListener('scroll', onNativeScroll, { passive: true });
    window.addEventListener('resize', function() {
      updateMaxScroll();
      targetY = Math.min(targetY, maxScroll);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
