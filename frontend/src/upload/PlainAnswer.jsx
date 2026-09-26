import React from 'react';
import { FiAlertTriangle, FiArrowRight } from 'react-icons/fi';
import { CONFIDENCE_LEVEL_STYLES, needsGeoTiffHint, STATUS_STYLES } from './lib/format.js';
import GeoTiffSources from './GeoTiffSources';

/** The everyday-language answer shown first; the technical answer lives under "Technical details". */
const PlainAnswer = ({ result, onAsk, askDisabled }) => {
    const plain = result?.plain;
    if (!plain) return null;
    const conf = plain.confidence || {};
    const tone = CONFIDENCE_LEVEL_STYLES[conf.level] || CONFIDENCE_LEVEL_STYLES['Not rated'];
    const status = STATUS_STYLES[result.status] || { label: result.status };

    return (
        <section aria-label="Answer" className="rounded-2xl border border-space-700/60 bg-space-800/80 p-5 shadow-xl">
            <p className="mb-2 text-xs text-gray-400">
                {status.label} · Q: {result.question}
            </p>
            <h2 className="text-xl font-semibold leading-snug text-white sm:text-2xl" data-testid="plain-headline">
                {plain.headline}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-gray-200">{plain.what_it_means}</p>

            {plain.key_numbers?.length > 0 && (
                <div className="mt-4">
                    <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">Key numbers</h3>
                    <ul className="space-y-1 text-sm text-gray-100">
                        {plain.key_numbers.map((n) => (
                            <li key={n} className="flex gap-2"><span className="text-accent-cyan">•</span>{n}</li>
                        ))}
                    </ul>
                </div>
            )}

            <div className="mt-4 flex flex-wrap items-start gap-2">
                <span data-testid="confidence-badge"
                    className={`shrink-0 rounded-full border px-3 py-0.5 text-xs font-semibold ${tone}`}>
                    {conf.level === 'Not rated' ? 'Confidence: not rated' : `${conf.level} confidence`}
                </span>
                <span className="text-xs leading-5 text-gray-300">{capitalize(conf.reason)}</span>
            </div>

            <p className="mt-3 text-xs leading-relaxed text-gray-400">
                <span className="font-semibold text-gray-300">How we know: </span>{plain.how_we_know}
            </p>

            {plain.caveats?.length > 0 && (
                <div role="note" className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                    <ul className="space-y-1">
                        {plain.caveats.map((c) => (
                            <li key={c} className="flex gap-2"><FiAlertTriangle className="mt-0.5 shrink-0 text-amber-300" />{c}</li>
                        ))}
                    </ul>
                </div>
            )}

            {result.status !== 'OK' && needsGeoTiffHint(result.answer) && <GeoTiffSources />}

            {plain.next_step && (
                <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-gray-400">
                    <span>Next, you could {result.status === 'OK' ? 'ask' : 'try'}:</span>
                    {isQuestion(plain.next_step) && onAsk ? (
                        <button type="button" disabled={askDisabled} onClick={() => onAsk(plain.next_step)} aria-label={`Ask next: ${plain.next_step}`}
                            className="inline-flex items-center gap-1 rounded-full border border-accent-cyan/40 px-3 py-1 text-accent-cyan hover:bg-accent-cyan/10 disabled:opacity-40">
                            {plain.next_step} <FiArrowRight />
                        </button>
                    ) : (
                        <span className="text-gray-200">{plain.next_step}</span>
                    )}
                </div>
            )}
        </section>
    );
};

const capitalize = (text) => (text ? text[0].toUpperCase() + text.slice(1) : '');

// Suggested questions are clickable; instructions ("Upload a ...") are plain text.
const isQuestion = (text) => /\?$/.test(text) || /^(describe|map|what|where|how|is|has|are)\b/i.test(text);

export default PlainAnswer;
