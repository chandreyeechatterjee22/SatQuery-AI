import React, { useState } from 'react';
import { FiUploadCloud, FiChevronDown, FiChevronRight } from 'react-icons/fi';
import { MODES, SENSORS, uploadProblems } from './lib/format.js';

const inputClass = 'w-full rounded-lg border border-space-700 bg-space-900/70 px-3 py-2 text-sm text-white '
    + 'focus:border-accent-cyan focus:outline-none';

const UploadForm = ({ onSubmit, busy }) => {
    const [mode, setMode] = useState('single');
    const [files, setFiles] = useState({});
    const [dates, setDates] = useState({});
    const [sensors, setSensors] = useState({});
    const [roles, setRoles] = useState({});
    const [benchmark, setBenchmark] = useState(false);
    const [advanced, setAdvanced] = useState(false);

    const spec = MODES[mode];
    const problems = uploadProblems(mode, files, dates, benchmark);
    // Always list PNG/JPEG too: filtering them out made folders of photos look empty in the Windows picker.
    const accept = '.tif,.tiff,.png,.jpg,.jpeg';

    const changeMode = (m) => {
        setMode(m);
        setFiles({});
        setDates({});
    };

    const submit = (e) => {
        e.preventDefault();
        if (problems.length || busy) return;
        const form = new FormData();
        form.append('mode', mode);
        form.append('benchmark_mode', benchmark ? 'true' : 'false');
        for (const f of spec.files) {
            form.append(`file_${f.slot}`, files[f.slot]);
            if (dates[f.slot]) form.append(`date_${f.slot}`, dates[f.slot]);
            if (sensors[f.slot] && sensors[f.slot] !== 'auto') form.append(`sensor_${f.slot}`, sensors[f.slot]);
            if (roles[f.slot]?.trim()) form.append(`band_roles_${f.slot}`, roles[f.slot].trim());
        }
        onSubmit(form, mode);
    };

    return (
        <form onSubmit={submit} className="space-y-4">
            <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">1. Mode</p>
                <p className="mb-2 text-xs text-gray-500">GeoTIFF (.tif) images. Ready-made demo files are in the repo's <code>samples</code> folder (see docs/DEMO.md).</p>
                <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Upload mode">
                    {Object.entries(MODES).map(([key, m]) => (
                        <button key={key} type="button" role="radio" aria-checked={mode === key}
                            onClick={() => changeMode(key)}
                            className={`rounded-lg border px-2 py-2 text-xs font-medium transition-colors ${mode === key
                                ? 'border-accent-cyan bg-accent-cyan/15 text-accent-cyan'
                                : 'border-space-700 bg-space-900/50 text-gray-300 hover:border-accent-cyan/60'}`}>
                            {m.label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">2. Files</p>
                {spec.files.map((f) => (
                    <div key={`${mode}-${f.slot}`} className="rounded-xl border border-space-700/70 bg-space-900/40 p-3 space-y-2">
                        <label className="block text-sm font-medium text-gray-200">
                            {f.label} <span className="text-xs font-normal text-gray-500">({f.hint})</span>
                            <input type="file" accept={accept}
                                onChange={(e) => setFiles({ ...files, [f.slot]: e.target.files[0] })}
                                className="mt-1 block w-full text-xs text-gray-300 file:mr-3 file:rounded-md file:border-0 file:bg-space-700 file:px-3 file:py-1.5 file:text-white hover:file:bg-accent-blue" />
                        </label>
                        {spec.needsDates && (
                            <label className="block text-xs text-gray-400">Acquisition date
                                <input type="date" value={dates[f.slot] || ''} className={`${inputClass} mt-1`}
                                    onChange={(e) => setDates({ ...dates, [f.slot]: e.target.value })} />
                            </label>
                        )}
                        {advanced && (
                            <div className="grid grid-cols-2 gap-2">
                                <label className="text-xs text-gray-400">Sensor
                                    <select value={sensors[f.slot] || 'auto'} className={`${inputClass} mt-1`}
                                        onChange={(e) => setSensors({ ...sensors, [f.slot]: e.target.value })}>
                                        {SENSORS.map((s) => <option key={s} value={s}>{s}</option>)}
                                    </select>
                                </label>
                                <label className="text-xs text-gray-400">Band roles (optional)
                                    <input type="text" placeholder="blue,green,red,nir" value={roles[f.slot] || ''}
                                        className={`${inputClass} mt-1`}
                                        onChange={(e) => setRoles({ ...roles, [f.slot]: e.target.value })} />
                                </label>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            <button type="button" onClick={() => setAdvanced(!advanced)}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-accent-cyan">
                {advanced ? <FiChevronDown /> : <FiChevronRight />} Advanced: sensor, band roles, benchmark mode
            </button>
            {advanced && (
                <label className="flex items-center gap-2 text-xs text-gray-300">
                    <input type="checkbox" checked={benchmark} onChange={(e) => setBenchmark(e.target.checked)} />
                    Benchmark mode (also accept PNG/JPEG)
                </label>
            )}

            {problems.length > 0 && (
                <ul className="text-xs text-gray-400 list-disc pl-5" aria-live="polite">
                    {problems.map((p) => <li key={p}>{p}</li>)}
                </ul>
            )}

            <button type="submit" disabled={problems.length > 0 || busy}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-accent-blue to-accent-cyan px-4 py-2.5 text-sm font-semibold text-white shadow-lg disabled:cursor-not-allowed disabled:opacity-40">
                <FiUploadCloud /> {busy ? 'Uploading and validating...' : 'Upload and validate'}
            </button>
        </form>
    );
};

export default UploadForm;
