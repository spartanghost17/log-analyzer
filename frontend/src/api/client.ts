import axios from "axios";
import type { MetricPoint } from "./types";

// API Configuration
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8005";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Type definitions based on API_DOCUMENTATION.md
export interface LogEntry {
  log_id: string;
  timestamp: string;
  service: string;
  environment: string;
  level: "ERROR" | "WARN" | "INFO" | "DEBUG" | "FATAL";
  message: string;
  stack_trace?: string;
  trace_id?: string;
  host?: string;
  pod_name?: string;
  user_id?: string;
}

export interface ServiceHealth {
  name: string;
  status: "healthy" | "degraded" | "unhealthy";
}

export interface HealthResponse {
  status: "healthy" | "degraded";
  services: Record<string, string>;
}

export interface LogsResponse {
  logs: LogEntry[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface SemanticSearchRequest {
  query: string;
  top_k?: number;
  level?: string;
  service?: string;
  start_time?: string;
  end_time?: string;
}

export interface SemanticSearchResult {
  log_id: string;
  timestamp: string;
  service: string;
  level: string;
  message: string;
  similarity_score: number;
  trace_id?: string;
}

export interface SemanticSearchResponse {
  query: string;
  results: SemanticSearchResult[];
  count: number;
  generation_time_seconds: number;
}

export interface ErrorPattern {
  pattern_hash: string;
  normalized_message: string;
  occurrence_count: number;
  services: string[];
  environments: string[];
  max_level: string;
  first_seen: string;
  last_seen: string;
  is_known: boolean;
  category: string;
  trend?: string;
  sample_log_ids: string[];
}

export interface PatternsResponse {
  patterns: ErrorPattern[];
  total: number;
  limit: number;
}

export interface Report {
  report_id: string;
  report_date: string;
  start_time: string;
  end_time: string;
  total_logs_processed: number;
  error_count: number;
  warning_count: number;
  unique_error_patterns: number;
  new_error_patterns: number;
  anomalies_detected: number;
  critical_issues: number;
  executive_summary: string;
  top_issues?: any[];
  recommendations?: string[];
  affected_services?: string[];
  generation_time_seconds: number;
  llm_model_used?: string;
  tokens_used?: number;
  status: string;
  error_message?: string;
  created_at: string;
}

export interface ReportsResponse {
  reports: Report[];
  total: number;
  limit: number;
}

export interface Anomaly {
  alert_id: string;
  anomaly_type: string;
  detected_at: string;
  service: string;
  environment: string;
  severity: "low" | "medium" | "high" | "critical";
  description: string;
  confidence_score: number;
  status: "new" | "acknowledged" | "resolved";
  metrics?: Record<string, any>;
}

export interface AnomaliesResponse {
  anomalies: Anomaly[];
  total: number;
  limit: number;
}

export interface SystemMetrics {
  log_rate: number;
  error_rate: number;
  total_logs: number;
  total_errors: number;
  total_patterns: number;
  total_anomalies: number;
  storage_used_gb: number;
  vector_count: number;
  cache_hit_rate: number;
  services: Record<
    string,
    {
      log_count: number;
      error_count: number;
      error_rate: number;
    }
  >;
}

// API Client Methods
export const api = {
  // Health Check
  getHealth: async (): Promise<HealthResponse> => {
    const { data } = await apiClient.get("/health");
    return data;
  },

  // Logs API
  getLogs: async (params?: {
    level?: string;
    service?: string;
    start_time?: string;
    end_time?: string;
    limit?: number;
    offset?: number;
  }): Promise<LogsResponse> => {
    const { data } = await apiClient.get("/api/logs", { params });
    return data;
  },

  // Semantic Search
  searchSemantic: async (
    request: SemanticSearchRequest
  ): Promise<SemanticSearchResponse> => {
    const { data } = await apiClient.post("/api/search/semantic", request);
    return data;
  },

  // Error Patterns
  getPatterns: async (params?: {
    min_count?: number;
    max_count?: number;
    level?: string;
    service?: string;
    limit?: number;
  }): Promise<PatternsResponse> => {
    const { data } = await apiClient.get("/api/patterns", { params });
    return data;
  },

  // Reports
  getReports: async (params?: {
    date_from?: string;
    date_to?: string;
    limit?: number;
  }): Promise<ReportsResponse> => {
    const { data } = await apiClient.get("/api/reports", { params });
    return data;
  },

  // Metrics
  getMetrics: async (): Promise<SystemMetrics> => {
    const { data } = await apiClient.get("/api/metrics");
    return data;
  },

  getThroughput: async (): Promise<MetricPoint[]> => {
    const { data } = await apiClient.get("/api/metrics/throughput");
    return data;
  },

  // Anomalies
  getAnomalies: async (params?: {
    severity?: string;
    status?: string;
    service?: string;
    limit?: number;
  }): Promise<AnomaliesResponse> => {
    const { data } = await apiClient.get("/api/anomalies", { params });
    return data;
  },

  acknowledgeAnomaly: async (alertId: string): Promise<Anomaly> => {
    const { data } = await apiClient.patch(
      `/api/anomalies/${alertId}/acknowledge`
    );
    return data;
  },

  resolveAnomaly: async (alertId: string): Promise<Anomaly> => {
    const { data } = await apiClient.patch(`/api/anomalies/${alertId}/resolve`);
    return data;
  },

  // LLM Analyzer Service
  triggerAnalysis: async (params?: {
    start_time?: string;
    end_time?: string;
    services?: string[];
  }): Promise<any> => {
    const { data } = await apiClient.post(
      "http://localhost:8002/analyze",
      params
    );
    return data;
  },

  getLatestReport: async (): Promise<Report> => {
    const { data } = await apiClient.get(
      "http://localhost:8002/reports/latest"
    );
    return data;
  },

  // Log Generator Service
  getGeneratorStats: async (): Promise<any> => {
    const { data } = await apiClient.get("http://localhost:8000/stats");
    return data;
  },

  startGenerator: async (): Promise<any> => {
    const { data } = await apiClient.post("http://localhost:8000/start");
    return data;
  },

  stopGenerator: async (): Promise<any> => {
    const { data } = await apiClient.post("http://localhost:8000/stop");
    return data;
  },

  updateGeneratorControl: async (params: {
    rate_per_second: number;
    error_rate_percentage: number;
  }): Promise<any> => {
    const { data } = await apiClient.put(
      "http://localhost:8000/control",
      params
    );
    return data;
  },

  // Kafka Consumer Service
  getConsumerStats: async (): Promise<any> => {
    const { data } = await apiClient.get("http://localhost:8001/stats");
    return data;
  },

  // Jina Embeddings Service
  getEmbeddingsStats: async (): Promise<any> => {
    const { data } = await apiClient.get("http://localhost:8003/stats");
    return data;
  },

  // Vectorization Worker Service
  getVectorizationStats: async (): Promise<any> => {
    const { data } = await apiClient.get("http://localhost:8004/stats");
    return data;
  },

  // Anomaly Detection Z-Score Data
  getAnomalyZScoreData: async (): Promise<any> => {
    const { data } = await apiClient.get("/api/anomalies/zscore");
    return data;
  },
};

// WebSocket Client for Real-time Logs
export class LogStreamClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;

  constructor(
    private onMessage: (log: LogEntry) => void,
    private onError: (error: Event) => void,
    private onOpen: () => void,
    private onClose: () => void
  ) {}

  connect(level?: string) {
    const wsUrl = `ws://localhost:8005/api/ws/logs${
      level ? `?level=${level}` : ""
    }`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log("WebSocket connected");
        this.reconnectAttempts = 0;
        this.onOpen();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "new_log") {
            this.onMessage(data.data);
          }
        } catch (error) {
          console.error("Failed to parse WebSocket message:", error);
        }
      };

      this.ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        this.onError(error);
      };

      this.ws.onclose = () => {
        console.log("WebSocket closed");
        this.onClose();
        this.attemptReconnect(level);
      };
    } catch (error) {
      console.error("Failed to create WebSocket:", error);
    }
  }

  private attemptReconnect(level?: string) {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(
        `Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`
      );
      setTimeout(
        () => this.connect(level),
        this.reconnectDelay * this.reconnectAttempts
      );
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }
}

export default api;
