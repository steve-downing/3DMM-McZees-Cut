// Subtle procedural surface texture for the cartoon cabin. Each face's kind
// rides in its vertex color alpha: 0 plain, 1 fabric, 2 carpet, 3 wood, 4 metal.
// Patterns are triplanar in object space (every seat copy matches) and fade
// out where they'd be smaller than a pixel.
export function addSurfaceTexture(material) {
  material.onBeforeCompile = shader => {
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vOPos;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvOPos = position;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
varying vec3 vOPos;
float sh_hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float sh_noise(vec2 p) {
  vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(sh_hash(i), sh_hash(i + vec2(1.0, 0.0)), f.x), mix(sh_hash(i + vec2(0.0, 1.0)), sh_hash(i + vec2(1.0, 1.0)), f.x), f.y);
}
float sh_fbm(vec2 p) { float v = 0.0, a = 0.5; for (int i = 0; i < 3; i++) { v += a * sh_noise(p); p *= 2.03; a *= 0.5; } return v; }
float sh_aa(vec2 p, float freq) { return clamp(1.0 - length(fwidth(p)) * freq * 0.35, 0.0, 1.0); }
// across = coordinate that changes across the grain/weave, along = along it
float sh_surf(vec2 p, float across, float along, float kind) {
  if (kind < 0.5) return 1.0 + 0.21 * (sh_fbm(p * 0.8) - 0.5) + 0.13 * (sh_noise(p * 10.0) - 0.5) * sh_aa(p, 10.0);
  if (kind < 1.5) {
    float w = sin(p.x * 26.0) * sin(p.y * 26.0);
    return 1.0 + 0.31 * w * sh_aa(p, 26.0) + 0.25 * (sh_fbm(p * 2.5) - 0.5);
  }
  if (kind < 2.5) return 1.0 + 0.42 * (sh_noise(p * 3.2) - 0.5) * sh_aa(p, 3.2) + 0.34 * (sh_fbm(p * 0.55) - 0.5);
  if (kind < 3.5) {
    float g = sh_fbm(vec2(along * 0.45, across * 5.0));
    return 1.0 + 0.21 * sin(across * 10.0 + g * 6.0) * sh_aa(vec2(across), 10.0) + 0.17 * (g - 0.5);
  }
  if (kind < 4.5) return 1.0 + 0.21 * (sh_noise(vec2(along * 1.5, across * 60.0)) - 0.5) * sh_aa(vec2(across), 60.0);
  // hammered metal (the door): big soft dents plus fine speckle
  return 1.0 + 0.3 * (sh_fbm(p * 1.4) - 0.5) + 0.2 * (sh_noise(p * 7.0) - 0.5) * sh_aa(p, 7.0) + 0.1 * (sh_noise(p * 18.0) - 0.5) * sh_aa(p, 18.0);
}`)
      .replace('#include <color_fragment>', `#include <color_fragment>
{
  vec3 fn = normalize(cross(dFdx(vOPos), dFdy(vOPos)));
  vec3 bw = pow(abs(fn), vec3(4.0)); bw /= (bw.x + bw.y + bw.z + 1e-5);
#ifdef USE_COLOR_ALPHA
  float kind = floor(vColor.a * 255.0 / 32.0 + 0.01);
#else
  float kind = 0.0;
#endif
  vec3 p = vOPos;
  // wood grain runs along z (armrests, tables); on z-facing ends, along x
  // flat faces mostly face one axis: skip projections that barely contribute
  float t = 0.0;
  if (bw.x > 0.02) t += sh_surf(p.zy, p.y, p.z, kind) * bw.x;
  if (bw.y > 0.02) t += sh_surf(p.xz, p.x, p.z, kind) * bw.y;
  if (bw.z > 0.02) t += sh_surf(p.xy, p.y, p.x, kind) * bw.z;
  t /= max(bw.x * step(0.02, bw.x) + bw.y * step(0.02, bw.y) + bw.z * step(0.02, bw.z), 1e-3);
  diffuseColor.rgb *= t;
  diffuseColor.a = 1.0;
}`);
  };
  material.customProgramCacheKey = () => 'surface-texture-v6';
  return material;
}

// What you see through the windows: a lavender sky over a deck of clouds,
// looked up by view direction so it sits infinitely far away (no parallax
// error in a headset). Unlit, and written straight to the screen.
export function makeSky(THREE) {
  // a big sphere around everything, drawn first and never in front of anything: the
  // windows are real openings, so whatever flies past outside shows against it
  const m = makeSkyMaterial(THREE); m.side = THREE.BackSide; m.depthWrite = false;
  const sky = new THREE.Mesh(new THREE.SphereGeometry(300, 32, 16), m);
  sky.renderOrder = -1; sky.frustumCulled = false;
  return sky;
}

export function makeSkyMaterial(THREE) {
  return new THREE.ShaderMaterial({
    side: THREE.DoubleSide, toneMapped: false,
    vertexShader: `varying vec3 vWorld;
      void main() { vec4 w = modelMatrix * vec4(position, 1.0); vWorld = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`,
    fragmentShader: `varying vec3 vWorld;
      float h3(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
      float vn(vec3 x) { vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
        return mix(mix(mix(h3(i), h3(i + vec3(1,0,0)), f.x), mix(h3(i + vec3(0,1,0)), h3(i + vec3(1,1,0)), f.x), f.y),
                   mix(mix(h3(i + vec3(0,0,1)), h3(i + vec3(1,0,1)), f.x), mix(h3(i + vec3(0,1,1)), h3(i + vec3(1,1,1)), f.x), f.y), f.z); }
      float fbm(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vn(p); p = p * 2.03 + 17.1; a *= 0.5; } return s; }
      void main() {
        vec3 d = normalize(vWorld - cameraPosition);
        vec3 col = mix(vec3(0.80, 0.78, 0.99), vec3(0.52, 0.55, 0.93), smoothstep(-0.05, 0.6, d.y));
        // soft, diffuse cloud everywhere (like the original's mottled sky), denser toward and below the horizon
        float c1 = fbm(vec3(d.x * 2.2, d.y * 4.0, d.z * 2.2) + 4.0);
        float c2 = fbm(vec3(d.x * 7.0, d.y * 11.0, d.z * 7.0) + 9.0);
        float cov = c1 * 0.75 + c2 * 0.35 + 0.12 * (1.0 - smoothstep(-0.3, 0.5, d.y));
        // mostly white, mottled with violet at two scales
        float m = smoothstep(0.36, 0.66, cov);
        col = mix(vec3(0.52, 0.52, 0.92), vec3(0.86, 0.85, 0.99), 0.7 * smoothstep(0.2, 0.5, cov));
        col = mix(col, vec3(1.0, 0.99, 1.0), m * 0.7);
        gl_FragColor = vec4(col, 1.0);
      }`
  });
}
