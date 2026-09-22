import React from 'react';
import { FaSatellite, FaLeaf, FaDroplet, FaCloudRain } from 'react-icons/fa6';

const FEATURES = [
    { icon: FaLeaf, label: 'Vegetation Monitoring', desc: 'Track crop health & vegetation using NDVI', color: 'text-green-400', ring: 'ring-green-400/30', query: 'Where is the vegetation?' },
    { icon: FaDroplet, label: 'Water Detection', desc: 'Identify water bodies & water resources using NDWI', color: 'text-sky-400', ring: 'ring-sky-400/30', query: 'Where are the water bodies?' },
    { icon: FaCloudRain, label: 'Potential Flood Detection', desc: 'Detect flooded regions using temporal analysis', color: 'text-purple-400', ring: 'ring-purple-400/30', query: 'Which regions are potentially flooded?' },
];

// Real NASA/ESA public-domain photos (Wikimedia Commons), not illustrations.
const EARTH_IMAGE_URL = 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/cb/The_Blue_Marble_%28remastered%29.jpg/960px-The_Blue_Marble_%28remastered%29.jpg';
const SATELLITE_IMAGE_URL = 'https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Sentinel_2-IMG_5873-black.jpg/500px-Sentinel_2-IMG_5873-black.jpg';

// A handful of fixed "star" positions rendered as tiny radial-gradient dots.
const STARFIELD = `
    radial-gradient(1.5px 1.5px at 10% 18%, white, transparent),
    radial-gradient(1px 1px at 24% 58%, white, transparent),
    radial-gradient(1.5px 1.5px at 38% 12%, white, transparent),
    radial-gradient(1px 1px at 58% 42%, white, transparent),
    radial-gradient(1.5px 1.5px at 74% 68%, white, transparent),
    radial-gradient(1px 1px at 84% 22%, white, transparent),
    radial-gradient(1px 1px at 91% 52%, white, transparent),
    radial-gradient(1.5px 1.5px at 18% 78%, white, transparent),
    radial-gradient(1px 1px at 48% 82%, white, transparent),
    radial-gradient(1.5px 1.5px at 64% 8%, white, transparent),
    radial-gradient(1px 1px at 95% 80%, white, transparent),
    radial-gradient(1px 1px at 33% 35%, white, transparent)
`;

const Hero = ({ onStartExploring, onSelectFeature }) => {
    return (
        <section id="hero" className="relative overflow-hidden bg-gradient-to-br from-space-900 via-[#0d1e45] to-space-900 border-b border-space-700/60">
            <div className="pointer-events-none absolute inset-0">
                <div className="absolute inset-0 opacity-70" style={{ backgroundImage: STARFIELD }} />
                <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-accent-blue/20 blur-3xl" />
                <div className="absolute top-1/2 -left-20 -translate-y-1/2 w-[26rem] h-[26rem] rounded-full bg-sky-400/25 blur-3xl" />

                {/* Earth - large, bleeding off the left edge (and top/bottom) like a planet seen from orbit */}
                <div className="absolute top-1/2 -left-48 -translate-y-1/2 w-[34rem] h-[34rem]">
                    {/* Atmospheric rim glow, slightly larger than the sphere itself */}
                    <div
                        className="absolute -inset-10 rounded-full"
                        style={{ background: 'radial-gradient(circle, transparent 60%, rgba(56,189,248,0.6) 70%, rgba(56,189,248,0.2) 82%, transparent 92%)' }}
                    />

                    {/* The sphere: a circular clipping mask around a zoomed-in crop of the photo,
                        so the source photo's black square background never shows through. */}
                    <div className="relative w-full h-full rounded-full overflow-hidden">
                        <img
                            src={EARTH_IMAGE_URL}
                            alt=""
                            className="absolute inset-0 w-full h-full object-cover scale-125"
                            style={{ filter: 'brightness(1.22) saturate(1.4) contrast(1.1)' }}
                        />
                    </div>
                </div>

                {/* Satellite, floating separately in open sky above the earth - not touching it */}
                <div className="absolute top-4 left-96 w-32 h-32">
                    <div className="absolute inset-3 rounded-full bg-cyan-300/50 blur-xl" />
                    <img
                        src={SATELLITE_IMAGE_URL}
                        alt=""
                        className="relative w-full h-full object-contain rotate-[-10deg] mix-blend-screen"
                    />
                </div>
            </div>

            <div className="relative max-w-7xl mx-auto px-6 py-14 flex flex-col lg:flex-row lg:items-center gap-10">
                <div className="flex-1 lg:pl-[26rem]">
                    <div className="flex items-center gap-2 mb-3">
                        <FaSatellite className="text-accent-cyan" size={28} />
                        <h1 className="text-4xl font-extrabold tracking-tight text-white">
                            SatQuery <span className="bg-gradient-to-r from-accent-cyan to-accent-blue bg-clip-text text-transparent">AI</span>
                        </h1>
                    </div>
                    <p className="text-xl font-semibold text-gray-100 mb-2">Ask Questions. Understand India from Space.</p>
                    <p className="text-sm text-gray-300 max-w-lg mb-6">
                        An AI-powered platform for satellite imagery analysis using Sentinel-2 and Google Earth Engine.
                    </p>
                    <button
                        onClick={onStartExploring}
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-accent-blue hover:bg-blue-600 text-white text-sm font-semibold shadow-lg shadow-accent-blue/30 transition-colors"
                    >
                        Start Exploring →
                    </button>
                </div>

                <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {FEATURES.map(({ icon: Icon, label, desc, color, ring, query }) => (
                        <button
                            key={label}
                            onClick={() => onSelectFeature(query)}
                            className={`text-left p-4 rounded-xl bg-space-800/80 border border-space-700 hover:border-accent-cyan/50 ring-1 ${ring} transition-all hover:-translate-y-0.5`}
                        >
                            <Icon className={`${color} mb-3`} size={22} />
                            <p className="text-sm font-semibold text-white leading-snug">{label}</p>
                            <p className="text-xs text-gray-500 mt-1 leading-snug">{desc}</p>
                        </button>
                    ))}
                </div>
            </div>
        </section>
    );
};

export default Hero;
