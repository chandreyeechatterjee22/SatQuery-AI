import React, { useEffect, useState } from 'react';
import { FiCpu } from 'react-icons/fi';
import { askQuestion, createUpload, describeError, fetchTools } from '../api';
import AnswerCard from './AnswerCard';
import GeeFetch from './GeeFetch';
import ImageViewer from './ImageViewer';
import PlainAnswer from './PlainAnswer';
import QuestionBox from './QuestionBox';
import ReportButtons from './ReportButtons';
import TraceTimeline from './TraceTimeline';
import UploadForm from './UploadForm';
import ValidationResult from './ValidationResult';

const UploadAnalysis = () => {
    const [validation, setValidation] = useState(null);   // {ok, status, body}
    const [upload, setUpload] = useState(null);           // accepted manifest
    const [result, setResult] = useState(null);
    const [tools, setTools] = useState(null);
    const [busy, setBusy] = useState('');                 // '', 'upload', 'query'
    const [error, setError] = useState('');

    useEffect(() => {
        fetchTools().then(setTools).catch((err) => setError(describeError(err)));
    }, []);

    const handleUpload = async (form) => {
        setBusy('upload');
        setError('');
        setResult(null);
        // Drop the previous upload right away so its panel and chips can't be used while the new one runs.
        setValidation(null);
        setUpload(null);
        try {
            const res = await createUpload(form);
            setValidation(res);
            setUpload(res.ok ? res.body : null);
        } catch (err) {
            setValidation(null);
            setUpload(null);
            setError(describeError(err));
        } finally {
            setBusy('');
        }
    };

    const handleFetched = (manifest) => {
        setError('');
        setResult(null);
        setValidation({ ok: true, status: 201, body: manifest });
        setUpload(manifest);
    };

    const handleAsk = async (question) => {
        setBusy('query');
        setError('');
        try {
            setResult(await askQuestion(upload.upload_id, question));
        } catch (err) {
            setError(describeError(err));
        } finally {
            setBusy('');
        }
    };

    return (
        <section id="upload-analysis" className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[380px_1fr]">
            <aside className="space-y-4">
                <div className="rounded-lg border border-white/[0.07] bg-space-800 p-5">
                    <h2 className="mb-4 font-display text-xl font-normal tracking-[-0.01em] text-white">Upload satellite images</h2>
                    <UploadForm onSubmit={handleUpload} busy={busy === 'upload'} />
                </div>
                <GeeFetch onFetched={handleFetched} disabled={busy !== ''} />
                <ValidationResult result={validation} />
                <ToolStatus tools={tools} />
            </aside>

            <div className="space-y-4 min-w-0">
                <div className="rounded-lg border border-white/[0.07] bg-space-800 p-5">
                    <h2 className="mb-4 font-display text-xl font-normal tracking-[-0.01em] text-white">Ask a question</h2>
                    <QuestionBox mode={upload?.mode || 'single'} disabled={!upload || busy === 'upload'} busy={busy === 'query'} onAsk={handleAsk} />
                </div>

                {error && (
                    <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p>
                )}

                {upload && (
                    <div className="grid gap-4 xl:grid-cols-2">
                        <ImageViewer upload={upload} result={result} />
                        <div className="space-y-4 min-w-0">
                            <PlainAnswer result={result} onAsk={handleAsk} askDisabled={busy !== ''} />
                            <ReportButtons upload={upload} result={result} />
                        </div>
                    </div>
                )}
                {result && (
                    // Closed by default when there is a plain answer; open when the server sent none.
                    <details key={result.query_id} open={!result.plain} data-testid="technical-details"
                        className="rounded-lg border border-white/[0.07] bg-space-800/60 p-4">
                        <summary className="cursor-pointer select-none text-sm font-medium text-gray-200 hover:text-white">
                            Technical details
                            <span className="ml-2 text-xs font-normal text-gray-500">full answer, confidence basis, raw numbers, execution trace</span>
                        </summary>
                        <div className="mt-3 space-y-4">
                            <AnswerCard result={result} />
                            <TraceTimeline trace={result.trace} />
                        </div>
                    </details>
                )}
                {!upload && (
                    <p className="rounded-lg border border-dashed border-white/15 p-10 text-center text-sm text-gray-500">
                        Upload a GeoTIFF (or an optical + SAR pair, or two dates) to start asking questions.
                    </p>
                )}
            </div>
        </section>
    );
};

const ToolStatus = ({ tools }) => {
    if (!tools) return null;
    return (
        <div className="rounded-lg border border-white/[0.07] bg-space-800 p-4 text-xs">
            <p className="mb-3 flex items-center gap-1.5 font-mono uppercase tracking-[0.08em] text-muted"><FiCpu /> Tools on this server</p>
            <ul className="space-y-1">
                {tools.map((t) => (
                    <li key={t.name} className="flex justify-between gap-2">
                        <span className="text-gray-300">{t.name} <span className="text-gray-500">{t.version}</span></span>
                        <span className={t.available ? 'text-emerald-300' : 'text-amber-300'}>
                            {t.available ? 'available' : 'NOT_AVAILABLE'}
                        </span>
                    </li>
                ))}
            </ul>
        </div>
    );
};

export default UploadAnalysis;
