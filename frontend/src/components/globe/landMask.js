// Land/ocean lookup for the globe's dots: Natural Earth 1:110m land (world-atlas) rasterised once
// onto an equirectangular canvas with d3-geo, then sampled per dot.

const MASK_W = 1024;
const MASK_H = 512;

let cached = null;

/** Resolves to `(lon, lat) => boolean` (true on land). Cached for the page's lifetime. */
export function loadLandSampler() {
    if (!cached) {
        cached = Promise.all([import('world-atlas/land-110m.json'), import('topojson-client'), import('d3-geo')])
            .then(([topoModule, topojson, d3]) => buildSampler(topoModule.default ?? topoModule, topojson, d3))
            .catch((error) => {
                cached = null;
                throw error;
            });
    }
    return cached;
}

function buildSampler(topo, topojson, d3) {
    const land = topojson.feature(topo, topo.objects.land);
    const canvas = document.createElement('canvas');
    canvas.width = MASK_W;
    canvas.height = MASK_H;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    // d3-geo clips polygons at the antimeridian and closes Antarctica around the pole correctly.
    const projection = d3.geoEquirectangular()
        .scale(MASK_W / (2 * Math.PI))
        .translate([MASK_W / 2, MASK_H / 2])
        .precision(0.1);
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    d3.geoPath(projection, ctx)(land);
    ctx.fill();

    const pixels = ctx.getImageData(0, 0, MASK_W, MASK_H).data;
    return (lon, lat) => {
        const x = Math.min(MASK_W - 1, Math.max(0, Math.floor(((lon + 180) / 360) * MASK_W)));
        const y = Math.min(MASK_H - 1, Math.max(0, Math.floor(((90 - lat) / 180) * MASK_H)));
        return pixels[(y * MASK_W + x) * 4 + 3] > 127;
    };
}
