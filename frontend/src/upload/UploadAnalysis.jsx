import React, { useEffect, useState } from 'react';
import { FiCpu } from 'react-icons/fi';
import { askQuestion, createUpload, describeError, fetchTools } from '../api';
import AnswerCard from './AnswerCard';
import ImageViewer from './ImageViewer';
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
                <div className="rounded-2xl border border-space-700/60 bg-space-800/80 p-4 shadow-xl">
                    <h2 className="mb-3 text-base font-semibold text-white">Upload satellite images</h2>
                    <UploadForm onSubmit={handleUpload} busy={busy === 'upload'} />
                </div>
                <ValidationResult result={validation} />
                <ToolStatus tools={tools} />
            </aside>

            <div className="space-y-4 min-w-0">
                <div className="rounded-2xl border border-space-700/60 bg-space-800/80 p-4 shadow-xl">
                    <h2 className="mb-3 text-base font-semibold text-white">Ask a question</h2>
                    <QuestionBox mode={upload?.mode || 'single'} disabled={!upload} busy={busy === 'query'} onAsk={handleAsk} />
                </div>

                {error && (
                    <p role="alert" className="rounded-xl border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p>
                )}

                {upload && (
                    <div className="grid gap-4 xl:grid-cols-2">
                        <ImageViewer upload={upload} result={result} />
                        <div className="space-y-4 min-w-0">
                            <AnswerCard result={result} />
                            <ReportButtons upload={upload} result={result} />
                        </div>
                    </div>
                )}
                {result && <TraceTimeline trace={result.trace} />}
                {!upload && (
                    <p className="rounded-2xl border border-dashed border-space-700 p-8 text-center text-sm text-gray-500">
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
        <div className="rounded-2xl border border-space-700/60 bg-space-800/60 p-3 text-xs">
            <p className="mb-2 flex items-center gap-1.5 font-semibold text-gray-300"><FiCpu /> Tools on this server</p>
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
