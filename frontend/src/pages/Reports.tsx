import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { mockApi } from '../api/mock';
import { format } from 'date-fns';
import Chart from 'chart.js/auto';

// Toggle this to switch between mock and real API
const USE_MOCK_API = true;

export const Reports = () => {
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const chartRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstance = useRef<Chart | null>(null);

  const { isLoading } = useQuery({
    queryKey: ['reports'],
    queryFn: () => USE_MOCK_API ? mockApi.getReports({ limit: 10 }) : api.getReports({ limit: 10 }),
  });

  const { data: latestReport } = useQuery({
    queryKey: ['latest-report'],
    queryFn: () => USE_MOCK_API ? mockApi.getLatestReport() : api.getLatestReport(),
    retry: false,
  });

  const { data: anomalyData } = useQuery({
    queryKey: ['anomaly-zscore'],
    queryFn: () => USE_MOCK_API ? mockApi.getAnomalyZScoreData() : api.getAnomalyZScoreData(),
    retry: false,
  });

  const report = latestReport;

  // Timeline data
  const timelineEntries = [
    { date: 'Dec 14', status: '3 Critical Anomalies', active: true },
    { date: 'Dec 13', status: 'System Stable', active: false },
    { date: 'Dec 12', status: 'Maintenance Window', active: false },
    { date: 'Dec 11', status: '1 Minor Alert', active: false },
    { date: 'Dec 10', status: 'System Stable', active: false },
  ];

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
            <button className="text-gray-400 hover:text-gray-900 dark:hover:text-white">
              <span className="material-symbols-outlined text-sm">filter_list</span>
            </button>
          </div>
          <div className="relative">
            <span className="absolute inset-y-0 left-0 flex items-center pl-2">
              <span className="material-symbols-outlined text-gray-500 text-xs">calendar_today</span>
            </span>
            <select className="w-full bg-gray-100 dark:bg-surface-darker border-none rounded text-xs py-1.5 pl-8 pr-2 text-gray-700 dark:text-gray-300 focus:ring-0 cursor-pointer">
              <option>Last 30 Days</option>
              <option>Last 7 Days</option>
              <option>Today</option>
            </select>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          <div className="px-4 py-2">
            <div className="relative pl-4 border-l border-gray-300 dark:border-gray-700 space-y-6">
              {timelineEntries.map((entry) => (
                <div
                  key={entry.date}
                  className={`relative group cursor-pointer ${entry.active ? '' : 'opacity-70 hover:opacity-100'} transition-opacity`}
                >
                  <div
                    className={`absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full ${
                      entry.active
                        ? 'bg-primary ring-4 ring-primary/20'
                        : 'bg-gray-400 dark:bg-gray-600 group-hover:bg-gray-300 dark:group-hover:bg-gray-400 border border-gray-200 dark:border-surface-dark'
                    }`}
                  ></div>
                  <h3 className={`text-sm font-medium ${entry.active ? 'text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-300'}`}>
                    {entry.date}
                  </h3>
                  <p className="text-xs text-gray-500 mt-0.5">{entry.status}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="p-4 border-t border-gray-200 dark:border-gray-800">
          <button className="w-full py-2 bg-gray-100 dark:bg-surface-darker hover:bg-gray-200 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-xs text-gray-700 dark:text-gray-300 transition-colors">
            Load Archive
          </button>
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
                    className="flex items-center px-3 py-2 text-sm bg-white dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 transition-colors"
                  >
                    <span className="material-symbols-outlined text-sm mr-2">visibility</span> Full Details
                  </button>
                  <button className="flex items-center px-3 py-2 text-sm bg-white dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 transition-colors">
                    <span className="material-symbols-outlined text-sm mr-2">share</span> Share
                  </button>
                  <button className="flex items-center px-3 py-2 text-sm bg-primary text-black font-semibold rounded hover:bg-primary-hover transition-colors shadow-lg shadow-primary/20">
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
                  <p>
                    {report.executive_summary.split(' ').map((word, idx) => {
                      const highlightWords = ['eviction', 'spike', 'deviations', 'timeout', 'critical'];
                      const shouldHighlight = highlightWords.some(hw => word.toLowerCase().includes(hw.toLowerCase()));
                      return shouldHighlight ? (
                        <span key={idx} className="bg-primary/15 text-primary px-0.5 rounded font-medium">
                          {word}{' '}
                        </span>
                      ) : (
                        word + ' '
                      );
                    })}
                  </p>
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
                      {report.affected_services?.length || 4}
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
                <div className="flex items-center justify-between mb-6">
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
                          <p className="text-sm text-gray-800 dark:text-gray-200 font-medium group-hover:text-primary transition-colors">
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
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              >
                <span className="material-symbols-outlined text-gray-500">close</span>
              </button>
            </div>

            {/* Modal Content - Scrollable */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Affected Services Detail */}
              <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary">dns</span>
                  Affected Services Detail
                </h3>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-red-50 dark:bg-red-900/10 rounded-lg border border-red-200 dark:border-red-900/30">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-lg bg-red-500/20 flex items-center justify-center">
                        <span className="material-symbols-outlined text-red-500 text-xl">database</span>
                      </div>
                      <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white">Redis Cache</h4>
                        <p className="text-sm text-gray-600 dark:text-gray-400">Memory overflow detected</p>
                        <p className="text-xs text-gray-500 mt-1">Last updated: 03:58 UTC</p>
                      </div>
                    </div>
                    <span className="px-3 py-1 rounded-full text-xs font-semibold bg-red-500/20 text-red-600 dark:text-red-400">Critical</span>
                  </div>
                  <div className="flex items-center justify-between p-4 bg-red-50 dark:bg-red-900/10 rounded-lg border border-red-200 dark:border-red-900/30">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-lg bg-red-500/20 flex items-center justify-center">
                        <span className="material-symbols-outlined text-red-500 text-xl">shield</span>
                      </div>
                      <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white">Auth Provider</h4>
                        <p className="text-sm text-gray-600 dark:text-gray-400">Thread lock contention</p>
                        <p className="text-xs text-gray-500 mt-1">Last updated: 03:58 UTC</p>
                      </div>
                    </div>
                    <span className="px-3 py-1 rounded-full text-xs font-semibold bg-red-500/20 text-red-600 dark:text-red-400">Critical</span>
                  </div>
                  <div className="flex items-center justify-between p-4 bg-yellow-50 dark:bg-yellow-900/10 rounded-lg border border-yellow-200 dark:border-yellow-900/30">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-lg bg-yellow-500/20 flex items-center justify-center">
                        <span className="material-symbols-outlined text-yellow-600 dark:text-yellow-500 text-xl">api</span>
                      </div>
                      <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white">API Gateway</h4>
                        <p className="text-sm text-gray-600 dark:text-gray-400">Increased latency</p>
                        <p className="text-xs text-gray-500 mt-1">Last updated: 03:52 UTC</p>
                      </div>
                    </div>
                    <span className="px-3 py-1 rounded-full text-xs font-semibold bg-yellow-500/20 text-yellow-700 dark:text-yellow-500">Warning</span>
                  </div>
                  <div className="flex items-center justify-between p-4 bg-green-50 dark:bg-green-900/10 rounded-lg border border-green-200 dark:border-green-900/30">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-lg bg-green-500/20 flex items-center justify-center">
                        <span className="material-symbols-outlined text-green-600 dark:text-green-500 text-xl">storage</span>
                      </div>
                      <div>
                        <h4 className="font-semibold text-gray-900 dark:text-white">PostgreSQL DB</h4>
                        <p className="text-sm text-gray-600 dark:text-gray-400">Operating normally</p>
                        <p className="text-xs text-gray-500 mt-1">Last updated: 04:00 UTC</p>
                      </div>
                    </div>
                    <span className="px-3 py-1 rounded-full text-xs font-semibold bg-green-500/20 text-green-700 dark:text-green-500">Healthy</span>
                  </div>
                </div>
              </div>

              {/* Event Timeline */}
              <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary">timeline</span>
                  Event Timeline
                </h3>
                <div className="relative pl-8 border-l-2 border-gray-300 dark:border-gray-700 space-y-8">
                  <div className="relative">
                    <div className="absolute -left-[33px] top-1 w-5 h-5 rounded-full bg-red-500 border-4 border-white dark:border-surface-darker shadow-lg"></div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-2 font-mono">03:47:23 UTC</div>
                    <h4 className="font-semibold text-gray-900 dark:text-white mb-2">Redis Memory Spike Detected</h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">Memory usage exceeded 95% threshold triggering automatic alerts across monitoring systems.</p>
                  </div>
                  <div className="relative">
                    <div className="absolute -left-[33px] top-1 w-5 h-5 rounded-full bg-yellow-500 border-4 border-white dark:border-surface-darker shadow-lg"></div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-2 font-mono">03:52:18 UTC</div>
                    <h4 className="font-semibold text-gray-900 dark:text-white mb-2">Eviction Events Started</h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">Cache began evicting keys to free memory. Temporary performance degradation expected.</p>
                  </div>
                  <div className="relative">
                    <div className="absolute -left-[33px] top-1 w-5 h-5 rounded-full bg-red-500 border-4 border-white dark:border-surface-darker shadow-lg"></div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-2 font-mono">03:58:41 UTC</div>
                    <h4 className="font-semibold text-gray-900 dark:text-white mb-2">Auth Service Degradation</h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">Thread lock contention causing authentication delays. User impact detected.</p>
                  </div>
                  <div className="relative">
                    <div className="absolute -left-[33px] top-1 w-5 h-5 rounded-full bg-primary border-4 border-white dark:border-surface-darker shadow-lg"></div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-2 font-mono">04:00:00 UTC</div>
                    <h4 className="font-semibold text-gray-900 dark:text-white mb-2">Report Generated</h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">Automated analysis completed by Synaps AI engine with 98.4% confidence.</p>
                  </div>
                </div>
              </div>

              {/* Technical Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                  <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-sm">speed</span>
                    System Load
                  </h4>
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between text-xs mb-2">
                        <span className="text-gray-600 dark:text-gray-400">CPU Usage</span>
                        <span className="font-semibold text-gray-900 dark:text-white">78%</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-gray-800 rounded-full h-2">
                        <div className="bg-yellow-500 h-2 rounded-full transition-all" style={{ width: '78%' }}></div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs mb-2">
                        <span className="text-gray-600 dark:text-gray-400">Memory Usage</span>
                        <span className="font-semibold text-gray-900 dark:text-white">94%</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-gray-800 rounded-full h-2">
                        <div className="bg-red-500 h-2 rounded-full transition-all" style={{ width: '94%' }}></div>
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs mb-2">
                        <span className="text-gray-600 dark:text-gray-400">Disk I/O</span>
                        <span className="font-semibold text-gray-900 dark:text-white">45%</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-gray-800 rounded-full h-2">
                        <div className="bg-green-500 h-2 rounded-full transition-all" style={{ width: '45%' }}></div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                  <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-sm">error</span>
                    Error Rates
                  </h4>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-gray-400">5xx Errors</span>
                      <span className="text-2xl font-bold text-red-500">342</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-gray-400">4xx Errors</span>
                      <span className="text-2xl font-bold text-yellow-500">1,247</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Timeouts</span>
                      <span className="text-2xl font-bold text-orange-500">89</span>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 dark:bg-surface-darker rounded-xl p-6 border border-gray-200 dark:border-gray-800">
                  <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
                    <span className="material-symbols-outlined text-sm">monitoring</span>
                    Performance
                  </h4>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Avg Response</span>
                      <span className="text-2xl font-bold text-gray-900 dark:text-white">245ms</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-gray-400">P95 Latency</span>
                      <span className="text-2xl font-bold text-gray-900 dark:text-white">1.2s</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Throughput</span>
                      <span className="text-2xl font-bold text-gray-900 dark:text-white">2.4k/s</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200 dark:border-border-dark bg-gray-50 dark:bg-surface-darker">
              <button
                onClick={() => setShowDetailsModal(false)}
                className="px-4 py-2 text-sm bg-white dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 transition-colors"
              >
                Close
              </button>
              <button className="px-4 py-2 text-sm bg-primary text-black font-semibold rounded-lg hover:bg-primary-hover transition-colors shadow-lg shadow-primary/20 flex items-center gap-2">
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
