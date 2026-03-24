/**
 * Ambient ink particles — subtle drifting particles behind content.
 * Creates a living, breathing background without competing with content.
 * Respects prefers-reduced-motion. Pauses when off-screen or hidden.
 */
(function() {
  'use strict';

  // Bail early if user prefers reduced motion
  var mql = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (mql.matches) return;

  var canvas, ctx, particles, raf, paused, dpr, w, h;
  var PARTICLE_COUNT = 50;
  var MOBILE_PARTICLE_COUNT = 25;
  var isMobile = window.innerWidth < 768;

  function getAccentColor() {
    var style = getComputedStyle(document.documentElement);
    return style.getPropertyValue('--color-accent').trim() || '#946070';
  }

  function getSecondaryColor() {
    var style = getComputedStyle(document.documentElement);
    return style.getPropertyValue('--color-secondary').trim() || '#6A7A5A';
  }

  function hexToRgb(hex) {
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
    var r = parseInt(hex.substring(0, 2), 16);
    var g = parseInt(hex.substring(2, 4), 16);
    var b = parseInt(hex.substring(4, 6), 16);
    return { r: r, g: g, b: b };
  }

  function getDividerColor() {
    var style = getComputedStyle(document.documentElement);
    return style.getPropertyValue('--color-divider').trim() || '#D8D0C4';
  }

  function createParticle() {
    var colors = [getAccentColor(), getSecondaryColor(), getDividerColor(), getAccentColor()];
    var color = hexToRgb(colors[Math.floor(Math.random() * colors.length)]);
    // Mixed sizes: 70% small (5-20px), 30% medium-large (25-60px)
    var isSmall = Math.random() < 0.7;
    var radius = isSmall ? (5 + Math.random() * 15) : (25 + Math.random() * 35);
    return {
      x: Math.random() * w,
      y: Math.random() * h,
      radius: radius,
      opacity: 0.04 + Math.random() * 0.10,
      vx: (Math.random() - 0.5) * 0.15,
      vy: (Math.random() - 0.5) * 0.1 - 0.02,  // slight upward drift
      color: color,
      phase: Math.random() * Math.PI * 2,
      phaseSpeed: 0.001 + Math.random() * 0.002,
      breathePhase: Math.random() * Math.PI * 2,
      breatheSpeed: 0.003 + Math.random() * 0.005
    };
  }

  function init() {
    canvas = document.createElement('canvas');
    canvas.id = 'ambient-particles';
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;';
    document.body.insertBefore(canvas, document.body.firstChild);

    ctx = canvas.getContext('2d');
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    resize();

    var count = isMobile ? MOBILE_PARTICLE_COUNT : PARTICLE_COUNT;
    particles = [];
    for (var i = 0; i < count; i++) {
      particles.push(createParticle());
    }

    paused = false;
    animate();

    window.addEventListener('resize', debounce(resize, 200));
    document.addEventListener('visibilitychange', onVisibility);

    // Listen for reduced motion changes
    mql.addEventListener('change', function(e) {
      if (e.matches) {
        destroy();
      }
    });
  }

  function resize() {
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function onVisibility() {
    if (document.hidden) {
      paused = true;
      if (raf) cancelAnimationFrame(raf);
    } else {
      paused = false;
      animate();
    }
  }

  function animate() {
    if (paused) return;
    ctx.clearRect(0, 0, w, h);

    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      // Gentle sinusoidal drift
      p.phase += p.phaseSpeed;
      p.breathePhase += p.breatheSpeed;
      p.x += p.vx + Math.sin(p.phase) * 0.05;
      p.y += p.vy;

      // Wrap around edges
      if (p.x < -p.radius) p.x = w + p.radius;
      if (p.x > w + p.radius) p.x = -p.radius;
      if (p.y < -p.radius) p.y = h + p.radius;
      if (p.y > h + p.radius) p.y = -p.radius;

      // Breathing opacity — particles pulse gently
      var breathe = 0.7 + Math.sin(p.breathePhase) * 0.3;
      var curOpacity = p.opacity * breathe;

      // Draw soft circle
      var gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.radius);
      gradient.addColorStop(0, 'rgba(' + p.color.r + ',' + p.color.g + ',' + p.color.b + ',' + curOpacity + ')');
      gradient.addColorStop(1, 'rgba(' + p.color.r + ',' + p.color.g + ',' + p.color.b + ',0)');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fill();
    }

    raf = requestAnimationFrame(animate);
  }

  function destroy() {
    paused = true;
    if (raf) cancelAnimationFrame(raf);
    if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
  }

  function debounce(fn, ms) {
    var timer;
    return function() {
      clearTimeout(timer);
      timer = setTimeout(fn, ms);
    };
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
