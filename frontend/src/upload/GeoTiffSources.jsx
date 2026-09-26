import React from 'react';
import { GEOTIFF_SOURCES } from './lib/format.js';

/** "Where to get proper GeoTIFFs": shown wherever a photo / uncalibrated input can't be analysed. */
const GeoTiffSources = () => (
    <div className="mt-2 text-xs text-gray-300">
        <p className="font-semibold text-gray-200">Where to get proper GeoTIFFs</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {GEOTIFF_SOURCES.map((s) => (
                <li key={s.label}>
                    {s.href ? (
                        <a href={s.href} target="_blank" rel="noreferrer" className="text-accent-cyan hover:underline">{s.label}</a>
                    ) : s.label}
                </li>
            ))}
        </ul>
    </div>
);

export default GeoTiffSources;
