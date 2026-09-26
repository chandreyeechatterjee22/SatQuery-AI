import React from 'react';
import { FaSatellite } from 'react-icons/fa6';

const VIEWS = [
    { key: 'map', label: 'Map Analysis' },
    { key: 'upload', label: 'Upload Analysis' },
];

const Header = ({ view = 'map', onViewChange }) => {
    const scrollTo = (id) => {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    };

    return (
        <header className="flex items-center justify-between gap-3 border-b border-white/[0.07] bg-space-900/90 px-4 py-3 text-white backdrop-blur-xl sm:px-6">
            <div className="flex shrink-0 items-center gap-2">
                <FaSatellite className="text-white" size={18} />
                <span className="whitespace-nowrap font-display text-base tracking-[-0.01em] sm:text-lg">
                    SatQuery <span className="text-muted">AI</span>
                </span>
            </div>

            <nav className="flex items-center gap-2 text-sm font-medium text-gray-300 sm:gap-6">
                {onViewChange && (
                    <div className="flex rounded-full border border-white/10 bg-white/[0.03] p-1" role="tablist">
                        {VIEWS.map((v) => (
                            <button key={v.key} role="tab" aria-selected={view === v.key} onClick={() => onViewChange(v.key)}
                                className={`whitespace-nowrap rounded-full px-2.5 py-1.5 text-xs font-medium transition-colors sm:px-4 sm:text-sm ${view === v.key
                                    ? 'bg-white text-primary' : 'text-gray-300 hover:text-white'}`}>
                                {v.label}
                            </button>
                        ))}
                    </div>
                )}
                {view === 'map' && (
                    <button onClick={() => scrollTo('explore')} className="hidden transition-colors hover:text-white sm:block">Explore</button>
                )}
            </nav>

            <div className="hidden items-center gap-1.5 rounded-full border border-white/10 px-3 py-1.5 font-mono text-xs uppercase tracking-[0.08em] text-gray-300 sm:flex">
                <span>🇮🇳</span> India
            </div>
        </header>
    );
};

export default Header;
