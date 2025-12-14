import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { Overview } from './pages/Overview';
import { LogStream } from './pages/LogStream';
import { SemanticSearch } from './pages/SemanticSearch';
import { Reports } from './pages/Reports';
import { Anomalies } from './pages/Anomalies';
import { Topology } from './pages/Topology';

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000, // 30 seconds
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<DashboardLayout />}>
            <Route index element={<Overview />} />
            <Route path="stream" element={<LogStream />} />
            <Route path="analysis" element={<SemanticSearch />} />
            <Route path="reports" element={<Reports />} />
            <Route path="anomalies" element={<Anomalies />} />
            <Route path="topology" element={<Topology />} />
            <Route path="settings" element={<div className="p-10 text-center text-gray-500">Settings page coming soon...</div>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          className: '',
          style: {
            borderRadius: '12px',
            padding: '14px 18px',
            boxShadow: '0 10px 40px rgba(0, 0, 0, 0.2)',
            fontFamily: 'Inter, sans-serif',
            fontSize: '14px',
            maxWidth: '420px',
            fontWeight: '500',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          },
          success: {
            duration: 3000,
            icon: <span className="material-symbols-outlined" style={{ fontSize: '24px', color: 'white' }}>check_circle</span>,
            style: {
              background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
              color: 'white',
              border: 'none',
            },
          },
          error: {
            duration: 5000,
            icon: <span className="material-symbols-outlined" style={{ fontSize: '24px', color: 'white' }}>cancel</span>,
            style: {
              background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
              color: 'white',
              border: 'none',
            },
          },
          loading: {
            icon: <span className="material-symbols-outlined toast-spin" style={{ fontSize: '24px', color: '#1a1a1a' }}>progress_activity</span>,
            style: {
              background: 'linear-gradient(135deg, #FACC15 0%, #EAB308 100%)',
              color: '#1a1a1a',
              border: 'none',
            },
          },
        }}
      />
    </QueryClientProvider>
  );
}

export default App;
