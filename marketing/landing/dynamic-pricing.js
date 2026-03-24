/**
 * Dynamic pricing — fetches A/B experiment variant and updates visible
 * price text on any marketing page.
 *
 * Usage: Add <script src="/dynamic-pricing.js" defer></script> to any
 * landing page that shows prices. Mark dynamic price elements with
 * data-dynamic-price="monthly" or data-dynamic-price="annual".
 *
 * Also auto-replaces any visible "$14.99/month" or "$149/year" text in
 * elements with class "dynamic-price-text".
 *
 * JSON-LD, meta tags, and competitor pricing are NOT modified
 * (search engines need stable structured data).
 */
(function() {
  'use strict';

  fetch('/api/experiment/price-variant')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data || data.variant === 'default' || !data.price_display) return;

      var match = data.price_display.match(/\$?([\d.]+)/);
      if (!match) return;

      var monthly = match[1];
      var annualPrice = Math.round(parseFloat(monthly) * 10); // ~10 months for annual
      var annualPerMonth = (annualPrice / 12).toFixed(2);
      var savings = ((parseFloat(monthly) * 12) - annualPrice).toFixed(0);

      // Update elements tagged with data-dynamic-price
      document.querySelectorAll('[data-dynamic-price="monthly"]').forEach(function(el) {
        el.textContent = '$' + monthly + '/month';
      });
      document.querySelectorAll('[data-dynamic-price="annual"]').forEach(function(el) {
        el.textContent = '$' + annualPrice + '/year';
      });
      document.querySelectorAll('[data-dynamic-price="annual-monthly"]').forEach(function(el) {
        el.textContent = '$' + annualPerMonth + '/month';
      });
      document.querySelectorAll('[data-dynamic-price="savings"]').forEach(function(el) {
        el.textContent = '$' + savings;
      });

      // Auto-replace "$14.99/month" text in pricing-visible elements
      document.querySelectorAll('.pricing-price, .pricing-note, .dynamic-price-text, .upgrade-plan-price').forEach(function(el) {
        if (el.innerHTML.indexOf('14.99') !== -1) {
          el.innerHTML = el.innerHTML.replace(/14\.99/g, monthly);
        }
        if (el.innerHTML.indexOf('$149') !== -1 && el.innerHTML.indexOf('149/year') !== -1) {
          el.innerHTML = el.innerHTML.replace(/\$149/g, '$' + annualPrice);
        }
      });
    })
    .catch(function() { /* silently fail — default prices shown */ });
})();
