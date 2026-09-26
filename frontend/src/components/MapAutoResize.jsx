import { useEffect } from 'react';
import { useMap } from 'react-leaflet';

/**
 * Re-measure the map whenever its container changes size (window or browser-zoom changes, panels
 * opening, a hidden tab becoming visible). Without this Leaflet only loads tiles for the old size and
 * leaves empty areas.
 */
const MapAutoResize = () => {
    const map = useMap();
    useEffect(() => {
        const el = map.getContainer();
        let frame = 0;
        const observer = new ResizeObserver(() => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => map.invalidateSize({ pan: false }));
        });
        observer.observe(el);
        return () => { cancelAnimationFrame(frame); observer.disconnect(); };
    }, [map]);
    return null;
};

export default MapAutoResize;
