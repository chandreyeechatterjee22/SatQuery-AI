// Pure math for the interactive globe. No three.js / DOM imports so it runs under `node --test`.
//
// Sphere convention (unit sphere, y up):
//   x = cos(lat) cos(lon),  y = sin(lat),  z = -cos(lat) sin(lon)

const DEG = Math.PI / 180;

/** Evenly spread `n` points on the unit sphere (Fibonacci lattice). Returns Float32Array(n * 3). */
export function fibonacciSphere(n) {
    const out = new Float32Array(n * 3);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i++) {
        const y = 1 - ((i + 0.5) / n) * 2;
        const r = Math.sqrt(1 - y * y);
        const theta = golden * i;
        out[i * 3] = Math.cos(theta) * r;
        out[i * 3 + 1] = y;
        out[i * 3 + 2] = Math.sin(theta) * r;
    }
    return out;
}

/** [lon, lat] in degrees for a unit vector. */
export function toLonLat(x, y, z) {
    const lat = Math.asin(Math.max(-1, Math.min(1, y))) / DEG;
    const lon = Math.atan2(-z, x) / DEG;
    return [lon, lat];
}

/** Unit vector for a longitude/latitude in degrees, written into `out` (length >= 3). */
export function fromLonLat(lon, lat, out = [0, 0, 0]) {
    const cl = Math.cos(lat * DEG);
    out[0] = cl * Math.cos(lon * DEG);
    out[1] = Math.sin(lat * DEG);
    out[2] = -cl * Math.sin(lon * DEG);
    return out;
}

/** Y-axis rotation that brings longitude `lon` (degrees) to face the camera on +z. */
export function yawFacingLongitude(lon) {
    return -Math.PI / 2 - lon * DEG;
}

/** Angle in radians between unit vectors stored at indices `i` and `j` of a flat xyz array. */
export function angleBetween(points, i, j) {
    const d = points[i * 3] * points[j * 3] + points[i * 3 + 1] * points[j * 3 + 1] + points[i * 3 + 2] * points[j * 3 + 2];
    return Math.acos(Math.max(-1, Math.min(1, d)));
}

/**
 * Spherical linear interpolation between unit vectors a and b (array-likes of length 3).
 * Writes into `out` and returns it; the result always lies on the unit sphere.
 */
export function slerp(a, b, t, out) {
    const dot = Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
    const omega = Math.acos(dot);
    if (omega < 1e-6) {
        out[0] = a[0]; out[1] = a[1]; out[2] = a[2];
        return out;
    }
    const s = Math.sin(omega);
    const wa = Math.sin((1 - t) * omega) / s;
    const wb = Math.sin(t * omega) / s;
    out[0] = wa * a[0] + wb * b[0];
    out[1] = wa * a[1] + wb * b[1];
    out[2] = wa * a[2] + wb * b[2];
    return out;
}

export const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

export function smoothstep(e0, e1, x) {
    const t = clamp01((x - e0) / (e1 - e0));
    return t * t * (3 - 2 * t);
}

export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/** Frame-rate independent exponential approach of `current` towards `target`. */
export function damp(current, target, lambda, dt) {
    return current + (target - current) * (1 - Math.exp(-lambda * dt));
}

export const randRange = (rng, [lo, hi]) => lo + (hi - lo) * rng();

/**
 * Pick a connection destination among `candidates` (indices into `points`).
 * Never returns `source`; prefers points for which `isVisible(index)` is true and whose angular
 * distance from the source lies in [minAngle, maxAngle]; avoids the pair in `avoidPair`
 * (either direction). Returns -1 only when no other candidate exists.
 */
export function chooseDestination({ points, candidates, source, rng, minAngle = 0.25, maxAngle = 1.3,
    isVisible = () => true, avoidPair = null, attempts = 48 }) {
    const n = candidates.length;
    if (n < 2) return -1;
    const blocked = (idx) => idx === source || (avoidPair
        && ((avoidPair[0] === source && avoidPair[1] === idx) || (avoidPair[1] === source && avoidPair[0] === idx)));

    // Pass 1: visible and in range. Pass 2: in range. Pass 3: anything but the source.
    for (let pass = 0; pass < 3; pass++) {
        for (let k = 0; k < attempts; k++) {
            const idx = candidates[Math.floor(rng() * n)];
            if (blocked(idx)) continue;
            if (pass < 2) {
                const ang = angleBetween(points, source, idx);
                if (ang < minAngle || ang > maxAngle) continue;
            }
            if (pass === 0 && !isVisible(idx)) continue;
            return idx;
        }
    }
    // Deterministic sweep: first without the avoided pair, then allowing it (still never the source).
    for (let k = 0; k < n; k++) if (!blocked(candidates[k])) return candidates[k];
    for (let k = 0; k < n; k++) if (candidates[k] !== source) return candidates[k];
    return -1;
}

/** Responsive quality tier from the viewport width (CSS px) and CPU core count. */
export function qualityTier(width, cores = 8) {
    let tier;
    if (width < 425) tier = 'small-mobile';
    else if (width < 768) tier = 'mobile';
    else if (width < 1024) tier = 'tablet';
    else if (width < 1440) tier = 'desktop';
    else tier = 'large-desktop';
    // Low-core machines get one step down from desktop quality.
    if (cores <= 2 && (tier === 'desktop' || tier === 'large-desktop')) tier = 'tablet';
    return tier;
}
