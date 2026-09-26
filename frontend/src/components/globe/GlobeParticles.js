import * as THREE from 'three';
import { fibonacciSphere, toLonLat } from './lib/math.js';

// Dots on the sphere: one BufferGeometry + one ShaderMaterial, drawn as a single THREE.Points.

const vertexShader = /* glsl */ `
#define MAX_HL __MAX_HL__
attribute float aLand;
attribute float aSeed;
uniform float uTime;
uniform float uSize;
uniform float uPixelRatio;
uniform float uCameraDistance;
uniform vec3 uPointer;
uniform float uPointerStrength;
uniform float uInteractionRadius;
uniform float uGlow;
uniform vec4 uHighlights[MAX_HL];
uniform float uHighlightRadius;
uniform vec3 uLandA;
uniform vec3 uLandB;
uniform vec3 uOcean;
uniform vec3 uRim;
uniform vec3 uHot;
varying vec3 vColor;
varying float vAlpha;

void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vec3 n = normalize(world.xyz);
    vec3 viewDir = normalize(cameraPosition - world.xyz);
    float facing = clamp(dot(n, viewDir), 0.0, 1.0);
    float rim = pow(1.0 - facing, 2.6);

    vec3 p = normalize(position);
    float dp = distance(p, uPointer);
    float glow = uPointerStrength * exp(-(dp * dp) / (uInteractionRadius * uInteractionRadius));
    for (int i = 0; i < MAX_HL; i++) {
        vec4 h = uHighlights[i];
        if (h.w > 0.001) {
            float d = distance(p, h.xyz);
            glow += h.w * exp(-(d * d) / (uHighlightRadius * uHighlightRadius));
        }
    }
    glow = min(glow, 1.4) * uGlow;

    float twinkle = 0.9 + 0.1 * sin(uTime * (0.35 + aSeed) + aSeed * 40.0);
    vec3 base = mix(uOcean, mix(uLandA, uLandB, aSeed), aLand);
    base = mix(base, uRim, rim * 0.8);
    vColor = mix(base, uHot, clamp(glow, 0.0, 1.0));

    float depth = 0.3 + 0.7 * smoothstep(0.0, 0.55, facing);
    float baseAlpha = mix(0.2, 1.0, aLand) * (0.7 + 0.3 * aSeed) * twinkle;
    vAlpha = baseAlpha * depth + rim * 0.4 * aLand + glow * 0.55;

    vec4 mv = viewMatrix * world;
    float size = uSize * mix(0.72, 1.0, aLand) * (1.0 + 0.5 * glow);
    gl_PointSize = size * uPixelRatio * (uCameraDistance / -mv.z);
    gl_Position = projectionMatrix * mv;
}
`;

const fragmentShader = /* glsl */ `
varying vec3 vColor;
varying float vAlpha;
void main() {
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5) discard;
    float a = pow(smoothstep(0.5, 0.05, d), 1.3);
    gl_FragColor = vec4(vColor, vAlpha * a);
}
`;

/**
 * Build the dot field.
 * Returns { points, positions (unit xyz, Float32Array), landIndices (Uint32Array), uniforms, dispose }.
 */
export function createGlobeParticles({ isLand, config, maxHighlights }) {
    const candidates = fibonacciSphere(config.particleCount);
    const count = config.particleCount;
    const positions = new Float32Array(count * 3);
    const land = new Float32Array(count);
    const seed = new Float32Array(count);
    const landList = [];
    let n = 0;
    for (let i = 0; i < count; i++) {
        const x = candidates[i * 3], y = candidates[i * 3 + 1], z = candidates[i * 3 + 2];
        const [lon, lat] = toLonLat(x, y, z);
        const onLand = isLand(lon, lat);
        if (!onLand && Math.random() > config.oceanDotRatio) continue;
        positions[n * 3] = x * config.radius;
        positions[n * 3 + 1] = y * config.radius;
        positions[n * 3 + 2] = z * config.radius;
        land[n] = onLand ? 1 : 0;
        seed[n] = Math.random();
        if (onLand) landList.push(n);
        n++;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions.subarray(0, n * 3), 3));
    geometry.setAttribute('aLand', new THREE.BufferAttribute(land.subarray(0, n), 1));
    geometry.setAttribute('aSeed', new THREE.BufferAttribute(seed.subarray(0, n), 1));
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), config.radius);

    const c = config.colors;
    const uniforms = {
        uTime: { value: 0 },
        uSize: { value: config.particleSize },
        uPixelRatio: { value: 1 },
        uCameraDistance: { value: 4 },
        uPointer: { value: new THREE.Vector3(0, 0, 10) },
        uPointerStrength: { value: 0 },
        uInteractionRadius: { value: config.interactionRadius },
        uGlow: { value: config.glowIntensity },
        uHighlights: { value: Array.from({ length: maxHighlights }, () => new THREE.Vector4(0, 0, 0, 0)) },
        uHighlightRadius: { value: 0.045 },
        uLandA: { value: new THREE.Color(c.landA) },
        uLandB: { value: new THREE.Color(c.landB) },
        uOcean: { value: new THREE.Color(c.ocean) },
        uRim: { value: new THREE.Color(c.rim) },
        uHot: { value: new THREE.Color(c.hot) },
    };
    const material = new THREE.ShaderMaterial({
        uniforms,
        vertexShader: vertexShader.replace('__MAX_HL__', String(maxHighlights)),
        fragmentShader,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
    });

    const points = new THREE.Points(geometry, material);
    // Unit-sphere copy used by the connection system (index-aligned with the geometry).
    const unit = new Float32Array(n * 3);
    for (let i = 0; i < n * 3; i++) unit[i] = positions[i] / config.radius;

    return {
        points,
        positions: unit,
        landIndices: Uint32Array.from(landList),
        uniforms,
        dispose() {
            geometry.dispose();
            material.dispose();
        },
    };
}

const bodyVertex = /* glsl */ `
varying vec3 vNormal;
varying vec3 vView;
void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vView = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
}
`;

const bodyFragment = /* glsl */ `
uniform vec3 uCore;
uniform vec3 uEdge;
varying vec3 vNormal;
varying vec3 vView;
void main() {
    float f = 1.0 - max(dot(normalize(vNormal), normalize(vView)), 0.0);
    gl_FragColor = vec4(mix(uCore, uEdge, pow(f, 3.0) * 0.55), 1.0);
}
`;

const atmosphereFragment = /* glsl */ `
uniform vec3 uColor;
uniform float uStrength;
varying vec3 vNormal;
varying vec3 vView;
void main() {
    // Back faces of a slightly larger shell: -dot(n, v) is 0 at the shell's silhouette and grows
    // towards the globe's limb, so the halo fades outwards from the edge of the globe.
    float d = clamp(-dot(normalize(vNormal), normalize(vView)) / 0.55, 0.0, 1.0);
    gl_FragColor = vec4(uColor, pow(d, 2.6) * uStrength);
}
`;

/** Dark opaque globe body (also hides dots and trails on the far side) plus a faint rim halo. */
export function createGlobeBody(config) {
    const c = config.colors;
    const bodyGeometry = new THREE.SphereGeometry(config.radius * 0.985, 64, 48);
    const bodyMaterial = new THREE.ShaderMaterial({
        uniforms: { uCore: { value: new THREE.Color(c.core) }, uEdge: { value: new THREE.Color(c.coreEdge) } },
        vertexShader: bodyVertex,
        fragmentShader: bodyFragment,
    });
    const body = new THREE.Mesh(bodyGeometry, bodyMaterial);
    body.renderOrder = -1;

    const haloGeometry = new THREE.SphereGeometry(config.radius * 1.16, 64, 48);
    const haloMaterial = new THREE.ShaderMaterial({
        uniforms: { uColor: { value: new THREE.Color(c.atmosphere) }, uStrength: { value: 0.32 * config.glowIntensity } },
        vertexShader: bodyVertex,
        fragmentShader: atmosphereFragment,
        side: THREE.BackSide,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
    });
    const halo = new THREE.Mesh(haloGeometry, haloMaterial);

    return {
        body,
        halo,
        dispose() {
            bodyGeometry.dispose();
            bodyMaterial.dispose();
            haloGeometry.dispose();
            haloMaterial.dispose();
        },
    };
}
