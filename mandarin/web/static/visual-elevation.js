/**
 * Visual elevation utilities — typography effects, scroll-driven reveals,
 * interaction richness. Part of the 2026 aesthetic elevation.
 * Respects prefers-reduced-motion throughout.
 */
(function() {
  'use strict';

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ── splitText: wrap each character in a span for staggered animation ──
  function splitText(el) {
    if (!el || el.dataset.split === 'true') return;
    var text = el.textContent;
    var html = '';
    var charIndex = 0;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (ch === ' ') {
        html += ' ';
      } else {
        html += '<span class="text-reveal-char" style="animation-delay:' + (charIndex * 30) + 'ms">' + ch + '</span>';
        charIndex++;
      }
    }
    el.innerHTML = html;
    el.dataset.split = 'true';
  }

  // ── Heading reveal: animate underline on scroll entry ──
  function initHeadingReveals() {
    var headings = document.querySelectorAll('.heading-reveal');
    if (!headings.length) return;

    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.3 });

    headings.forEach(function(h) { observer.observe(h); });
  }

  // ── Scroll-driven section reveal ──
  function initScrollReveals() {
    var sections = document.querySelectorAll('[data-reveal], .stagger-children');
    if (!sections.length) return;

    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          // Stagger children if requested
          var children = entry.target.querySelectorAll('[data-reveal-child]');
          children.forEach(function(child, i) {
            child.style.transitionDelay = (i * 80) + 'ms';
            child.classList.add('is-revealed');
          });
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -30px 0px' });

    sections.forEach(function(s) { observer.observe(s); });
  }

  // ── Parallax scroll tracking ──
  function initParallax() {
    var parallaxEls = document.querySelectorAll('[data-parallax]');
    if (!parallaxEls.length) return;

    var ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function() {
        var scrollY = window.scrollY;
        parallaxEls.forEach(function(el) {
          var speed = parseFloat(el.dataset.parallax) || 0.1;
          el.style.transform = 'translateY(' + (scrollY * -speed) + 'px)';
        });
        ticking = false;
      });
    }

    window.addEventListener('scroll', onScroll, { passive: true });
  }

  // ── Magnetic hover on interactive elements ──
  function initMagneticHover() {
    if ('ontouchstart' in window) return; // skip on touch devices

    var magnetics = document.querySelectorAll('[data-magnetic]');
    magnetics.forEach(function(el) {
      var strength = parseFloat(el.dataset.magnetic) || 0.3;

      el.addEventListener('mousemove', function(e) {
        var rect = el.getBoundingClientRect();
        var cx = rect.left + rect.width / 2;
        var cy = rect.top + rect.height / 2;
        var dx = (e.clientX - cx) * strength;
        var dy = (e.clientY - cy) * strength;
        el.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
      });

      el.addEventListener('mouseleave', function() {
        el.style.transition = 'transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
        el.style.transform = 'translate(0, 0)';
        setTimeout(function() { el.style.transition = ''; }, 400);
      });
    });
  }

  // ── Haptic press feedback ──
  function initPressEffects() {
    var buttons = document.querySelectorAll('.btn-primary, .btn-secondary, [data-press]');
    buttons.forEach(function(btn) {
      btn.addEventListener('mousedown', function() {
        btn.style.transform = 'scale(0.97)';
        btn.style.transition = 'transform 0.1s ease';
      });
      btn.addEventListener('mouseup', function() {
        btn.style.transition = 'transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
        btn.style.transform = 'scale(1)';
      });
      btn.addEventListener('mouseleave', function() {
        btn.style.transition = 'transform 0.3s ease';
        btn.style.transform = 'scale(1)';
      });
    });
  }

  // ── Initialize ──
  function init() {
    if (reducedMotion) {
      // Still apply static styles, skip animations
      initHeadingReveals(); // underline still appears, just no transition
      return;
    }

    initHeadingReveals();
    initScrollReveals();
    initParallax();
    initMagneticHover();
    initPressEffects();

    // Auto-split any element with [data-split-text]
    document.querySelectorAll('[data-split-text]').forEach(splitText);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-init on dynamic content (for SPA section switches)
  var _observer = new MutationObserver(function(mutations) {
    var hasNew = mutations.some(function(m) { return m.addedNodes.length > 0; });
    if (hasNew) {
      initMagneticHover();
      initPressEffects();
      initHeadingReveals();
    }
  });
  _observer.observe(document.getElementById('app') || document.body, { childList: true, subtree: true });
})();
