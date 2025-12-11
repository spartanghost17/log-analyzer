import React from 'react';
import { NavLink } from 'react-router-dom';

const NavItem = ({ to, icon, label }: { to: string; icon: string; label: string }) => (
    <NavLink
        to={to}
        className={({ isActive }) =>
            `group flex items-center gap-3 px-3 py-3 rounded-lg transition-colors ${isActive
                ? 'bg-primary text-background-dark'
                : 'text-text-muted hover:bg-border-dark hover:text-white'
            }`
        }
        title={label}
    >
        <span className="material-symbols-outlined text-[24px]">{icon}</span>
        <span className="hidden lg:block text-sm font-bold">{label}</span>
    </NavLink>
);

export const Sidebar = () => {
    return (
        <aside className="w-20 lg:w-64 flex flex-col items-center lg:items-stretch border-r border-border-dark bg-background-dark py-6 lg:px-4 shrink-0 transition-all duration-300">
            {/* Brand */}
            <div className="flex items-center gap-3 px-2 mb-8">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary">
                    <span className="material-symbols-outlined text-[24px]">bubble_chart</span>
                </div>
                <div className="hidden lg:flex flex-col">
                    <h1 className="text-lg font-bold leading-tight tracking-tight text-white font-display">SYNAPS</h1>
                    <p className="text-xs font-medium text-text-muted">Log Analysis System</p>
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex flex-1 flex-col gap-2">
                <NavItem to="/" icon="dashboard" label="Dashboard" />
                <NavItem to="/stream" icon="stream" label="Log Stream" />
                <NavItem to="/analysis" icon="manage_search" label="Analysis" />
                <NavItem to="/reports" icon="description" label="Reports" />
                <NavItem to="/anomalies" icon="warning" label="Anomalies" />
            </nav>

            {/* Bottom Actions */}
            <div className="flex flex-col gap-2 border-t border-border-dark pt-6 mt-auto">
                <NavItem to="/settings" icon="settings" label="Settings" />
                <div className="px-3 py-3 flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-border-dark border border-white/10 flex items-center justify-center text-text-muted font-bold text-xs">
                        JD
                    </div>
                    <div className="hidden lg:flex flex-col">
                        <span className="text-sm font-bold text-white">John Doe</span>
                        <span className="text-xs text-text-muted">Admin</span>
                    </div>
                </div>
            </div>
        </aside>
    );
};
