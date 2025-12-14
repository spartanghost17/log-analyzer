import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';

const NavItem = ({ to, icon, label }: { to: string; icon: string; label: string }) => {
  const location = useLocation();
  const isActive = location.pathname === to || (to !== '/' && location.pathname.startsWith(to));

  return (
    <NavLink
      to={to}
      className={`group relative h-10 w-10 mx-auto flex items-center justify-center rounded-lg transition-all ${
        isActive
          ? 'bg-primary text-black shadow-[0_0_15px_rgba(253,224,71,0.3)]'
          : 'text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800'
      }`}
      title={label}
    >
      <span className="material-icons-outlined text-xl">{icon}</span>
      <span className="absolute left-full ml-2 px-2 py-1 bg-gray-800 text-xs text-white rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 transition-opacity">
        {label}
      </span>
    </NavLink>
  );
};

export const Sidebar = () => {
  return (
    <aside className="w-16 md:w-20 bg-white dark:bg-surface-darker border-r border-gray-200 dark:border-gray-800 flex flex-col items-center py-6 gap-6 z-20 flex-shrink-0">
      {/* Brand */}
      <div className="mb-4">
        <div className="w-10 h-10 rounded-xl bg-primary/20 flex items-center justify-center text-primary cursor-pointer hover:bg-primary/30 transition">
          <span className="material-icons-outlined text-2xl">psychology</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-4 w-full px-2">
        <NavItem to="/" icon="grid_view" label="Dashboard" />
        <NavItem to="/stream" icon="dns" label="Data Cortex" />
        <NavItem to="/analysis" icon="search" label="Cognitive Search" />
        <NavItem to="/reports" icon="article" label="Insight Pathways" />
        <NavItem to="/anomalies" icon="timeline" label="Metrics" />
        <NavItem to="/topology" icon="hub" label="Topology" />
      </nav>

      {/* Bottom Actions */}
      <div className="mt-auto flex flex-col gap-4">
        <button className="h-10 w-10 mx-auto flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
          <span className="material-icons-outlined text-xl">settings</span>
        </button>
        <div className="h-8 w-8 mx-auto rounded-full bg-gradient-to-tr from-primary to-orange-400 border border-white dark:border-gray-700"></div>
      </div>
    </aside>
  );
};
