import React, { Suspense, lazy } from 'react';
import { FaSatellite, FaLeaf, FaDroplet, FaCloudRain } from 'react-icons/fa6';

// three.js is only downloaded when the hero is rendered.
const InteractiveGlobe = lazy(() => import('./globe/InteractiveGlobe.jsx'));

const FEATURES = [
    { icon: FaLeaf, label: 'Vegetation Monitoring', desc: 'Track crop health & vegetation using NDVI', color: 'text-green-300', query: 'Where is the vegetation?' },
    { icon: FaDroplet, label: 'Water Detection', desc: 'Identify water bodies & water resources using NDWI', color: 'text-sky-300', query: 'Where are the water bodies?' },
    { icon: FaCloudRain, label: 'Potential Flood Detection', desc: 'Detect flooded regions using temporal analysis', color: 'text-violet-300', query: 'Which regions are potentially flooded?' },
];

const Hero = ({ onStartExploring, onSelectFeature }) => {
    return (
        <section id="hero" className="relative overflow-hidden border-b border-white/[0.07] bg-space-900">
            <div className="relative mx-auto grid max-w-7xl items-center gap-8 px-4 pt-12 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-12 lg:pt-16">
                <div className="order-2 lg:order-1">
                    <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-[0.14em] text-muted">
                        <FaSatellite size={13} /> Sentinel-2 · Google Earth Engine
                    </p>
                    <h1 className="mt-5 font-display text-5xl font-normal leading-none tracking-[-0.02em] text-white sm:text-6xl xl:text-[80px]">
                        SatQuery <span className="text-muted">AI</span>
                    </h1>
                    <p className="mt-6 max-w-xl text-xl leading-snug text-gray-100 sm:text-2xl">Ask Questions. Understand India from Space.</p>
                    <p className="mt-3 max-w-lg text-base leading-relaxed text-slate">
                        An AI-powered platform for satellite imagery analysis using Sentinel-2 and Google Earth Engine.
                    </p>
                    <button
                        onClick={onStartExploring}
                        className="mt-8 inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-medium text-primary transition-colors hover:bg-soft-stone"
                    >
                        Start Exploring →
                    </button>
                </div>

                <div className="order-1 mx-auto aspect-square w-full max-w-[300px] sm:max-w-[420px] lg:order-2 lg:max-w-[560px]">
                    <Suspense fallback={null}>
                        <InteractiveGlobe className="h-full w-full" />
                    </Suspense>
                </div>
            </div>

            <div className="relative mx-auto max-w-7xl px-4 pb-12 pt-10 sm:px-6 lg:pb-16">
                <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-white/[0.07] bg-white/[0.07] sm:grid-cols-3">
                    {FEATURES.map(({ icon: Icon, label, desc, color, query }, i) => (
                        <button
                            key={label}
                            onClick={() => onSelectFeature(query)}
                            className="bg-space-900 p-6 text-left transition-colors hover:bg-space-800"
                        >
                            <div className="flex items-center justify-between">
                                <Icon className={color} size={20} />
                                <span className="font-mono text-xs text-muted">0{i + 1}</span>
                            </div>
                            <p className="mt-6 text-lg leading-snug text-white">{label}</p>
                            <p className="mt-1.5 text-sm leading-snug text-slate">{desc}</p>
                        </button>
                    ))}
                </div>
            </div>
        </section>
    );
};

export default Hero;
