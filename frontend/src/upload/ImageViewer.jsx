import React, { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../api';
import { splitEvidence } from './lib/format.js';

const ImageViewer = ({ upload, result }) => {
    const { bases, overlays } = useMemo(
        () => splitEvidence(upload.upload_id, upload.files, result), [upload, result]);
    const [baseId, setBaseId] = useState(bases[0]?.id);
    const [shown, setShown] = useState({});
    const [opacity, setOpacity] = useState(0.8);
    const [failed, setFailed] = useState({});

    // New result: show its overlays by default, on the base the first overlay belongs to.
    useEffect(() => {
        setShown(Object.fromEntries(overlays.map((o) => [o.id, true])));
        if (overlays[0]?.base) setBaseId(overlays[0].base);
        else if (!bases.find((b) => b.id === baseId)) setBaseId(bases[0]?.id);
    }, [result]); // eslint-disable-line react-hooks/exhaustive-deps

    const base = bases.find((b) => b.id === baseId) || bases[0];
    if (!base) return null;
    const visible = overlays.filter((o) => (o.base || 'preview_1') === base.id);

    return (
        <section aria-label="Image viewer" className="rounded-lg border border-white/[0.07] bg-space-800 p-5">
            <div className="mb-3 flex flex-wrap gap-2">
                {bases.map((b) => (
                    <button key={b.id} type="button" onClick={() => setBaseId(b.id)}
                        className={`rounded-lg border px-2.5 py-1 text-xs ${b.id === base.id
                            ? 'border-accent-cyan text-accent-cyan' : 'border-space-700 text-gray-400 hover:text-white'}`}>
                        {b.label}
                    </button>
                ))}
            </div>

            <div className="relative overflow-hidden rounded-lg border border-white/[0.07] bg-black">
                {failed[base.id] ? (
                    <p className="p-6 text-center text-xs text-red-300" role="alert">Could not load {base.label}.</p>
                ) : (
                    <img src={apiUrl(base.url)} alt={base.label} className="block w-full h-auto"
                        style={{ imageRendering: 'pixelated' }}
                        onError={() => setFailed({ ...failed, [base.id]: true })} />
                )}
                {visible.filter((o) => shown[o.id]).map((o) => (
                    <img key={o.id} src={apiUrl(o.url)} alt={o.label}
                        className="pointer-events-none absolute inset-0 h-full w-full"
                        style={{ opacity, imageRendering: 'pixelated' }} />
                ))}
            </div>

            {visible.length > 0 && (
                <div className="mt-3 space-y-2">
                    <div className="flex flex-wrap items-center gap-4">
                        {visible.map((o) => (
                            <label key={o.id} className="flex items-center gap-1.5 text-xs text-gray-300">
                                <input type="checkbox" checked={!!shown[o.id]}
                                    onChange={(e) => setShown({ ...shown, [o.id]: e.target.checked })} />
                                {o.label}
                            </label>
                        ))}
                        <label className="ml-auto flex items-center gap-2 text-xs text-gray-400">
                            Opacity
                            <input type="range" min="0" max="1" step="0.05" value={opacity}
                                onChange={(e) => setOpacity(Number(e.target.value))} aria-label="Overlay opacity" />
                        </label>
                    </div>
                    {visible.filter((o) => shown[o.id]).map((o) => (
                        <div key={o.id} className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
                            <span className="font-medium text-gray-300">{o.label}:</span>
                            {(o.legend || []).map((l) => (
                                <span key={l.label} className="flex items-center gap-1">
                                    <span className="inline-block h-3 w-3 rounded-sm border border-white/20" style={{ background: l.color }} />
                                    {l.label}
                                </span>
                            ))}
                        </div>
                    ))}
                </div>
            )}
            {overlays.length > 0 && visible.length === 0 && (
                <p className="mt-2 text-xs text-gray-500">Overlays for this result belong to another image; switch above.</p>
            )}
        </section>
    );
};

export default ImageViewer;
