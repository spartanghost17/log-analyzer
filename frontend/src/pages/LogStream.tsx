import React, { useState, useEffect, useRef } from "react";
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
    info: true,
    error: true,
    warn: true,
    debug: false,
    fatal: true,
  });
  const [searchQuery, setSearchQuery] = useState("");
  const logContainerRef = useRef<HTMLDivElement>(null);
  const wsClientRef = useRef<LogStreamClient | null>(null);

  useEffect(() => {
    if (USE_MOCK_API) {
      // Mock log stream - generate fake logs
      setIsConnected(true);

      const services = [
        "api-gateway",
        "auth-service",
        "payment-gateway",
        "user-service",
        "analytics",
      ];
      const levels: Array<"INFO" | "WARN" | "ERROR" | "DEBUG" | "FATAL"> = [
        "INFO",
        "WARN",
        "ERROR",
        "DEBUG",
        "FATAL",
      ];
      const messages = [
        "Request processed successfully",
        "Connection timeout to database after 5000ms",
        "User authentication failed: invalid token",
        "Payment processing completed",
        "Rate limit exceeded for API endpoint",
        "Cache miss for key: user_profile_123",
        "Slow query detected: SELECT * FROM transactions",
        "Health check ping received from load balancer",
        "Circuit breaker opened for downstream service",
        "Memory usage threshold exceeded",
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

          setLogs((prev) => [mockLog, ...prev].slice(0, 100));
        }
      }, 1000); // Generate a log every second

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
            setLogs((prev) => [log, ...prev].slice(0, 100)); // Keep last 100 logs
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
    // Filter by level
    const levelMatch =
      (filters.info && log.level === "INFO") ||
      (filters.error && log.level === "ERROR") ||
      (filters.warn && log.level === "WARN") ||
      (filters.debug && log.level === "DEBUG") ||
      (filters.fatal && log.level === "FATAL");

    if (!levelMatch) return false;

    // Filter by search query
    if (searchQuery) {
      return (
        log.message.toLowerCase().includes(searchQuery.toLowerCase()) ||
        log.service.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    return true;
  });

  const getLevelColor = (level: string) => {
    switch (level) {
      case "ERROR":
      case "FATAL":
        return {
          bg: "bg-accent-yellow/20",
          text: "text-accent-yellow",
          border: "border-accent-yellow/40",
        };
      case "WARN":
        return {
          bg: "bg-orange-500/10",
          text: "text-orange-400",
          border: "border-orange-500/20",
        };
      case "INFO":
        return {
          bg: "bg-primary-alt/10",
          text: "text-primary-alt",
          border: "border-primary-alt/20",
        };
      case "DEBUG":
        return {
          bg: "bg-gray-700",
          text: "text-gray-400",
          border: "border-gray-600",
        };
      default:
        return {
          bg: "bg-gray-700",
          text: "text-gray-400",
          border: "border-gray-600",
        };
    }
  };

  return (
    <div className="flex h-full flex-col -m-6 md:-m-8">
      {/* Header with controls */}
      <div className="border-b border-border-dark bg-[#111c22] p-4 shrink-0">
        <div className="flex flex-wrap justify-between items-start gap-4 mb-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-white text-2xl font-bold leading-tight font-display">
              Log Stream
            </h1>
            <p className="text-text-muted text-sm flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                {isConnected && (
                  <>
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-alt opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-primary-alt"></span>
                  </>
                )}
                {!isConnected && (
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-error"></span>
                )}
              </span>
              {isConnected ? "Listening on /api/ws/logs" : "Disconnected"}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setIsPaused(!isPaused)}
              className="flex items-center gap-2 px-4 h-9 bg-border-dark hover:bg-white/10 text-white text-sm font-medium rounded-lg border border-transparent transition-all"
            >
              <span className="material-symbols-outlined text-[18px]">
                {isPaused ? "play_arrow" : "pause"}
              </span>
              <span className="hidden sm:inline">
                {isPaused ? "Resume" : "Pause"}
              </span>
            </button>
            <button
              onClick={() => setLogs([])}
              className="flex items-center gap-2 px-4 h-9 bg-primary-alt hover:bg-blue-500 text-white text-sm font-bold rounded-lg shadow-lg shadow-primary-alt/20 transition-all"
            >
              <span className="material-symbols-outlined text-[18px]">
                refresh
              </span>
              <span className="hidden sm:inline">Clear</span>
            </button>
          </div>
        </div>

        {/* Mini stats */}
        <div className="flex flex-col gap-2">
          <div className="flex justify-between items-end">
            <span className="text-xs font-bold text-text-muted uppercase">
              Ingestion Rate
            </span>
            <span className="text-xs font-mono text-primary-alt">
              {logs.length} logs buffered
            </span>
          </div>
        </div>
      </div>

      {/* Filters bar */}
      <div className="flex items-center gap-3 p-4 bg-panel-dark border-b border-border-dark shrink-0">
        <div className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-text-muted">
            search
          </span>
          <input
            className="w-full h-10 pl-10 pr-4 bg-background-dark border border-border-dark rounded-lg text-white placeholder-text-muted focus:ring-1 focus:ring-primary-alt focus:border-primary-alt text-sm font-mono"
            placeholder="Search logs (e.g., level:error OR service:payment)..."
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Level Filters */}
        <div className="flex gap-2">
          <label className="flex items-center gap-2 px-2 py-1 bg-border-dark rounded cursor-pointer border border-transparent hover:border-text-muted/30">
            <input
              checked={filters.info}
              onChange={(e) =>
                setFilters({ ...filters, info: e.target.checked })
              }
              className="rounded border-gray-600 bg-background-dark text-primary-alt focus:ring-0 focus:ring-offset-0 size-3"
              type="checkbox"
            />
            <span className="text-xs text-text-muted">Info</span>
          </label>
          <label className="flex items-center gap-2 px-2 py-1 bg-border-dark rounded cursor-pointer border border-transparent hover:border-text-muted/30">
            <input
              checked={filters.error}
              onChange={(e) =>
                setFilters({ ...filters, error: e.target.checked })
              }
              className="rounded border-gray-600 bg-background-dark text-primary-alt focus:ring-0 focus:ring-offset-0 size-3"
              type="checkbox"
            />
            <span className="text-xs text-accent-yellow">Error</span>
          </label>
          <label className="flex items-center gap-2 px-2 py-1 bg-border-dark rounded cursor-pointer border border-transparent hover:border-text-muted/30">
            <input
              checked={filters.warn}
              onChange={(e) =>
                setFilters({ ...filters, warn: e.target.checked })
              }
              className="rounded border-gray-600 bg-background-dark text-primary-alt focus:ring-0 focus:ring-offset-0 size-3"
              type="checkbox"
            />
            <span className="text-xs text-orange-400">Warn</span>
          </label>
        </div>
      </div>

      {/* Log Table Header */}
      <div className="flex items-center px-4 py-2 bg-panel-dark border-b border-border-dark text-xs font-bold text-text-muted uppercase shrink-0">
        <div className="w-36 shrink-0">Timestamp</div>
        <div className="w-20 shrink-0">Level</div>
        <div className="w-32 shrink-0 hidden md:block">Service</div>
        <div className="flex-1">Message</div>
      </div>

      {/* Log Rows (Scrollable) */}
      <div
        ref={logContainerRef}
        className="flex-1 overflow-y-auto bg-background-dark relative group"
      >
        {filteredLogs.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <span className="material-symbols-outlined text-[64px] text-text-muted mb-4">
                stream
              </span>
              <p className="text-text-muted text-sm">
                {isConnected
                  ? "Waiting for logs..."
                  : "Disconnected. Trying to reconnect..."}
              </p>
            </div>
          </div>
        )}

        {filteredLogs.map((log, index) => {
          const levelColors = getLevelColor(log.level);
          const isError = log.level === "ERROR" || log.level === "FATAL";
          const isExpanded = selectedLog?.log_id === log.log_id;

          return (
            <div
              key={`${log.log_id}-${index}`}
              className={
                isExpanded
                  ? "flex flex-col border-b border-white/5 bg-[#142028]"
                  : ""
              }
            >
              <div
                onClick={() => setSelectedLog(isExpanded ? null : log)}
                className={`flex items-start px-4 py-2 border-b transition-colors cursor-pointer group/row ${
                  isError
                    ? `${levelColors.bg} border-accent-yellow/20 hover:bg-accent-yellow/10`
                    : "border-white/5 hover:bg-white/5"
                } ${isExpanded ? "border-l-2 border-primary-alt" : ""}`}
              >
                <div
                  className={`w-36 shrink-0 font-mono text-xs pt-0.5 ${
                    isError ? "text-accent-yellow" : "text-text-muted"
                  }`}
                >
                  {format(new Date(log.timestamp), "MMM dd HH:mm:ss.SSS")}
                </div>
                <div className="w-20 shrink-0 pt-0.5">
                  <span
                    className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${levelColors.bg} ${levelColors.text} border ${levelColors.border}`}
                  >
                    {log.level}
                  </span>
                </div>
                <div
                  className={`w-32 shrink-0 hidden md:block text-xs pt-0.5 ${
                    isError ? "text-accent-yellow" : "text-text-muted"
                  }`}
                >
                  {log.service}
                </div>
                <div className="flex-1 font-mono text-sm text-gray-300 break-all leading-relaxed">
                  {log.message}
                </div>
                <div className="w-8 shrink-0 flex justify-end opacity-0 group-hover/row:opacity-100">
                  <span className="material-symbols-outlined text-text-muted text-[16px]">
                    {isExpanded ? "expand_less" : "expand_more"}
                  </span>
                </div>
              </div>

              {/* Detail View */}
              {isExpanded && (
                <div className="px-4 py-3 pl-12 bg-black/20 font-mono text-xs text-text-muted overflow-x-auto">
                  <pre className="whitespace-pre-wrap">
                    {JSON.stringify(log, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="bg-[#111c22] border-t border-border-dark px-4 py-1.5 flex justify-between items-center text-[10px] text-text-muted shrink-0">
        <div className="flex gap-4">
          <span>
            Logs: {filteredLogs.length} / {logs.length}
          </span>
          <span>Filtered: {logs.length - filteredLogs.length}</span>
        </div>
        <div className="flex gap-4">
          <span className="flex items-center gap-1">
            <span
              className={`size-1.5 rounded-full ${
                isConnected ? "bg-green-500" : "bg-error"
              }`}
            ></span>
            {isConnected ? "Live" : "Disconnected"}
          </span>
          <span>v1.0.0</span>
        </div>
      </div>
    </div>
  );
};
