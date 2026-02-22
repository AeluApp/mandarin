/**
 * ab-test.js — Lightweight A/B testing utility for Mandarin landing pages.
 * No external dependencies. Under 100 lines.
 *
 * Usage:
 *
 *   // 1. Test which variant a user is assigned to:
 *   var headline = abTest('hero-headline', ['A', 'B']);
 *   if (headline === 'A') {
 *     document.getElementById('hero-h1').textContent = 'Patient Mandarin study.';
 *   } else {
 *     document.getElementById('hero-h1').textContent = 'Learn Chinese with honest data.';
 *   }
 *
 *   // 2. Swap element content directly:
 *   abTestElement('cta-text', 'cta-btn', {
 *     A: 'Start learning free',
 *     B: 'Try it — no credit card'
 *   });
 *
 *   // 3. Track a CTA click for the current variant:
 *   document.getElementById('cta-btn').addEventListener('click', function() {
 *     abTrackClick('hero-headline');
 *   });
 *
 * How it works:
 *   - On first visit, assigns user randomly to a variant via cookie (365 days).
 *   - Fires GA4 event `ab_test_assigned` with test name and variant.
 *   - abTrackClick fires `ab_test_click` with test name and variant.
 *   - Cookie name: `ab_{testName}` (one per test).
 */

(function () {
  'use strict';

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
  }

  function setCookie(name, value, days) {
    var expires = new Date();
    expires.setDate(expires.getDate() + (days || 365));
    document.cookie = name + '=' + encodeURIComponent(value) +
      ';expires=' + expires.toUTCString() +
      ';path=/;SameSite=Lax';
  }

  function fireGA4(eventName, params) {
    if (typeof window.gtag === 'function') {
      window.gtag('event', eventName, params);
    }
  }

  /**
   * Assign user to a variant for the given test.
   * @param {string} testName — unique test identifier (e.g. 'hero-headline')
   * @param {string[]} variants — array of variant labels (e.g. ['A', 'B'])
   * @returns {string} the assigned variant
   */
  function abTest(testName, variants) {
    if (!variants || variants.length === 0) return '';
    var cookieName = 'ab_' + testName;
    var assigned = getCookie(cookieName);

    if (assigned && variants.indexOf(assigned) !== -1) {
      return assigned;
    }

    // Random assignment
    var index = Math.floor(Math.random() * variants.length);
    assigned = variants[index];
    setCookie(cookieName, assigned, 365);

    // Fire assignment event
    fireGA4('ab_test_assigned', {
      test_name: testName,
      variant: assigned
    });

    return assigned;
  }

  /**
   * Swap an element's textContent based on variant assignment.
   * @param {string} testName — unique test identifier
   * @param {string} elementId — DOM element ID to modify
   * @param {Object} variants — { A: 'text for A', B: 'text for B' }
   */
  function abTestElement(testName, elementId, variants) {
    var keys = Object.keys(variants);
    var assigned = abTest(testName, keys);
    var el = document.getElementById(elementId);
    if (el && variants[assigned] !== undefined) {
      el.textContent = variants[assigned];
    }
  }

  /**
   * Track a CTA click tied to an A/B test variant.
   * @param {string} testName — the test whose variant to report
   */
  function abTrackClick(testName) {
    var cookieName = 'ab_' + testName;
    var variant = getCookie(cookieName) || 'unknown';
    fireGA4('ab_test_click', {
      test_name: testName,
      variant: variant
    });
  }

  // Public API
  window.abTest = abTest;
  window.abTestElement = abTestElement;
  window.abTrackClick = abTrackClick;
})();
