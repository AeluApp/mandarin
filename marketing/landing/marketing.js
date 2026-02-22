// marketing.js — Shared marketing infrastructure for Mandarin landing pages

(function() {
  'use strict';

  // === UTM Parameter Capture ===
  // Reads UTM params from URL, stores in sessionStorage

  var UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];

  function captureUTMParams() {
    var params = new URLSearchParams(window.location.search);
    var captured = {};
    UTM_KEYS.forEach(function(key) {
      var value = params.get(key);
      if (value) {
        captured[key] = value;
        try {
          sessionStorage.setItem(key, value);
        } catch (e) {
          // sessionStorage not available
        }
      }
    });
    return captured;
  }

  // === Referral Cookie ===
  // If ?ref=PARTNER_CODE exists, set a first-party cookie lasting 90 days
  // Cookie name: mandarin_ref
  // Only set if no existing cookie (first-click attribution)

  function captureReferralCode() {
    var params = new URLSearchParams(window.location.search);
    var ref = params.get('ref');
    if (!ref) return;

    // Check if cookie already exists (first-click attribution)
    if (getCookie('mandarin_ref')) return;

    var expires = new Date();
    expires.setDate(expires.getDate() + 90);
    document.cookie = 'mandarin_ref=' + encodeURIComponent(ref) +
      ';expires=' + expires.toUTCString() +
      ';path=/;SameSite=Lax';
  }

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
  }

  // === GA4 Event Helpers ===
  // Wrapper functions for gtag() that fire events gracefully

  function safeGtag() {
    if (typeof window.gtag === 'function') {
      window.gtag.apply(window, arguments);
    }
  }

  function trackWaitlistSignup(source) {
    safeGtag('event', 'waitlist_signup', {
      event_category: 'conversion',
      signup_source: source || 'unknown',
      referral_code: getCookie('mandarin_ref') || '',
      utm_source: getStoredUTM('utm_source'),
      utm_medium: getStoredUTM('utm_medium'),
      utm_campaign: getStoredUTM('utm_campaign')
    });
  }

  function trackCTAClick(page, ctaText) {
    safeGtag('event', 'cta_click', {
      event_category: 'engagement',
      page_name: page || window.location.pathname,
      cta_text: ctaText || ''
    });
  }

  function trackBlogRead(postSlug, readTimePercent) {
    safeGtag('event', 'blog_read', {
      event_category: 'engagement',
      post_slug: postSlug || '',
      read_time_percent: readTimePercent || 0
    });
  }

  function trackPricingView(source) {
    safeGtag('event', 'pricing_view', {
      event_category: 'conversion',
      view_source: source || window.location.pathname
    });
  }

  function trackAffiliateFormSubmit() {
    safeGtag('event', 'affiliate_form_submit', {
      event_category: 'conversion',
      referral_code: getCookie('mandarin_ref') || ''
    });
  }

  function getStoredUTM(key) {
    try {
      return sessionStorage.getItem(key) || '';
    } catch (e) {
      return '';
    }
  }

  // === Newsletter Signup ===
  // Intercept newsletter form submissions
  // Fire GA4 event, show thank you message, store in localStorage

  function initNewsletterSignup() {
    // Check if user already signed up
    var alreadySignedUp = false;
    try {
      alreadySignedUp = localStorage.getItem('mandarin_waitlist_signed_up') === 'true';
    } catch (e) {
      // localStorage not available
    }

    document.querySelectorAll('form.cta-email, form#signup-form, form#signup-form-bottom').forEach(function(form) {
      // If already signed up, hide form and show message
      if (alreadySignedUp) {
        form.style.display = 'none';
        var success = form.parentElement.querySelector('.cta-success');
        if (success) {
          success.style.display = 'block';
          success.textContent = "You're already on the list. We'll be in touch.";
        }
        return;
      }

      form.addEventListener('submit', function(e) {
        e.preventDefault();
        var email = form.querySelector('input[type="email"]').value;
        if (!email) return;

        // Fire GA4 event
        trackWaitlistSignup(form.id || window.location.pathname);

        // Store signup state
        try {
          localStorage.setItem('mandarin_waitlist_signed_up', 'true');
          localStorage.setItem('mandarin_waitlist_email', email);
        } catch (err) {
          // localStorage not available
        }

        // Show thank you message
        form.style.display = 'none';
        var success = form.parentElement.querySelector('.cta-success');
        if (success) {
          success.style.display = 'block';
        } else {
          var msg = document.createElement('div');
          msg.className = 'cta-success';
          msg.style.display = 'block';
          msg.textContent = "You're on the list. We'll let you know when it's ready.";
          form.parentElement.appendChild(msg);
        }
      });
    });
  }

  // === Scroll Depth Tracking ===
  // Fire GA4 events at 25%, 50%, 75%, 100% scroll depth
  // Debounced, fires once per threshold per page load

  function initScrollDepthTracking() {
    var thresholds = [25, 50, 75, 100];
    var fired = {};
    var debounceTimer = null;

    function getScrollPercent() {
      var docHeight = Math.max(
        document.body.scrollHeight,
        document.body.offsetHeight,
        document.documentElement.scrollHeight,
        document.documentElement.offsetHeight
      );
      var windowHeight = window.innerHeight || document.documentElement.clientHeight;
      var scrollTop = window.pageYOffset || document.documentElement.scrollTop;

      if (docHeight <= windowHeight) return 100;
      return Math.round((scrollTop / (docHeight - windowHeight)) * 100);
    }

    function checkThresholds() {
      var percent = getScrollPercent();
      thresholds.forEach(function(threshold) {
        if (percent >= threshold && !fired[threshold]) {
          fired[threshold] = true;
          safeGtag('event', 'scroll_depth', {
            event_category: 'engagement',
            depth_threshold: threshold,
            page_path: window.location.pathname
          });
        }
      });
    }

    window.addEventListener('scroll', function() {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(checkThresholds, 150);
    }, { passive: true });
  }

  // === CTA Click Tracking ===
  // Track clicks on primary and secondary CTA buttons

  function initCTATracking() {
    document.addEventListener('click', function(e) {
      var btn = e.target.closest('.btn-primary, .btn-secondary');
      if (btn && btn.tagName === 'A') {
        trackCTAClick(window.location.pathname, btn.textContent.trim());
      }
    });
  }

  // === Pricing Page View Tracking ===

  function initPricingTracking() {
    if (window.location.pathname.indexOf('pricing') !== -1) {
      trackPricingView(document.referrer || 'direct');
    }
  }

  // === Affiliate Form Tracking ===

  function initAffiliateFormTracking() {
    var form = document.getElementById('partner-form');
    if (!form) return;

    form.addEventListener('submit', function() {
      trackAffiliateFormSubmit();
    });
  }

  // === Mobile Nav Toggle ===

  function initMobileNav() {
    var toggle = document.querySelector('.nav-toggle');
    var links = document.querySelector('.nav-links');
    if (!toggle || !links) return;

    toggle.addEventListener('click', function() {
      var expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!expanded));
      links.classList.toggle('nav-open');
    });

    // Close menu when a link is clicked
    links.querySelectorAll('a').forEach(function(link) {
      link.addEventListener('click', function() {
        toggle.setAttribute('aria-expanded', 'false');
        links.classList.remove('nav-open');
      });
    });
  }

  // === Initialize Everything ===

  function init() {
    captureUTMParams();
    captureReferralCode();
    initNewsletterSignup();
    initScrollDepthTracking();
    initCTATracking();
    initPricingTracking();
    initAffiliateFormTracking();
    initMobileNav();
  }

  // Run when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // === Public API (for use by other scripts if needed) ===
  window.MandarinMarketing = {
    trackWaitlistSignup: trackWaitlistSignup,
    trackCTAClick: trackCTAClick,
    trackBlogRead: trackBlogRead,
    trackPricingView: trackPricingView,
    trackAffiliateFormSubmit: trackAffiliateFormSubmit,
    getCookie: getCookie,
    getStoredUTM: getStoredUTM
  };

})();
