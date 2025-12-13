import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, type Report } from '../api/client';
import { mockApi } from '../api/mock';
import { format } from 'date-fns';

// Toggle this to switch between mock and real API
const USE_MOCK_API = true;

export const Reports = () => {
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

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

  const openReportModal = (report: Report) => {
    setSelectedReport(report);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    // Delay clearing selected report for exit animation
    setTimeout(() => setSelectedReport(null), 300);
  };

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
              <button
                onClick={() => openReportModal(latestReport)}
                className="text-xs text-primary font-bold hover:underline cursor-pointer transition-colors"
              >
                View Full Report
              </button>
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
              <p className="text-red-400 text-xl font-bold font-mono">{latestReport.error_count.toLocaleString()}</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">Warnings</p>
              <p className="text-yellow-400 text-xl font-bold font-mono">{latestReport.warning_count.toLocaleString()}</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">Unique Patterns</p>
              <p className="text-white text-xl font-bold font-mono">{latestReport.unique_error_patterns}</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">New Patterns</p>
              <p className="text-blue-400 text-xl font-bold font-mono">{latestReport.new_error_patterns}</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">Anomalies</p>
              <p className="text-primary text-xl font-bold font-mono">{latestReport.anomalies_detected}</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">Critical Issues</p>
              <p className="text-red-500 text-xl font-bold font-mono">{latestReport.critical_issues}</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-text-muted text-xs mb-1">Status</p>
              <p className="text-green-400 text-sm font-bold uppercase">{latestReport.status}</p>
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
                    className="flex items-center gap-3 p-3 rounded-lg bg-black/20 border border-border-dark"
                  >
                    <div className="flex-shrink-0 flex items-center justify-center rounded-full bg-primary/20 p-1.5">
                      <span className="material-symbols-outlined text-primary text-[16px]">arrow_forward</span>
                    </div>
                    <p className="text-sm text-gray-200 leading-relaxed">{rec}</p>
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
                  <th className="px-6 py-3 font-bold">Warnings</th>
                  <th className="px-6 py-3 font-bold">Critical</th>
                  <th className="px-6 py-3 font-bold">Status</th>
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
                    <td className="px-6 py-4 text-red-400 font-mono">{report.error_count.toLocaleString()}</td>
                    <td className="px-6 py-4 text-yellow-400 font-mono">{report.warning_count.toLocaleString()}</td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center rounded bg-red-500/10 px-2 py-1 text-xs font-bold text-red-500 ring-1 ring-inset ring-red-500/20">
                        {report.critical_issues}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center rounded px-2 py-1 text-xs font-bold ring-1 ring-inset ${
                        report.status === 'completed' 
                          ? 'bg-green-500/10 text-green-400 ring-green-500/20' 
                          : 'bg-yellow-500/10 text-yellow-400 ring-yellow-500/20'
                      }`}>
                        {report.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => openReportModal(report)}
                        className="text-primary hover:text-white transition-colors cursor-pointer"
                        title="View Report Details"
                      >
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

      {/* Report Details Modal */}
      {isModalOpen && selectedReport && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={closeModal}
        >
          <div
            className="relative w-full max-w-4xl h-[90vh] flex flex-col bg-panel-dark border border-border-dark rounded-2xl shadow-2xl animate-in slide-in-from-bottom-4 zoom-in-95 duration-300"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex-shrink-0 flex items-center justify-between p-6 border-b border-border-dark bg-panel-dark">
              <div>
                <h2 className="text-2xl font-bold text-white font-display">
                  Analysis Report
                </h2>
                <p className="text-sm text-text-muted mt-1">
                  {format(new Date(selectedReport.report_date), 'MMMM d, yyyy')}
                </p>
              </div>
              <button
                onClick={closeModal}
                className="flex items-center justify-center w-10 h-10 rounded-lg bg-border-dark hover:bg-red-500/20 text-text-muted hover:text-red-400 transition-all cursor-pointer"
                title="Close"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            {/* Modal Content - Scrollable */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Executive Summary */}
              <div className="rounded-xl bg-gradient-to-br from-primary/5 to-transparent border border-primary/20 p-5">
                <h3 className="text-primary font-bold text-sm mb-3 uppercase tracking-wider flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px]">auto_awesome</span>
                  Executive Summary
                </h3>
                <p className="text-gray-200 text-sm leading-relaxed">
                  {selectedReport.executive_summary}
                </p>
              </div>

              {/* Statistics Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="rounded-xl bg-background-dark border border-border-dark p-4">
                  <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Total Logs</p>
                  <p className="text-2xl font-bold text-white font-mono">
                    {selectedReport.total_logs_processed.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-xl bg-background-dark border border-border-dark p-4">
                  <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Errors</p>
                  <p className="text-2xl font-bold text-red-400 font-mono">
                    {selectedReport.error_count.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-xl bg-background-dark border border-border-dark p-4">
                  <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Warnings</p>
                  <p className="text-2xl font-bold text-yellow-400 font-mono">
                    {selectedReport.warning_count.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-xl bg-background-dark border border-border-dark p-4">
                  <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Critical Issues</p>
                  <p className="text-2xl font-bold text-red-500 font-mono">
                    {selectedReport.critical_issues}
                  </p>
                </div>
                <div className="rounded-xl bg-background-dark border border-border-dark p-4">
                  <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Unique Patterns</p>
                  <p className="text-2xl font-bold text-blue-400 font-mono">
                    {selectedReport.unique_error_patterns}
                  </p>
                </div>
                <div className="rounded-xl bg-background-dark border border-border-dark p-4">
                  <p className="text-xs text-text-muted uppercase tracking-wider mb-2">New Patterns</p>
                  <p className="text-2xl font-bold text-blue-300 font-mono">
                    {selectedReport.new_error_patterns}
                  </p>
                </div>
                <div className="rounded-xl bg-background-dark border border-border-dark p-4">
                  <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Anomalies</p>
                  <p className="text-2xl font-bold text-primary font-mono">
                    {selectedReport.anomalies_detected}
                  </p>
                </div>
                <div className="rounded-xl bg-background-dark border border-border-dark p-4">
                  <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Status</p>
                  <p className={`text-lg font-bold uppercase ${
                    selectedReport.status === 'completed' ? 'text-green-400' : 'text-yellow-400'
                  }`}>
                    {selectedReport.status}
                  </p>
                </div>
              </div>

              {/* Top Issues */}
              {selectedReport.top_issues && selectedReport.top_issues.length > 0 && (
                <div className="rounded-xl bg-background-dark border border-border-dark p-5">
                  <h3 className="text-white font-bold text-base mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-red-400">error</span>
                    Top Issues
                  </h3>
                  <div className="space-y-3">
                    {selectedReport.top_issues.map((issue: any, index: number) => (
                      <div
                        key={index}
                        className="p-4 rounded-lg bg-panel-dark border border-border-dark hover:border-primary/30 transition-colors"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <h4 className="text-white font-semibold text-sm">
                            {issue.pattern_hash || `Issue #${index + 1}`}
                          </h4>
                          <span className="text-xs font-bold text-red-400 bg-red-400/10 px-2 py-1 rounded">
                            {issue.count || issue.occurrence_count || 0} occurrences
                          </span>
                        </div>
                        <p className="text-sm text-gray-300 font-mono">
                          {issue.normalized_message || issue.description}
                        </p>
                        {issue.services && (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {issue.services.map((service: string, idx: number) => (
                              <span
                                key={idx}
                                className="text-xs text-text-muted bg-border-dark px-2 py-1 rounded"
                              >
                                {service}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations */}
              {selectedReport.recommendations && selectedReport.recommendations.length > 0 && (
                <div className="rounded-xl bg-background-dark border border-border-dark p-5">
                  <h3 className="text-white font-bold text-base mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-green-400">playlist_add_check</span>
                    Recommended Actions
                  </h3>
                  <div className="space-y-2">
                    {selectedReport.recommendations.map((rec, index) => (
                      <div
                        key={index}
                        className="flex items-center gap-3 p-3 rounded-lg bg-panel-dark border border-border-dark"
                      >
                        <div className="flex-shrink-0 flex items-center justify-center rounded-full bg-green-400/20 p-1.5">
                          <span className="material-symbols-outlined text-green-400 text-[16px]">
                            check_circle
                          </span>
                        </div>
                        <p className="text-sm text-gray-200 leading-relaxed">{rec}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Affected Services */}
              {selectedReport.affected_services && selectedReport.affected_services.length > 0 && (
                <div className="rounded-xl bg-background-dark border border-border-dark p-5">
                  <h3 className="text-white font-bold text-base mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-blue-400">cloud_sync</span>
                    Affected Services
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {selectedReport.affected_services.map((service: string, index: number) => (
                      <span
                        key={index}
                        className="inline-flex items-center rounded-lg bg-blue-500/10 px-3 py-1.5 text-sm font-medium text-blue-400 ring-1 ring-inset ring-blue-500/20"
                      >
                        {service}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Metadata */}
              <div className="rounded-xl bg-background-dark border border-border-dark p-5">
                <h3 className="text-white font-bold text-base mb-4">Report Metadata</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-text-muted mb-1">Report Date</p>
                    <p className="text-white font-mono">
                      {format(new Date(selectedReport.report_date), 'MMM d, yyyy')}
                    </p>
                  </div>
                  <div>
                    <p className="text-text-muted mb-1">Generation Time</p>
                    <p className="text-white font-mono">
                      {selectedReport.generation_time_seconds.toFixed(2)}s
                    </p>
                  </div>
                  <div>
                    <p className="text-text-muted mb-1">Analysis Start Time</p>
                    <p className="text-white font-mono text-xs">
                      {format(new Date(selectedReport.start_time), 'MMM d, yyyy HH:mm:ss')}
                    </p>
                  </div>
                  <div>
                    <p className="text-text-muted mb-1">Analysis End Time</p>
                    <p className="text-white font-mono text-xs">
                      {format(new Date(selectedReport.end_time), 'MMM d, yyyy HH:mm:ss')}
                    </p>
                  </div>
                  {selectedReport.llm_model_used && (
                    <div>
                      <p className="text-text-muted mb-1">LLM Model</p>
                      <p className="text-white font-mono text-xs">
                        {selectedReport.llm_model_used}
                      </p>
                    </div>
                  )}
                  {selectedReport.tokens_used && (
                    <div>
                      <p className="text-text-muted mb-1">Tokens Used</p>
                      <p className="text-white font-mono">
                        {selectedReport.tokens_used.toLocaleString()}
                      </p>
                    </div>
                  )}
                  <div>
                    <p className="text-text-muted mb-1">Report ID</p>
                    <p className="text-white font-mono text-xs break-all">
                      {selectedReport.report_id}
                    </p>
                  </div>
                  <div>
                    <p className="text-text-muted mb-1">Created At</p>
                    <p className="text-white font-mono text-xs">
                      {format(new Date(selectedReport.created_at), 'MMM d, yyyy HH:mm:ss')}
                    </p>
                  </div>
                </div>
                {selectedReport.error_message && (
                  <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                    <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Error Message</p>
                    <p className="text-sm text-red-400 font-mono">{selectedReport.error_message}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex-shrink-0 flex items-center justify-end gap-3 p-6 border-t border-border-dark bg-panel-dark">
              <button
                onClick={closeModal}
                className="px-4 py-2 rounded-lg bg-border-dark hover:bg-border-dark/80 text-white font-medium transition-colors cursor-pointer"
              >
                Close
              </button>
              <button className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-background-dark font-bold transition-colors cursor-pointer flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px]">download</span>
                Export Report
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
