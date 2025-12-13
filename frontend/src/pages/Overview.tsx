import React from "react";
import { useQuery } from "@tanstack/react-query";
import { mockApi } from "../api/mock";
import { api } from "../api/client";
import { MetricCard } from "../components/ui/MetricCard";
import { MainChart } from "../components/charts/MainChart";
import { format } from "date-fns";

// Toggle this to switch between mock and real API
const USE_MOCK_API = true;

export const Overview = () => {
  const { data: metrics, isLoading: loadingMetrics } = useQuery({
    queryKey: ["metrics"],
    queryFn: USE_MOCK_API ? mockApi.getMetrics : api.getMetrics,
    refetchInterval: USE_MOCK_API ? false : 10000,
  });

  const { data: healthData } = useQuery({
    queryKey: ["health"],
    queryFn: USE_MOCK_API ? mockApi.getHealth : api.getHealth,
    refetchInterval: USE_MOCK_API ? false : 5000,
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
  const services = healthData?.services || {};

  // Convert services object to array
  const servicesArray = Object.entries(services).map(([name, status]) => ({
    name,
    status: status as "healthy" | "degraded" | "unhealthy",
  }));

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Metrics Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Total Logs Ingested"
          value={metrics?.total_logs?.toLocaleString() || "-"}
          icon="database"
          loading={loadingMetrics}
          trend={
            metrics?.log_rate ? `+${metrics.log_rate.toFixed(1)}/s` : undefined
          }
        />
        <MetricCard
          label="Error Rate"
          value={`${(metrics?.error_rate! * 100 || 0).toFixed(2)}%`}
          icon="error"
          loading={loadingMetrics}
          trend={`${metrics?.total_errors?.toLocaleString() || 0} errors`}
        />
        <MetricCard
          label="Cache Hit Rate"
          value={`${(metrics?.cache_hit_rate! * 100 || 0).toFixed(1)}%`}
          icon="memory"
          loading={loadingMetrics}
          trend={`${metrics?.storage_used_gb?.toFixed(1) || 0} GB used`}
        />
        <div className="rounded-xl border border-primary/30 bg-panel-light p-5 shadow-[0_0_15px_rgba(250,204,21,0.05)] relative overflow-hidden group">
          <div className="mb-2 flex items-center justify-between relative z-10">
            <p className="text-sm font-medium text-primary uppercase tracking-wider">
              Active Anomalies
            </p>
            <span className="material-symbols-outlined text-primary text-[20px] animate-pulse">
              notifications_active
            </span>
          </div>
          {loadingMetrics ? (
            <div className="h-8 w-1/3 rounded bg-border-dark animate-pulse"></div>
          ) : (
            <div className="flex items-baseline gap-2 relative z-10">
              <span className="text-3xl font-bold text-white font-display">
                {metrics?.total_anomalies || 0}
              </span>
              <span className="text-xs text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20">
                TOTAL
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main Chart */}
        <div className="lg:col-span-2">
          <MainChart data={throughputData || []} loading={loadingThroughput} />
        </div>

        {/* System Health List */}
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-border-dark bg-panel-light p-6 h-full">
            <h3 className="mb-4 text-lg font-bold text-white">System Health</h3>
            <div className="space-y-3">
              {!healthData ? (
                [1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-12 w-full rounded-lg bg-border-dark/30 animate-pulse"
                  ></div>
                ))
              ) : servicesArray.length === 0 ? (
                <div className="text-center text-text-muted py-4">
                  No services data
                </div>
              ) : (
                servicesArray.map((service) => (
                  <div
                    key={service.name}
                    className={`flex items-center justify-between rounded-lg p-3 ${
                      service.status === "degraded"
                        ? "bg-background-dark border border-warning/30"
                        : service.status === "unhealthy"
                        ? "bg-background-dark border border-error/30"
                        : "bg-background-dark border border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="material-symbols-outlined text-text-muted">
                        {service.name === "qdrant"
                          ? "dns"
                          : service.name === "clickhouse"
                          ? "database"
                          : service.name === "postgresql"
                          ? "storage"
                          : service.name === "redis"
                          ? "memory"
                          : "hub"}
                      </span>
                      <span className="text-sm font-medium text-white capitalize">
                        {service.name.replace("_", " ")}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          service.status === "healthy"
                            ? "bg-success shadow-[0_0_8px_rgba(34,197,94,0.6)]"
                            : service.status === "degraded"
                            ? "bg-warning shadow-[0_0_8px_rgba(249,115,22,0.6)]"
                            : "bg-error shadow-[0_0_8px_rgba(250,204,21,0.6)]"
                        }`}
                      ></span>
                      <span
                        className={`text-xs font-bold ${
                          service.status === "healthy"
                            ? "text-success"
                            : service.status === "degraded"
                            ? "text-warning"
                            : "text-error"
                        }`}
                      >
                        {service.status === "healthy"
                          ? "Healthy"
                          : service.status === "degraded"
                          ? "Degraded"
                          : "Down"}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* AI Insight Card */}
          <div className="flex-1 rounded-xl border border-primary/20 bg-gradient-to-br from-[#2d2b15] to-[#16232b] p-6 relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
              <span className="material-symbols-outlined text-[80px] text-primary">
                auto_awesome
              </span>
            </div>
            <div className="flex items-center gap-2 mb-3">
              <span className="material-symbols-outlined text-primary text-[20px]">
                auto_awesome
              </span>
              <h3 className="text-base font-bold text-white">
                AI Daily Insight
              </h3>
            </div>
            <p className="text-sm leading-relaxed text-text-muted relative z-10">
              <span className="text-white font-medium">Attention:</span> System
              monitoring active. Check error patterns and anomalies for optimal
              performance.
            </p>
            <button className="mt-4 text-xs font-bold text-primary hover:underline flex items-center gap-1 z-10 relative cursor-pointer">
              View Full Report{" "}
              <span className="material-symbols-outlined text-[14px]">
                arrow_forward
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Critical Anomalies Table */}
      <div className="rounded-xl border border-border-dark bg-panel-dark overflow-hidden">
        <div className="flex items-center justify-between border-b border-border-dark px-6 py-4">
          <h3 className="text-lg font-bold text-white">
            Recent Critical Anomalies
          </h3>
          <button className="text-xs font-bold text-text-muted hover:text-white cursor-pointer">
            View All
          </button>
        </div>

        {loadingAnomalies ? (
          <div className="p-12 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : anomalies.length === 0 ? (
          <div className="p-12 text-center text-text-muted">
            <span className="material-symbols-outlined text-[64px] mb-4">
              check_circle
            </span>
            <p>No critical anomalies detected</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-background-dark text-xs uppercase text-text-muted">
                <tr>
                  <th className="px-6 py-3 font-bold">Severity</th>
                  <th className="px-6 py-3 font-bold">Timestamp</th>
                  <th className="px-6 py-3 font-bold">Source</th>
                  <th className="px-6 py-3 font-bold">Type</th>
                  <th className="px-6 py-3 font-bold">Description</th>
                  <th className="px-6 py-3 font-bold">Status</th>
                  <th className="px-6 py-3 font-bold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-dark">
                {anomalies.map((anomaly) => (
                  <tr
                    key={anomaly.alert_id}
                    className="hover:bg-border-dark/30"
                  >
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center rounded px-2 py-1 text-xs font-bold ring-1 ring-inset ${
                          anomaly.severity === "critical"
                            ? "bg-red-500/10 text-red-500 ring-red-500/20"
                            : anomaly.severity === "high"
                            ? "bg-orange-500/10 text-orange-500 ring-orange-500/20"
                            : anomaly.severity === "medium"
                            ? "bg-yellow-500/10 text-yellow-500 ring-yellow-500/20"
                            : "bg-blue-500/10 text-blue-500 ring-blue-500/20"
                        }`}
                      >
                        {anomaly.severity.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-white font-mono text-xs">
                      {format(new Date(anomaly.detected_at), "MMM d, HH:mm:ss")}
                    </td>
                    <td className="px-6 py-4 text-text-muted">
                      {anomaly.service}
                    </td>
                    <td className="px-6 py-4 text-text-muted capitalize">
                      {anomaly.anomaly_type.replace("_", " ")}
                    </td>
                    <td className="px-6 py-4 text-white max-w-md truncate">
                      {anomaly.description}
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center rounded px-2 py-1 text-xs font-medium ${
                          anomaly.status === "new"
                            ? "bg-primary/10 text-primary"
                            : anomaly.status === "acknowledged"
                            ? "bg-blue-500/10 text-blue-400"
                            : "bg-success/10 text-success"
                        }`}
                      >
                        {anomaly.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button className="text-primary hover:text-white cursor-pointer">
                        <span className="material-symbols-outlined text-[20px]">
                          search
                        </span>
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
