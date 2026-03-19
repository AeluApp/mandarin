/**
 * Celebration effects — canvas-based celebrations for Aelu.
 * Paper lanterns rising (session complete), ink bloom (correct answer).
 * Uses 2D canvas (not WebGL) for lightweight overlay effects.
 * Respects prefers-reduced-motion.
 */
(function() {
  'use strict';

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function hexToRgb(hex) {
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
    return {
      r: parseInt(hex.substring(0, 2), 16),
      g: parseInt(hex.substring(2, 4), 16),
      b: parseInt(hex.substring(4, 6), 16)
    };
  }

  function getCSSColor(prop) {
    return getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
  }

  // ── Paper Lanterns — calm celebration for session complete ──
  // Soft glowing circles rise upward with physics (buoyancy + wind).
  // NOT confetti. Calm but celebratory. 2-second duration.
  function paperLanterns(options) {
    if (reducedMotion) return;
    options = options || {};

    var canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9998;pointer-events:none;';
    canvas.setAttribute('aria-hidden', 'true');
    document.body.appendChild(canvas);

    var ctx = canvas.getContext('2d');
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = window.innerWidth;
    var h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Lantern colors from mastery palette
    var colors = [
      getCSSColor('--color-mastery-durable') || '#4A6A4A',
      getCSSColor('--color-mastery-stable') || '#6A8A5A',
      getCSSColor('--color-mastery-stabilizing') || '#B8A050',
      getCSSColor('--color-accent') || '#946070'
    ];

    var count = options.count || 7;
    var lanterns = [];
    for (var i = 0; i < count; i++) {
      var c = hexToRgb(colors[i % colors.length]);
      lanterns.push({
        x: w * 0.2 + Math.random() * w * 0.6,
        y: h + 20 + Math.random() * 40,
        radius: 12 + Math.random() * 10,
        buoyancy: 1.5 + Math.random() * 1.0,
        wind: (Math.random() - 0.5) * 0.4,
        wobble: Math.random() * Math.PI * 2,
        wobbleSpeed: 0.02 + Math.random() * 0.02,
        color: c,
        opacity: 0.6 + Math.random() * 0.3,
        glowRadius: 30 + Math.random() * 20
      });
    }

    var startTime = performance.now();
    var duration = 2500; // 2.5 seconds

    function animate(now) {
      var elapsed = now - startTime;
      var progress = elapsed / duration;

      if (progress >= 1) {
        canvas.parentNode.removeChild(canvas);
        return;
      }

      ctx.clearRect(0, 0, w, h);

      for (var i = 0; i < lanterns.length; i++) {
        var l = lanterns[i];
        l.y -= l.buoyancy;
        l.x += l.wind + Math.sin(l.wobble) * 0.3;
        l.wobble += l.wobbleSpeed;

        // Fade in then out
        var fadeIn = Math.min(1, elapsed / 400);
        var fadeOut = progress > 0.6 ? 1 - (progress - 0.6) / 0.4 : 1;
        var alpha = l.opacity * fadeIn * fadeOut;

        // Glow
        var glow = ctx.createRadialGradient(l.x, l.y, 0, l.x, l.y, l.glowRadius);
        glow.addColorStop(0, 'rgba(' + l.color.r + ',' + l.color.g + ',' + l.color.b + ',' + (alpha * 0.3) + ')');
        glow.addColorStop(1, 'rgba(' + l.color.r + ',' + l.color.g + ',' + l.color.b + ',0)');
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(l.x, l.y, l.glowRadius, 0, Math.PI * 2);
        ctx.fill();

        // Core
        var core = ctx.createRadialGradient(l.x, l.y, 0, l.x, l.y, l.radius);
        core.addColorStop(0, 'rgba(' + l.color.r + ',' + l.color.g + ',' + l.color.b + ',' + alpha + ')');
        core.addColorStop(0.7, 'rgba(' + l.color.r + ',' + l.color.g + ',' + l.color.b + ',' + (alpha * 0.5) + ')');
        core.addColorStop(1, 'rgba(' + l.color.r + ',' + l.color.g + ',' + l.color.b + ',0)');
        ctx.fillStyle = core;
        ctx.beginPath();
        ctx.arc(l.x, l.y, l.radius, 0, Math.PI * 2);
        ctx.fill();
      }

      requestAnimationFrame(animate);
    }

    requestAnimationFrame(animate);
  }

  // ── Ink Bloom — radial ink wash expanding from a point ──
  // Used for correct answer feedback. 600ms duration.
  function inkBloom(originEl, options) {
    if (reducedMotion) return;
    options = options || {};

    var rect = originEl.getBoundingClientRect();
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;

    var canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9997;pointer-events:none;';
    canvas.setAttribute('aria-hidden', 'true');
    document.body.appendChild(canvas);

    var ctx = canvas.getContext('2d');
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = window.innerWidth;
    var h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    var color = hexToRgb(options.color || getCSSColor('--color-correct') || '#5A7A5A');
    var maxRadius = Math.max(w, h) * 0.3;
    var startTime = performance.now();
    var duration = options.duration || 600;

    function animate(now) {
      var elapsed = now - startTime;
      var progress = elapsed / duration;

      if (progress >= 1) {
        canvas.parentNode.removeChild(canvas);
        return;
      }

      ctx.clearRect(0, 0, w, h);

      // Ease-out expansion
      var ease = 1 - Math.pow(1 - progress, 3);
      var radius = maxRadius * ease;
      var opacity = (1 - progress) * 0.08; // very subtle

      var gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
      gradient.addColorStop(0, 'rgba(' + color.r + ',' + color.g + ',' + color.b + ',' + opacity + ')');
      gradient.addColorStop(0.5, 'rgba(' + color.r + ',' + color.g + ',' + color.b + ',' + (opacity * 0.5) + ')');
      gradient.addColorStop(1, 'rgba(' + color.r + ',' + color.g + ',' + color.b + ',0)');

      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fill();

      requestAnimationFrame(animate);
    }

    requestAnimationFrame(animate);
  }

  // ── Expose API ──
  window.AeluCelebrations = {
    paperLanterns: paperLanterns,
    inkBloom: inkBloom
  };
})();
