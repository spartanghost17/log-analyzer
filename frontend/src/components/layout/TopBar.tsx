import React from 'react';

export const TopBar = ({ title = 'Dashboard Overview' }: { title?: string }) => {
    return (
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-border-dark bg-header px-6">
            {/* Breadcrumbs */}
            <div className="flex items-center gap-4">
                <div className="flex items-center text-text-muted">
                    <span className="material-symbols-outlined text-[20px]">home</span>
                    <span className="mx-2 text-sm">/</span>
                    <span className="text-sm font-medium text-white">{title}</span>
                </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-4">
                {/* Live Status */}
                <div className="hidden md:flex items-center gap-2 rounded-full border border-success/30 bg-success/10 px-3 py-1 text-xs font-bold text-success ring-1 ring-emerald-500/20">
                    <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-success"></span>
                    </span>
                    SYSTEM ONLINE
                </div>

                {/* Time Picker Mock */}
                <div className="flex items-center gap-1 rounded-lg bg-panel-light p-1 border border-border-dark">
                    <button className="px-3 py-1.5 rounded text-sm font-bold text-background-dark bg-primary cursor-pointer">24h</button>
                    <button className="px-3 py-1.5 rounded text-sm font-medium text-text-muted hover:text-white transition-colors cursor-pointer">7d</button>
                    <button className="px-3 py-1.5 rounded text-sm font-medium text-text-muted hover:text-white transition-colors cursor-pointer">30d</button>
                </div>

                {/* Global Actions */}
                <button className="flex h-9 w-9 items-center justify-center rounded-lg bg-border-dark text-text-muted hover:text-white transition-colors hover:bg-border-dark/80 cursor-pointer">
                    <span className="material-symbols-outlined text-[20px]">refresh</span>
                </button>
            </div>
        </header>
    );
};
