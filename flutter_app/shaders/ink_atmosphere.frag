#version 460 core

// Ink Atmosphere — animated gradient mesh for Flutter.
// Port of the web WebGL shader (ink-atmosphere.js).
// Uses the same simplex noise + 3-point gradient mesh approach.

#include <flutter/runtime_effect.glsl>

uniform float uTime;
uniform vec2 uSize;
uniform float uIntensity;
// Brand colors (passed as RGB 0-1)
uniform vec3 uColor1;     // accent (bougainvillea)
uniform vec3 uColor2;     // secondary (cypress)
uniform vec3 uColorBase;  // base (linen/indigo)

out vec4 fragColor;

// Simplex-like noise
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec3 permute(vec3 x) { return mod289(((x * 34.0) + 1.0) * x); }

float snoise(vec2 v) {
    const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
    vec2 i = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);
    vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod289(i);
    vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
    vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
    m = m * m;
    m = m * m;
    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;
    m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
    vec3 g;
    g.x = a0.x * x0.x + h.x * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
}

void main() {
    vec2 uv = FlutterFragCoord().xy / uSize;
    float t = uTime * 0.07;

    // Animated gradient control points
    vec2 p1 = vec2(0.2 + sin(t * 0.7) * 0.1, 0.15 + cos(t * 0.5) * 0.1);
    vec2 p2 = vec2(0.8 + cos(t * 0.6) * 0.1, 0.3 + sin(t * 0.8) * 0.1);
    vec2 p3 = vec2(0.5 + sin(t * 0.4) * 0.15, 0.7 + cos(t * 0.3) * 0.1);

    // Distance-based blending
    float d1 = 1.0 - smoothstep(0.0, 0.6, distance(uv, p1));
    float d2 = 1.0 - smoothstep(0.0, 0.55, distance(uv, p2));
    float d3 = 1.0 - smoothstep(0.0, 0.65, distance(uv, p3));

    // Organic noise
    float n = snoise(uv * 3.0 + t * 0.2) * 0.3;

    // Color mixing
    vec3 color = uColorBase;
    color = mix(color, uColor1, d1 * uIntensity + n * 0.02);
    color = mix(color, uColor2, d2 * uIntensity * 0.8 + n * 0.01);
    color = mix(color, uColor1, d3 * uIntensity * 0.6);

    // Film grain
    float grain = (snoise(uv * 300.0 + uTime * 2.0) * 0.5 + 0.5) * 0.02;
    color += grain - 0.01;

    fragColor = vec4(color, 1.0);
}
