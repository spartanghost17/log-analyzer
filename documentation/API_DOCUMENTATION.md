# 🌐 API Documentation

Complete API reference for all services in the log analysis platform. All services use FastAPI with OpenAPI documentation available at `http://localhost:<port>/docs`.

---

## 📦 Service Overview

| Service | Port | Base URL | OpenAPI Docs |
|---------|------|----------|--------------|
| **Log Generator** | 8000 | http://localhost:8000 | http://localhost:8000/docs |
| **Kafka Consumer** | 8001 | http://localhost:8001 | http://localhost:8001/docs |
| **LLM Analyzer** | 8002 | http://localhost:8002 | http://localhost:8002/docs |
| **Jina Embeddings** | 8003 | http://localhost:8003 | http://localhost:8003/docs |
| **Vectorization Worker** | 8004 | http://localhost:8004 | http://localhost:8004/docs |
| **API Gateway** | 8005 | http://localhost:8005 | http://localhost:8005/docs |

---

## 🔧 Log Generator Service (Port 8000)

Generates realistic synthetic logs and produces them to Kafka.

### GET `/health`

Health check with service status.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "log-generator",
  "version": "1.0.0",
  "kafka_connected": true,
  "is_generating": true,
  "logs_generated": 50000,
  "logs_sent": 49998,
  "current_rate": 50,
  "uptime_seconds": 3600.5
}
```

**cURL:**
```bash
curl http://localhost:8000/health
```

---

### GET `/stats`

Get current generator statistics.

**Response (200 OK):**
```json
{
  "total_generated": 50000,
  "total_sent": 49998,
  "total_failed": 2,
  "current_rate": 50,
  "error_rate": 5,
  "is_running": true
}
```

**cURL:**
```bash
curl http://localhost:8000/stats
```

---

### POST `/start`

Start log generation.

**Response (200 OK):**
```json
{
  "status": "started",
  "rate": 50
}
```

**Response (200 OK - Already Running):**
```json
{
  "status": "already_running",
  "rate": 50
}
```

**cURL:**
```bash
curl -X POST http://localhost:8000/start
```

---

### POST `/stop`

Stop log generation.

**Response (200 OK):**
```json
{
  "status": "stopped"
}
```

**Response (200 OK - Already Stopped):**
```json
{
  "status": "already_stopped"
}
```

**cURL:**
```bash
curl -X POST http://localhost:8000/stop
```

---

### PUT `/control`

Update generation parameters (rate and error percentage).

**Request Body:**
```json
{
  "rate_per_second": 100,
  "error_rate_percentage": 15
}
```

**Parameters:**
- `rate_per_second` (integer, 1-10000): Logs per second to generate
- `error_rate_percentage` (integer, 0-100): Percentage of error logs

**Response (200 OK):**
```json
{
  "status": "updated",
  "rate_per_second": 100,
  "error_rate_percentage": 15
}
```

**cURL:**
```bash
curl -X PUT http://localhost:8000/control \
  -H "Content-Type: application/json" \
  -d '{
    "rate_per_second": 100,
    "error_rate_percentage": 15
  }'
```

---

### GET `/metrics`

Prometheus metrics endpoint.

**Metrics:**
- `logs_generated_total` - Total logs generated
- `logs_sent_total` - Total logs successfully sent to Kafka
- `logs_send_failed_total` - Total send failures
- `generation_rate_per_second` - Current generation rate
- `error_log_rate_percentage` - Current error rate percentage

**Response (200 OK):**
```
# HELP logs_generated_total Total logs generated
# TYPE logs_generated_total counter
logs_generated_total 50000.0
# HELP logs_sent_total Total logs sent to Kafka
# TYPE logs_sent_total counter
logs_sent_total 49998.0
...
```

**cURL:**
```bash
curl http://localhost:8000/metrics
```

---

## 📊 Kafka Consumer Service (Port 8001)

Consumes logs from Kafka and writes to ClickHouse with at-least-once delivery.

### GET `/health`

Health check with dependency status.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "clickhouse-consumer",
  "version": "2.0.0",
  "kafka_connected": true,
  "clickhouse_connected": true,
  "clickhouse_circuit_breaker": "closed",
  "messages_processed": 50000,
  "current_batch_size": 342,
  "uptime_seconds": 3600.5
}
```

**cURL:**
```bash
curl http://localhost:8001/health
```

---

### GET `/ready`

Kubernetes readiness probe - checks if service is ready to accept traffic.

**Response (200 OK):**
```json
{
  "status": "ready"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Consumer not running"
}
```

**cURL:**
```bash
curl http://localhost:8001/ready
```

---

### GET `/live`

Kubernetes liveness probe - checks if service is alive.

**Response (200 OK):**
```json
{
  "status": "alive"
}
```

**cURL:**
```bash
curl http://localhost:8001/live
```

---

### GET `/stats`

Get consumer statistics including DLQ and vectorization metrics.

**Response (200 OK):**
```json
{
  "total_consumed": 50000,
  "total_written": 49850,
  "total_failed": 20,
  "total_dlq": 150,
  "total_vectorization_sent": 2500,
  "current_batch_size": 342,
  "retry_count": 5,
  "circuit_breaker_state": "closed"
}
```

**cURL:**
```bash
curl http://localhost:8001/stats
```

---

### POST `/flush`

Force flush current batch to ClickHouse.

**Response (200 OK):**
```json
{
  "status": "flushed",
  "batch_size": 0
}
```

**cURL:**
```bash
curl -X POST http://localhost:8001/flush
```

---

### GET `/metrics`

Prometheus metrics endpoint.

**Metrics:**
- `messages_consumed_total{topic, partition}` - Total messages consumed from Kafka
- `messages_written_total` - Total messages written to ClickHouse
- `messages_failed_total` - Total processing failures
- `messages_dlq_total` - Total messages sent to Dead Letter Queue
- `messages_vectorization_total` - Total messages sent to vectorization queue
- `message_processing_seconds` - Processing time histogram
- `current_batch_size` - Current batch size gauge
- `consumer_lag{topic, partition}` - Kafka consumer lag
- `clickhouse_circuit_breaker_state` - Circuit breaker state (0=closed, 1=open, 2=half-open)
- `batch_retry_total` - Total batch retry attempts

**cURL:**
```bash
curl http://localhost:8001/metrics
```

---

## 🤖 LLM Analyzer Service (Port 8002)

Analyzes log patterns using LLM (Ollama) and generates reports.

### GET `/health`

Health check with all dependencies.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "llm-analyzer",
  "version": "2.0.0",
  "clickhouse_connected": true,
  "postgres_connected": true,
  "ollama_connected": true,
  "last_analysis": "2024-12-11T10:30:00Z"
}
```

**cURL:**
```bash
curl http://localhost:8002/health
```

---

### POST `/analyze`

Trigger manual log analysis.

**Request Body (Optional):**
```json
{
  "start_time": "2024-12-11T00:00:00Z",
  "end_time": "2024-12-11T23:59:59Z",
  "services": ["api-gateway", "user-service"]
}
```

**Parameters:**
- `start_time` (string, ISO 8601, optional): Analysis window start time (defaults to 24 hours ago)
- `end_time` (string, ISO 8601, optional): Analysis window end time (defaults to now)
- `services` (array of strings, optional): Filter by specific services

**Response (200 OK):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "report_id": "b2c3d4e5-f6a7-8901-bcde-f234567890ab",
  "report_date": "2024-12-11",
  "total_logs": 432156,
  "error_count": 2341,
  "unique_patterns": 47,
  "anomalies_detected": 3,
  "executive_summary": "System health is generally good. Detected spike in database connection timeouts affecting api-gateway service between 14:00-15:00. Root cause appears to be connection pool exhaustion under peak load.",
  "generation_time_seconds": 125.3,
  "status": "completed"
}
```

**cURL:**
```bash
# Analyze last 24 hours (default)
curl -X POST http://localhost:8002/analyze

# Analyze specific time range
curl -X POST http://localhost:8002/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2024-12-11T00:00:00Z",
    "end_time": "2024-12-11T23:59:59Z",
    "services": ["api-gateway"]
  }'
```

---

### GET `/reports/latest`

Get the most recent analysis report.

**Response (200 OK):**
```json
{
  "report_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "report_date": "2024-12-11",
  "start_time": "2024-12-10T00:00:00Z",
  "end_time": "2024-12-11T00:00:00Z",
  "total_logs_processed": 432156,
  "error_count": 2341,
  "unique_error_patterns": 47,
  "anomalies_detected": 3,
  "executive_summary": "System health is generally good...",
  "top_issues": [
    {
      "pattern_hash": "abc123def456",
      "normalized_message": "Connection timeout to database after <NUM>ms",
      "count": 523,
      "services": ["api-gateway", "user-service"],
      "example_message": "Connection timeout to database after 5000ms",
      "first_seen": "2024-12-11T02:15:00Z",
      "last_seen": "2024-12-11T14:30:00Z",
      "max_level": "ERROR",
      "sample_log_ids": ["log-id-1", "log-id-2", "log-id-3"]
    }
  ],
  "recommendations": [
    "Investigate api-gateway database connection pool settings",
    "Review recent deployments for configuration changes",
    "Monitor database server resource utilization"
  ],
  "generation_time_seconds": 125.3
}
```

**Response (404 Not Found):**
```json
{
  "detail": "No reports found"
}
```

**cURL:**
```bash
curl http://localhost:8002/reports/latest | jq
```

---

### POST `/baselines/calculate`

Manually trigger anomaly baseline calculation.

**Query Parameters:**
- `lookback_days` (integer, default=30): Number of days to analyze for baseline

**Response (200 OK):**
```json
{
  "job_id": "c3d4e5f6-a7b8-9012-cdef-3456789012ab",
  "status": "triggered",
  "message": "Baseline calculation started (lookback: 30 days)",
  "lookback_days": 30
}
```

**cURL:**
```bash
curl -X POST "http://localhost:8002/baselines/calculate?lookback_days=30"
```

---

### GET `/baselines/stats`

Get statistics about anomaly baselines.

**Response (200 OK):**
```json
{
  "total_baselines": 150,
  "unique_services": 5,
  "unique_environments": 1,
  "unique_levels": 3,
  "last_updated": "2024-12-11T03:00:00Z",
  "next_scheduled_run": "Sunday 03:00 UTC"
}
```

**cURL:**
```bash
curl http://localhost:8002/baselines/stats
```

---

### GET `/metrics`

Prometheus metrics endpoint.

**Metrics:**
- `analyses_total` - Total analyses performed
- `analyses_failed_total` - Failed analyses
- `analysis_duration_seconds` - Analysis duration histogram
- `patterns_detected` - Number of error patterns detected
- `anomalies_detected` - Number of anomalies detected
- `error_patterns_created_total` - Error patterns created in ClickHouse
- `anomaly_alerts_created_total` - Anomaly alerts created

**cURL:**
```bash
curl http://localhost:8002/metrics
```

---

## 🎯 Jina Embeddings Service (Port 8003)

Generates text embeddings using Jina AI API with Redis caching.

### GET `/health`

Health check with service status and statistics.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "jina-embeddings",
  "jina_api_configured": true,
  "redis_connected": true,
  "circuit_breaker_state": "closed",
  "model": "jina-embeddings-v3",
  "uptime_seconds": 7200.5,
  "total_embeddings": 125000,
  "cache_hit_rate": 87.5
}
```

**Response (200 OK - Degraded):**
```json
{
  "status": "degraded",
  "service": "jina-embeddings",
  "jina_api_configured": true,
  "redis_connected": false,
  "circuit_breaker_state": "closed",
  "model": "jina-embeddings-v3",
  "uptime_seconds": 7200.5,
  "total_embeddings": 125000,
  "cache_hit_rate": 0.0
}
```

**cURL:**
```bash
curl http://localhost:8003/health
```

---

### POST `/embeddings`

Generate embeddings for a list of texts.

**Request Body:**
```json
{
  "texts": [
    "Database connection failed",
    "User authentication successful",
    "Payment processing timeout"
  ]
}
```

**Parameters:**
- `texts` (array of strings, 1-100 items): Text strings to embed

**Limits:**
- Maximum batch size: 100 texts
- Maximum text length: 8192 characters (auto-truncated)

**Response (200 OK):**
```json
{
  "embeddings": [
    {
      "text": "Database connection failed",
      "embedding": [0.123, -0.456, 0.789, ...],
      "index": 0,
      "cached": false
    },
    {
      "text": "User authentication successful",
      "embedding": [-0.234, 0.567, -0.890, ...],
      "index": 1,
      "cached": true
    },
    {
      "text": "Payment processing timeout",
      "embedding": [0.345, -0.678, 0.901, ...],
      "index": 2,
      "cached": false
    }
  ],
  "model": "jina-embeddings-v3",
  "dimension": 1024,
  "count": 3,
  "cache_hits": 1,
  "cache_misses": 2,
  "generation_time_seconds": 0.523,
  "request_id": "d4e5f6a7-b8c9-0123-def4-56789012abc"
}
```

**Response (400 Bad Request):**
```json
{
  "detail": "Batch size 150 exceeds maximum 100"
}
```

**Response (502 Bad Gateway):**
```json
{
  "detail": "Jina API error: 429"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Jina API circuit breaker is open - service temporarily unavailable"
}
```

**cURL:**
```bash
curl -X POST http://localhost:8003/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [
      "Database connection failed",
      "User authentication successful"
    ]
  }' | jq
```

---

### GET `/stats`

Get service statistics.

**Response (200 OK):**
```json
{
  "total_embeddings_generated": 125000,
  "total_embeddings_failed": 150,
  "cache_hits": 109375,
  "cache_misses": 15625,
  "cache_hit_rate": 87.5,
  "circuit_breaker_failures": 2,
  "model": "jina-embeddings-v3",
  "dimension": 1024,
  "max_batch_size": 100
}
```

**cURL:**
```bash
curl http://localhost:8003/stats | jq
```

---

### POST `/cache/clear`

Clear all cached embeddings (admin endpoint).

**Response (200 OK):**
```json
{
  "status": "success",
  "deleted_keys": 15420,
  "message": "Cleared 15420 cached embeddings"
}
```

**Response (503 Service Unavailable):**
```json
{
  "detail": "Redis cache not available"
}
```

**cURL:**
```bash
curl -X POST http://localhost:8003/cache/clear
```

---

### GET `/metrics`

Prometheus metrics endpoint.

**Metrics:**
- `embeddings_generated_total{status, source}` - Total embeddings generated (by status and source: cache/api)
- `embedding_generation_seconds` - Time to generate embeddings
- `embedding_batch_size` - Size of embedding batches processed
- `cache_hits_total` - Number of cache hits
- `cache_misses_total` - Number of cache misses
- `cache_errors_total` - Number of cache errors
- `circuit_breaker_state` - Circuit breaker state (0=closed, 1=open, 2=half-open)
- `circuit_breaker_failures_total` - Number of circuit breaker failures
- `api_retries_total` - Number of API retries

**cURL:**
```bash
curl http://localhost:8003/metrics
```

---

## 🔄 Vectorization Worker Service (Port 8004)

Consumes logs from Kafka, generates embeddings, stores in Qdrant, and updates ClickHouse.

### GET `/health`

Enhanced health check with DLQ monitoring.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "vectorization-worker",
  "kafka_connected": true,
  "qdrant_connected": true,
  "clickhouse_connected": true,
  "jina_service_connected": true,
  "messages_processed": 25000,
  "embeddings_stored": 24950,
  "clickhouse_updates": 24950,
  "dlq_messages_sent": 50,
  "qdrant_circuit_breaker_state": "closed",
  "clickhouse_circuit_breaker_state": "closed",
  "uptime_seconds": 5400.2
}
```

**cURL:**
```bash
curl http://localhost:8004/health
```

---

### GET `/stats`

Get service statistics including DLQ.

**Response (200 OK):**
```json
{
  "total_consumed": 25000,
  "total_embedded": 24950,
  "total_stored": 24950,
  "total_failed": 50,
  "total_clickhouse_updates": 24950,
  "total_dlq_sent": 50,
  "current_batch_size": 7
}
```

**cURL:**
```bash
curl http://localhost:8004/stats
```

---

### GET `/metrics`

Prometheus metrics endpoint.

**Metrics:**
- `vectorization_messages_consumed_total` - Total messages consumed from Kafka
- `vectorization_embeddings_generated_total{status}` - Total embeddings generated
- `vectorization_qdrant_writes_total{status}` - Total writes to Qdrant
- `vectorization_clickhouse_updates_total{status}` - Total ClickHouse is_vectorized updates
- `vectorization_circuit_breaker_state{breaker_name}` - Circuit breaker state (0=closed, 1=open, 2=half-open)
- `vectorization_circuit_breaker_failures_total{breaker_name}` - Number of circuit breaker failures
- `vectorization_api_retries_total{operation}` - Number of API call retries
- `vectorization_batch_processing_seconds` - Time to process a batch
- `vectorization_current_batch_size` - Current batch size being processed
- `vectorization_dlq_messages_sent_total{reason}` - Total messages sent to dead letter queue
- `vectorization_batch_retries_total` - Total number of batch retries

**cURL:**
```bash
curl http://localhost:8004/metrics
```

---

## 🌐 API Gateway (Port 8005)

Unified REST API for the log analysis platform with WebSocket support.

### GET `/`

API root with available endpoints.

**Response (200 OK):**
```json
{
  "name": "Log Analysis Platform API",
  "version": "1.0.0",
  "status": "running",
  "endpoints": {
    "logs": "/api/logs",
    "search": "/api/search",
    "patterns": "/api/patterns",
    "reports": "/api/reports",
    "metrics": "/api/metrics",
    "summary": "/api/summary",
    "config": "/api/config",
    "websocket": "/api/ws",
    "health": "/health",
    "docs": "/docs"
  }
}
```

**cURL:**
```bash
curl http://localhost:8005/
```

---

### GET `/health`

Health check with all service dependencies.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "services": {
    "clickhouse": "healthy",
    "postgresql": "healthy",
    "qdrant": "healthy",
    "redis": "healthy"
  }
}
```

**Response (200 OK - Degraded):**
```json
{
  "status": "degraded",
  "services": {
    "clickhouse": "healthy",
    "postgresql": "healthy",
    "qdrant": "unhealthy",
    "redis": "healthy"
  }
}
```

**cURL:**
```bash
curl http://localhost:8005/health
```

---

### GET `/api/logs`

Query logs from ClickHouse with filtering.

**Query Parameters:**
- `level` (string, optional): Filter by log level (ERROR, WARN, INFO, DEBUG, FATAL)
- `service` (string, optional): Filter by service name
- `start_time` (string, ISO 8601, optional): Start time for time range filter
- `end_time` (string, ISO 8601, optional): End time for time range filter
- `limit` (integer, default=100, max=1000): Number of logs to return
- `offset` (integer, default=0): Offset for pagination

**Response (200 OK):**
```json
{
  "logs": [
    {
      "log_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "timestamp": "2024-12-11T10:30:00Z",
      "service": "api-gateway",
      "environment": "production",
      "level": "ERROR",
      "message": "Connection timeout to database after 5000ms",
      "stack_trace": "Traceback...",
      "trace_id": "b2c3d4e5-f6a7-8901-bcde-f234567890ab",
      "host": "api-gateway-pod-1",
      "pod_name": "api-gateway-5f6a7b8c9-xyz12",
      "user_id": "user_123"
    }
  ],
  "total": 1500,
  "limit": 100,
  "offset": 0,
  "has_more": true
}
```

**cURL:**
```bash
# Get recent ERROR logs
curl "http://localhost:8005/api/logs?level=ERROR&limit=10" | jq

# Get logs for specific service
curl "http://localhost:8005/api/logs?service=api-gateway&limit=50" | jq

# Get logs in time range
curl "http://localhost:8005/api/logs?start_time=2024-12-11T00:00:00Z&end_time=2024-12-11T23:59:59Z" | jq
```

---

### POST `/api/search/semantic`

Semantic similarity search using Qdrant vector database.

**Request Body:**
```json
{
  "query": "database connection timeout",
  "top_k": 20,
  "level": "ERROR",
  "service": "api-gateway",
  "start_time": "2024-12-11T00:00:00Z",
  "end_time": "2024-12-11T23:59:59Z"
}
```

**Parameters:**
- `query` (string, required): Search query text
- `top_k` (integer, default=20, max=100): Number of similar results to return
- `level` (string, optional): Filter by log level
- `service` (string, optional): Filter by service name
- `start_time` (string, ISO 8601, optional): Start time for time range filter
- `end_time` (string, ISO 8601, optional): End time for time range filter

**Response (200 OK):**
```json
{
  "query": "database connection timeout",
  "results": [
    {
      "log_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "timestamp": "2024-12-11T10:30:00Z",
      "service": "api-gateway",
      "level": "ERROR",
      "message": "Connection timeout to database after 5000ms",
      "similarity_score": 0.95,
      "trace_id": "b2c3d4e5-f6a7-8901-bcde-f234567890ab"
    },
    {
      "log_id": "c3d4e5f6-a7b8-9012-cdef-3456789012ab",
      "timestamp": "2024-12-11T10:32:00Z",
      "service": "user-service",
      "level": "ERROR",
      "message": "Database query timeout after 3000ms",
      "similarity_score": 0.87,
      "trace_id": "d4e5f6a7-b8c9-0123-def4-56789012abc"
    }
  ],
  "count": 20,
  "generation_time_seconds": 0.125
}
```

**cURL:**
```bash
curl -X POST http://localhost:8005/api/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "database connection timeout",
    "top_k": 20,
    "level": "ERROR"
  }' | jq
```

---

### GET `/api/patterns`

Get error patterns from PostgreSQL.

**Query Parameters:**
- `min_count` (integer, default=1): Minimum occurrence count
- `max_count` (integer, optional): Maximum occurrence count
- `level` (string, optional): Filter by max severity level
- `service` (string, optional): Filter by service
- `limit` (integer, default=100): Number of patterns to return

**Response (200 OK):**
```json
{
  "patterns": [
    {
      "pattern_hash": "abc123def456",
      "normalized_message": "Connection timeout to database after <NUM>ms",
      "occurrence_count": 523,
      "services": ["api-gateway", "user-service"],
      "environments": ["production"],
      "max_level": "ERROR",
      "first_seen": "2024-12-11T02:15:00Z",
      "last_seen": "2024-12-11T14:30:00Z",
      "is_known": false,
      "category": "auto-detected",
      "trend": "increasing",
      "sample_log_ids": ["log-id-1", "log-id-2", "log-id-3"]
    }
  ],
  "total": 47,
  "limit": 100
}
```

**cURL:**
```bash
# Get patterns with at least 10 occurrences
curl "http://localhost:8005/api/patterns?min_count=10" | jq

# Get ERROR level patterns
curl "http://localhost:8005/api/patterns?level=ERROR" | jq
```

---

### GET `/api/reports`

Get analysis reports from PostgreSQL.

**Query Parameters:**
- `date_from` (string, ISO date, optional): Start date for report range
- `date_to` (string, ISO date, optional): End date for report range
- `limit` (integer, default=10): Number of reports to return

**Response (200 OK):**
```json
{
  "reports": [
    {
      "report_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "report_date": "2024-12-11",
      "total_logs_processed": 432156,
      "error_count": 2341,
      "unique_error_patterns": 47,
      "anomalies_detected": 3,
      "executive_summary": "System health is generally good...",
      "generation_time_seconds": 125.3
    }
  ],
  "total": 30,
  "limit": 10
}
```

**cURL:**
```bash
# Get recent reports
curl "http://localhost:8005/api/reports?limit=5" | jq

# Get reports in date range
curl "http://localhost:8005/api/reports?date_from=2024-12-01&date_to=2024-12-11" | jq
```

---

### GET `/api/metrics`

Get system metrics and statistics.

**Response (200 OK):**
```json
{
  "log_rate": 50.2,
  "error_rate": 0.048,
  "total_logs": 5432156,
  "total_errors": 26789,
  "total_patterns": 147,
  "total_anomalies": 23,
  "storage_used_gb": 15.3,
  "vector_count": 26789,
  "cache_hit_rate": 87.5,
  "services": {
    "api-gateway": {
      "log_count": 1234567,
      "error_count": 5678,
      "error_rate": 0.0046
    },
    "user-service": {
      "log_count": 987654,
      "error_count": 4321,
      "error_rate": 0.0044
    }
  }
}
```

**cURL:**
```bash
curl http://localhost:8005/api/metrics | jq
```

---

### GET `/api/anomalies`

Get detected anomalies from PostgreSQL.

**Query Parameters:**
- `severity` (string, optional): Filter by severity (low, medium, high, critical)
- `status` (string, optional): Filter by status (new, acknowledged, resolved)
- `service` (string, optional): Filter by service
- `limit` (integer, default=50): Number of anomalies to return

**Response (200 OK):**
```json
{
  "anomalies": [
    {
      "alert_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "anomaly_type": "error_spike",
      "detected_at": "2024-12-11T14:15:00Z",
      "service": "api-gateway",
      "environment": "production",
      "severity": "high",
      "description": "High frequency error pattern detected: Connection timeout to database",
      "confidence_score": 0.92,
      "status": "new",
      "metrics": {
        "occurrence_count": 523,
        "percentage_of_errors": 22.3,
        "threshold": 100
      }
    }
  ],
  "total": 12,
  "limit": 50
}
```

**cURL:**
```bash
# Get high severity anomalies
curl "http://localhost:8005/api/anomalies?severity=high" | jq

# Get new anomalies
curl "http://localhost:8005/api/anomalies?status=new" | jq
```

---

### WS `/api/ws/logs`

WebSocket endpoint for real-time log streaming.

**Query Parameters:**
- `level` (string, optional): Filter by log level

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8005/api/ws/logs?level=ERROR');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

**Message Format:**
```json
{
  "type": "new_log",
  "data": {
    "log_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2024-12-11T10:30:00Z",
    "service": "api-gateway",
    "level": "ERROR",
    "message": "Connection timeout to database after 5000ms"
  }
}
```

---

### GET `/metrics`

Prometheus metrics endpoint for API Gateway.

**Metrics:**
- `api_requests_total{method, endpoint, status}` - Total API requests
- `api_request_duration_seconds{method, endpoint}` - API request latency

**cURL:**
```bash
curl http://localhost:8005/metrics
```

---

## 🔄 Common Workflows

### Workflow 1: Complete System Health Check

```bash
#!/bin/bash
# Check all services

services=(
  "log-generator:8000"
  "kafka-consumer:8001"
  "llm-analyzer:8002"
  "jina-embeddings:8003"
  "vectorization-worker:8004"
  "api-gateway:8005"
)

for service in "${services[@]}"; do
  name=$(echo $service | cut -d: -f1)
  port=$(echo $service | cut -d: -f2)

  status=$(curl -s http://localhost:$port/health | jq -r '.status')
  echo "$name ($port): $status"
done
```

---

### Workflow 2: Generate High-Error Load for Testing

```bash
#!/bin/bash
# Stress test with high error rate

# Stop generation
curl -X POST http://localhost:8000/stop

# Set high error rate
curl -X PUT http://localhost:8000/control \
  -H "Content-Type: application/json" \
  -d '{"rate_per_second": 500, "error_rate_percentage": 30}'

# Start generation
curl -X POST http://localhost:8000/start

echo "Generating 500 logs/sec with 30% error rate for 5 minutes..."
sleep 300

# Trigger analysis
echo "Triggering analysis..."
curl -X POST http://localhost:8002/analyze | jq

# Reset to normal
curl -X PUT http://localhost:8000/control \
  -H "Content-Type: application/json" \
  -d '{"rate_per_second": 50, "error_rate_percentage": 5}'

echo "Test complete!"
```

---

### Workflow 3: Monitor Dead Letter Queue

```bash
#!/bin/bash
# Monitor DLQ messages

while true; do
  consumer_stats=$(curl -s http://localhost:8001/stats)
  worker_stats=$(curl -s http://localhost:8004/stats)

  consumer_dlq=$(echo $consumer_stats | jq -r '.total_dlq')
  worker_dlq=$(echo $worker_stats | jq -r '.total_dlq_sent')

  echo "$(date) - Consumer DLQ: $consumer_dlq | Worker DLQ: $worker_dlq"

  if [ "$consumer_dlq" -gt 100 ] || [ "$worker_dlq" -gt 100 ]; then
    echo "⚠️  WARNING: DLQ messages exceeded 100!"
  fi

  sleep 30
done
```

---

### Workflow 4: Daily Analysis Automation

```bash
#!/bin/bash
# Daily analysis report

echo "Running daily analysis..."

# Trigger analysis
response=$(curl -s -X POST http://localhost:8002/analyze)
report_id=$(echo $response | jq -r '.report_id')

echo "Analysis triggered: $report_id"

# Wait for completion (check every 30 seconds)
for i in {1..20}; do
  sleep 30

  report=$(curl -s http://localhost:8002/reports/latest)
  status=$(echo $report | jq -r '.status // "completed"')

  if [ "$status" = "completed" ]; then
    echo "Analysis complete!"

    # Extract key metrics
    error_count=$(echo $report | jq -r '.error_count')
    anomalies=$(echo $report | jq -r '.anomalies_detected')

    echo "Errors: $error_count"
    echo "Anomalies: $anomalies"

    # Send summary (implement your notification method)
    # ./send_notification.sh "$report"

    exit 0
  fi
done

echo "Analysis timeout!"
exit 1
```

---

## 🐛 Debugging with APIs

### Check Why Messages Are Failing

```bash
# Check consumer DLQ count
curl -s http://localhost:8001/stats | jq '.total_dlq'

# Check worker DLQ count
curl -s http://localhost:8004/stats | jq '.total_dlq_sent'

# View Kafka DLQ topic (consumer)
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic raw-logs-dlq \
  --from-beginning \
  --max-messages 10

# View Kafka DLQ topic (vectorization)
docker exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic vectorization-queue-dlq \
  --from-beginning \
  --max-messages 10
```

---

### Verify LLM Availability

```bash
# Check Ollama connection via analyzer
health=$(curl -s http://localhost:8002/health)
ollama_connected=$(echo $health | jq -r '.ollama_connected')

if [ "$ollama_connected" = "false" ]; then
  echo "Ollama not available!"

  # Check Ollama directly
  docker exec ollama ollama list

  # Test Ollama
  docker exec ollama curl http://localhost:11434/api/generate -d '{
    "model": "deepseek-coder:6.7b",
    "prompt": "Hello, are you working?",
    "stream": false
  }'
fi
```

---

### Monitor Processing Performance

```bash
# Get consumer metrics
curl -s http://localhost:8001/metrics | grep processing_seconds

# Example output:
# message_processing_seconds_sum 1234.56
# message_processing_seconds_count 50000
# Average: 1234.56 / 50000 = 0.025 seconds per message

# Get vectorization metrics
curl -s http://localhost:8004/metrics | grep batch_processing_seconds

# Get embedding metrics
curl -s http://localhost:8003/metrics | grep embedding_generation_seconds
```

---

### Monitor Cache Performance

```bash
# Check Jina cache hit rate
curl -s http://localhost:8003/stats | jq '.cache_hit_rate'

# Clear cache if needed (admin operation)
curl -X POST http://localhost:8003/cache/clear

# Monitor cache after clearing
watch -n 5 'curl -s http://localhost:8003/stats | jq ".cache_hit_rate"'
```

---

## 🔐 Security Considerations

### Production Deployment

For production, add:

1. **Authentication**: JWT tokens via FastAPI middleware
2. **Rate Limiting**: Limit API requests per client
3. **HTTPS**: TLS certificates for all endpoints
4. **API Keys**: Require API keys for sensitive operations
5. **CORS**: Configure CORS policies appropriately

**Example with API Key:**

```python
from fastapi import Security, HTTPException, Depends
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

# Add to endpoint
@app.get("/api/logs", dependencies=[Depends(verify_api_key)])
async def get_logs():
    ...
```

---

## 📚 Additional Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Pydantic Models**: https://docs.pydantic.dev/
- **Prometheus Metrics**: https://prometheus.io/docs/
- **OpenAPI Spec**: https://swagger.io/specification/

---

## 🎯 Quick Reference

**Service Ports:**
- 8000: Log Generator
- 8001: Kafka Consumer
- 8002: LLM Analyzer
- 8003: Jina Embeddings
- 8004: Vectorization Worker
- 8005: API Gateway
- 8080: Kafka UI
- 8123: ClickHouse HTTP
- 6333: Qdrant

**All Services Support:**
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `GET /docs` - OpenAPI documentation (Swagger UI)
- `GET /redoc` - ReDoc documentation

**Interactive API Docs:**
- http://localhost:8000/docs (Log Generator)
- http://localhost:8001/docs (Kafka Consumer)
- http://localhost:8002/docs (LLM Analyzer)
- http://localhost:8003/docs (Jina Embeddings)
- http://localhost:8004/docs (Vectorization Worker)
- http://localhost:8005/docs (API Gateway)

**Status Codes:**
- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found
- `500` - Internal Server Error
- `502` - Bad Gateway (upstream service error)
- `503` - Service Unavailable (service not initialized or circuit breaker open)
