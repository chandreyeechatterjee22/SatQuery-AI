import React from 'react';
import { FiCheckCircle, FiXCircle, FiMinusCircle } from 'react-icons/fi';
import { formatMs, humanize } from './lib/format.js';

const ICONS = {
    ok: <FiCheckCircle className="text-emerald-400" />,
    failed: <FiXCircle className="text-red-400" />,
    not_available: <FiMinusCircle className="text-amber-400" />,
};

const TraceTimeline = ({ trace }) => {
    if (!trace) return null;
    return (
        <section aria-label="Execution trace" className="rounded-2xl border border-space-700/60 bg-space-800/80 p-4 shadow-xl">
            <h3 className="mb-2 text-sm font-semibold text-white">Execution trace</h3>
            <dl className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
                <Fact label="Task" value={trace.task + (trace.rerouted_from ? ` (from ${trace.rerouted_from})` : '')} />
                <Fact label="Tool" value={trace.tool ? `${trace.tool} ${trace.tool_version}` : '-'} />
                <Fact label="Status" value={trace.status} />
                <Fact label="Duration" value={formatMs(trace.duration_ms)} />
                <Fact label="Inputs" value={(trace.inputs || []).map((i) => `${i.role || i.kind}: ${i.filename}`).join(', ') || '-'} />
                <Fact label="Params" value={JSON.stringify(trace.params || {})} mono />
            </dl>
            <ol className="relative space-y-2 border-l border-space-700 pl-4">
                {(trace.steps || []).map((s, i) => (
                    <li key={i} className="relative">
                        <span className="absolute -left-[1.4rem] top-0.5 rounded-full bg-space-800">{ICONS[s.status] || ICONS.ok}</span>
                        <details className="group">
                            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-xs text-gray-200">
                                <span>{humanize(s.step)} <span className="text-gray-500">({s.status})</span></span>
                                <span className="text-gray-500">{formatMs(s.duration_ms)}</span>
                            </summary>
                            <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-space-900 p-2 text-[11px] text-gray-300">
                                {JSON.stringify(s.detail, null, 2)}
                            </pre>
                        </details>
                    </li>
                ))}
            </ol>
        </section>
    );
};

const Fact = ({ label, value, mono }) => (
    <div className="min-w-0">
        <dt className="text-gray-500">{label}</dt>
        <dd className={`truncate text-gray-200 ${mono ? 'font-mono text-[11px]' : ''}`} title={value}>{value}</dd>
    </div>
);

export default TraceTimeline;
