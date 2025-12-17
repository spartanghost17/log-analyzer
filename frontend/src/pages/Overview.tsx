import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { mockApi } from "../api/mock";
import { api } from "../api/client";
import { MainChart } from "../components/charts/MainChart";
import { format } from "date-fns";

// Toggle this to switch between mock and real API
const USE_MOCK_API = true;

export const Overview = () => {
  const navigate = useNavigate();
  
  const { data: metrics, isLoading: loadingMetrics } = useQuery({
    queryKey: ["metrics"],
    queryFn: USE_MOCK_API ? mockApi.getMetrics : api.getMetrics,
    refetchInterval: USE_MOCK_API ? false : 10000,
  });

  const { data: anomaliesData, isLoading: loadingAnomalies } = useQuery({
    queryKey: ["anomalies"],
    queryFn: () =>
      USE_MOCK_API
        ? mockApi.getAnomalies({ severity: "critical", limit: 5 })
        : api.getAnomalies({ severity: "critical", limit: 5 }),
  });

  const { data: throughputData, isLoading: loadingThroughput } = useQuery({
    queryKey: ["throughput"],
    queryFn: USE_MOCK_API ? mockApi.getThroughput : api.getThroughput,
  });

  const anomalies = anomaliesData?.anomalies || [];

  return (
    <div className="flex-1 overflow-y-auto scroll-smooth">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-8 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            Neural Hub - Dashboard
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Real-time system monitoring and anomaly detection
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-gray-100 dark:bg-surface-dark rounded-lg p-1 border border-gray-200 dark:border-gray-700">
            <button className="px-3 py-1 text-xs font-medium rounded text-gray-900 dark:text-white bg-white dark:bg-gray-700 shadow-sm cursor-pointer">
              Overview
            </button>
            <button className="px-3 py-1 text-xs font-medium rounded text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
              Topology
            </button>
          </div>
          <button className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-black px-4 py-2 rounded-lg text-sm font-semibold shadow-lg shadow-primary/20 transition-all">
            <span className="material-icons-outlined text-lg">add</span>
            New Dashboard
          </button>
        </div>
      </div>

      {/* Metrics Grid - Dark cards on light background */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
        {/* Ingestion Rate */}
        <div className="bg-[#1a1d24] dark:bg-surface-dark border border-gray-800 dark:border-gray-800 rounded-xl p-5 shadow-sm relative overflow-hidden group">
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Ingestion Rate</p>
              <h3 className="text-3xl font-bold text-white mt-1">
                {loadingMetrics ? "..." : `${(metrics?.log_rate || 12.4).toFixed(1)}k`}{" "}
                <span className="text-sm font-normal text-gray-400">logs/s</span>
              </h3>
            </div>
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
            </span>
          </div>
          <div className="h-12 w-full flex items-end gap-1 opacity-50">
            {[30, 50, 40, 70, 60, 85, 75, 65, 55, 45].map((height, i) => (
              <div
                key={i}
                className={`w-1 rounded-t-sm ${
                  i === 5 ? 'bg-primary shadow-[0_0_10px_rgba(253,224,71,0.5)]' : 'bg-gray-700'
                }`}
                style={{ height: `${height}%` }}
              ></div>
            ))}
          </div>
        </div>

        {/* Error Rate */}
        <div className="bg-[#1a1d24] dark:bg-surface-dark border border-gray-800 dark:border-gray-800 rounded-xl p-5 shadow-sm group">
          <div className="flex justify-between items-start mb-2">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Error Rate</p>
          </div>
          <div className="flex items-end gap-2 mb-4">
            <h3 className="text-3xl font-bold text-white">
              {loadingMetrics ? "..." : `${(metrics?.error_rate! * 100 || 0.45).toFixed(2)}%`}
            </h3>
            <span className="text-xs text-red-500 font-medium flex items-center mb-1">
              <span className="material-icons-outlined text-sm mr-0.5">arrow_upward</span> 1.2%
            </span>
          </div>
          <div className="relative h-10 w-full">
            <svg className="w-full h-full overflow-visible" viewBox="0 0 100 25">
              <defs>
                <linearGradient id="gradientRed" x1="0%" x2="100%" y1="0%" y2="0%">
                  <stop offset="0%" style={{ stopColor: '#EF4444', stopOpacity: 0 }}></stop>
                  <stop offset="50%" style={{ stopColor: '#EF4444', stopOpacity: 1 }}></stop>
                  <stop offset="100%" style={{ stopColor: '#EF4444', stopOpacity: 0 }}></stop>
                </linearGradient>
              </defs>
              <path
                d="M0,25 C10,25 20,20 30,22 C40,24 40,10 50,5 C60,0 60,15 70,18 C80,21 90,25 100,25"
                fill="none"
                stroke="url(#gradientRed)"
                strokeLinecap="round"
                strokeWidth="2"
              ></path>
            </svg>
          </div>
        </div>

        {/* Anomaly Score - Highlighted */}
        <div className="bg-[#1a1d24] dark:bg-surface-dark border border-primary/30 rounded-xl p-5 shadow-[0_0_15px_rgba(253,224,71,0.05)] relative overflow-hidden">
          <div className="absolute top-0 right-0 w-16 h-16 bg-primary/10 rounded-bl-full -mr-4 -mt-4"></div>
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Anomaly Score</p>
              <h3 className="text-3xl font-bold text-primary mt-1 drop-shadow-sm">High</h3>
            </div>
            <span className="material-icons-outlined text-primary text-xl animate-pulse">warning</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-1.5 mb-2 mt-4">
            <div className="bg-primary h-1.5 rounded-full" style={{ width: '85%' }}></div>
          </div>
          <p className="text-xs text-primary/80 font-mono">(Blinking Token Detected)</p>
        </div>

        {/* Processing Lag */}
        <div className="bg-[#1a1d24] dark:bg-surface-dark border border-gray-800 dark:border-gray-800 rounded-xl p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Processing Lag</p>
          </div>
          <h3 className="text-3xl font-bold text-white mb-4">15ms</h3>
          <div className="h-10 flex items-end justify-between gap-0.5">
            {[20, 30, 25, 40, 60, 35, 20, 15, 25, 30].map((height, i) => (
              <div
                key={i}
                className={`w-1.5 rounded-sm ${i === 4 ? 'bg-blue-500' : 'bg-blue-500/40'}`}
                style={{ height: `${height}%` }}
              ></div>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* Main Chart */}
        <div className="lg:col-span-2 bg-[#1a1d24] dark:bg-surface-dark border border-gray-800 dark:border-gray-800 rounded-xl p-6 shadow-sm flex flex-col h-[400px]">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-sm font-semibold text-white uppercase tracking-wide">
              LAG VOLUME (LAST HOUR)
            </h2>
            <div className="flex items-center gap-4 text-xs">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                <span className="text-gray-400">Errors</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-primary"></span>
                <span className="text-gray-400">Warn</span>
              </div>
            </div>
          </div>
          <div className="relative w-full h-full flex-1">
            <MainChart data={throughputData || []} loading={loadingThroughput} />
          </div>
        </div>

        {/* Service Health Map */}
        <div className="bg-[#1a1d24] dark:bg-surface-dark border border-gray-800 dark:border-gray-800 rounded-xl p-6 shadow-sm flex flex-col h-[400px]">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-sm font-semibold text-white uppercase tracking-wide">
              SERVICE HEALTH MAP
            </h2>
            <button className="text-gray-400 hover:text-white">
              <span className="material-icons-outlined text-lg">more_horiz</span>
            </button>
          </div>
          <div className="flex-1 relative bg-[#0f1014] rounded-lg overflow-hidden border border-gray-800/50">
            {/* Grid background */}
            <div
              className="absolute inset-0 opacity-10"
              style={{
                backgroundImage:
                  'linear-gradient(#4B5563 1px, transparent 1px), linear-gradient(90deg, #4B5563 1px, transparent 1px)',
                backgroundSize: '20px 20px',
              }}
            ></div>

            {/* Connection lines */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="relative w-full h-full">
                <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
                  <line stroke="#4B5563" strokeOpacity="0.5" strokeWidth="1" x1="50%" x2="30%" y1="50%" y2="30%"></line>
                  <line stroke="#4B5563" strokeOpacity="0.5" strokeWidth="1" x1="50%" x2="70%" y1="50%" y2="30%"></line>
                  <line stroke="#4B5563" strokeOpacity="0.5" strokeWidth="1" x1="50%" x2="40%" y1="50%" y2="70%"></line>
                  <line stroke="#4B5563" strokeOpacity="0.5" strokeWidth="1" x1="50%" x2="75%" y1="50%" y2="60%"></line>
                  <line stroke="#4B5563" strokeOpacity="0.5" strokeWidth="1" x1="30%" x2="20%" y1="30%" y2="40%"></line>
                  <line stroke="#4B5563" strokeOpacity="0.5" strokeWidth="1" x1="70%" x2="80%" y1="30%" y2="20%"></line>
                </svg>

                {/* Central node */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 bg-primary rounded shadow-[0_0_20px_rgba(253,224,71,0.6)] animate-pulse z-10 flex items-center justify-center">
                  <div className="w-3 h-3 bg-white/50 rounded-sm"></div>
                </div>

                {/* Service nodes */}
                <div className="absolute top-[30%] left-[30%] w-6 h-6 bg-gray-700 rounded shadow-lg border border-gray-500 z-10"></div>
                <div className="absolute top-[30%] left-[70%] w-6 h-6 bg-gray-700 rounded shadow-lg border border-gray-500 z-10"></div>
                <div className="absolute top-[70%] left-[40%] w-6 h-6 bg-gray-700 rounded shadow-lg border border-gray-500 z-10"></div>
                <div className="absolute top-[60%] left-[75%] w-6 h-6 bg-primary/80 rounded shadow-[0_0_10px_rgba(253,224,71,0.3)] z-10"></div>
                <div className="absolute top-[20%] right-[15%] w-4 h-4 bg-gray-700 rounded z-10 opacity-70"></div>
                <div className="absolute top-[25%] right-[12%] w-4 h-4 bg-gray-700 rounded z-10 opacity-70"></div>
                <div className="absolute top-[22%] right-[18%] w-4 h-4 bg-gray-700 rounded z-10 opacity-70"></div>

                {/* Info badge */}
                <div className="absolute bottom-4 left-4 bg-black/80 text-xs text-white p-2 rounded border border-gray-700 backdrop-blur-sm">
                  <span className="text-primary font-bold">Service-A:</span> 98% Healthy
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Anomalies Table */}
      <div className="bg-[#1a1d24] dark:bg-surface-dark border border-gray-800 dark:border-gray-800 rounded-xl p-6 shadow-sm mb-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-sm font-semibold text-white uppercase tracking-wide">
            RECENT ANOMALIES
          </h2>
          <button
            onClick={() => navigate("/anomalies")}
            className="text-xs text-primary hover:text-primary-hover font-medium"
          >
            View All Logs
          </button>
        </div>

        {loadingAnomalies ? (
          <div className="p-12 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : anomalies.length === 0 ? (
          <div className="p-12 text-center text-gray-400">
            <span className="material-icons-outlined text-[64px] mb-4">check_circle</span>
            <p>No critical anomalies detected</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-400 uppercase">
                  <th className="py-3 font-medium w-32">TIMESTAMP</th>
                  <th className="py-3 font-medium w-24">LEVEL</th>
                  <th className="py-3 font-medium w-40">SERVICE</th>
                  <th className="py-3 font-medium">MESSAGE</th>
                  <th className="py-3 font-medium w-24 text-right">ACTION</th>
                </tr>
              </thead>
              <tbody className="text-gray-300">
                {anomalies.slice(0, 3).map((anomaly) => (
                  <tr
                    key={anomaly.alert_id}
                    className="border-b border-gray-800/50 hover:bg-white/5 transition-colors group cursor-pointer"
                  >
                    <td className="py-3 font-mono text-xs opacity-70">
                      {format(new Date(anomaly.detected_at), "yyyy-MM-dd HH:mm:ss")}
                    </td>
                    <td className="py-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                          anomaly.severity === "critical"
                            ? "bg-red-900/30 text-red-400 border-red-900/50"
                            : "bg-yellow-900/30 text-primary border-primary/30"
                        }`}
                      >
                        {anomaly.severity === "critical" ? "ERROR" : "WARN"}
                      </span>
                    </td>
                    <td className="py-3 font-mono text-xs">{anomaly.service}</td>
                    <td className="py-3 truncate max-w-md">
                      <span className="text-gray-400">Connection refused:</span> {anomaly.description}
                    </td>
                    <td className="py-3 text-right">
                      <button className="opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-700 rounded transition-all">
                        <span className="material-icons-outlined text-base">arrow_forward</span>
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
