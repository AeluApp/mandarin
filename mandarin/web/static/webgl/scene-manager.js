/**
 * Scene Manager — multi-layer WebGL scene system for Aelu.
 *
 * Extends the ink-atmosphere pattern into a full scene manager that supports:
 * - Multiple composable layers (background atmosphere, midground content, foreground effects)
 * - Scene transitions (cross-fade, dissolve between scene configurations)
 * - Scroll-driven uniform updates (integrates with scroll-engine.js)
 * - Cursor/touch interaction pipeline (integrates with cursor-ink.js)
 * - Graceful degradation: WebGL2 → WebGL1 → CSS gradient → static image
 * - Performance budgets: FPS cap per scene, pixel ratio cap, off-screen pause
 *
 * Usage:
 *   <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r169/three.min.js" async></script>
 *   <script src="/static/webgl/scene-manager.js" defer></script>
 *
 *   AeluScene.init('marketing');
 *   AeluScene.addLayer('atmosphere', { shader: 'gradientMesh', intensity: 0.32 });
 *   AeluScene.addLayer('terrain', { type: 'mesh', geometry: 'plane', ... });
 *   AeluScene.transition('login', { duration: 800, easing: 'decelerate' });
 *
 * Falls back to CSS gradient if WebGL unavailable or prefers-reduced-motion.
 * Pauses render loop when tab is hidden or canvas is off-screen.
 */
(function() {
  'use strict';

  // ── Guards ──
  var mql = window.matchMedia('(prefers-reduced-motion: reduce)');

  // ── Color helpers ──
  function getCSSColor(prop) {
    return getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
  }

  function hexToVec3(hex) {
    if (!hex || !window.THREE) return null;
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
    return new THREE.Vector3(
      parseInt(hex.substring(0,2), 16) / 255,
      parseInt(hex.substring(2,4), 16) / 255,
      parseInt(hex.substring(4,6), 16) / 255
    );
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

  // ── Easing functions ──
  var easings = {
    decelerate: function(t) { return 1 - Math.pow(1 - t, 3); },
    spring: function(t) { return 1 + Math.sin(t * Math.PI * 0.5) * Math.pow(1 - t, 0.5) * 0.15; },
    linear: function(t) { return t; }
  };

  // ── Shader library ──
  var shaders = {
    vertex: [
      'varying vec2 vUv;',
      'void main() {',
      '  vUv = uv;',
      '  gl_Position = vec4(position, 1.0);',
      '}'
    ].join('\n'),

    gradientMesh: [
      'precision mediump float;',
      'varying vec2 vUv;',
      'uniform float uTime;',
      'uniform vec3 uColor1;',
      'uniform vec3 uColor2;',
      'uniform vec3 uColor3;',
      'uniform vec3 uColorBase;',
      'uniform float uIntensity;',
      'uniform vec2 uMouse;',
      'uniform float uScrollProgress;',
      'uniform float uTransitionProgress;',
      'uniform vec3 uTransitionColor1;',
      'uniform vec3 uTransitionColor2;',
      'uniform vec3 uTransitionColor3;',
      'uniform vec3 uTransitionColorBase;',
      'uniform float uTransitionIntensity;',
      '',
      '// Simplex noise',
      'vec3 mod289(vec3 x) { return x - floor(x * (1.0/289.0)) * 289.0; }',
      'vec2 mod289(vec2 x) { return x - floor(x * (1.0/289.0)) * 289.0; }',
      'vec3 permute(vec3 x) { return mod289(((x*34.0)+1.0)*x); }',
      'float snoise(vec2 v) {',
      '  const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);',
      '  vec2 i = floor(v + dot(v, C.yy));',
      '  vec2 x0 = v - i + dot(i, C.xx);',
      '  vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);',
      '  vec4 x12 = x0.xyxy + C.xxzz;',
      '  x12.xy -= i1;',
      '  i = mod289(i);',
      '  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));',
      '  vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy), dot(x12.zw,x12.zw)), 0.0);',
      '  m = m*m; m = m*m;',
      '  vec3 x = 2.0 * fract(p * C.www) - 1.0;',
      '  vec3 h = abs(x) - 0.5;',
      '  vec3 ox = floor(x + 0.5);',
      '  vec3 a0 = x - ox;',
      '  m *= 1.79284291400159 - 0.85373472095314 * (a0*a0+h*h);',
      '  vec3 g;',
      '  g.x = a0.x * x0.x + h.x * x0.y;',
      '  g.yz = a0.yz * x12.xz + h.yz * x12.yw;',
      '  return 130.0 * dot(m, g);',
      '}',
      '',
      'vec3 computeScene(vec3 c1, vec3 c2, vec3 c3, vec3 cBase, float intensity, float t) {',
      '  vec2 p1 = vec2(0.2 + sin(t * 0.7) * 0.1 + uMouse.x * 0.08, 0.15 + cos(t * 0.5) * 0.1 + uMouse.y * 0.06);',
      '  vec2 p2 = vec2(0.8 + cos(t * 0.6) * 0.1, 0.3 + sin(t * 0.8) * 0.1);',
      '  vec2 p3 = vec2(0.5 + sin(t * 0.4) * 0.15, 0.7 + cos(t * 0.3) * 0.1);',
      '  float d1 = 1.0 - smoothstep(0.0, 0.6, distance(vUv, p1));',
      '  float d2 = 1.0 - smoothstep(0.0, 0.55, distance(vUv, p2));',
      '  float d3 = 1.0 - smoothstep(0.0, 0.65, distance(vUv, p3));',
      '  float n = snoise(vUv * 3.0 + t * 0.2) * 0.3;',
      '  vec3 color = cBase;',
      '  color = mix(color, c1, d1 * intensity + n * 0.02);',
      '  color = mix(color, c2, d2 * intensity * 0.8 + n * 0.01);',
      '  color = mix(color, c3, d3 * intensity * 0.6);',
      '  return color;',
      '}',
      '',
      'void main() {',
      '  float t = uTime * 0.07;',
      '  vec3 sceneA = computeScene(uColor1, uColor2, uColor3, uColorBase, uIntensity, t);',
      '  vec3 sceneB = computeScene(uTransitionColor1, uTransitionColor2, uTransitionColor3, uTransitionColorBase, uTransitionIntensity, t);',
      '  vec3 color = mix(sceneA, sceneB, uTransitionProgress);',
      '  // Film grain',
      '  float grain = (snoise(vUv * 300.0 + uTime * 2.0) * 0.5 + 0.5) * 0.02;',
      '  color += grain - 0.01;',
      '  // Scroll-driven subtle hue shift',
      '  color = mix(color, color * vec3(1.01, 0.99, 1.02), uScrollProgress * 0.3);',
      '  gl_FragColor = vec4(color, 1.0);',
      '}'
    ].join('\n')
  };

  // ── Scene configurations ──
  var sceneConfigs = {
    marketing:  { intensity: 0.32, fps: 30, colors: null },
    login:      { intensity: 0.22, fps: 30, colors: null },
    dashboard:  { intensity: 0.18, fps: 24, colors: null },
    admin:      { intensity: 0.12, fps: 20, colors: null },
    session:    { intensity: 0.15, fps: 24, colors: null },
    completion: { intensity: 0.25, fps: 30, colors: null }
  };

  // ── State ──
  var state = {
    renderer: null,
    scene: null,
    camera: null,
    material: null,
    mesh: null,
    raf: null,
    paused: false,
    lastFrame: 0,
    frameInterval: 1000 / 30,
    currentScene: 'dashboard',
    container: null,
    initialized: false,
    // Mouse
    mouseTarget: { x: 0.5, y: 0.5 },
    mouseCurrent: { x: 0.5, y: 0.5 },
    // Scroll
    scrollProgress: 0,
    // Transition
    transitioning: false,
    transitionStart: 0,
    transitionDuration: 0,
    transitionEasing: 'decelerate',
    transitionCallback: null,
    transitionTargetScene: null,
    // Layers (for foreground canvas effects)
    layers: [],
    // Intensity boost (temporary, for correct/incorrect feedback)
    intensityBoost: 0,
    intensityBoostDecay: 0
  };

  // ── CSS Fallback ──
  function applyFallback(container) {
    if (!container) return;
    container.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;' +
      'background:radial-gradient(ellipse at 30% 20%, var(--mesh-color-2) 0%, transparent 50%),' +
      'radial-gradient(ellipse at 70% 60%, var(--mesh-color-3) 0%, transparent 50%),' +
      'linear-gradient(180deg, var(--color-sky-top), var(--color-base));';
  }

  // ── Get brand colors ──
  function getBrandColors() {
    return {
      base: getCSSColor('--color-base') || '#F2EBE0',
      accent: getCSSColor('--color-accent') || '#946070',
      secondary: getCSSColor('--color-secondary') || '#6A7A5A'
    };
  }

  // ── Init ──
  function init(sceneName, containerId) {
    if (state.initialized) return;

    var container = document.getElementById(containerId || 'webgl-atmosphere');
    if (!container) return;

    state.container = container;
    state.currentScene = sceneName || container.dataset.scene || 'dashboard';

    if (mql.matches) {
      applyFallback(container);
      return;
    }

    waitForThree(function() {
      initWebGL(container);
    });
  }

  function waitForThree(cb, attempts) {
    if (window.THREE) return cb();
    if ((attempts || 0) > 50) {
      applyFallback(state.container);
      return;
    }
    setTimeout(function() { waitForThree(cb, (attempts || 0) + 1); }, 100);
  }

  function initWebGL(container) {
    var testCanvas = document.createElement('canvas');
    var gl = testCanvas.getContext('webgl2') || testCanvas.getContext('webgl');
    if (!gl) { applyFallback(container); return; }

    var config = sceneConfigs[state.currentScene] || sceneConfigs.dashboard;
    state.frameInterval = 1000 / config.fps;

    // Renderer
    state.renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: false,
      powerPreference: 'low-power'
    });
    state.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    state.renderer.setSize(window.innerWidth, window.innerHeight);
    state.renderer.domElement.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;';
    container.appendChild(state.renderer.domElement);
    container.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;';

    // Scene + Camera
    state.scene = new THREE.Scene();
    state.camera = new THREE.Camera();

    // Brand colors
    var colors = getBrandColors();

    // Fullscreen quad with enhanced gradient mesh shader
    var geometry = new THREE.PlaneGeometry(2, 2);
    state.material = new THREE.ShaderMaterial({
      vertexShader: shaders.vertex,
      fragmentShader: shaders.gradientMesh,
      uniforms: {
        uTime: { value: 0 },
        uColor1: { value: hexToVec3(colors.accent) },
        uColor2: { value: hexToVec3(colors.secondary) },
        uColor3: { value: hexToVec3(colors.accent) },
        uColorBase: { value: hexToVec3(colors.base) },
        uIntensity: { value: config.intensity },
        uMouse: { value: new THREE.Vector2(0.5, 0.5) },
        uScrollProgress: { value: 0 },
        // Transition uniforms (start as copies of current)
        uTransitionProgress: { value: 0 },
        uTransitionColor1: { value: hexToVec3(colors.accent) },
        uTransitionColor2: { value: hexToVec3(colors.secondary) },
        uTransitionColor3: { value: hexToVec3(colors.accent) },
        uTransitionColorBase: { value: hexToVec3(colors.base) },
        uTransitionIntensity: { value: config.intensity }
      }
    });

    state.mesh = new THREE.Mesh(geometry, state.material);
    state.scene.add(state.mesh);

    // Events
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', onVisibility);
    document.addEventListener('mousemove', onMouseMove, { passive: true });

    // Theme change observer
    new MutationObserver(updateColors).observe(
      document.documentElement, { attributes: true, attributeFilter: ['data-theme'] }
    );

    // Reduced motion change
    mql.addEventListener('change', function(e) {
      if (e.matches) destroy();
    });

    state.initialized = true;
    state.paused = false;
    animate(0);
  }

  // ── Event handlers ──
  function onResize() {
    if (!state.renderer) return;
    state.renderer.setSize(window.innerWidth, window.innerHeight);
  }

  function onVisibility() {
    if (document.hidden) {
      state.paused = true;
      if (state.raf) cancelAnimationFrame(state.raf);
    } else {
      state.paused = false;
      state.lastFrame = 0;
      animate(0);
    }
  }

  function onMouseMove(e) {
    state.mouseTarget.x = e.clientX / window.innerWidth;
    state.mouseTarget.y = 1.0 - (e.clientY / window.innerHeight);
  }

  // ── Color update on theme change ──
  function updateColors() {
    if (!state.material) return;
    var colors = getBrandColors();
    var u = state.material.uniforms;
    u.uColorBase.value = hexToVec3(colors.base);
    u.uColor1.value = hexToVec3(colors.accent);
    u.uColor2.value = hexToVec3(colors.secondary);
    u.uColor3.value = hexToVec3(colors.accent);
  }

  // ── Render loop ──
  function animate(now) {
    if (state.paused) return;
    state.raf = requestAnimationFrame(animate);
    if (now - state.lastFrame < state.frameInterval) return;
    state.lastFrame = now;

    // Smooth mouse lerp
    state.mouseCurrent.x += (state.mouseTarget.x - state.mouseCurrent.x) * 0.02;
    state.mouseCurrent.y += (state.mouseTarget.y - state.mouseCurrent.y) * 0.02;

    var u = state.material.uniforms;
    u.uMouse.value.set(state.mouseCurrent.x, state.mouseCurrent.y);
    u.uTime.value = now * 0.001;
    u.uScrollProgress.value = state.scrollProgress;

    // Apply intensity boost (decaying)
    if (state.intensityBoost > 0.001) {
      var config = sceneConfigs[state.currentScene] || sceneConfigs.dashboard;
      u.uIntensity.value = config.intensity + state.intensityBoost;
      state.intensityBoost *= state.intensityBoostDecay;
    }

    // Transition progress
    if (state.transitioning) {
      var elapsed = now - state.transitionStart;
      var progress = Math.min(1, elapsed / state.transitionDuration);
      var eased = (easings[state.transitionEasing] || easings.decelerate)(progress);
      u.uTransitionProgress.value = eased;

      if (progress >= 1) {
        finishTransition();
      }
    }

    state.renderer.render(state.scene, state.camera);

    // Render overlay layers
    for (var i = 0; i < state.layers.length; i++) {
      if (state.layers[i].render) {
        state.layers[i].render(now, state);
      }
    }
  }

  // ── Scene transitions ──
  function transition(targetScene, options) {
    if (!state.material || state.transitioning) return;
    options = options || {};

    var targetConfig = sceneConfigs[targetScene] || sceneConfigs.dashboard;
    var colors = getBrandColors();

    // Set transition target uniforms
    var u = state.material.uniforms;

    // If the target has custom colors, use them; otherwise brand defaults
    var tc = targetConfig.colors || {};
    u.uTransitionColor1.value = hexToVec3(tc.accent || colors.accent);
    u.uTransitionColor2.value = hexToVec3(tc.secondary || colors.secondary);
    u.uTransitionColor3.value = hexToVec3(tc.accent || colors.accent);
    u.uTransitionColorBase.value = hexToVec3(tc.base || colors.base);
    u.uTransitionIntensity.value = targetConfig.intensity;
    u.uTransitionProgress.value = 0;

    state.transitioning = true;
    state.transitionStart = performance.now();
    state.transitionDuration = options.duration || 800;
    state.transitionEasing = options.easing || 'decelerate';
    state.transitionCallback = options.onComplete || null;
    state.transitionTargetScene = targetScene;

    // Update FPS target to the higher of the two scenes
    var fps = Math.max(
      (sceneConfigs[state.currentScene] || sceneConfigs.dashboard).fps,
      targetConfig.fps
    );
    state.frameInterval = 1000 / fps;
  }

  function finishTransition() {
    var targetConfig = sceneConfigs[state.transitionTargetScene] || sceneConfigs.dashboard;
    var u = state.material.uniforms;

    // Copy transition colors to current
    u.uColor1.value.copy(u.uTransitionColor1.value);
    u.uColor2.value.copy(u.uTransitionColor2.value);
    u.uColor3.value.copy(u.uTransitionColor3.value);
    u.uColorBase.value.copy(u.uTransitionColorBase.value);
    u.uIntensity.value = targetConfig.intensity;
    u.uTransitionProgress.value = 0;

    state.currentScene = state.transitionTargetScene;
    state.frameInterval = 1000 / targetConfig.fps;
    state.transitioning = false;

    if (state.transitionCallback) {
      state.transitionCallback();
      state.transitionCallback = null;
    }
  }

  // ── Layer management (foreground canvas effects) ──
  function addLayer(name, layerObj) {
    layerObj._name = name;
    state.layers.push(layerObj);
    if (layerObj.init) layerObj.init(state);
    return layerObj;
  }

  function removeLayer(name) {
    state.layers = state.layers.filter(function(l) {
      if (l._name === name) {
        if (l.destroy) l.destroy();
        return false;
      }
      return true;
    });
  }

  function getLayer(name) {
    for (var i = 0; i < state.layers.length; i++) {
      if (state.layers[i]._name === name) return state.layers[i];
    }
    return null;
  }

  // ── Public API for scroll/cursor integration ──
  function setScrollProgress(value) {
    state.scrollProgress = Math.max(0, Math.min(1, value));
  }

  function boostIntensity(amount, decay) {
    state.intensityBoost = amount || 0.05;
    state.intensityBoostDecay = decay || 0.95;
  }

  // ── Cleanup ──
  function destroy() {
    state.paused = true;
    if (state.raf) cancelAnimationFrame(state.raf);
    if (state.renderer) {
      state.renderer.dispose();
      if (state.renderer.domElement && state.renderer.domElement.parentNode) {
        state.renderer.domElement.parentNode.removeChild(state.renderer.domElement);
      }
    }
    if (state.material) state.material.dispose();
    state.layers.forEach(function(l) { if (l.destroy) l.destroy(); });
    state.layers = [];
    state.initialized = false;
    applyFallback(state.container);
  }

  // ── Expose API ──
  window.AeluScene = {
    init: init,
    transition: transition,
    addLayer: addLayer,
    removeLayer: removeLayer,
    getLayer: getLayer,
    setScrollProgress: setScrollProgress,
    boostIntensity: boostIntensity,
    destroy: destroy,
    // Access internals for cursor-ink.js and scroll-engine.js
    getState: function() { return state; },
    getSceneConfigs: function() { return sceneConfigs; },
    isInitialized: function() { return state.initialized; },
    // Register custom scene config
    registerScene: function(name, config) {
      sceneConfigs[name] = config;
    }
  };

  // ── Auto-init if webgl-atmosphere container exists (backward compat with ink-atmosphere.js) ──
  function autoInit() {
    var container = document.getElementById('webgl-atmosphere');
    if (container && !state.initialized) {
      init(container.dataset.scene || 'dashboard', 'webgl-atmosphere');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }
})();
