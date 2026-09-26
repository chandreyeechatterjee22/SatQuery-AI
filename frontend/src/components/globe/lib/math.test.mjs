import test from 'node:test';
import assert from 'node:assert/strict';
import {
    angleBetween, chooseDestination, damp, fibonacciSphere, fromLonLat, qualityTier, slerp, toLonLat,
    yawFacingLongitude,
} from './math.js';
import { GLOBE_CONFIG, resolveGlobeConfig } from '../globeConfig.js';

const norm = (v) => Math.hypot(v[0], v[1], v[2]);

test('fibonacciSphere returns n unit vectors covering both hemispheres', () => {
    const pts = fibonacciSphere(500);
    assert.equal(pts.length, 1500);
    let north = 0;
    for (let i = 0; i < 500; i++) {
        assert.ok(Math.abs(norm([pts[i * 3], pts[i * 3 + 1], pts[i * 3 + 2]]) - 1) < 1e-5);
        if (pts[i * 3 + 1] > 0) north++;
    }
    assert.equal(north, 250);
});

test('lon/lat round-trips', () => {
    for (const [lon, lat] of [[0, 0], [78, 21], [-120, -45], [179, 60]]) {
        const v = fromLonLat(lon, lat);
        const [lon2, lat2] = toLonLat(v[0], v[1], v[2]);
        assert.ok(Math.abs(lon - lon2) < 1e-9 && Math.abs(lat - lat2) < 1e-9);
    }
});

test('yawFacingLongitude turns that longitude towards +z', () => {
    const [x, , z] = fromLonLat(78, 0);
    const a = yawFacingLongitude(78);
    // three.js rotation.y: x' = x cos a + z sin a, z' = -x sin a + z cos a
    assert.ok(Math.abs(x * Math.cos(a) + z * Math.sin(a)) < 1e-9);
    assert.ok(Math.abs(-x * Math.sin(a) + z * Math.cos(a) - 1) < 1e-9);
});

test('slerp hits both endpoints and stays on the sphere (great-circle path)', () => {
    const a = fromLonLat(10, 20);
    const b = fromLonLat(80, -10);
    const out = [0, 0, 0];
    assert.deepEqual(slerp(a, b, 0, out).map((v) => +v.toFixed(9)), a.map((v) => +v.toFixed(9)));
    assert.deepEqual(slerp(a, b, 1, out).map((v) => +v.toFixed(9)), b.map((v) => +v.toFixed(9)));
    for (let t = 0; t <= 1; t += 0.1) assert.ok(Math.abs(norm(slerp(a, b, t, out)) - 1) < 1e-9);
    // identical endpoints do not produce NaN
    assert.ok(slerp(a, a, 0.5, out).every(Number.isFinite));
});

test('chooseDestination never returns the source and respects the angular range', () => {
    const points = fibonacciSphere(400);
    const candidates = Uint32Array.from({ length: 400 }, (_, i) => i);
    let seed = 1;
    const rng = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let k = 0; k < 200; k++) {
        const source = k % 400;
        const d = chooseDestination({ points, candidates, source, rng, minAngle: 0.3, maxAngle: 1.2 });
        assert.notEqual(d, source);
        const ang = angleBetween(points, source, d);
        assert.ok(ang >= 0.3 && ang <= 1.2, `angle ${ang}`);
    }
});

test('chooseDestination avoids repeating the last pair and handles tiny candidate sets', () => {
    const points = fibonacciSphere(3);
    const rng = () => 0; // always proposes candidates[0]
    assert.equal(chooseDestination({ points, candidates: [5], source: 5, rng }), -1);
    const d = chooseDestination({ points, candidates: Uint32Array.from([0, 1, 2]), source: 1, rng,
        minAngle: 0, maxAngle: 4, avoidPair: [1, 0] });
    assert.equal(d, 2);
});

test('damp converges without overshoot', () => {
    let v = 0;
    for (let i = 0; i < 200; i++) v = damp(v, 1, 5, 1 / 60);
    assert.ok(v > 0.99 && v <= 1);
});

test('quality tiers and resolved config scale particles and connections down on small screens', () => {
    assert.equal(qualityTier(360), 'small-mobile');
    assert.equal(qualityTier(600), 'mobile');
    assert.equal(qualityTier(900), 'tablet');
    assert.equal(qualityTier(1280), 'desktop');
    assert.equal(qualityTier(1920), 'large-desktop');
    assert.equal(qualityTier(1920, 2), 'tablet');
    const desk = resolveGlobeConfig({}, 1280, 8);
    const phone = resolveGlobeConfig({}, 360, 8);
    assert.equal(desk.particleCount, GLOBE_CONFIG.particleDensity);
    assert.ok(phone.particleCount < desk.particleCount);
    assert.ok(phone.maxConnections <= desk.maxConnections);
    assert.ok(phone.maxPixelRatio <= desk.maxPixelRatio);
    assert.equal(resolveGlobeConfig({ colors: { rim: '#000000' } }).colors.hot, GLOBE_CONFIG.colors.hot);
});
