import * as THREE from 'three';
import { chooseDestination, clamp01, easeInOutCubic, randRange, slerp, smoothstep } from './lib/math.js';

// Short-lived "data packets" travelling between surface dots along great-circle arcs.
// A fixed pool of trails is allocated once and reused; nothing is created per frame.

const SEGMENTS = 160;
export const HIGHLIGHTS_PER_CONNECTION = 3; // source, travelling head, destination

const trailVertex = /* glsl */ `
attribute float aT;
uniform float uHead;
uniform float uTail;
uniform float uOpacity;
uniform float uSize;
uniform float uPixelRatio;
uniform float uCameraDistance;
varying float vAlpha;
void main() {
    float visible = step(uTail, aT) * step(aT, uHead);
    float headness = smoothstep(uHead - 0.22, uHead, aT);
    vAlpha = visible * (0.12 + 0.88 * headness) * uOpacity;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = uSize * (0.55 + 0.75 * headness) * uPixelRatio * (uCameraDistance / -mv.z);
    gl_Position = projectionMatrix * mv;
}
`;

const trailFragment = /* glsl */ `
uniform vec3 uColor;
varying float vAlpha;
void main() {
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5 || vAlpha < 0.003) discard;
    gl_FragColor = vec4(uColor, vAlpha * smoothstep(0.5, 0.1, d));
}
`;

export class GlobeConnections {
    /**
     * @param {object} opts
     * @param {Float32Array} opts.positions unit xyz of every dot
     * @param {Uint32Array} opts.landIndices dots that may act as endpoints
     * @param {THREE.Vector4[]} opts.highlights shared uniform array written for the dot shader
     * @param {object} opts.config resolved globe config
     */
    constructor({ positions, landIndices, highlights, config, rng = Math.random }) {
        this.positions = positions;
        this.landIndices = landIndices;
        this.highlights = highlights;
        this.config = config;
        this.rng = rng;
        this.group = new THREE.Group();
        this.enabled = true;
        this.nextSpawn = 0.8;
        this.lastPair = null;
        this.recentSources = new Int32Array(6).fill(-1);
        this.recentCursor = 0;
        this._a = [0, 0, 0];
        this._b = [0, 0, 0];
        this._p = [0, 0, 0];

        this.slots = [];
        for (let s = 0; s < config.maxConnections; s++) {
            const geometry = new THREE.BufferGeometry();
            const pos = new Float32Array(SEGMENTS * 3);
            const t = new Float32Array(SEGMENTS);
            for (let i = 0; i < SEGMENTS; i++) t[i] = i / (SEGMENTS - 1);
            geometry.setAttribute('position', new THREE.BufferAttribute(pos, 3));
            geometry.setAttribute('aT', new THREE.BufferAttribute(t, 1));
            geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), config.radius * 1.2);
            const material = new THREE.ShaderMaterial({
                uniforms: {
                    uHead: { value: 0 },
                    uTail: { value: 0 },
                    uOpacity: { value: 0 },
                    uSize: { value: config.connectionThickness },
                    uPixelRatio: { value: 1 },
                    uCameraDistance: { value: 4 },
                    uColor: { value: new THREE.Color(config.connectionColors[0]) },
                },
                vertexShader: trailVertex,
                fragmentShader: trailFragment,
                transparent: true,
                depthWrite: false,
                blending: THREE.AdditiveBlending,
            });
            const trail = new THREE.Points(geometry, material);
            trail.visible = false;
            trail.frustumCulled = false;
            this.group.add(trail);
            this.slots.push({ trail, geometry, material, active: false, source: -1, destination: -1,
                startTime: 0, duration: 1, opacity: 1, intensity: 1, lift: 0 });
        }
    }

    setViewport(pixelRatio, cameraDistance) {
        for (const s of this.slots) {
            s.material.uniforms.uPixelRatio.value = pixelRatio;
            s.material.uniforms.uCameraDistance.value = cameraDistance;
        }
    }

    /**
     * Advance all connections.
     * @param {number} time seconds
     * @param {(i:number)=>boolean} isVisible whether dot i currently faces the camera
     * @param {()=>number} pointerSource returns a dot index near the pointer, or -1 (only called on spawn)
     */
    update(time, isVisible, pointerSource) {
        if (this.enabled && time >= this.nextSpawn) {
            const free = this.slots.find((s) => !s.active);
            if (free) this._spawn(free, time, isVisible, pointerSource());
            const interval = randRange(this.rng, this.config.connectionInterval);
            this.nextSpawn = time + interval / Math.max(0.05, this.config.connectionFrequency);
        }

        for (let s = 0; s < this.slots.length; s++) {
            const slot = this.slots[s];
            const base = s * HIGHLIGHTS_PER_CONNECTION;
            if (!slot.active) {
                for (let k = 0; k < HIGHLIGHTS_PER_CONNECTION; k++) this.highlights[base + k].w = 0;
                continue;
            }
            const u = (time - slot.startTime) / slot.duration;
            if (u >= 1) {
                slot.active = false;
                slot.trail.visible = false;
                for (let k = 0; k < HIGHLIGHTS_PER_CONNECTION; k++) this.highlights[base + k].w = 0;
                continue;
            }
            // 1 source emphasised -> 2-3 trail emerges and travels -> 4 destination pulse
            // -> 5 trail retracts into the globe -> 6 dots settle back.
            const head = easeInOutCubic(clamp01((u - 0.1) / 0.5));
            const tail = easeInOutCubic(clamp01((u - 0.6) / 0.33));
            const fade = 1 - smoothstep(0.9, 1, u);
            const uni = slot.material.uniforms;
            uni.uHead.value = head;
            uni.uTail.value = tail;
            uni.uOpacity.value = slot.opacity * fade;

            const i = slot.intensity;
            const src = this.highlights[base];
            this._copyPoint(slot.source, src);
            src.w = 0.75 * i * smoothstep(0, 0.12, u) * (1 - smoothstep(0.5, 0.85, u));

            const mid = this.highlights[base + 1];
            this._pointAt(slot, head, mid);
            mid.w = 0.45 * i * smoothstep(0.1, 0.16, u) * (1 - smoothstep(0.55, 0.62, u));

            const dst = this.highlights[base + 2];
            this._copyPoint(slot.destination, dst);
            dst.w = 0.95 * i * smoothstep(0.52, 0.6, u) * (1 - smoothstep(0.64, 0.95, u));
        }
    }

    _spawn(slot, time, isVisible, pointerSource) {
        const land = this.landIndices;
        if (land.length < 2) return;
        let source = pointerSource;
        if (source < 0 || this._recent(source)) {
            source = -1;
            for (let k = 0; k < 40 && source < 0; k++) {
                const idx = land[Math.floor(this.rng() * land.length)];
                if (isVisible(idx) && !this._recent(idx)) source = idx;
            }
            if (source < 0) source = land[Math.floor(this.rng() * land.length)];
        }
        const destination = chooseDestination({
            points: this.positions, candidates: land, source, rng: this.rng,
            minAngle: 0.22, maxAngle: randRange(this.rng, [0.6, 1.35]), isVisible, avoidPair: this.lastPair,
        });
        if (destination < 0) return;

        this.lastPair = [source, destination];
        this.recentSources[this.recentCursor] = source;
        this.recentCursor = (this.recentCursor + 1) % this.recentSources.length;

        const cfg = this.config;
        slot.source = source;
        slot.destination = destination;
        slot.startTime = time;
        slot.duration = randRange(this.rng, cfg.connectionDuration);
        slot.opacity = randRange(this.rng, cfg.connectionOpacity);
        slot.intensity = 0.7 + 0.3 * this.rng();
        slot.lift = 0.01 + 0.03 * this.rng();
        slot.material.uniforms.uColor.value.set(cfg.connectionColors[Math.floor(this.rng() * cfg.connectionColors.length)]);

        const pos = slot.geometry.attributes.position.array;
        this._load(source, this._a);
        this._load(destination, this._b);
        for (let k = 0; k < SEGMENTS; k++) {
            const t = k / (SEGMENTS - 1);
            slerp(this._a, this._b, t, this._p);
            // Hug the surface: a whisker above the dots, never a straight chord through space.
            const r = cfg.radius * (1.012 + slot.lift * Math.sin(Math.PI * t));
            pos[k * 3] = this._p[0] * r;
            pos[k * 3 + 1] = this._p[1] * r;
            pos[k * 3 + 2] = this._p[2] * r;
        }
        slot.geometry.attributes.position.needsUpdate = true;
        slot.material.uniforms.uHead.value = 0;
        slot.material.uniforms.uTail.value = 0;
        slot.trail.visible = true;
        slot.active = true;
    }

    _recent(idx) {
        for (let k = 0; k < this.recentSources.length; k++) if (this.recentSources[k] === idx) return true;
        return false;
    }

    _load(idx, out) {
        out[0] = this.positions[idx * 3];
        out[1] = this.positions[idx * 3 + 1];
        out[2] = this.positions[idx * 3 + 2];
    }

    _copyPoint(idx, v) {
        v.x = this.positions[idx * 3];
        v.y = this.positions[idx * 3 + 1];
        v.z = this.positions[idx * 3 + 2];
    }

    _pointAt(slot, t, v) {
        this._load(slot.source, this._a);
        this._load(slot.destination, this._b);
        slerp(this._a, this._b, t, this._p);
        v.x = this._p[0];
        v.y = this._p[1];
        v.z = this._p[2];
    }

    dispose() {
        for (const s of this.slots) {
            s.geometry.dispose();
            s.material.dispose();
        }
    }
}
