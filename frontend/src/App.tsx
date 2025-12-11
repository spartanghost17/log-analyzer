import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { Overview } from './pages/Overview';
import { LogStream } from './pages/LogStream';
import { SemanticSearch } from './pages/SemanticSearch';
import { Reports } from './pages/Reports';

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
            <Route path="anomalies" element={<div className="p-10 text-center text-text-muted">Anomalies page coming soon...</div>} />
            <Route path="settings" element={<div className="p-10 text-center text-text-muted">Settings page coming soon...</div>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
