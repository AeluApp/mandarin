/**
 * Visual elevation utilities — typography effects and scroll-driven reveals.
 * Stripped to purposeful essentials. Respects prefers-reduced-motion.
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

  // ── Parallax scroll tracking (marketing page only) ──
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

  // ── Initialize ──
  function init() {
    if (reducedMotion) {
      initHeadingReveals();
      return;
    }

    initHeadingReveals();
    initScrollReveals();
    initParallax();

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
      initHeadingReveals();
    }
  });
  _observer.observe(document.getElementById('app') || document.body, { childList: true, subtree: true });
})();
