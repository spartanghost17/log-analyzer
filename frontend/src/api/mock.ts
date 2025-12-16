import type {
  LogEntry,
  LogsResponse,
  SystemMetrics,
  HealthResponse,
  SemanticSearchResult,
  SemanticSearchResponse,
  ErrorPattern,
  PatternsResponse,
  Report,
  ReportsResponse,
  Anomaly,
  AnomaliesResponse,
  TopIssue,
} from "./client";
import type { MetricPoint } from "./types";

// Helper function to generate random dates
const randomDate = (hoursAgo: number = 24) => {
  const now = Date.now();
  const ago = hoursAgo * 60 * 60 * 1000;
  return new Date(now - Math.random() * ago).toISOString();
};

// Generate mock logs
const generateMockLogs = (count: number): LogEntry[] => {
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

  return Array.from({ length: count }, (_, i) => ({
    log_id: `log-${Date.now()}-${i}`,
    timestamp: randomDate(1),
    service: services[Math.floor(Math.random() * services.length)],
    environment: "production",
    level: levels[Math.floor(Math.random() * levels.length)],
    message: messages[Math.floor(Math.random() * messages.length)],
    trace_id: `trace-${Math.random().toString(36).substr(2, 9)}`,
    host: `host-${Math.floor(Math.random() * 10)}`,
    pod_name: `pod-${Math.random().toString(36).substr(2, 6)}`,
  }));
};

// Generate mock throughput data
const generateThroughputData = (): MetricPoint[] => {
  return Array.from({ length: 24 }, (_, i) => ({
    time: `${String(i).padStart(2, "0")}:00`,
    value: Math.floor(Math.random() * 3000) + 1000,
    errors: Math.floor(Math.random() * 50),
  }));
};

// Mock System Metrics
const mockSystemMetrics: SystemMetrics = {
  log_rate: 50.2,
  error_rate: 0.048,
  total_logs: 2450000,
  total_errors: 11760,
  total_patterns: 47,
  total_anomalies: 3,
  storage_used_gb: 15.3,
  vector_count: 11760,
  cache_hit_rate: 0.875,
  services: {
    "api-gateway": {
      log_count: 750000,
      error_count: 3600,
      error_rate: 0.0048,
    },
    "auth-service": {
      log_count: 500000,
      error_count: 2400,
      error_rate: 0.0048,
    },
    "payment-gateway": {
      log_count: 400000,
      error_count: 2000,
      error_rate: 0.005,
    },
    "user-service": {
      log_count: 450000,
      error_count: 2160,
      error_rate: 0.0048,
    },
    analytics: {
      log_count: 350000,
      error_count: 1600,
      error_rate: 0.0046,
    },
  },
};

// Mock Health Response
const mockHealthResponse: HealthResponse = {
  status: "healthy",
  services: {
    clickhouse: "healthy",
    postgresql: "healthy",
    qdrant: "degraded",
    redis: "healthy",
  },
};

// Mock Anomalies
const mockAnomalies: Anomaly[] = [
  {
    alert_id: "anom-001",
    anomaly_type: "error_spike",
    detected_at: randomDate(2),
    service: "payment-gateway",
    environment: "production",
    severity: "critical",
    description:
      "High frequency error pattern detected: Connection timeout to database",
    confidence_score: 0.92,
    status: "new",
    metrics: {
      occurrence_count: 523,
      percentage_of_errors: 22.3,
      threshold: 100,
    },
  },
  {
    alert_id: "anom-002",
    anomaly_type: "latency_spike",
    detected_at: randomDate(3),
    service: "api-gateway",
    environment: "production",
    severity: "high",
    description: "Response time increased by 300% compared to baseline",
    confidence_score: 0.85,
    status: "acknowledged",
    metrics: {
      current_latency: 450,
      baseline_latency: 150,
      spike_percentage: 300,
    },
  },
  {
    alert_id: "anom-003",
    anomaly_type: "memory_leak",
    detected_at: randomDate(5),
    service: "user-service",
    environment: "production",
    severity: "medium",
    description: "Memory usage growing at 2MB/min without releases",
    confidence_score: 0.78,
    status: "resolved",
  },
];

// Mock Error Patterns
const mockErrorPatterns: ErrorPattern[] = [
  {
    pattern_hash: "abc123def456",
    normalized_message: "Connection timeout to database after <NUM>ms",
    occurrence_count: 523,
    services: ["api-gateway", "user-service"],
    environments: ["production"],
    max_level: "ERROR",
    first_seen: randomDate(72),
    last_seen: randomDate(1),
    is_known: false,
    category: "auto-detected",
    trend: "increasing",
    sample_log_ids: ["log-001", "log-002", "log-003"],
  },
  {
    pattern_hash: "def456ghi789",
    normalized_message: "Rate limit exceeded for endpoint <PATH>",
    occurrence_count: 342,
    services: ["api-gateway"],
    environments: ["production"],
    max_level: "WARN",
    first_seen: randomDate(48),
    last_seen: randomDate(2),
    is_known: true,
    category: "rate-limiting",
    trend: "stable",
    sample_log_ids: ["log-004", "log-005"],
  },
  {
    pattern_hash: "ghi789jkl012",
    normalized_message: "Invalid authentication token for user <USER_ID>",
    occurrence_count: 234,
    services: ["auth-service"],
    environments: ["production"],
    max_level: "ERROR",
    first_seen: randomDate(96),
    last_seen: randomDate(1),
    is_known: true,
    category: "authentication",
    trend: "decreasing",
    sample_log_ids: ["log-006", "log-007"],
  },
];

// Mock Top Issues (matching actual database structure)
const mockTopIssues: TopIssue[] = [
  {
    pattern_hash: "abc123def456",
    normalized_message: "Database connection timeout after <NUM>ms",
    example_message: "Database connection timeout after 5000ms",
    count: 856,
    max_level: "ERROR",
    services: ["api-gateway", "user-service"],
    first_seen: randomDate(96),
    last_seen: randomDate(1),
    sample_log_ids: ["log-001", "log-002", "log-003"],
  },
  {
    pattern_hash: "def456ghi789",
    normalized_message: "Redis connection failed: <ERROR>",
    example_message: "Redis connection failed: ECONNREFUSED",
    count: 542,
    max_level: "FATAL",
    services: ["auth-service", "api-gateway"],
    first_seen: randomDate(72),
    last_seen: randomDate(2),
    sample_log_ids: ["log-004", "log-005"],
  },
  {
    pattern_hash: "ghi789jkl012",
    normalized_message: "Invalid authentication token for user <USER_ID>",
    example_message: "Invalid authentication token for user user_12345",
    count: 234,
    max_level: "ERROR",
    services: ["auth-service"],
    first_seen: randomDate(96),
    last_seen: randomDate(1),
    sample_log_ids: ["log-006", "log-007"],
  },
  {
    pattern_hash: "jkl012mno345",
    normalized_message: "Payment processing failed: insufficient funds",
    example_message: "Payment processing failed: insufficient funds",
    count: 187,
    max_level: "ERROR",
    services: ["payment-service"],
    first_seen: randomDate(48),
    last_seen: randomDate(3),
    sample_log_ids: ["log-008", "log-009"],
  },
  {
    pattern_hash: "mno345pqr678",
    normalized_message: "External API returned <NUM> error",
    example_message: "External API returned 500 error",
    count: 145,
    max_level: "WARN",
    services: ["api-gateway", "notification-service"],
    first_seen: randomDate(120),
    last_seen: randomDate(1),
    sample_log_ids: ["log-010", "log-011"],
  },
];

// Mock Reports
const mockReports: Report[] = [
  {
    report_id: "550e8400-e29b-41d4-a716-446655440001",
    report_date: new Date().toISOString().split("T")[0],
    start_time: new Date(Date.now() - 86400000).toISOString(),
    end_time: new Date().toISOString(),
    total_logs_processed: 432156,
    error_count: 2341,
    warning_count: 8723,
    unique_error_patterns: 47,
    new_error_patterns: 12,
    anomalies_detected: 3,
    critical_issues: 5,
    executive_summary:
      "System health is generally good with 99.5% uptime. Detected spike in database connection timeouts affecting api-gateway service between 14:00-15:00. Root cause appears to be connection pool exhaustion under peak load. Recommend increasing connection pool size and implementing circuit breaker pattern.",
    top_issues: mockTopIssues.slice(0, 5),
    recommendations: [
      "Increase Redis memory allocation",
      "Restart Service: Auth-Provider",
      "Investigate api-gateway database connection pool settings",
      "Implement circuit breaker for database connections",
    ],
    affected_services: {
      count: 4,
      services: ["redis", "auth-service", "api-gateway", "postgresql"],
    },
    generation_time_seconds: 125.3,
    llm_model_used: "deepseek-coder:6.7b",
    tokens_used: 15420,
    status: "completed",
    error_message: null,
    created_at: new Date().toISOString(),
  },
  {
    report_id: "550e8400-e29b-41d4-a716-446655440002",
    report_date: new Date(Date.now() - 86400000).toISOString().split("T")[0],
    start_time: new Date(Date.now() - 172800000).toISOString(),
    end_time: new Date(Date.now() - 86400000).toISOString(),
    total_logs_processed: 398234,
    error_count: 1987,
    warning_count: 7456,
    unique_error_patterns: 42,
    new_error_patterns: 8,
    anomalies_detected: 2,
    critical_issues: 3,
    executive_summary:
      "System performed well with minor authentication issues. Rate limiting working as expected to prevent abuse. Overall stability maintained throughout the analysis period.",
    top_issues: mockTopIssues.slice(0, 3),
    recommendations: [
      "Review authentication token expiration policies",
      "Consider implementing token refresh mechanism",
    ],
    affected_services: {
      count: 2,
      services: ["auth-service", "api-gateway"],
    },
    generation_time_seconds: 108.7,
    llm_model_used: "deepseek-coder:6.7b",
    tokens_used: 12350,
    status: "completed",
    error_message: null,
    created_at: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    report_id: "550e8400-e29b-41d4-a716-446655440003",
    report_date: new Date(Date.now() - 172800000).toISOString().split("T")[0],
    start_time: new Date(Date.now() - 259200000).toISOString(),
    end_time: new Date(Date.now() - 172800000).toISOString(),
    total_logs_processed: 445678,
    error_count: 3124,
    warning_count: 9234,
    unique_error_patterns: 53,
    new_error_patterns: 15,
    anomalies_detected: 4,
    critical_issues: 7,
    executive_summary:
      "Elevated error rates detected across multiple services. Payment gateway experienced intermittent connectivity issues. Database performance degraded during peak hours.",
    top_issues: mockTopIssues.slice(0, 4),
    recommendations: [
      "Scale up database resources during peak hours",
      "Investigate payment gateway network connectivity",
      "Review error handling in user-service",
      "Implement retry logic for transient failures",
    ],
    affected_services: {
      count: 4,
      services: ["payment-gateway", "api-gateway", "user-service", "auth-service"],
    },
    generation_time_seconds: 142.6,
    llm_model_used: "deepseek-coder:6.7b",
    tokens_used: 18750,
    status: "completed",
    error_message: null,
    created_at: new Date(Date.now() - 172800000).toISOString(),
  },
];

// Mock Semantic Search Results
const mockSemanticSearchResults: SemanticSearchResult[] = [
  {
    log_id: "log-semantic-001",
    timestamp: randomDate(1),
    service: "payment-gateway",
    level: "ERROR",
    message:
      "Connection timeout while reaching upstream payment-gateway:5432. Retrying... (Attempt 3/5)",
    similarity_score: 0.98,
    trace_id: "trace-abc123",
  },
  {
    log_id: "log-semantic-002",
    timestamp: randomDate(1),
    service: "payment-api",
    level: "WARN",
    message:
      "PaymentGatewayClient: Latency spike detected (4500ms). Circuit breaker state: HALF_OPEN.",
    similarity_score: 0.92,
    trace_id: "trace-def456",
  },
  {
    log_id: "log-semantic-003",
    timestamp: randomDate(2),
    service: "auth-service",
    level: "ERROR",
    message: "AuthService: Token validation failed due to timeout from DB.",
    similarity_score: 0.89,
    trace_id: "trace-ghi789",
  },
];

// Mock API Implementation
export const mockApi = {
  // Health
  getHealth: async (): Promise<HealthResponse> => {
    await new Promise((r) => setTimeout(r, 300));
    return mockHealthResponse;
  },

  // Metrics
  getMetrics: async (): Promise<SystemMetrics> => {
    await new Promise((r) => setTimeout(r, 500));
    return mockSystemMetrics;
  },

  // Logs
  getLogs: async (params?: any): Promise<LogsResponse> => {
    await new Promise((r) => setTimeout(r, 400));
    const logs = generateMockLogs(params?.limit || 100);
    return {
      logs,
      total: 2450000,
      limit: params?.limit || 100,
      offset: params?.offset || 0,
      has_more: true,
    };
  },

  // Semantic Search
  searchSemantic: async (request: any): Promise<SemanticSearchResponse> => {
    await new Promise((r) => setTimeout(r, 800));
    return {
      query: request.query,
      results: mockSemanticSearchResults,
      count: mockSemanticSearchResults.length,
      generation_time_seconds: 0.125,
    };
  },

  // Error Patterns
  getPatterns: async (params?: any): Promise<PatternsResponse> => {
    await new Promise((r) => setTimeout(r, 500));
    return {
      patterns: mockErrorPatterns,
      total: mockErrorPatterns.length,
      limit: params?.limit || 100,
    };
  },

  // Reports
  getReports: async (params?: any): Promise<ReportsResponse> => {
    await new Promise((r) => setTimeout(r, 600));
    return {
      reports: mockReports,
      total: mockReports.length,
      limit: params?.limit || 10,
    };
  },

  getLatestReport: async (): Promise<Report> => {
    await new Promise((r) => setTimeout(r, 400));
    return mockReports[0];
  },

  // Anomalies
  getAnomalies: async (params?: any): Promise<AnomaliesResponse> => {
    await new Promise((r) => setTimeout(r, 500));
    return {
      anomalies: mockAnomalies.filter(
        (a) => !params?.severity || a.severity === params.severity
      ),
      total: mockAnomalies.length,
      limit: params?.limit || 50,
    };
  },

  // Acknowledge anomaly (mock)
  acknowledgeAnomaly: async (alertId: string): Promise<Anomaly> => {
    await new Promise((r) => setTimeout(r, 800));
    const anomaly = mockAnomalies.find((a) => a.alert_id === alertId);
    if (!anomaly) throw new Error("Anomaly not found");
    return { ...anomaly, status: "acknowledged" };
  },

  // Resolve anomaly (mock)
  resolveAnomaly: async (alertId: string): Promise<Anomaly> => {
    await new Promise((r) => setTimeout(r, 800));
    const anomaly = mockAnomalies.find((a) => a.alert_id === alertId);
    if (!anomaly) throw new Error("Anomaly not found");
    return { ...anomaly, status: "resolved" };
  },

  // Throughput data
  getThroughput: async (): Promise<MetricPoint[]> => {
    await new Promise((r) => setTimeout(r, 400));
    return generateThroughputData();
  },

  // Log Generator Stats
  getGeneratorStats: async (): Promise<any> => {
    await new Promise((r) => setTimeout(r, 300));
    return {
      total_generated: 2450000,
      total_sent: 2449850,
      total_failed: 150,
      current_rate: 50,
      error_rate: 5,
      is_running: true,
    };
  },

  // Consumer Stats
  getConsumerStats: async (): Promise<any> => {
    await new Promise((r) => setTimeout(r, 300));
    return {
      total_consumed: 2450000,
      total_written: 2449700,
      total_failed: 50,
      total_dlq: 250,
      total_vectorization_sent: 11760,
      current_batch_size: 342,
      retry_count: 5,
      circuit_breaker_state: "closed",
    };
  },

  // Embeddings Stats
  getEmbeddingsStats: async (): Promise<any> => {
    await new Promise((r) => setTimeout(r, 300));
    return {
      total_embeddings_generated: 125000,
      total_embeddings_failed: 150,
      cache_hits: 109375,
      cache_misses: 15625,
      cache_hit_rate: 87.5,
      circuit_breaker_failures: 2,
      model: "jina-embeddings-v3",
      dimension: 768,
      max_batch_size: 100,
    };
  },

  // Vectorization Stats
  getVectorizationStats: async (): Promise<any> => {
    await new Promise((r) => setTimeout(r, 300));
    return {
      total_consumed: 11760,
      total_embedded: 11700,
      total_stored: 11700,
      total_failed: 60,
      total_clickhouse_updates: 11700,
      total_dlq_sent: 60,
      current_batch_size: 7,
    };
  },

  // Anomaly Detection Z-Score Data
  getAnomalyZScoreData: async (params?: {
    hours?: number;
    service?: string;
    level?: string;
    threshold?: number;
    report_start_time?: string;
  }): Promise<any> => {
    await new Promise((r) => setTimeout(r, 400));
    
    // Use report_start_time if provided, otherwise use current time
    const endTime = params?.report_start_time 
      ? new Date(params.report_start_time).getTime() 
      : Date.now();
    
    const hours = params?.hours || 24;
    const threshold = params?.threshold || 1.0;
    
    // Generate realistic anomaly detection data
    const points = 50;
    const data = Array.from({ length: points }, (_, i) => {
      // Create a baseline with some noise
      let value = Math.random() * 0.5 - 0.25;
      // Add spike patterns at different points
      if (i > 30 && i < 40) {
        value += Math.random() * 2 + 1; // Significant spike
      } else if (i > 15 && i < 18) {
        value += Math.random() * 1.5 + 0.5; // Minor spike
      }
      
      // Calculate timestamp working backwards from endTime
      const intervalMs = (hours * 60 * 60 * 1000) / points; // Distribute evenly over time range
      const timestamp = new Date(endTime - (points - i) * intervalMs).toISOString();
      
      return {
        index: i,
        z_score: value,
        is_anomaly: Math.abs(value) > threshold,
        timestamp: timestamp,
      };
    });
    
    return {
      data_points: data,
      threshold: threshold,
      time_range: {
        start: data[0].timestamp,
        end: data[data.length - 1].timestamp,
      },
      anomaly_count: data.filter(d => d.is_anomaly).length,
      baseline_mean: 0,
      baseline_stddev: 0.8,
    };
  },
};

export default mockApi;
