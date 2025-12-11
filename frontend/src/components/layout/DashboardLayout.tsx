import React from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { Outlet } from 'react-router-dom';

export const DashboardLayout = () => {
    return (
        <div className="flex h-screen w-full overflow-hidden bg-background-dark text-white font-body selection:bg-primary selection:text-black">
            <Sidebar />
            <main className="flex flex-1 flex-col overflow-hidden relative">
                <TopBar />
                <div className="flex-1 overflow-y-auto p-6 md:p-8 custom-scrollbar">
                    <Outlet />
                </div>
            </main>
        </div>
    );
};
