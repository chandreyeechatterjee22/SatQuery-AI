// Tile-layer settings shared by every Leaflet map in the app (pure, tested with node --test).

export const ESRI_IMAGERY_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

/**
 * Options for the Esri World Imagery layer. On high-DPI / scaled displays (devicePixelRatio > 1)
 * Leaflet's detectRetina asks for tiles one zoom level deeper and draws them at half size, so the
 * imagery is sharp instead of being stretched by the browser. Esri serves imagery up to zoom 19,
 * so the deepest requested level must stay at 19: maxNativeZoom 18 + the retina offset of 1.
 * keepBuffer keeps more tiles around the view, so panning and zooming show fewer empty gaps.
 */
export function imageryTileOptions(devicePixelRatio = 1) {
    const retina = devicePixelRatio > 1;
    // With detectRetina Leaflet lowers the layer's maxZoom by one; the maps zoom to 21, and a layer whose
    // maxZoom is below the map zoom removes all its tiles (a black map), so ask for 22 to end up at 21.
    return { detectRetina: retina, maxNativeZoom: retina ? 18 : 19, maxZoom: retina ? 22 : 21, keepBuffer: 4 };
}

export const ESRI_TILEMAP_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tilemap';
// Esri has imagery everywhere down to at least this level, so shallower requests are never checked.
export const ALWAYS_AVAILABLE_LEVEL = 16;
const MAX_BLOCK = 8;  // tiles per side checked per level (the view's centre block when larger)

/** Web-Mercator tile column/row for a lat/lon at zoom z. */
export function tileXY(lat, lon, z) {
    const n = 2 ** z;
    const x = Math.floor(((lon + 180) / 360) * n);
    const rad = (Math.max(-85.05, Math.min(85.05, lat)) * Math.PI) / 180;
    const y = Math.floor(((1 - Math.asinh(Math.tan(rad)) / Math.PI) / 2) * n);
    return { x: Math.max(0, Math.min(n - 1, x)), y: Math.max(0, Math.min(n - 1, y)) };
}

/** Tile block {x, y, w, h} covering bounds [west, south, east, north] at z, capped to MAX_BLOCK per side around the centre. */
export function tileBlock([west, south, east, north], z) {
    const a = tileXY(north, west, z);
    const b = tileXY(south, east, z);
    let { x } = a; let { y } = a;
    let w = b.x - a.x + 1; let h = b.y - a.y + 1;
    if (w > MAX_BLOCK) { x += Math.floor((w - MAX_BLOCK) / 2); w = MAX_BLOCK; }
    if (h > MAX_BLOCK) { y += Math.floor((h - MAX_BLOCK) / 2); h = MAX_BLOCK; }
    return { x, y, w, h };
}

/**
 * Deepest level in [floor, fromLevel] at which Esri has real imagery for every tile in the view
 * (Esri serves grey "Map data not yet available" tiles beyond that). ``fetchBlock(z, block)``
 * resolves to the tilemap's 0/1 ``data`` array for that block. Levels at or above
 * ALWAYS_AVAILABLE_LEVEL are returned without asking. Returns fromLevel if a check fails.
 */
export async function deepestAvailableLevel(bounds, fromLevel, fetchBlock, floor = ALWAYS_AVAILABLE_LEVEL) {
    for (let z = fromLevel; z > floor; z -= 1) {
        let data;
        try {
            data = await fetchBlock(z, tileBlock(bounds, z));
        } catch {
            return fromLevel;  // no answer: keep the normal behaviour rather than guessing
        }
        if (Array.isArray(data) && data.length > 0 && data.every((v) => v === 1)) return z;
    }
    return floor;
}
