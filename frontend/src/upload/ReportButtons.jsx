import React, { useState } from 'react';
import { FiDownload } from 'react-icons/fi';
import { describeError, fetchAsDataUrl } from '../api';
import { buildReportHtml, buildReportJson, reportFilename } from './lib/report.js';

const save = (content, type, filename) => {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
};

const ReportButtons = ({ upload, result }) => {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    if (!result) return null;

    const downloadJson = () => {
        save(JSON.stringify(buildReportJson(upload, result), null, 2), 'application/json',
            reportFilename(upload, result, 'json'));
    };

    const downloadHtml = async () => {
        setBusy(true);
        setError('');
        try {
            const images = {};
            for (const e of result.evidence_images || []) {
                images[e.id] = await fetchAsDataUrl(e.url);
            }
            save(buildReportHtml(upload, result, images), 'text/html', reportFilename(upload, result, 'html'));
        } catch (err) {
            setError(`HTML report failed: ${describeError(err)}`);
        } finally {
            setBusy(false);
        }
    };

    const btn = 'flex items-center gap-2 rounded-lg border border-space-700 px-3 py-1.5 text-xs text-gray-200 hover:border-accent-cyan hover:text-accent-cyan disabled:opacity-40';
    return (
        <div className="space-y-1">
            <div className="flex gap-2">
                <button type="button" onClick={downloadJson} className={btn}><FiDownload /> Report (JSON)</button>
                <button type="button" onClick={downloadHtml} disabled={busy} className={btn}>
                    <FiDownload /> {busy ? 'Building...' : 'Report (HTML)'}
                </button>
            </div>
            {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
        </div>
    );
};

export default ReportButtons;
