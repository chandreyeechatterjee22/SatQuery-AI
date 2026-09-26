import React from 'react';
import { FiChevronDown, FiMapPin } from 'react-icons/fi';

const SUGGESTED_QUERIES = [
    { icon: '🌿', label: 'Where is the vegetation?', sub: 'NDVI' },
    { icon: '💧', label: 'Where are the water bodies?', sub: 'NDWI' },
    { icon: '☁️', label: 'Which regions are potentially flooded?', sub: 'Flood Analysis' },
];

const selectClasses = "w-full appearance-none p-2.5 pr-9 bg-space-900/60 rounded-lg border border-space-700 text-sm text-white outline-none transition-colors focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan/50 disabled:opacity-40 disabled:cursor-not-allowed";

const Sidebar = ({
    states,
    selectedState,
    onStateChange,
    areas,
    selectedArea,
    onAreaChange,
    onExploreArea,
    query,
    onQuerySelect,
    onAnalyze,
    canAnalyze,
    landcoverWarning
}) => {
    return (
        <div className="w-1/4 h-full flex flex-col bg-space-800/95 backdrop-blur-xl text-white border-r border-white/[0.07] p-6 overflow-y-auto">
            <div className="flex items-center gap-2 mb-4 text-sm font-semibold text-gray-300">
                <FiMapPin className="text-accent-cyan" /> Explore India
            </div>

            <div className="space-y-4">
                <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">Country</label>
                    <div className="flex items-center gap-2 p-2.5 bg-space-900/60 rounded-lg border border-space-700 text-sm">
                        <span>🇮🇳</span> India
                    </div>
                </div>

                <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">State</label>
                    <div className="relative">
                        <select value={selectedState} onChange={onStateChange} className={selectClasses}>
                            <option value="">Select state</option>
                            {states.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                        <FiChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-500" />
                    </div>
                </div>

                <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">Area / District</label>
                    <div className="relative">
                        <select value={selectedArea} onChange={onAreaChange} disabled={!selectedState} className={selectClasses}>
                            <option value="">Select area</option>
                            {areas.map(a => <option key={a} value={a}>{a}</option>)}
                        </select>
                        <FiChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-500" />
                    </div>
                </div>

                <button
                    onClick={onExploreArea}
                    disabled={!selectedState || !selectedArea}
                    className="w-full py-2.5 rounded-full bg-accent-blue hover:bg-focus-blue disabled:bg-space-700 disabled:text-gray-500 disabled:cursor-not-allowed text-sm font-semibold transition-colors"
                >
                    Explore Area
                </button>
            </div>

            <div className="pt-6 mt-6 border-t border-space-700/60">
                {landcoverWarning && (
                    <div className="mb-4 p-3 bg-red-900/40 border border-red-500/50 rounded-lg text-sm text-red-200">
                        {landcoverWarning}
                    </div>
                )}

                <h2 className="font-mono text-xs font-normal uppercase tracking-[0.1em] text-muted mb-3">Choose Analysis Query</h2>
                <div className="space-y-2">
                    {SUGGESTED_QUERIES.map(q => (
                        <button
                            key={q.label}
                            onClick={() => onQuerySelect(q.label)}
                            className={`w-full flex items-center gap-3 text-left px-3 py-2.5 rounded-lg border text-sm transition-all ${query === q.label ? 'bg-accent-cyan/10 border-accent-cyan text-accent-cyan shadow-[0_0_0_1px_rgba(91,192,190,0.4)]' : 'border-space-700 hover:bg-space-700/50'}`}
                        >
                            <span className="text-base leading-none">{q.icon}</span>
                            <span>
                                <span className="block">{q.label}</span>
                                <span className="block text-xs text-gray-500">{q.sub}</span>
                            </span>
                        </button>
                    ))}
                </div>

                <button
                    onClick={onAnalyze}
                    disabled={!canAnalyze}
                    className={`w-full mt-4 py-2.5 rounded-full font-medium text-sm transition-colors ${canAnalyze ? 'bg-white text-primary hover:bg-soft-stone' : 'bg-space-700 text-gray-500 cursor-not-allowed'}`}
                >
                    ✨ Analyze
                </button>
                {!canAnalyze && (
                    <p className="mt-2 text-xs text-gray-500 leading-relaxed">
                        Select a state, area, draw an AOI on the map, and pick a question to enable analysis.
                    </p>
                )}
            </div>

            <div className="mt-auto pt-6 text-xs text-gray-500 space-y-1.5">
                <p>ⓘ India only</p>
                <p>ⓘ No image upload</p>
                <p>ⓘ No manual coordinates</p>
            </div>
        </div>
    );
};

export default Sidebar;
