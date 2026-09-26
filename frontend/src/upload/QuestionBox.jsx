import React, { useState } from 'react';
import { FiSend } from 'react-icons/fi';
import { EXAMPLES } from './lib/format.js';

const QuestionBox = ({ mode, disabled, busy, onAsk }) => {
    const [question, setQuestion] = useState('');
    const submit = (e) => {
        e.preventDefault();
        if (question.trim() && !disabled && !busy) onAsk(question.trim());
    };

    return (
        <form onSubmit={submit} className="space-y-2">
            <div className="flex gap-2">
                <input type="text" value={question} maxLength={1000} disabled={disabled}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder={disabled ? 'Upload an image first' : 'Ask a question about the upload...'}
                    aria-label="Question"
                    className="flex-1 rounded-full border border-white/10 bg-space-900 px-5 py-2.5 text-sm text-white placeholder-gray-500 focus:border-accent-cyan focus:outline-none disabled:opacity-50" />
                <button type="submit" disabled={disabled || busy || !question.trim()}
                    className="flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-soft-stone disabled:cursor-not-allowed disabled:opacity-40">
                    <FiSend /> {busy ? 'Running...' : 'Ask'}
                </button>
            </div>
            <div className="flex flex-wrap gap-2">
                {(EXAMPLES[mode] || []).map((ex) => (
                    <button key={ex} type="button" disabled={disabled || busy}
                        onClick={() => { setQuestion(ex); onAsk(ex); }}
                        className="rounded-full border border-space-700 bg-space-800 px-3 py-1 text-xs text-gray-300 hover:border-accent-cyan hover:text-accent-cyan disabled:opacity-40">
                        {ex}
                    </button>
                ))}
            </div>
        </form>
    );
};

export default QuestionBox;
