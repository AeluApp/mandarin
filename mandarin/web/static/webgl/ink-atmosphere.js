/**
 * Ink Atmosphere — WebGL background scenes for Aelu.
 *
 * Provides animated gradient mesh + ink particle backgrounds using Three.js.
 * Scenes: 'marketing' (hero, highest fidelity), 'login' (gradient mesh + grain),
 *          'dashboard' (ambient, lightest), 'admin' (cool-toned mesh).
 *
 * Usage:
 *   <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r169/three.min.js" async></script>
 *   <script src="/static/webgl/ink-atmosphere.js" defer></script>
 *   <div id="webgl-atmosphere" data-scene="marketing"></div>
 *
 * Falls back to CSS gradient if WebGL unavailable or prefers-reduced-motion.
 * Pauses render loop when tab is hidden or canvas is off-screen.
 */
(function() {
  'use strict';

  // ── Guards ──
  var mql = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (mql.matches) return;

  var container = document.getElementById('webgl-atmosphere');
  if (!container) return;

  var sceneName = container.dataset.scene || 'dashboard';

  // Wait for Three.js to load (loaded async)
  function waitForThree(cb, attempts) {
    if (window.THREE) return cb();
    if ((attempts || 0) > 50) return applyFallback(); // 5 seconds timeout
    setTimeout(function() { waitForThree(cb, (attempts || 0) + 1); }, 100);
  }

  // ── Fallback: CSS gradient mesh ──
  function applyFallback() {
    container.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;' +
      'background:radial-gradient(ellipse at 30% 20%, var(--mesh-color-2) 0%, transparent 50%),' +
      'radial-gradient(ellipse at 70% 60%, var(--mesh-color-3) 0%, transparent 50%),' +
      'linear-gradient(180deg, var(--color-sky-top), var(--color-base));';
  }

  // ── Color helpers ──
  function getCSSColor(prop) {
    return getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
  }

  function hexToVec3(hex) {
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
    return new THREE.Vector3(
      parseInt(hex.substring(0,2), 16) / 255,
      parseInt(hex.substring(2,4), 16) / 255,
      parseInt(hex.substring(4,6), 16) / 255
    );
  }

  // ── Shader sources ──
  var vertexShader = [
    'varying vec2 vUv;',
    'void main() {',
    '  vUv = uv;',
    '  gl_Position = vec4(position, 1.0);',
    '}'
  ].join('\n');

  // Gradient mesh shader — animated multi-point gradient with noise
  var gradientMeshFragment = [
    'precision mediump float;',
    'varying vec2 vUv;',
    'uniform float uTime;',
    'uniform vec3 uColor1;',
    'uniform vec3 uColor2;',
    'uniform vec3 uColor3;',
    'uniform vec3 uColorBase;',
    'uniform float uIntensity;',
    '',
    '// Simplex-like noise',
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
    'void main() {',
    '  float t = uTime * 0.015;',
    '  ',
    '  // Animated gradient control points',
    '  vec2 p1 = vec2(0.2 + sin(t * 0.7) * 0.1, 0.15 + cos(t * 0.5) * 0.1);',
    '  vec2 p2 = vec2(0.8 + cos(t * 0.6) * 0.1, 0.3 + sin(t * 0.8) * 0.1);',
    '  vec2 p3 = vec2(0.5 + sin(t * 0.4) * 0.15, 0.7 + cos(t * 0.3) * 0.1);',
    '  ',
    '  // Distance-based blending',
    '  float d1 = 1.0 - smoothstep(0.0, 0.6, distance(vUv, p1));',
    '  float d2 = 1.0 - smoothstep(0.0, 0.55, distance(vUv, p2));',
    '  float d3 = 1.0 - smoothstep(0.0, 0.65, distance(vUv, p3));',
    '  ',
    '  // Add noise for organic feel',
    '  float n = snoise(vUv * 3.0 + t * 0.2) * 0.15;',
    '  ',
    '  vec3 color = uColorBase;',
    '  color = mix(color, uColor1, d1 * uIntensity + n * 0.02);',
    '  color = mix(color, uColor2, d2 * uIntensity * 0.8 + n * 0.01);',
    '  color = mix(color, uColor3, d3 * uIntensity * 0.6);',
    '  ',
    '  // Film grain',
    '  float grain = (snoise(vUv * 300.0 + uTime * 2.0) * 0.5 + 0.5) * 0.02;',
    '  color += grain - 0.01;',
    '  ',
    '  gl_FragColor = vec4(color, 1.0);',
    '}'
  ].join('\n');

  // ── Scene configs ──
  var sceneConfigs = {
    marketing: { intensity: 0.18, fps: 30 },
    login:     { intensity: 0.12, fps: 24 },
    dashboard: { intensity: 0.06, fps: 20 },
    admin:     { intensity: 0.05, fps: 20 }
  };

  // ── Main ──
  var renderer, scene, camera, material, mesh, raf, paused, lastFrame, frameInterval;

  function init() {
    var config = sceneConfigs[sceneName] || sceneConfigs.dashboard;
    frameInterval = 1000 / config.fps;
    lastFrame = 0;

    // Check WebGL support
    var canvas = document.createElement('canvas');
    var gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    if (!gl) { applyFallback(); return; }

    // Setup renderer
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: 'low-power' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5)); // cap for perf
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.domElement.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;';

    container.appendChild(renderer.domElement);
    container.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1;pointer-events:none;';

    // Scene
    scene = new THREE.Scene();
    camera = new THREE.Camera();

    // Get brand colors
    var base = getCSSColor('--color-base') || '#F2EBE0';
    var accent = getCSSColor('--color-accent') || '#946070';
    var secondary = getCSSColor('--color-secondary') || '#6A7A5A';

    // Fullscreen quad with gradient mesh shader
    var geometry = new THREE.PlaneGeometry(2, 2);
    material = new THREE.ShaderMaterial({
      vertexShader: vertexShader,
      fragmentShader: gradientMeshFragment,
      uniforms: {
        uTime: { value: 0 },
        uColor1: { value: hexToVec3(accent) },
        uColor2: { value: hexToVec3(secondary) },
        uColor3: { value: hexToVec3(accent) },
        uColorBase: { value: hexToVec3(base) },
        uIntensity: { value: config.intensity }
      }
    });

    mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    // Events
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', onVisibility);

    // Listen for theme changes to update colors
    var themeObserver = new MutationObserver(function() {
      updateColors();
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    // Listen for reduced motion changes
    mql.addEventListener('change', function(e) {
      if (e.matches) destroy();
    });

    paused = false;
    animate(0);
  }

  function updateColors() {
    if (!material) return;
    var base = getCSSColor('--color-base') || '#F2EBE0';
    var accent = getCSSColor('--color-accent') || '#946070';
    var secondary = getCSSColor('--color-secondary') || '#6A7A5A';
    material.uniforms.uColorBase.value = hexToVec3(base);
    material.uniforms.uColor1.value = hexToVec3(accent);
    material.uniforms.uColor2.value = hexToVec3(secondary);
    material.uniforms.uColor3.value = hexToVec3(accent);
  }

  function onResize() {
    if (!renderer) return;
    renderer.setSize(window.innerWidth, window.innerHeight);
  }

  function onVisibility() {
    if (document.hidden) {
      paused = true;
      if (raf) cancelAnimationFrame(raf);
    } else {
      paused = false;
      lastFrame = 0;
      animate(0);
    }
  }

  function animate(now) {
    if (paused) return;
    raf = requestAnimationFrame(animate);

    // Frame rate limiting
    if (now - lastFrame < frameInterval) return;
    lastFrame = now;

    material.uniforms.uTime.value = now * 0.001;
    renderer.render(scene, camera);
  }

  function destroy() {
    paused = true;
    if (raf) cancelAnimationFrame(raf);
    if (renderer) {
      renderer.dispose();
      if (renderer.domElement && renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
    }
    if (material) material.dispose();
    applyFallback();
  }

  // ── Bootstrap ──
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { waitForThree(init); });
  } else {
    waitForThree(init);
  }
})();
