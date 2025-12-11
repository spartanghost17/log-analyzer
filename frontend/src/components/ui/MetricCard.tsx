import React from 'react';

interface MetricCardProps {
    label: string;
    value: string | number;
    icon: string;
    trend?: string;
    loading?: boolean;
}

export const MetricCard = ({ label, value, icon, trend, loading }: MetricCardProps) => {
    return (
        <div className="rounded-xl border border-border-dark bg-panel-light p-5 shadow-sm relative overflow-hidden group hover:border-border-dark/80 transition-colors">
            <div className="mb-2 flex items-center justify-between z-10 relative">
                <p className="text-sm font-medium text-text-muted uppercase tracking-wider">{label}</p>
                <span className="material-symbols-outlined text-text-muted text-[20px] group-hover:text-white transition-colors">{icon}</span>
            </div>

            {loading ? (
                <div className="h-8 w-2/3 rounded bg-border-dark animate-pulse"></div>
            ) : (
                <div className="flex flex-col gap-1 z-10 relative">
                    <span className="text-3xl font-bold text-white font-display tracking-tight">{value}</span>
                    {trend && (
                        <span className="text-xs text-text-muted font-medium">{trend}</span>
                    )}
                </div>
            )}

            {/* Decorative Sparkline Background (Optional visual flair) */}
            <div className="absolute bottom-0 right-0 w-24 h-12 opacity-5 translate-y-2 translate-x-2">
                <svg viewBox="0 0 100 50" className="w-full h-full fill-current text-white">
                    <path d="M0,50 L0,20 L10,30 L20,10 L30,40 L40,20 L50,30 L60,10 L70,40 L80,20 L90,30 L100,0 L100,50 Z" />
                </svg>
            </div>
        </div>
    );
};
