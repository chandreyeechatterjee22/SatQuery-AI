import React from 'react';
import { confidenceBasis, formatConfidence, needsGeoTiffHint, STATUS_STYLES } from './lib/format.js';
import GeoTiffSources from './GeoTiffSources';

const TONES = {
    ok: 'border-emerald-500/50 bg-emerald-500/15 text-emerald-300',
    warn: 'border-amber-500/50 bg-amber-500/15 text-amber-300',
    error: 'border-red-500/50 bg-red-500/15 text-red-300',
};

const AnswerCard = ({ result }) => {
    if (!result) return null;
    const style = STATUS_STYLES[result.status] || { label: result.status, tone: 'warn' };
    const conf = result.confidence;
    // Some tools already put their warnings into the answer text; don't repeat those.
    const warnings = (result.details?.warnings || []).filter((w) => !result.answer?.includes(w));

    return (
        <section aria-label="Answer" className="rounded-2xl border border-space-700/60 bg-space-800/80 p-4 shadow-xl">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <span className={`rounded-full border px-3 py-0.5 text-xs font-semibold ${TONES[style.tone]}`}>
                    {style.label}{result.status !== 'OK' ? ` (${result.status})` : ''}
                </span>
                <span className="text-xs text-gray-400">Q: {result.question}</span>
            </div>

            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-100">{result.answer}</p>

            {result.details?.short_answer && (
                <p className="mt-2 text-xs text-gray-400">Short answer: <strong className="text-white">{result.details.short_answer}</strong></p>
            )}

            <div className="mt-4">
                <div className="mb-1 flex justify-between text-xs text-gray-400">
                    <span>Confidence</span>
                    <span><strong className="text-white">{formatConfidence(conf)}</strong> · {confidenceBasis(result)}</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-space-900" role="meter"
                    aria-valuemin={0} aria-valuemax={1} aria-valuenow={conf ?? undefined} aria-label="Confidence">
                    {conf != null && (
                        <div className="h-full rounded-full bg-gradient-to-r from-accent-blue to-accent-cyan"
                            style={{ width: `${Math.round(conf * 100)}%` }} />
                    )}
                </div>
            </div>

            {result.status !== 'OK' && needsGeoTiffHint(result.answer) && <GeoTiffSources />}

            {warnings.length > 0 && (
                <ul className="mt-3 space-y-1 text-xs text-amber-200">
                    {warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}
                </ul>
            )}
        </section>
    );
};

export default AnswerCard;
