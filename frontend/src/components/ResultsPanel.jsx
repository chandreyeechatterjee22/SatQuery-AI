import React from 'react';
import { FiMapPin, FiHelpCircle, FiBarChart2, FiCalendar, FiDownload } from 'react-icons/fi';
import { FaWandMagicSparkles } from 'react-icons/fa6';

const LEGENDS = {
    NDVI: [
        { color: '#012E01', label: '0.6 - 0.8 (High)' },
        { color: '#66A000', label: '0.4 - 0.6' },
        { color: '#FCD163', label: '0.2 - 0.4' },
        { color: '#CE7E45', label: '0.0 - 0.2 (Low)' },
    ],
    NDWI: [
        { color: '#0000FF', label: 'Water (dense)' },
        { color: '#00FFFF', label: 'Water (sparse)' },
    ],
    'Potential Flood Proxy': [
        { color: '#FF4500', label: 'Potential flood proxy' },
    ],
};

const meanValueFor = (stats) => {
    if (stats.mean_ndvi !== undefined) return { label: 'Mean NDVI', value: stats.mean_ndvi };
    if (stats.mean_ndwi !== undefined) return { label: 'Mean NDWI', value: stats.mean_ndwi };
    return null;
};

const downloadReport = (ctx) => {
    const { selectedState, selectedArea, query, sentinelData, analysisResult } = ctx;
    const lines = [
        'SatQuery AI - Analysis Report',
        '==============================',
        `Location: ${selectedArea}, ${selectedState}, India`,
        `Query: ${query}`,
        `Index: ${analysisResult.index}`,
        `Satellite: ${sentinelData.satellite}`,
        `Source: ${sentinelData.source}`,
        `Image/Analysis Period: ${sentinelData.analysis_period}`,
        '',
        `Detected Area: ${analysisResult.stats.area} ${analysisResult.stats.area_unit}`,
        `AOI Size: ${analysisResult.stats.total_aoi} ${analysisResult.stats.area_unit}`,
        `AOI Coverage: ${analysisResult.stats.percentage_coverage}%`,
    ];
    const mean = meanValueFor(analysisResult.stats);
    if (mean) lines.push(`${mean.label}: ${mean.value}`);
    lines.push('', 'AI Analysis:', analysisResult.explanation);

    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `satquery-report-${selectedArea.replace(/\s+/g, '_')}.txt`;
    a.click();
    URL.revokeObjectURL(url);
};

const ResultsPanel = ({ selectedState, selectedArea, query, sentinelData, analysisResult }) => {
    if (!analysisResult || !sentinelData) {
        return (
            <div className="w-1/4 h-full flex flex-col items-center justify-center text-center bg-space-800/95 backdrop-blur-xl text-gray-500 border-l border-space-700/60 p-8">
                <FaWandMagicSparkles size={28} className="mb-3 text-space-700" />
                <p className="text-sm">Run an analysis to see results, stats, and AI insights here.</p>
            </div>
        );
    }

    const mean = meanValueFor(analysisResult.stats);
    const legend = LEGENDS[analysisResult.index] || [];

    return (
        <div className="w-1/4 h-full flex flex-col bg-space-800/95 backdrop-blur-xl text-white border-l border-space-700/60 p-6 overflow-y-auto">
            <div className="flex items-center gap-2 mb-5 text-sm font-semibold text-gray-300">
                <FaWandMagicSparkles className="text-accent-cyan" /> Analysis Results
            </div>

            <div className="space-y-3 text-sm">
                <div className="flex items-start gap-2">
                    <FiMapPin className="text-accent-cyan mt-0.5 shrink-0" />
                    <div>
                        <p className="text-xs text-gray-500">Location</p>
                        <p>{selectedArea}, {selectedState}, India</p>
                    </div>
                </div>
                <div className="flex items-start gap-2">
                    <FiHelpCircle className="text-accent-cyan mt-0.5 shrink-0" />
                    <div>
                        <p className="text-xs text-gray-500">Selected Query</p>
                        <p>{query}</p>
                    </div>
                </div>
                <div className="flex items-start gap-2">
                    <FiBarChart2 className="text-accent-cyan mt-0.5 shrink-0" />
                    <div>
                        <p className="text-xs text-gray-500">Index Used</p>
                        <p>{analysisResult.index}</p>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mt-5">
                <div className="p-3 rounded-xl bg-space-900/60 border border-space-700">
                    <p className="text-xs text-gray-500 mb-1">Detected Area</p>
                    <p className="text-lg font-bold text-white">{analysisResult.stats.area} {analysisResult.stats.area_unit}</p>
                </div>
                <div className="p-3 rounded-xl bg-space-900/60 border border-space-700">
                    <p className="text-xs text-gray-500 mb-1">AOI Coverage</p>
                    <p className="text-lg font-bold text-accent-cyan">{analysisResult.stats.percentage_coverage}%</p>
                </div>
                {mean && (
                    <div className="p-3 rounded-xl bg-space-900/60 border border-space-700 col-span-2">
                        <p className="text-xs text-gray-500 mb-1">{mean.label}</p>
                        <p className="text-lg font-bold text-white">{mean.value}</p>
                    </div>
                )}
            </div>

            <div className="flex items-start gap-2 mt-4 text-sm">
                <FiCalendar className="text-accent-cyan mt-0.5 shrink-0" />
                <div>
                    <p className="text-xs text-gray-500">Image/Analysis Period</p>
                    <p>{sentinelData.analysis_period}</p>
                </div>
            </div>

            <div className="mt-5 pt-5 border-t border-space-700/60">
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">AI Analysis</p>
                <p className="text-sm text-gray-300 leading-relaxed">{analysisResult.explanation}</p>
            </div>

            {(sentinelData.thumb_url || analysisResult.thumb_url) && (
                <div className="mt-5 pt-5 border-t border-space-700/60">
                    <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">Visualization</p>
                    <div className="grid grid-cols-2 gap-3">
                        {sentinelData.thumb_url && (
                            <div>
                                <img src={sentinelData.thumb_url} alt="Satellite" className="w-full aspect-square object-cover rounded-lg border border-space-700" />
                                <p className="text-xs text-gray-500 mt-1 text-center">Satellite Image</p>
                            </div>
                        )}
                        {analysisResult.thumb_url && (
                            <div>
                                {analysisResult.stats.percentage_coverage > 0 ? (
                                    <img src={analysisResult.thumb_url} alt={analysisResult.index} className="w-full aspect-square object-cover rounded-lg border border-space-700" />
                                ) : (
                                    <div className="w-full aspect-square flex items-center justify-center rounded-lg border border-space-700 bg-space-900/60 text-center px-2">
                                        <p className="text-xs text-gray-500">Nothing detected in this AOI</p>
                                    </div>
                                )}
                                <p className="text-xs text-gray-500 mt-1 text-center">{analysisResult.index} Overlay</p>
                            </div>
                        )}
                    </div>
                    {legend.length > 0 && (
                        <div className="mt-3 space-y-1">
                            {legend.map(l => (
                                <div key={l.label} className="flex items-center gap-2 text-xs text-gray-400">
                                    <span className="w-3 h-3 rounded-sm shrink-0" style={{ backgroundColor: l.color }} />
                                    {l.label}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            <button
                onClick={() => downloadReport({ selectedState, selectedArea, query, sentinelData, analysisResult })}
                className="mt-5 w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-space-700 hover:border-accent-cyan hover:text-accent-cyan text-sm font-semibold transition-colors"
            >
                <FiDownload /> Download Report
            </button>
        </div>
    );
};

export default ResultsPanel;
