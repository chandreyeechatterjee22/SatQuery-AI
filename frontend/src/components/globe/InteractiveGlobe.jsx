import React, { useEffect, useRef, useState } from 'react';
import { createGlobe } from './GlobeRenderer.js';

/**
 * Decorative interactive dotted globe (three.js / WebGL). Purely visual: it owns its canvas and
 * pointer handling and never touches app state. `config` overrides GLOBE_CONFIG and is read once.
 */
const InteractiveGlobe = ({ className = '', config }) => {
    const ref = useRef(null);
    const configRef = useRef(config);
    const [unavailable, setUnavailable] = useState(false);

    useEffect(() => {
        let globe = null;
        let cancelled = false;
        createGlobe(ref.current, configRef.current)
            .then((g) => {
                if (cancelled) g?.dispose();
                else if (!g) setUnavailable(true);
                else globe = g;
            })
            .catch((error) => {
                console.warn('Globe disabled:', error);
                if (!cancelled) setUnavailable(true);
            });
        return () => {
            cancelled = true;
            globe?.dispose();
        };
    }, []);

    return (
        <div ref={ref} className={`relative ${className}`} aria-hidden="true" data-testid="interactive-globe">
            {unavailable && (
                // Static stand-in when WebGL is not available.
                <div className="absolute inset-[6%] rounded-full bg-navy ring-1 ring-white/10" />
            )}
        </div>
    );
};

export default InteractiveGlobe;
