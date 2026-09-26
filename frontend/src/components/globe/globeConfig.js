import { qualityTier } from './lib/math.js';

/**
 * Tunables for the interactive globe. Pass a partial object as `config` to <InteractiveGlobe>
 * to override any of them.
 */
export const GLOBE_CONFIG = {
    // Geometry
    radius: 1,
    scale: 0.92,                 // fraction of the canvas the globe's diameter fills
    particleDensity: 110000,     // candidate dots on the sphere at desktop quality (~30% end up on land)
    oceanDotRatio: 0.14,         // share of ocean candidates kept as faint dots
    tabletParticleReduction: 0.7,
    mobileParticleReduction: 0.45,
    smallMobileParticleReduction: 0.32,

    // Motion
    rotationSpeed: 0.05,         // rad/s of automatic spin
    axialTilt: 0.3,              // rad, tips the northern hemisphere towards the viewer
    initialLongitude: 70,        // degrees; starts with India just left of centre
    pointerInfluence: 0.16,      // max orientation offset (rad) from the pointer
    motionDamping: 2.2,          // higher = orientation follows the pointer faster

    // Particles
    particleSize: 2.5,           // CSS px at the globe's front
    interactionRadius: 0.16,     // on the unit sphere
    glowIntensity: 1.0,

    // Network connections
    connectionFrequency: 1,      // multiplier on the spawn rate
    connectionInterval: [0.9, 2.8],
    connectionDuration: [2.6, 4.4],
    connectionThickness: 2.2,    // CSS px of the travelling trail
    connectionOpacity: [0.55, 0.9],
    connectionColors: ['#6cd3c3', '#8aa8ff', '#5cc39a'],
    maxConnections: 4,

    // Rendering
    maxPixelRatio: 2,
    colors: {
        landA: '#8ea2f0',        // indigo
        landB: '#bcd2ff',        // cool blue
        ocean: '#34457a',
        rim: '#5fd0bd',          // restrained cyan/green edge light
        hot: '#c9fff4',          // pointer / pulse highlight
        core: '#050a12',         // globe body
        coreEdge: '#003c33',     // deep enterprise green at the limb
        atmosphere: '#2f8f84',
    },
};

const TIER_SETTINGS = {
    'small-mobile': { density: 'smallMobileParticleReduction', connections: 0.5, maxConnections: 1, pixelRatio: 1.5, glow: 0.8 },
    mobile: { density: 'mobileParticleReduction', connections: 0.6, maxConnections: 2, pixelRatio: 1.5, glow: 0.85 },
    tablet: { density: 'tabletParticleReduction', connections: 0.8, maxConnections: 3, pixelRatio: 2, glow: 1 },
    desktop: { density: null, connections: 1, maxConnections: null, pixelRatio: null, glow: 1 },
    'large-desktop': { density: null, connections: 1, maxConnections: null, pixelRatio: null, glow: 1 },
};

/** Merge overrides and apply the responsive tier for this device. */
export function resolveGlobeConfig(overrides = {}, viewportWidth = 1280, cores = 8) {
    const base = { ...GLOBE_CONFIG, ...overrides, colors: { ...GLOBE_CONFIG.colors, ...(overrides.colors || {}) } };
    const tier = qualityTier(viewportWidth, cores);
    const t = TIER_SETTINGS[tier];
    return {
        ...base,
        tier,
        particleCount: Math.round(base.particleDensity * (t.density ? base[t.density] : 1)),
        connectionFrequency: base.connectionFrequency * t.connections,
        maxConnections: t.maxConnections ? Math.min(base.maxConnections, t.maxConnections) : base.maxConnections,
        maxPixelRatio: t.pixelRatio ? Math.min(base.maxPixelRatio, t.pixelRatio) : base.maxPixelRatio,
        glowIntensity: base.glowIntensity * t.glow,
    };
}
