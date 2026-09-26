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
    return { detectRetina: retina, maxNativeZoom: retina ? 18 : 19, maxZoom: 21, keepBuffer: 4 };
}
