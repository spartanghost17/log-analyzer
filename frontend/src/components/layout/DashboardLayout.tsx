import React from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { Outlet } from 'react-router-dom';

export const DashboardLayout = () => {
  return (
    <div className="bg-background-light dark:bg-background-dark text-gray-900 dark:text-gray-100 font-sans antialiased h-screen flex overflow-hidden transition-colors duration-200">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar />
        <div className="flex-1 overflow-y-auto p-6 scroll-smooth bg-background-light dark:bg-background-dark">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
