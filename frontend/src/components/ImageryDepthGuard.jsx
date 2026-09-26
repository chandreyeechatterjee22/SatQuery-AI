import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import { deepestAvailableLevel, ESRI_TILEMAP_URL } from '../upload/lib/mapTiles.js';

const cache = new Map();

/** Esri tilemap: 0/1 per tile in the block (1 = real imagery exists at that level). */
async function fetchBlock(z, { x, y, w, h }) {
    const key = `${z}/${y}/${x}/${w}/${h}`;
    if (!cache.has(key)) {
        cache.set(key, fetch(`${ESRI_TILEMAP_URL}/${key}?f=json`)
            .then((r) => { if (!r.ok) throw new Error(`tilemap ${r.status}`); return r.json(); })
            .then((j) => j.data)
            .catch((err) => { cache.delete(key); throw err; }));
    }
    return cache.get(key);
}

/**
 * Keeps the Esri imagery layer from requesting levels where Esri has no imagery for the area in view
 * (it answers those with grey "Map data not yet available" tiles). Beyond the deepest real level the
 * map shows that level enlarged. ``onCapped(level | null)`` reports when the view is capped.
 */
const ImageryDepthGuard = ({ layerRef, baseMaxNativeZoom, onCapped }) => {
    const map = useMap();
    useEffect(() => {
        let timer = 0;
        let request = 0;
        const check = () => {
            const layer = layerRef.current;
            if (!layer) return;
            const offset = layer.options.zoomOffset || 0;          // 1 with detectRetina on scaled displays
            const wanted = Math.min(Math.round(map.getZoom()), baseMaxNativeZoom) + offset;
            const b = map.getBounds();
            const id = ++request;
            deepestAvailableLevel([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], wanted, fetchBlock)
                .then((level) => {
                    if (id !== request || !layerRef.current) return;  // a newer check is running
                    const native = Math.min(baseMaxNativeZoom, level - offset);
                    if (layer.options.maxNativeZoom !== native) {
                        layer.options.maxNativeZoom = native;
                        map.fire('viewreset');                          // grid layers re-pick their tile level
                    }
                    onCapped?.(level < wanted ? level : null);
                });
        };
        const schedule = () => { clearTimeout(timer); timer = setTimeout(check, 200); };
        map.on('zoomend moveend', schedule);
        schedule();
        return () => { clearTimeout(timer); request += 1; map.off('zoomend moveend', schedule); };
    }, [map, layerRef, baseMaxNativeZoom, onCapped]);
    return null;
};

export default ImageryDepthGuard;
