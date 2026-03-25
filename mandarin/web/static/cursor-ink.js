/**
 * Cursor Ink — custom cursor and ink trail system for Aelu.
 *
 * Replaces the default cursor on marketing pages with:
 * - Small ink dot cursor (12px) that follows the mouse
 * - Trailing ink particles in brand colors
 * - Click triggers ink splash (reuses InkBloom pattern)
 * - On touch devices: disabled cursor trail, touch ripple instead
 *
 * Integrates with AeluScene for cursor position pipeline.
 * Respects prefers-reduced-motion.
 *
 * Usage:
 *   <body data-cursor-ink>
 *   <script src="/static/cursor-ink.js" defer></script>
 *
 *   // Or programmatic:
 *   AeluCursor.enable();
 *   AeluCursor.disable();
 */
(function() {
  'use strict';

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var isTouch = 'ontouchstart' in window;

  // ── Configuration ──
  var config = {
    dotSize: 12,
    trailCount: 20,
    trailLifespan: 600,       // ms
    trailMinSize: 2,
    trailMaxSize: 6,
    trailOpacity: 0.25,
    splashParticles: 12,
    splashRadius: 80,
    splashDuration: 500
  };

  // ── State ──
  var state = {
    enabled: false,
    canvas: null,
    ctx: null,
    dpr: 1,
    w: 0,
    h: 0,
    cursorX: -100,
    cursorY: -100,
    smoothX: -100,
    smoothY: -100,
    velocityX: 0,
    velocityY: 0,
    trail: [],
    splashes: [],
    raf: null,
    dotEl: null
  };

  // ── Colors (from brand) ──
  function getColors() {
    var accent = getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim() || '#946070';
    var secondary = getComputedStyle(document.documentElement).getPropertyValue('--color-secondary').trim() || '#6A7A5A';
    var text = getComputedStyle(document.documentElement).getPropertyValue('--color-text').trim() || '#2A3650';
    return { accent: accent, secondary: secondary, text: text };
  }

  function hexToRgb(hex) {
    hex = (hex || '').replace('#', '');
    if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
    return {
      r: parseInt(hex.substring(0, 2), 16) || 0,
      g: parseInt(hex.substring(2, 4), 16) || 0,
      b: parseInt(hex.substring(4, 6), 16) || 0
    };
  }

  // ── Enable ──
  function enable() {
    if (state.enabled || isTouch || reducedMotion) return;

    // Create canvas overlay
    state.canvas = document.createElement('canvas');
    state.canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9999;pointer-events:none;';
    state.canvas.setAttribute('aria-hidden', 'true');
    document.body.appendChild(state.canvas);

    state.ctx = state.canvas.getContext('2d');
    state.dpr = Math.min(window.devicePixelRatio || 1, 2);
    resize();

    // Create dot element (CSS for hover state changes)
    state.dotEl = document.createElement('div');
    state.dotEl.style.cssText = 'position:fixed;width:' + config.dotSize + 'px;height:' + config.dotSize + 'px;' +
      'border-radius:50%;background:var(--color-text, #2A3650);pointer-events:none;z-index:10000;' +
      'transform:translate(-50%,-50%);transition:width 0.2s,height 0.2s,background 0.2s;mix-blend-mode:multiply;';
    state.dotEl.setAttribute('aria-hidden', 'true');
    document.body.appendChild(state.dotEl);

    // Hide default cursor
    document.body.style.cursor = 'none';
    // Also hide on all interactive elements
    var style = document.createElement('style');
    style.id = 'cursor-ink-style';
    style.textContent = '[data-cursor-ink] * { cursor: none !important; }';
    document.head.appendChild(style);

    // Events
    document.addEventListener('mousemove', onMouseMove, { passive: true });
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mouseover', onMouseOver, { passive: true });
    document.addEventListener('mouseout', onMouseOut, { passive: true });
    window.addEventListener('resize', resize);

    state.enabled = true;
    state.smoothX = -100;
    state.smoothY = -100;
    animate();
  }

  // ── Disable ──
  function disable() {
    if (!state.enabled) return;

    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mousedown', onMouseDown);
    document.removeEventListener('mouseover', onMouseOver);
    document.removeEventListener('mouseout', onMouseOut);
    window.removeEventListener('resize', resize);

    if (state.raf) cancelAnimationFrame(state.raf);
    if (state.canvas && state.canvas.parentNode) state.canvas.parentNode.removeChild(state.canvas);
    if (state.dotEl && state.dotEl.parentNode) state.dotEl.parentNode.removeChild(state.dotEl);

    var style = document.getElementById('cursor-ink-style');
    if (style) style.parentNode.removeChild(style);

    document.body.style.cursor = '';
    state.enabled = false;
    state.trail = [];
    state.splashes = [];
  }

  // ── Event handlers ──
  function onMouseMove(e) {
    var prevX = state.cursorX;
    var prevY = state.cursorY;
    state.cursorX = e.clientX;
    state.cursorY = e.clientY;
    state.velocityX = e.clientX - prevX;
    state.velocityY = e.clientY - prevY;

    // Emit trail particle based on velocity
    var speed = Math.sqrt(state.velocityX * state.velocityX + state.velocityY * state.velocityY);
    if (speed > 2) {
      var colors = getColors();
      var colorArr = [colors.accent, colors.secondary];
      var c = hexToRgb(colorArr[Math.floor(Math.random() * colorArr.length)]);
      state.trail.push({
        x: e.clientX,
        y: e.clientY,
        born: performance.now(),
        size: config.trailMinSize + Math.min(speed * 0.15, config.trailMaxSize - config.trailMinSize),
        color: c
      });

      // Cap trail length
      if (state.trail.length > config.trailCount) {
        state.trail.shift();
      }
    }
  }

  function onMouseDown(e) {
    // Ink splash on click
    var colors = getColors();
    var c = hexToRgb(colors.accent);
    var now = performance.now();
    var particles = [];
    for (var i = 0; i < config.splashParticles; i++) {
      var angle = (Math.PI * 2 * i) / config.splashParticles + (Math.random() - 0.5) * 0.5;
      var speed = 1 + Math.random() * 3;
      particles.push({
        x: e.clientX,
        y: e.clientY,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        size: 2 + Math.random() * 3,
        color: c
      });
    }
    state.splashes.push({ born: now, particles: particles });
  }

  function onMouseOver(e) {
    // Expand dot on interactive elements
    var target = e.target;
    if (target && (target.tagName === 'A' || target.tagName === 'BUTTON' || target.closest('a, button, [data-magnetic], [data-press]'))) {
      if (state.dotEl) {
        state.dotEl.style.width = '24px';
        state.dotEl.style.height = '24px';
        state.dotEl.style.background = 'var(--color-accent, #946070)';
        state.dotEl.style.mixBlendMode = 'normal';
        state.dotEl.style.opacity = '0.3';
      }
    }
  }

  function onMouseOut(e) {
    var target = e.target;
    if (target && (target.tagName === 'A' || target.tagName === 'BUTTON' || target.closest('a, button, [data-magnetic], [data-press]'))) {
      if (state.dotEl) {
        state.dotEl.style.width = config.dotSize + 'px';
        state.dotEl.style.height = config.dotSize + 'px';
        state.dotEl.style.background = 'var(--color-text, #2A3650)';
        state.dotEl.style.mixBlendMode = 'multiply';
        state.dotEl.style.opacity = '1';
      }
    }
  }

  function resize() {
    state.w = window.innerWidth;
    state.h = window.innerHeight;
    if (state.canvas) {
      state.canvas.width = state.w * state.dpr;
      state.canvas.height = state.h * state.dpr;
      state.ctx.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
    }
  }

  // ── Render loop ──
  function animate() {
    if (!state.enabled) return;
    state.raf = requestAnimationFrame(animate);

    var now = performance.now();
    var ctx = state.ctx;

    // Smooth cursor position
    state.smoothX += (state.cursorX - state.smoothX) * 0.15;
    state.smoothY += (state.cursorY - state.smoothY) * 0.15;

    // Position dot element
    if (state.dotEl) {
      state.dotEl.style.left = state.smoothX + 'px';
      state.dotEl.style.top = state.smoothY + 'px';
    }

    // Clear canvas
    ctx.clearRect(0, 0, state.w, state.h);

    // Draw trail particles
    for (var i = state.trail.length - 1; i >= 0; i--) {
      var p = state.trail[i];
      var age = now - p.born;
      if (age > config.trailLifespan) {
        state.trail.splice(i, 1);
        continue;
      }
      var life = 1 - (age / config.trailLifespan);
      var alpha = config.trailOpacity * life * life; // ease-out fade
      var size = p.size * life;

      ctx.beginPath();
      ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + p.color.r + ',' + p.color.g + ',' + p.color.b + ',' + alpha + ')';
      ctx.fill();
    }

    // Draw splash particles
    for (var s = state.splashes.length - 1; s >= 0; s--) {
      var splash = state.splashes[s];
      var splashAge = now - splash.born;
      if (splashAge > config.splashDuration) {
        state.splashes.splice(s, 1);
        continue;
      }
      var splashLife = 1 - (splashAge / config.splashDuration);
      for (var j = 0; j < splash.particles.length; j++) {
        var sp = splash.particles[j];
        sp.x += sp.vx;
        sp.y += sp.vy;
        sp.vx *= 0.96; // decelerate
        sp.vy *= 0.96;
        var sa = splashLife * splashLife * 0.4;
        var ss = sp.size * splashLife;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, ss, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(' + sp.color.r + ',' + sp.color.g + ',' + sp.color.b + ',' + sa + ')';
        ctx.fill();
      }
    }
  }

  // ── Touch ripple (for mobile) ──
  function touchRipple(x, y) {
    if (reducedMotion) return;
    var colors = getColors();
    var c = hexToRgb(colors.accent);

    var canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9997;pointer-events:none;';
    canvas.setAttribute('aria-hidden', 'true');
    document.body.appendChild(canvas);

    var ctx = canvas.getContext('2d');
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    var start = performance.now();
    var duration = 400;
    var maxRadius = 60;

    function animateRipple(now) {
      var elapsed = now - start;
      var progress = Math.min(1, elapsed / duration);
      if (progress >= 1) {
        canvas.parentNode.removeChild(canvas);
        return;
      }

      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      var ease = 1 - Math.pow(1 - progress, 3);
      var radius = maxRadius * ease;
      var alpha = (1 - progress) * 0.15;

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(' + c.r + ',' + c.g + ',' + c.b + ',' + alpha + ')';
      ctx.lineWidth = 2;
      ctx.stroke();

      requestAnimationFrame(animateRipple);
    }
    requestAnimationFrame(animateRipple);
  }

  // ── Auto-init ──
  function autoInit() {
    if (document.body.hasAttribute('data-cursor-ink')) {
      enable();
    }

    // Touch ripple on mobile
    if (isTouch && !reducedMotion) {
      document.addEventListener('touchstart', function(e) {
        if (document.body.hasAttribute('data-cursor-ink')) {
          var touch = e.touches[0];
          if (touch) touchRipple(touch.clientX, touch.clientY);
        }
      }, { passive: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  // ── Expose ──
  window.AeluCursor = {
    enable: enable,
    disable: disable,
    touchRipple: touchRipple,
    isEnabled: function() { return state.enabled; }
  };
})();
