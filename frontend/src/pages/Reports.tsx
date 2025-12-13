import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { mockApi } from '../api/mock';
import { format } from 'date-fns';

// Toggle this to switch between mock and real API
const USE_MOCK_API = true;

export const Reports = () => {
  const { data: reportsData, isLoading } = useQuery({
    queryKey: ['reports'],
    queryFn: () => USE_MOCK_API ? mockApi.getReports({ limit: 10 }) : api.getReports({ limit: 10 }),
  });

  const { data: latestReport } = useQuery({
    queryKey: ['latest-report'],
    queryFn: () => USE_MOCK_API ? mockApi.getLatestReport() : api.getLatestReport(),
    retry: false,
  });

  const reports = reportsData?.reports || [];

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-white tracking-tight text-[28px] font-bold leading-tight font-display">
            Analysis Reports & Trends
          </h1>
          <p className="text-text-muted text-sm font-normal mt-1">
            View AI-generated log analysis reports and identify trends over time.
          </p>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-primary hover:bg-primary/90 text-background-dark px-4 py-2 transition-colors font-bold text-sm cursor-pointer">
          <span className="material-symbols-outlined">add</span>
          Generate New Report
        </button>
      </div>

      {/* Latest Report Card */}
      {latestReport && (
        <div className="rounded-xl border border-primary/30 bg-gradient-to-br from-panel-dark to-background-dark p-6 shadow-lg">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                <span className="material-symbols-outlined">auto_awesome</span>
              </div>
              <div>
                <h3 className="text-white font-bold text-lg">Latest Analysis Report</h3>
                <p className="text-text-muted text-sm">
                  Generated on {format(new Date(latestReport.report_date), 'MMMM d, yyyy')}
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              <button className="text-xs text-primary font-bold hover:underline cursor-pointer">View Full Report</button>
            </div>
          </div>

          {/* Executive Summary */}
          <div className="bg-black/20 rounded-lg p-4 mb-4">
            <h4 className="text-primary font-bold text-sm mb-2 uppercase tracking-wider">Executive Summary</h4>
            <p className="text-gray-200 text-sm leading-relaxed">{latestReport.executive_summary}</p>
          </div>

          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">Total Logs</p>
              <p className="text-white text-xl font-bold font-mono">
                {latestReport.total_logs_processed.toLocaleString()}
              </p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">Errors Found</p>
              <p className="text-white text-xl font-bold font-mono">{latestReport.error_count.toLocaleString()}</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">Unique Patterns</p>
              <p className="text-white text-xl font-bold font-mono">{latestReport.unique_error_patterns}</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">Anomalies</p>
              <p className="text-primary text-xl font-bold font-mono">{latestReport.anomalies_detected}</p>
            </div>
          </div>

          {/* Recommendations */}
          {latestReport.recommendations && latestReport.recommendations.length > 0 && (
            <div className="mt-4">
              <h4 className="text-white font-bold text-sm mb-2 flex items-center gap-2">
                <span className="material-symbols-outlined text-green-400">playlist_add_check</span>
                Recommended Actions
              </h4>
              <div className="space-y-2">
                {latestReport.recommendations.map((rec, index) => (
                  <div
                    key={index}
                    className="flex items-start gap-2 p-3 rounded-lg bg-black/20 border border-border-dark"
                  >
                    <div className="mt-0.5 rounded-full bg-primary/20 p-1">
                      <span className="material-symbols-outlined text-primary text-sm">arrow_forward</span>
                    </div>
                    <p className="text-sm text-gray-200">{rec}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Reports History */}
      <div className="rounded-xl border border-border-dark bg-panel-dark overflow-hidden">
        <div className="flex items-center justify-between border-b border-border-dark px-6 py-4">
          <h3 className="text-lg font-bold text-white">Report History</h3>
          <div className="flex items-center gap-2">
            <select className="bg-background-dark border border-border-dark rounded-lg px-3 py-1.5 text-white text-sm cursor-pointer">
              <option>Last 30 days</option>
              <option>Last 7 days</option>
              <option>Last 24 hours</option>
            </select>
          </div>
        </div>

        {isLoading ? (
          <div className="p-12 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : reports.length === 0 ? (
          <div className="p-12 text-center text-text-muted">
            <span className="material-symbols-outlined text-[64px] mb-4">description</span>
            <p>No reports found</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-background-dark text-xs uppercase text-text-muted">
                <tr>
                  <th className="px-6 py-3 font-bold">Report Date</th>
                  <th className="px-6 py-3 font-bold">Logs Processed</th>
                  <th className="px-6 py-3 font-bold">Errors</th>
                  <th className="px-6 py-3 font-bold">Patterns</th>
                  <th className="px-6 py-3 font-bold">Anomalies</th>
                  <th className="px-6 py-3 font-bold">Generation Time</th>
                  <th className="px-6 py-3 font-bold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-dark">
                {reports.map((report) => (
                  <tr key={report.report_id} className="hover:bg-border-dark/30 transition-colors">
                    <td className="px-6 py-4 text-white font-medium">
                      {format(new Date(report.report_date), 'MMM d, yyyy')}
                    </td>
                    <td className="px-6 py-4 text-text-muted font-mono">
                      {report.total_logs_processed.toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-text-muted font-mono">{report.error_count.toLocaleString()}</td>
                    <td className="px-6 py-4 text-text-muted font-mono">{report.unique_error_patterns}</td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center rounded bg-primary/10 px-2 py-1 text-xs font-bold text-primary ring-1 ring-inset ring-primary/20">
                        {report.anomalies_detected}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-text-muted font-mono">
                      {report.generation_time_seconds.toFixed(1)}s
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button className="text-primary hover:text-white transition-colors cursor-pointer">
                        <span className="material-symbols-outlined text-[20px]">visibility</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
