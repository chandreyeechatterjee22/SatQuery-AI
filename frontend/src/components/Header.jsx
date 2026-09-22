import React from 'react';
import { FaSatellite } from 'react-icons/fa6';

const Header = () => {
    const scrollTo = (id) => {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    };

    return (
        <header className="flex items-center justify-between px-6 py-3 bg-space-800/95 backdrop-blur-xl border-b border-space-700/60 text-white">
            <div className="flex items-center gap-2">
                <FaSatellite className="text-accent-cyan" size={22} />
                <span className="text-lg font-bold tracking-tight">
                    SatQuery <span className="bg-gradient-to-r from-accent-cyan to-accent-blue bg-clip-text text-transparent">AI</span>
                </span>
            </div>

            <nav className="hidden sm:flex items-center gap-8 text-sm font-medium text-gray-300">
                <button onClick={() => scrollTo('explore')} className="hover:text-accent-cyan transition-colors">Explore</button>
            </nav>

            <div className="hidden sm:flex items-center gap-1.5 text-sm text-gray-300 px-3 py-1.5 rounded-lg border border-space-700 bg-space-900/60">
                <span>🇮🇳</span> India
            </div>
        </header>
    );
};

export default Header;
