import React from 'react';
import { FiCheckCircle, FiXCircle, FiAlertTriangle } from 'react-icons/fi';
import GeoTiffSources from './GeoTiffSources';

const fmtRes = (r) => {
    if (!r) return '-';
    if (r.units === 'pixels') return 'pixel size unknown';  // no CRS (e.g. a JPG/PNG photo)
    return `${Number(r.x.toPrecision(4))} x ${Number(r.y.toPrecision(4))} ${r.units}`;
};

const ValidationResult = ({ result }) => {
    if (!result) return null;

    if (!result.ok) {
        return (
            <div role="alert" className="rounded-xl border border-red-500/50 bg-red-500/10 p-3 text-sm">
                <p className="mb-2 flex items-center gap-2 font-semibold text-red-300"><FiXCircle /> Upload rejected</p>
                <ul className="space-y-1 text-red-200">
                    {(result.body?.reasons || []).map((r, i) => (
                        <li key={i}><code className="mr-1 rounded bg-red-900/40 px-1 text-xs">{r.code}</code>{r.message}</li>
                    ))}
                </ul>
                {result.body?.warnings?.length > 0 && <Warnings items={result.body.warnings} />}
                <GeoTiffSources />
            </div>
        );
    }

    const m = result.body;
    return (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
            <p className="mb-2 flex items-center gap-2 font-semibold text-emerald-300">
                <FiCheckCircle /> Accepted <span className="font-normal text-gray-400">({m.mode}, id {m.upload_id.slice(0, 8)})</span>
            </p>
            <ul className="space-y-2 text-xs text-gray-300">
                {m.files.map((f) => (
                    <li key={f.slot} className="rounded-lg bg-space-900/50 px-2.5 py-2">
                        <p className="font-medium text-gray-100">
                            {f.slot}. {f.filename} <span className="font-normal text-gray-500">· {f.kind}{f.date ? ` · ${f.date}` : ''}</span>
                        </p>
                        <p className="text-gray-400">
                            {f.metadata.band_count} bands ({Object.keys(f.bands.roles).join(', ') || 'no roles'}) · {f.metadata.dtypes[0]}
                        </p>
                        <p className="text-gray-400">
                            {f.metadata.crs || 'no CRS'} · {fmtRes(f.metadata.resolution)} · {f.metadata.width} x {f.metadata.height} px
                        </p>
                    </li>
                ))}
            </ul>
            {m.source && (
                <p className="mt-2 text-xs text-gray-400" data-testid="upload-source">
                    Source: {m.source.provider} · {m.source.products.map((p) => `${p.product} ${p.date_range.join(' to ')} (${p.scenes} scenes)`).join(' · ')} · {m.source.crs}, {m.source.scale_m} m
                </p>
            )}
            {m.pair?.overlap_fraction != null && (
                <p className="mt-2 text-xs text-gray-400">Overlap: {Math.round(m.pair.overlap_fraction * 100)}% of the smaller image</p>
            )}
            {m.warnings?.length > 0 && <Warnings items={m.warnings} />}
        </div>
    );
};

const Warnings = ({ items }) => (
    <ul className="mt-2 space-y-1 text-xs text-amber-200">
        {items.map((w, i) => <li key={i} className="flex gap-1.5"><FiAlertTriangle className="mt-0.5 shrink-0" />{w}</li>)}
    </ul>
);

export default ValidationResult;
