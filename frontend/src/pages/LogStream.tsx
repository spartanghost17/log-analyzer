import { useState, useEffect, useRef } from "react";
import { LogStreamClient, type LogEntry } from "../api/client";
import { format } from "date-fns";

// Toggle this to switch between mock and real WebSocket
const USE_MOCK_API = true;

export const LogStream = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);
  const [filters, setFilters] = useState({
    ERROR: true,
    WARN: true,
    INFO: false,
    DEBUG: false,
    FATAL: true,
  });
  const [searchQuery, setSearchQuery] = useState("");
  const [searchService, setSearchService] = useState("");
  const logContainerRef = useRef<HTMLDivElement>(null);
  const wsClientRef = useRef<LogStreamClient | null>(null);

  useEffect(() => {
    if (USE_MOCK_API) {
      // Mock log stream - generate fake logs
      setIsConnected(true);

      const services = [
        "auth-service",
        "payment-gateway",
        "user-profile",
        "frontend-proxy",
        "cache-worker",
        "notification-svc",
      ];
      const levels: Array<"INFO" | "WARN" | "ERROR" | "DEBUG" | "FATAL"> = [
        "INFO",
        "WARN",
        "ERROR",
        "DEBUG",
        "FATAL",
      ];
      const messages = [
        "Failed to connect to database instance db-shard-04. Connection timed out after 3000ms.",
        "Retry attempt 2/5 for transaction #tx-998231 due to high latency.",
        "NullReferenceException: Object reference not set to an instance of an object at UserProfile.GetDetails(String id).",
        "Token refreshed successfully for user user_8821. Expires in 3600s.",
        "Request received: GET /api/v1/users/me (200 OK) - 45ms",
        "Cache hit ratio: 94.2%. Evicting key: user_sess_9912.",
        "SMTP connection failed. Provider responded with 503 Service Unavailable.",
      ];

      const interval = setInterval(() => {
        if (!isPaused) {
          const mockLog: LogEntry = {
            log_id: `log-${Date.now()}-${Math.random()
              .toString(36)
              .substr(2, 9)}`,
            timestamp: new Date().toISOString(),
            service: services[Math.floor(Math.random() * services.length)],
            environment: "production",
            level: levels[Math.floor(Math.random() * levels.length)],
            message: messages[Math.floor(Math.random() * messages.length)],
            trace_id: `trace-${Math.random().toString(36).substr(2, 9)}`,
            host: `host-${Math.floor(Math.random() * 10)}`,
            pod_name: `pod-${Math.random().toString(36).substr(2, 6)}`,
          };

          setLogs((prev) => [mockLog, ...prev].slice(0, 200));
        }
      }, 1500); // Generate a log every 1.5 seconds

      return () => {
        clearInterval(interval);
        setIsConnected(false);
      };
    } else {
      // Real WebSocket connection
      const client = new LogStreamClient(
        // onMessage
        (log) => {
          if (!isPaused) {
            setLogs((prev) => [log, ...prev].slice(0, 200)); // Keep last 200 logs
          }
        },
        // onError
        (error) => {
          console.error("WebSocket error:", error);
          setIsConnected(false);
        },
        // onOpen
        () => {
          setIsConnected(true);
        },
        // onClose
        () => {
          setIsConnected(false);
        }
      );

      wsClientRef.current = client;
      client.connect();

      return () => {
        client.disconnect();
      };
    }
  }, [isPaused]);

  const filteredLogs = logs.filter((log) => {
    // Filter by level checkboxes
    const levelMatch = filters[log.level as keyof typeof filters];
    if (!levelMatch) return false;

    // Filter by search query
    if (searchQuery && !log.message.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }

    // Filter by service
    if (searchService && !log.service.toLowerCase().includes(searchService.toLowerCase())) {
      return false;
    }

    return true;
  });

  const uniqueServices = Array.from(new Set(logs.map(log => log.service)));

  // Calculate stats
  const fatalCount = logs.filter(l => l.level === 'FATAL').length;
  const errorCount = logs.filter(l => l.level === 'ERROR').length;
  const warnCount = logs.filter(l => l.level === 'WARN').length;
  const infoCount = logs.filter(l => l.level === 'INFO').length;

  return (
    <div className="flex h-full -m-6 overflow-hidden">
      {/* Sidebar Filter Panel */}
      <div className="w-72 h-full bg-white dark:bg-surface-darker border-r border-gray-200 dark:border-gray-800 p-4 flex flex-col gap-6 overflow-y-auto flex-shrink-0">
        <div>
          <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
            <span className="material-icons-outlined text-sm">filter_list</span> Filters
          </h2>
          
          <div className="mb-6">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">Level</label>
            <div className="space-y-2">
              <label className="flex items-center gap-2 cursor-pointer group">
                <input
                  checked={filters.FATAL}
                  onChange={(e) => setFilters({ ...filters, FATAL: e.target.checked })}
                  className="rounded border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-800 text-purple-600 focus:ring-0 focus:ring-offset-0"
                  type="checkbox"
                />
                <span className="w-2 h-2 rounded-full bg-purple-600"></span>
                <span className="text-sm text-gray-600 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
                  FATAL
                </span>
                <span className="ml-auto text-xs text-gray-500">{fatalCount}</span>
              </label>
              
              <label className="flex items-center gap-2 cursor-pointer group">
                <input
                  checked={filters.ERROR}
                  onChange={(e) => setFilters({ ...filters, ERROR: e.target.checked })}
                  className="rounded border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-800 text-red-500 focus:ring-0 focus:ring-offset-0"
                  type="checkbox"
                />
                <span className="w-2 h-2 rounded-full bg-red-500"></span>
                <span className="text-sm text-gray-600 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
                  ERROR
                </span>
                <span className="ml-auto text-xs text-gray-500">{errorCount}</span>
              </label>
              
              <label className="flex items-center gap-2 cursor-pointer group">
                <input
                  checked={filters.WARN}
                  onChange={(e) => setFilters({ ...filters, WARN: e.target.checked })}
                  className="rounded border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-800 text-yellow-500 focus:ring-0 focus:ring-offset-0"
                  type="checkbox"
                />
                <span className="w-2 h-2 rounded-full bg-yellow-500"></span>
                <span className="text-sm text-gray-600 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
                  WARN
                </span>
                <span className="ml-auto text-xs text-gray-500">{warnCount}</span>
              </label>
              
              <label className="flex items-center gap-2 cursor-pointer group">
                <input
                  checked={filters.INFO}
                  onChange={(e) => setFilters({ ...filters, INFO: e.target.checked })}
                  className="rounded border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-800 text-blue-500 focus:ring-0 focus:ring-offset-0"
                  type="checkbox"
                />
                <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                <span className="text-sm text-gray-600 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
                  INFO
                </span>
                <span className="ml-auto text-xs text-gray-500">{infoCount}</span>
              </label>
            </div>
          </div>

          <div className="mb-6">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">Service</label>
            <div className="relative">
              <span className="material-icons-outlined absolute left-2 top-2.5 text-gray-500 text-xs">search</span>
              <input
                className="w-full bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-xs py-2 pl-7 pr-2 text-gray-700 dark:text-gray-300 focus:border-primary focus:ring-0"
                placeholder="Search services..."
                type="text"
                value={searchService}
                onChange={(e) => setSearchService(e.target.value)}
              />
            </div>
            <div className="mt-2 space-y-1 max-h-32 overflow-y-auto pr-1">
              {uniqueServices.slice(0, 6).map(service => (
                <label key={service} className="flex items-center gap-2 cursor-pointer py-1 px-1 rounded hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <input
                    checked={!searchService || service.includes(searchService)}
                    onChange={() => setSearchService(service)}
                    className="rounded border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-800 text-primary focus:ring-0 focus:ring-offset-0"
                    type="radio"
                    name="service"
                  />
                  <span className="text-sm text-gray-600 dark:text-gray-400">{service}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="mb-6">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 block">Time Range</label>
            <div className="flex items-center gap-2 mb-2">
              <button className="flex-1 py-1 px-2 text-xs rounded bg-primary text-gray-900 font-medium border border-primary cursor-pointer">
                1h
              </button>
              <button className="flex-1 py-1 px-2 text-xs rounded bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border border-transparent hover:border-gray-300 dark:hover:border-gray-600 cursor-pointer">
                24h
              </button>
              <button className="flex-1 py-1 px-2 text-xs rounded bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border border-transparent hover:border-gray-300 dark:hover:border-gray-600 cursor-pointer">
                7d
              </button>
            </div>
            <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded border border-gray-200 dark:border-gray-700">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>Start</span>
                <span>End</span>
              </div>
              <div className="h-8 flex items-end gap-0.5 mb-2 opacity-60">
                {[2, 3, 5, 8, 4, 2, 1, 3, 6, 4, 2, 1, 3, 7, 5].map((h, i) => (
                  <div
                    key={i}
                    className={`w-1 rounded-t-sm ${[2, 3, 4, 8, 13].includes(i) ? 'bg-primary' : 'bg-gray-400'}`}
                    style={{ height: `${h * 12.5}%` }}
                  ></div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-auto">
          <div className="p-3 bg-gradient-to-br from-indigo-900 to-purple-900 rounded-lg border border-indigo-700 relative overflow-hidden">
            <div className="absolute -top-6 -right-6 w-16 h-16 bg-primary opacity-20 rounded-full blur-xl"></div>
            <h3 className="text-white text-sm font-semibold mb-1 relative z-10">AI Insights</h3>
            <p className="text-indigo-200 text-xs mb-3 relative z-10">
              {fatalCount + errorCount + warnCount} anomalies detected in the last hour.
            </p>
            <button className="w-full bg-white/10 hover:bg-white/20 text-white text-xs py-1.5 rounded border border-white/10 transition-colors cursor-pointer">
              Analyze
            </button>
          </div>
        </div>
      </div>

      {/* Main Log Explorer */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0 bg-background-light dark:bg-background-dark p-4">
        {/* Search Bar */}
        <div className="mb-4 flex gap-3">
          <div className="flex-1 relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <span className="material-icons-outlined text-gray-500 dark:text-gray-400">code</span>
            </div>
            <input
              className="block w-full pl-10 pr-12 py-3 bg-white dark:bg-surface-dark border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent font-mono shadow-sm"
              placeholder='msg="database timeout" service="payment" level=error'
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <div className="absolute inset-y-0 right-0 pr-3 flex items-center">
              <span className="text-xs text-gray-400 border border-gray-300 dark:border-gray-600 rounded px-1.5 py-0.5">/</span>
            </div>
          </div>
          <button
            onClick={() => setIsPaused(!isPaused)}
            className="bg-primary hover:bg-yellow-400 text-gray-900 font-medium py-2 px-4 rounded-lg flex items-center gap-2 shadow-sm shadow-primary/20 transition-all cursor-pointer"
          >
            <span className="material-icons-outlined text-sm">{isPaused ? 'play_arrow' : 'pause'}</span>
            {isPaused ? 'Run' : 'Pause'}
          </button>
          <button
            onClick={() => {
              setLogs([]);
              setSearchQuery("");
            }}
            className="bg-white dark:bg-surface-dark border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 py-2 px-4 rounded-lg flex items-center gap-2 shadow-sm transition-all cursor-pointer"
          >
            <span className="material-icons-outlined text-sm">save_alt</span>
            Export
          </button>
        </div>

        {/* Log Table */}
        <div className="flex-1 bg-white dark:bg-surface-dark rounded-lg border border-gray-200 dark:border-gray-700 flex flex-col shadow-sm overflow-hidden">
          {/* Table Header */}
          <div className="grid grid-cols-12 gap-4 px-6 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            <div className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200">
              Timestamp
              <span className="material-icons-outlined text-xs">arrow_downward</span>
            </div>
            <div className="col-span-1 flex items-center gap-1 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200">
              Level
            </div>
            <div className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200">
              Service
            </div>
            <div className="col-span-7 flex items-center gap-1 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200">
              Message
            </div>
          </div>

          {/* Table Body */}
          <div ref={logContainerRef} className="overflow-y-auto flex-1 font-mono text-sm">
            {filteredLogs.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <span className="material-icons-outlined text-[64px] text-gray-400 mb-4">dns</span>
                  <p className="text-gray-500 dark:text-gray-400 text-sm">
                    {isConnected ? "Waiting for logs..." : "Disconnected. Trying to reconnect..."}
                  </p>
                </div>
              </div>
            ) : (
              filteredLogs.map((log, index) => {
                const isExpanded = selectedLog?.log_id === log.log_id;
                const isError = log.level === 'ERROR';
                const isWarn = log.level === 'WARN';
                const isFatal = log.level === 'FATAL';
                const isHighlight = isFatal || (isError && index % 3 === 0);

                return (
                  <div
                    key={`${log.log_id}-${index}`}
                    onClick={() => setSelectedLog(isExpanded ? null : log)}
                    className={`grid grid-cols-12 gap-4 px-6 py-3 border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group cursor-pointer items-start ${
                      isHighlight ? 'bg-yellow-50/50 dark:bg-primary/5' : ''
                    }`}
                  >
                    <div className="col-span-2 text-gray-500 dark:text-gray-400 text-xs mt-0.5">
                      {format(new Date(log.timestamp), "yyyy-MM-dd HH:mm:ss.SSS")}
                    </div>
                    <div className="col-span-1">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          isFatal
                            ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400'
                            : isError
                            ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                            : isWarn
                            ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
                            : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
                        }`}
                      >
                        {log.level}
                      </span>
                    </div>
                    <div className="col-span-2 text-blue-600 dark:text-blue-400 truncate mt-0.5">
                      {log.service}
                    </div>
                    <div className="col-span-7 text-gray-800 dark:text-gray-300 break-all leading-relaxed">
                      <span className="text-gray-400 select-none mr-2">msg=</span>
                      {log.message}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-surface-darker px-4 py-2 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
            <div>
              Showing <span className="font-medium text-gray-900 dark:text-white">1</span> to{' '}
              <span className="font-medium text-gray-900 dark:text-white">{Math.min(50, filteredLogs.length)}</span> of{' '}
              <span className="font-medium text-gray-900 dark:text-white">{filteredLogs.length}</span> results
            </div>
            <div className="flex gap-2">
              <button className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-surface-dark hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed" disabled>
                Previous
              </button>
              <button className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-surface-dark hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer">
                Next
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
