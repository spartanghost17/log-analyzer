export interface LogEntry {
  id: string;
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR" | "DEBUG" | "FATAL";
  service: string;
  message: string;
  metadata?: Record<string, any>;
}

export interface ServiceHealth {
  name: string;
  status: "healthy" | "degraded" | "down";
  version: string;
  uptime: number;
}

export interface AnomalyCluster {
  id: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  timestamp: string;
  source: string;
  description: string;
  status: "active" | "resolved" | "investigating";
}

export interface MetricPoint {
  time: string;
  value: number;
  errors?: number;
}

export interface OverviewMetrics {
  total_logs: number;
  error_rate?: number;
  avg_latency: number;
  active_anomalies: number;
}
