import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tantml:parameter>
import { api, Report } from '../api/client';
import { mockApi } from '../api/mock';
import { format, subDays, startOfDay, endOfDay } from 'date-fns';
import Chart from 'chart.js/auto';

// Toggle this to switch between mock and real API
const USE_MOCK_API = false;

type TimeRange = '30days' | '7days' | 'today';

export const Reports = () => {
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [selectedService, setSelectedService] = useState<string>('');
  const [selectedLevel, setSelectedLevel] = useState<string>('ERROR');
  const [timeRange, setTimeRange] = useState<TimeRange>('30days');
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const chartRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstance = useRef<Chart | null>(null);

  // Calculate date range based on selected time range
  const getDateRange = () => {
    const now = new Date();
    const today = startOfDay(now);
    
    switch (timeRange) {
      case 'today':
        return {
          date_from: format(today, 'yyyy-MM-dd'),
          date_to: format(today, 'yyyy-MM-dd'),
        };
      case '7days':
        return {
          date_from: format(subDays(today, 6), 'yyyy-MM-dd'),
          date_to: format(today, 'yyyy-MM-dd'),
        };
      case '30days':
      default:
        return {
          date_from: format(subDays(today, 29), 'yyyy-MM-dd'),
          date_to: format(today, 'yyyy-MM-dd'),
        };
    }
  };

  // Fetch all reports for the timeline
  const { data: reportsData, isLoading } = useQuery({
    queryKey: ['reports', timeRange],
    queryFn: () => {
      const { date_from, date_to } = getDateRange();
      return USE_MOCK_API 
        ? mockApi.getReports({ limit: 100, date_from, date_to }) 
        : api.getReports({ limit: 100, date_from, date_to });
    },
  });

  const reports = reportsData?.reports || [];

  // Get the selected report or default to the latest
  const report = selectedReportId 
    ? reports.find(r => r.report_id === selectedReportId) 
    : reports[0];

  // Extract unique services and levels from report
  const availableServices = report?.affected_services?.services || [];
  const availableLevels = ['ERROR', 'WARN', 'FATAL', 'INFO'];

  // Set default selected report to the latest one
  useEffect(() => {
    if (reports.length > 0 && !selectedReportId) {
      setSelectedReportId(reports[0].report_id);
    }
  }, [reports, selectedReportId]);

  // Set default service when report loads
  useEffect(() => {
    if (report && availableServices.length > 0 && !selectedService) {
      setSelectedService(availableServices[0]);
    }
  }, [report, availableServices, selectedService]);

  const { data: anomalyData } = useQuery({
    queryKey: ['anomaly-zscore', report?.start_time, selectedService, selectedLevel],
    queryFn: () => {
      const params = report?.start_time ? { 
        service: selectedService || undefined,
        level: selectedLevel,
        report_start_time: report.start_time 
      } : {};
      return USE_MOCK_API ? mockApi.getAnomalyZScoreData(params) : api.getAnomalyZScoreData(params);
    },
    enabled: !!report, // Only fetch when report is available
    retry: false,
  });

  // Helper function to get report status text
  const getReportStatusText = (report: Report): string => {
    if (report.critical_issues > 0) {
      return `${report.critical_issues} Critical ${report.critical_issues === 1 ? 'Issue' : 'Issues'}`;
    }
    if (report.anomalies_detected > 0) {
      return `${report.anomalies_detected} ${report.anomalies_detected === 1 ? 'Anomaly' : 'Anomalies'}`;
    }
    if (report.error_count === 0 && report.warning_count === 0) {
      return 'System Stable';
    }
    return `${report.error_count} Errors`;
  };

  // Initialize Z-Score Anomaly Detection Chart
  useEffect(() => {
    if (chartRef.current && anomalyData) {
      const ctx = chartRef.current.getContext('2d');
      if (ctx) {
        // Destroy existing chart instance if it exists
        if (chartInstance.current) {
          chartInstance.current.destroy();
        }

        // Extract data from API response
        const dataPoints = anomalyData.data_points || [];
        const threshold = anomalyData.threshold || 1.0;
        
        const labels = dataPoints.map((dp: any) => dp.index);
        const data = dataPoints.map((dp: any) => dp.z_score);

        // Color points based on anomaly status (yellow for outliers)
        const pointColors = data.map((val: number) => Math.abs(val) > threshold ? '#FDE047' : '#4B5563');
        const pointRadii = data.map((val: number) => Math.abs(val) > threshold ? 4 : 2);

        // Register custom plugin to add glow to anomaly points
        const glowPlugin = {
          id: 'glowPlugin',
          beforeDatasetsDraw: (chart: any) => {
            const ctx = chart.ctx;
            const meta = chart.getDatasetMeta(0);
            
            meta.data.forEach((point: any, index: number) => {
              const value = data[index];
              if (Math.abs(value) > threshold) {
                // Save context
                ctx.save();
                
                // Add glow effect for anomaly points
                ctx.shadowColor = '#FDE047';
                ctx.shadowBlur = 15;
                ctx.shadowOffsetX = 0;
                ctx.shadowOffsetY = 0;
                
                // Draw glowing point
                ctx.beginPath();
                ctx.arc(point.x, point.y, 4, 0, 2 * Math.PI);
                ctx.fillStyle = '#FDE047';
                ctx.fill();
                
                // Restore context
                ctx.restore();
              }
            });
          },
        };

        chartInstance.current = new Chart(ctx, {
          type: 'scatter',
          data: {
            labels: labels,
            datasets: [
              {
                label: 'Z-Score',
                data: data.map((y: number, x: number) => ({ x, y })),
                borderColor: '#374151',
                borderWidth: 1,
                showLine: true,
                pointBackgroundColor: pointColors,
                pointBorderColor: pointColors,
                pointRadius: pointRadii,
                pointHoverRadius: 6,
                tension: 0.1,
                segment: {
                  borderColor: '#374151',
                  borderDash: [2, 2],
                },
              },
              // Add a zero baseline line
              {
                type: 'line',
                label: 'Baseline',
                data: Array(dataPoints.length).fill(0),
                borderColor: 'rgba(255, 255, 255, 0.1)',
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
              },
            ],
          },
          plugins: [glowPlugin],
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                display: false,
              },
              tooltip: {
                mode: 'index',
                intersect: false,
                backgroundColor: '#1F2937',
                titleColor: '#F3F4F6',
                bodyColor: '#D1D5DB',
                borderColor: '#374151',
                borderWidth: 1,
              },
            },
            scales: {
              x: {
                display: false,
                grid: {
                  display: false,
                },
              },
              y: {
                grid: {
                  color: 'rgba(55, 65, 81, 0.3)',
                },
                ticks: {
                  color: '#6B7280',
                  font: {
                    size: 10,
                  },
                },
                suggestedMin: -2,
                suggestedMax: 4,
              },
            },
            layout: {
              padding: {
                left: 0,
                right: 0,
                top: 10,
                bottom: 10,
              },
            },
          },
        });
      }
    }

    return () => {
      if (chartInstance.current) {
        chartInstance.current.destroy();
      }
    };
  }, [anomalyData]);

  return (
    <div className="flex gap-0 h-full -m-6">
      {/* Timeline Sidebar */}
      <aside className="w-64 bg-white dark:bg-surface-dark border-r border-gray-200 dark:border-border-dark flex flex-col flex-shrink-0 overflow-hidden">
        <div className="p-4 border-b border-gray-200 dark:border-border-dark">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200">Timeline</h2>
            <div className="text-xs text-gray-500">{reports.length} {reports.length === 1 ? 'report' : 'reports'}</div>
          </div>
          <div className="relative">
            <span className="absolute inset-y-0 left-0 flex items-center pl-2">
              <span className="material-symbols-outlined text-gray-500 text-xs">calendar_today</span>
            </span>
            <select 
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as TimeRange)}
              className="w-full bg-gray-100 dark:bg-surface-darker border-none rounded text-xs py-1.5 pl-8 pr-2 text-gray-700 dark:text-gray-300 focus:ring-0 cursor-pointer"
            >
              <option value="30days">Last 30 Days</option>
              <option value="7days">Last 7 Days</option>
              <option value="today">Today</option>
            </select>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
            </div>
          ) : reports.length === 0 ? (
            <div className="text-center py-8 px-4">
              <span className="material-symbols-outlined text-gray-400 text-2xl mb-2">description</span>
              <p className="text-xs text-gray-500">No reports found</p>
            </div>
          ) : (
            <div className="px-4 py-2">
              <div className="relative pl-4 border-l border-gray-300 dark:border-gray-700 space-y-6">
                {reports.map((reportItem) => {
                  const isActive = reportItem.report_id === (selectedReportId || reports[0]?.report_id);
                  const reportDate = new Date(reportItem.report_date);
                  
                  return (
                    <div
                      key={reportItem.report_id}
                      onClick={() => setSelectedReportId(reportItem.report_id)}
                      className={`relative group cursor-pointer ${isActive ? '' : 'opacity-70 hover:opacity-100'} transition-opacity`}
                    >
                      <div
                        className={`absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full transition-all ${
                          isActive
                            ? 'bg-primary ring-4 ring-primary/20'
                            : 'bg-gray-400 dark:bg-gray-600 group-hover:bg-gray-300 dark:group-hover:bg-gray-400 border border-gray-200 dark:border-surface-dark'
                        }`}
                      ></div>
                      <h3 className={`text-sm font-medium ${isActive ? 'text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-300'}`}>
                        {format(reportDate, 'MMM d')}
                      </h3>
                      <p className={`text-xs mt-0.5 ${
                        reportItem.critical_issues > 0 ? 'text-red-500' :
                        reportItem.anomalies_detected > 0 ? 'text-yellow-500' :
                        'text-gray-500'
                      }`}>
                        {getReportStatusText(reportItem)}
                      </p>
                      {reportItem.status === 'failed' && (
                        <p className="text-xs text-red-400 mt-0.5">
                          <span className="material-symbols-outlined text-[10px]">error</span> Failed
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-200 dark:border-gray-800">
          <div className="text-xs text-gray-500 text-center mb-2">
            {report && format(new Date(report.report_date), 'MMM d, yyyy')}
          </div>
        </div>
      </aside>

      {/* Main Report Content */}
      <main className="flex-1 overflow-y-auto py-6 pr-6 relative min-h-0">
        {/* Grid background */}
        <div
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{
            backgroundImage:
              'linear-gradient(to right, #1f2937 1px, transparent 1px), linear-gradient(to bottom, #1f2937 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
        ></div>

        <div className="max-w-5xl mx-auto space-y-6 relative z-0">
          {!report && isLoading ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
            </div>
          ) : !report ? (
            <div className="text-center py-20 text-gray-500 dark:text-gray-400">
              <span className="material-symbols-outlined text-[64px] mb-4">description</span>
              <p>No reports available</p>
            </div>
          ) : (
            <>
              {/* Report Header */}
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center space-x-3 mb-1">
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                      Analysis Report: {format(new Date(report.report_date), 'MMM d, yyyy')}
                    </h1>
                    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/20">
                      Critical Attention Needed
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Generated automatically by Synaps Core Engine at 04:00 UTC
                  </p>
                </div>
                <div className="flex space-x-2">
                  <button 
                    onClick={() => setShowDetailsModal(true)}
                    className="flex items-center px-3 py-2 text-sm bg-white dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 transition-colors cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-sm mr-2">visibility</span> Full Details
                  </button>
                  <button className="flex items-center px-3 py-2 text-sm bg-white dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 transition-colors cursor-pointer">
                    <span className="material-symbols-outlined text-sm mr-2">share</span> Share
                  </button>
                  <button className="flex items-center px-3 py-2 text-sm bg-primary text-black font-semibold rounded hover:bg-primary-hover transition-colors shadow-lg shadow-primary/20 cursor-pointer">
                    <span className="material-symbols-outlined text-sm mr-2">download</span> Export PDF
                  </button>
                </div>
              </div>

              {/* Executive Summary */}
              <div className="bg-white dark:bg-surface-dark rounded-xl shadow-sm border border-gray-200 dark:border-border-dark p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
                  <span className="material-symbols-outlined text-primary mr-2 text-xl">insights</span>
                  Executive Summary
                </h2>
                <div className="prose dark:prose-invert max-w-none text-sm text-gray-600 dark:text-gray-400 leading-relaxed space-y-4">
                  {report.executive_summary.split('\n\n').map((paragraph, pIdx) => (
                    <p key={pIdx}>
                      {paragraph.split('\n').map((line, lIdx) => (
                        <span key={lIdx}>
                          {lIdx > 0 && <br />}
                          {line.split(' ').map((word, wIdx) => {
                            const highlightWords = ['eviction', 'spike', 'deviations', 'timeout', 'critical', 'database', 'error', 'failure', 'failed'];
                            const shouldHighlight = highlightWords.some(hw => word.toLowerCase().includes(hw.toLowerCase()));
                            return shouldHighlight ? (
                              <span key={wIdx} className="bg-primary/15 text-primary px-0.5 rounded font-medium">
                                {word}{' '}
                              </span>
                            ) : (
                              word + ' '
                            );
                          })}
                        </span>
                      ))}
                    </p>
                  ))}
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
                  <div className="p-4 rounded-lg bg-gray-100 dark:bg-surface-darker border border-gray-200 dark:border-gray-800/50">
                    <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Anomaly Confidence</div>
                    <div className="text-2xl font-bold text-gray-900 dark:text-white">98.4%</div>
                    <div className="mt-2 w-full bg-gray-300 dark:bg-gray-800 rounded-full h-1.5">
                      <div className="bg-primary h-1.5 rounded-full" style={{ width: '98%' }}></div>
                    </div>
                  </div>
                  <div className="p-4 rounded-lg bg-gray-100 dark:bg-surface-darker border border-gray-200 dark:border-gray-800/50">
                    <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Affected Services</div>
                    <div className="text-2xl font-bold text-gray-900 dark:text-white">
                      {report.affected_services?.count || 0}
                    </div>
                    <div className="flex space-x-1 mt-2">
                      <span className="w-2 h-2 rounded-full bg-red-500"></span>
                      <span className="w-2 h-2 rounded-full bg-red-500"></span>
                      <span className="w-2 h-2 rounded-full bg-yellow-500"></span>
                      <span className="w-2 h-2 rounded-full bg-green-500"></span>
                    </div>
                  </div>
                  <div className="p-4 rounded-lg bg-gray-100 dark:bg-surface-darker border border-gray-200 dark:border-gray-800/50">
                    <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Est. Recovery Time</div>
                    <div className="text-2xl font-bold text-gray-900 dark:text-white">~12m</div>
                    <div className="text-xs text-green-400 mt-1 flex items-center">
                      <span className="material-symbols-outlined text-[10px] mr-1">arrow_downward</span> 5m vs avg
                    </div>
                  </div>
                </div>
              </div>

              {/* Z-Score Anomaly Detection Chart */}
              <div className="bg-white dark:bg-surface-dark rounded-xl shadow-sm border border-gray-200 dark:border-border-dark p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Z-Score Anomaly Detection</h2>
                  <div className="flex items-center space-x-2">
                    <span className="flex items-center text-xs text-gray-500">
                      <span className="w-2 h-2 rounded-full bg-primary mr-2"></span> Outlier
                    </span>
                    <span className="flex items-center text-xs text-gray-500">
                      <span className="w-2 h-2 rounded-full bg-gray-600 mr-2"></span> Baseline
                    </span>
                  </div>
                </div>
                
                {/* Filter Controls */}
                <div className="flex items-center gap-3 mb-6 pb-4 border-b border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Service:</label>
                    <select
                      value={selectedService}
                      onChange={(e) => setSelectedService(e.target.value)}
                      className="text-xs px-3 py-1.5 bg-gray-100 dark:bg-surface-darker border border-gray-300 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
                    >
                      <option value="">All Services</option>
                      {availableServices.map((service) => (
                        <option key={service} value={service}>
                          {service}
                        </option>
                      ))}
                    </select>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-medium text-gray-600 dark:text-gray-400">Level:</label>
                    <select
                      value={selectedLevel}
                      onChange={(e) => setSelectedLevel(e.target.value)}
                      className="text-xs px-3 py-1.5 bg-gray-100 dark:bg-surface-darker border border-gray-300 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
                    >
                      {availableLevels.map((level) => (
                        <option key={level} value={level}>
                          {level}
                        </option>
                      ))}
                    </select>
                  </div>
                  
                  {anomalyData && (
                    <div className="ml-auto flex items-center gap-4 text-xs text-gray-500">
                      <span className="flex items-center gap-1">
                        <span className="material-symbols-outlined text-xs">schedule</span>
                        {anomalyData.metadata?.hours || 24}h window
                      </span>
                      <span className="flex items-center gap-1">
                        <span className="material-symbols-outlined text-xs text-yellow-500">warning</span>
                        {anomalyData.anomaly_count || 0} anomalies
                      </span>
                    </div>
                  )}
                </div>
                <div className="h-64 w-full relative">
                  <canvas ref={chartRef} id="anomalyChart"></canvas>
                </div>
                <div className="flex justify-between text-xs text-gray-500 mt-2 px-2">
                  <span>00:00</span>
                  <span>06:00</span>
                  <span>12:00</span>
                  <span>18:00</span>
                  <span>24:00</span>
                </div>
              </div>

              {/* Recommended Actions & Root Cause */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pb-8">
                {/* Recommended Actions */}
                <div className="bg-white dark:bg-surface-dark rounded-xl shadow-sm border border-gray-200 dark:border-border-dark p-6">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-4">
                    Recommended Actions
                  </h3>
                  <ul className="space-y-3">
                    {(report.recommendations || [
                      'Increase Redis memory allocation',
                      'Restart Service: Auth-Provider',
                    ]).slice(0, 2).map((rec, idx) => (
                      <li
                        key={idx}
                        className="flex items-start p-3 bg-gray-50 dark:bg-surface-darker rounded border border-gray-200 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-600 transition-colors cursor-pointer group"
                      >
                        <span className="material-symbols-outlined text-primary text-sm mt-0.5 mr-3">bolt</span>
                        <div>
                          <p className="text-sm text-gray-800 dark:text-gray-200 font-medium group-hover:text-primary transition-colors whitespace-pre-line">
                            {rec}
                          </p>
                          <p className="text-xs text-gray-500">
                            {idx === 0 ? 'Scaling to 4GB limits eviction risks.' : 'Clear accumulated thread locks.'}
                          </p>
                        </div>
                        <span className="ml-auto material-symbols-outlined text-gray-400 dark:text-gray-600 text-sm">
                          chevron_right
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Root Cause Probability */}
                <div className="bg-white dark:bg-surface-dark rounded-xl shadow-sm border border-gray-200 dark:border-border-dark p-6">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-4">
                    Root Cause Probability
                  </h3>
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-gray-700 dark:text-gray-300">Memory Leak (Redis Module)</span>
                        <span className="text-primary">85%</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-surface-darker rounded-full h-2">
                        <div
                          className="bg-gradient-to-r from-yellow-600 to-primary h-2 rounded-full"
                          style={{ width: '85%' }}
                        ></div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-gray-700 dark:text-gray-300">Network Latency Spike</span>
                        <span className="text-gray-500 dark:text-gray-400">12%</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-surface-darker rounded-full h-2">
                        <div className="bg-gray-500 dark:bg-gray-600 h-2 rounded-full" style={{ width: '12%' }}></div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-gray-700 dark:text-gray-300">Database Lock Contention</span>
                        <span className="text-gray-500 dark:text-gray-400">3%</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-surface-darker rounded-full h-2">
                        <div className="bg-gray-500 dark:bg-gray-600 h-2 rounded-full" style={{ width: '3%' }}></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>

      {/* Full Details Modal */}
      {showDetailsModal && (
        <div className="fixed inset-0 z-50 overflow-hidden flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in-up">
          <div className="relative w-full max-w-6xl max-h-[90vh] m-4 bg-white dark:bg-surface-dark rounded-2xl shadow-2xl flex flex-col border border-gray-200 dark:border-border-dark">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-border-dark">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
                  <span className="material-symbols-outlined text-primary">description</span>
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                    Complete Analysis Report
                  </h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {report ? format(new Date(report.report_date), 'MMM d, yyyy') : 'Dec 14, 2025'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowDetailsModal(false)}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-gray-500">close</span>
              </button>
            </div>

            {/* Modal Content - Scrollable */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Report Statistics */}
              <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary">assessment</span>
                  Report Statistics
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-white dark:bg-surface-dark p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="text-xs text-gray-500 mb-1">Total Logs</div>
                    <div className="text-2xl font-bold text-gray-900 dark:text-white">
                      {report?.total_logs_processed.toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-white dark:bg-surface-dark p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="text-xs text-gray-500 mb-1">Errors</div>
                    <div className="text-2xl font-bold text-red-500">
                      {report?.error_count.toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-white dark:bg-surface-dark p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="text-xs text-gray-500 mb-1">Warnings</div>
                    <div className="text-2xl font-bold text-yellow-500">
                      {report?.warning_count.toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-white dark:bg-surface-dark p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="text-xs text-gray-500 mb-1">Anomalies</div>
                    <div className="text-2xl font-bold text-orange-500">
                      {report?.anomalies_detected}
                    </div>
                  </div>
                  <div className="bg-white dark:bg-surface-dark p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="text-xs text-gray-500 mb-1">Error Patterns</div>
                    <div className="text-2xl font-bold text-gray-900 dark:text-white">
                      {report?.unique_error_patterns}
                    </div>
                  </div>
                  <div className="bg-white dark:bg-surface-dark p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="text-xs text-gray-500 mb-1">New Patterns</div>
                    <div className="text-2xl font-bold text-purple-500">
                      {report?.new_error_patterns}
                    </div>
                  </div>
                  <div className="bg-white dark:bg-surface-dark p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="text-xs text-gray-500 mb-1">Critical Issues</div>
                    <div className="text-2xl font-bold text-red-600">
                      {report?.critical_issues}
                    </div>
                  </div>
                  <div className="bg-white dark:bg-surface-dark p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="text-xs text-gray-500 mb-1">Gen. Time</div>
                    <div className="text-2xl font-bold text-gray-900 dark:text-white">
                      {report?.generation_time_seconds.toFixed(1)}s
                    </div>
                  </div>
                </div>
              </div>

              {/* Affected Services */}
              {report?.affected_services && report.affected_services.count > 0 && (
                <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-primary">dns</span>
                    Affected Services
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {report.affected_services.services.map((service, idx) => {
                      const serviceIcons: Record<string, string> = {
                        'redis': 'memory',
                        'auth-service': 'shield',
                        'api-gateway': 'api',
                        'postgresql': 'storage',
                        'kafka': 'queue',
                        'clickhouse': 'database',
                      };
                      const icon = serviceIcons[service.toLowerCase()] || 'dns';
                      
                      return (
                        <div key={idx} className="flex items-center gap-3 p-3 bg-white dark:bg-surface-dark rounded-lg border border-gray-200 dark:border-gray-700">
                          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                            <span className="material-symbols-outlined text-primary">{icon}</span>
                          </div>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white capitalize truncate">
                              {service.replace(/-/g, ' ')}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Top Issues */}
              {report?.top_issues && report.top_issues.length > 0 && (
                <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-primary">error</span>
                    Top Issues
                  </h3>
                  <div className="space-y-3">
                    {report.top_issues.slice(0, 5).map((issue, idx) => (
                      <div key={idx} className="p-4 bg-white dark:bg-surface-dark rounded-lg border border-gray-200 dark:border-gray-700">
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-red-100 dark:bg-red-900/20 flex items-center justify-center text-red-600 dark:text-red-400 font-bold text-sm">
                            {idx + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white mb-1">
                              {issue.normalized_message || 'Unknown Issue'}
                            </p>
                            <div className="flex flex-wrap gap-2 text-xs text-gray-500">
                              {issue.count && (
                                <span className="flex items-center gap-1">
                                  <span className="material-symbols-outlined text-xs">receipt_long</span>
                                  {issue.count.toLocaleString()} occurrences
                                </span>
                              )}
                              {issue.max_level && (
                                <span className={`px-2 py-0.5 rounded font-medium ${
                                  issue.max_level === 'FATAL' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400' :
                                  issue.max_level === 'ERROR' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                  'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                                }`}>
                                  {issue.max_level}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations */}
              {report?.recommendations && report.recommendations.length > 0 && (
                <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-primary">lightbulb</span>
                    AI Recommendations
                  </h3>
                  <div className="space-y-3">
                    {report.recommendations.map((rec, idx) => (
                      <div key={idx} className="flex items-start gap-3 p-4 bg-white dark:bg-surface-dark rounded-lg border border-gray-200 dark:border-gray-700 hover:border-primary dark:hover:border-primary transition-colors">
                        <span className="material-symbols-outlined text-primary text-lg flex-shrink-0 mt-0.5">bolt</span>
                        <p className="text-sm text-gray-700 dark:text-gray-300 flex-1 whitespace-pre-line">{rec}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Report Metadata */}
              <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary">info</span>
                  Report Metadata
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div className="flex justify-between p-3 bg-white dark:bg-surface-dark rounded border border-gray-200 dark:border-gray-700">
                    <span className="text-gray-500">Report ID</span>
                    <span className="font-mono text-gray-900 dark:text-white text-xs">{report?.report_id}</span>
                  </div>
                  <div className="flex justify-between p-3 bg-white dark:bg-surface-dark rounded border border-gray-200 dark:border-gray-700">
                    <span className="text-gray-500">Status</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                      report?.status === 'completed' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                      report?.status === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                      'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400'
                    }`}>
                      {report?.status}
                    </span>
                  </div>
                  <div className="flex justify-between p-3 bg-white dark:bg-surface-dark rounded border border-gray-200 dark:border-gray-700">
                    <span className="text-gray-500">LLM Model</span>
                    <span className="font-mono text-gray-900 dark:text-white text-xs">{report?.llm_model_used || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between p-3 bg-white dark:bg-surface-dark rounded border border-gray-200 dark:border-gray-700">
                    <span className="text-gray-500">Tokens Used</span>
                    <span className="font-mono text-gray-900 dark:text-white">{report?.tokens_used?.toLocaleString() || 'N/A'}</span>
                  </div>
                  <div className="flex justify-between p-3 bg-white dark:bg-surface-dark rounded border border-gray-200 dark:border-gray-700">
                    <span className="text-gray-500">Analysis Period</span>
                    <span className="text-gray-900 dark:text-white">
                      {report && format(new Date(report.start_time), 'MMM d, HH:mm')} - {report && format(new Date(report.end_time), 'HH:mm')}
                    </span>
                  </div>
                  <div className="flex justify-between p-3 bg-white dark:bg-surface-dark rounded border border-gray-200 dark:border-gray-700">
                    <span className="text-gray-500">Generated At</span>
                    <span className="text-gray-900 dark:text-white">
                      {report && format(new Date(report.created_at), 'MMM d, yyyy HH:mm:ss')}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200 dark:border-border-dark bg-gray-50 dark:bg-surface-darker">
              <button
                onClick={() => setShowDetailsModal(false)}
                className="px-4 py-2 text-sm bg-white dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 transition-colors cursor-pointer"
              >
                Close
              </button>
              <button className="px-4 py-2 text-sm bg-primary text-black font-semibold rounded-lg hover:bg-primary-hover transition-colors shadow-lg shadow-primary/20 flex items-center gap-2 cursor-pointer">
                <span className="material-symbols-outlined text-sm">download</span>
                Export Full Report
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
