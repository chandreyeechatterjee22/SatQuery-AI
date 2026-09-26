import * as THREE from 'three';
import { resolveGlobeConfig } from './globeConfig.js';
import { loadLandSampler } from './landMask.js';
import { createGlobeBody, createGlobeParticles } from './GlobeParticles.js';
import { GlobeConnections, HIGHLIGHTS_PER_CONNECTION } from './GlobeConnections.js';
import { GlobeInteraction } from './GlobeInteraction.js';
import { yawFacingLongitude } from './lib/math.js';

const FOV = 32;

function webglAvailable() {
    try {
        const c = document.createElement('canvas');
        return Boolean(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
    } catch {
        return false;
    }
}

/**
 * Mount the globe into `container`. Resolves to `{ dispose }`, or `null` when WebGL is unavailable.
 * All animation state lives here (not in React); nothing is allocated per frame.
 */
export async function createGlobe(container, overrides = {}) {
    if (!container || !webglAvailable()) return null;
    const isLand = await loadLandSampler();
    if (!container.isConnected) return null;

    const config = resolveGlobeConfig(overrides, window.innerWidth, navigator.hardwareConcurrency || 4);
    const reducedMotionQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    let reducedMotion = Boolean(reducedMotionQuery?.matches);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setClearColor(0x000000, 0);
    const canvas = renderer.domElement;
    canvas.style.display = 'block';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.touchAction = 'pan-y';   // vertical page scrolling keeps working on touch screens
    canvas.setAttribute('aria-hidden', 'true');
    container.appendChild(canvas);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 50);
    const globe = new THREE.Group();
    scene.add(globe);

    const maxHighlights = Math.max(1, config.maxConnections * HIGHLIGHTS_PER_CONNECTION);
    const particles = createGlobeParticles({ isLand, config, maxHighlights });
    const body = createGlobeBody(config);
    const connections = new GlobeConnections({
        positions: particles.positions,
        landIndices: particles.landIndices,
        highlights: particles.uniforms.uHighlights.value,
        config,
    });
    globe.add(body.body, particles.points, connections.group);
    scene.add(body.halo);

    const interaction = new GlobeInteraction(canvas, camera, config.radius);

    // --- sizing -----------------------------------------------------------------------------
    let cameraDistance = 4;
    const resize = () => {
        const w = Math.max(1, container.clientWidth);
        const h = Math.max(1, container.clientHeight);
        const pr = Math.min(window.devicePixelRatio || 1, config.maxPixelRatio);
        renderer.setPixelRatio(pr);
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        // Fit the globe's diameter to `scale` of the shorter side.
        const halfFov = THREE.MathUtils.degToRad(FOV / 2);
        const fitHeight = config.radius / (Math.tan(halfFov) * config.scale);
        cameraDistance = w < h ? fitHeight / camera.aspect : fitHeight;
        camera.position.set(0, 0, cameraDistance);
        camera.updateProjectionMatrix();
        // Dots scale gently with the rendered globe size.
        const sizeScale = THREE.MathUtils.clamp(Math.min(w, h) / 560, 0.7, 1.15);
        particles.uniforms.uPixelRatio.value = pr * sizeScale;
        particles.uniforms.uCameraDistance.value = cameraDistance - config.radius;
        connections.setViewport(pr * sizeScale, cameraDistance - config.radius);
    };
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);

    // --- visibility helpers (allocation free) -----------------------------------------------
    const rot = new THREE.Matrix3();
    const pos = particles.positions;
    const isVisible = (i) => {
        const e = rot.elements; // column-major; world z = row 2
        const z = e[2] * pos[i * 3] + e[5] * pos[i * 3 + 1] + e[8] * pos[i * 3 + 2];
        return z > 0.3;
    };
    const land = particles.landIndices;
    const pointerSource = () => {
        if (!interaction.onGlobe || interaction.strength < 0.5 || land.length === 0) return -1;
        const p = interaction.local;
        let best = -1;
        let bestDot = Math.cos(0.3);
        for (let k = 0; k < 160; k++) {
            const idx = land[Math.floor(Math.random() * land.length)];
            const d = pos[idx * 3] * p.x + pos[idx * 3 + 1] * p.y + pos[idx * 3 + 2] * p.z;
            if (d > bestDot) { bestDot = d; best = idx; }
        }
        return best;
    };

    // --- animation loop ---------------------------------------------------------------------
    let yaw = yawFacingLongitude(config.initialLongitude);
    let raf = 0;
    let running = false;
    let last = 0;
    let elapsed = 0;

    const frame = (now) => {
        raf = requestAnimationFrame(frame);
        const dt = Math.min(0.05, last ? (now - last) / 1000 : 0.016);
        last = now;
        elapsed += dt;

        if (!reducedMotion) yaw += config.rotationSpeed * dt;
        interaction.update(globe, dt, config.motionDamping);
        const influence = reducedMotion ? 0 : config.pointerInfluence;
        globe.rotation.set(config.axialTilt - interaction.influenceY * influence * 0.6, yaw + interaction.influenceX * influence, 0);
        globe.updateMatrixWorld();
        rot.setFromMatrix4(globe.matrixWorld);

        const u = particles.uniforms;
        u.uTime.value = reducedMotion ? 0 : elapsed;
        u.uPointer.value.copy(interaction.local);
        u.uPointerStrength.value = interaction.strength;

        connections.enabled = !reducedMotion;
        connections.update(elapsed, isVisible, pointerSource);

        renderer.render(scene, camera);
    };

    const start = () => {
        if (running) return;
        running = true;
        last = 0;
        raf = requestAnimationFrame(frame);
    };
    const stop = () => {
        running = false;
        cancelAnimationFrame(raf);
    };

    // Only animate while the globe is on screen (also pauses when its tab is hidden).
    const visibilityObserver = new IntersectionObserver(([entry]) => (entry.isIntersecting ? start() : stop()));
    visibilityObserver.observe(container);

    const onMotionChange = (e) => { reducedMotion = e.matches; };
    reducedMotionQuery?.addEventListener?.('change', onMotionChange);

    return {
        dispose() {
            stop();
            visibilityObserver.disconnect();
            resizeObserver.disconnect();
            reducedMotionQuery?.removeEventListener?.('change', onMotionChange);
            interaction.dispose();
            connections.dispose();
            particles.dispose();
            body.dispose();
            renderer.dispose();
            renderer.forceContextLoss();
            canvas.remove();
        },
    };
}
