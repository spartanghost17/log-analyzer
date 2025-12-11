# Schema Enhancement Summary

## Overview

This document summarizes the enhancements made to fully utilize the ClickHouse and PostgreSQL schemas, along with recommendations for future improvements.

## ✅ Completed Changes

### 1. Enhanced Log Generator (`services/log-generator`)

**Added Dependencies:**
- `faker>=33.1.0` for realistic data generation

**Enhanced LogEntry Model:**
Added the following fields to match the ClickHouse schema:
- **Infrastructure:** `host`, `pod_name`, `container_id`
- **Logging:** `logger_name`
- **Distributed Tracing:** `span_id`, `parent_span_id`
- **Context:** `thread_name`, `correlation_id`
- **Metadata:** `labels` (Dict), `metadata` (JSON string)
- **Source:** `source_type`, `source_file`, `source_line`

**Realistic Data Generation:**
The log generator now produces:
- Realistic hostnames via Faker
- Kubernetes-style pod names (e.g., `api-gateway-deploy-3`)
- Container IDs (12-char hex)
- Java/Python-style logger names
- Thread names matching common patterns
- HTTP metadata (method, endpoint, status code, IP, user agent)
- Regional labels (region, cluster, version, deployment)
- Distributed tracing IDs (70% of logs)
- Source code locations

### 2. Enhanced Kafka Consumer (`services/kafka-consumer`)

**Updated LogEntry Model:**
- Added all new fields from log-generator
- Proper validation and default values

**Updated ClickHouse Integration:**
- Expanded `COLUMN_NAMES` to include all 23 fields
- Updated `_transform_to_row()` to map all fields correctly
- Handles labels dict → ClickHouse Map conversion
- Handles metadata JSON string

### 3. Table Ownership Documentation

Created `documentation/TABLE_OWNERSHIP.md` detailing:
- Which service owns which table
- When tables are updated
- Data flow between services
- Missing implementations
- Priority recommendations

## 📊 Current Data Flow

```
log-generator (Enhanced with Faker)
  ↓ (produces to Kafka: raw-logs)
kafka-consumer
  ↓ (writes to ClickHouse)
logs table (Now with 23 fields populated!)
  ↓ (auto-updates via materialized view)
logs_hourly_agg
```

## 📋 Table Utilization Status

### ClickHouse Tables

| Table | Updated By | Status | Notes |
|-------|-----------|--------|-------|
| `logs` | kafka-consumer | ✅ **FULLY UTILIZED** | Now populates all 23 fields |
| `logs_hourly_agg` | Automatic (materialized view) | ✅ **ACTIVE** | Auto-updates from logs |
| `logs_hourly_stats` | View only | ✅ **ACTIVE** | Read-only view |
| `error_patterns` | llm-analyzer | ⚠️ **PARTIAL** | Basic structure exists, needs enhancement |
| `anomaly_baselines` | llm-analyzer | ❌ **NOT YET** | Needs weekly job implementation |
| Views | Read-only | ✅ **ACTIVE** | Available for queries |

### PostgreSQL Tables

| Table | Updated By | Status | Notes |
|-------|-----------|--------|-------|
| `nightly_reports` | llm-analyzer | ✅ **ACTIVE** | Updated during nightly analysis |
| `error_catalog` | llm-analyzer | ⚠️ **PARTIAL** | Seed data exists, auto-creation needed |
| `anomaly_alerts` | llm-analyzer | ❌ **NOT YET** | Needs implementation |
| `services` | API (Phase 3) | ✅ **SEEDED** | Has initial data, CRUD pending |
| `user_preferences` | Frontend/API (Phase 3) | ❌ **NOT YET** | Phase 3 feature |
| `analysis_jobs` | llm-analyzer | ⚠️ **PARTIAL** | Should track all analysis runs |
| `app_config` | API (Phase 3) | ✅ **SEEDED** | Has config, admin UI pending |

## 🔧 Recommended Next Steps

### **Priority 1: Enhance LLM Analyzer**

The `llm-analyzer` service should be enhanced to:

1. **Update `error_patterns` table:**
```python
# After detecting patterns:
clickhouse_client.insert('error_patterns', [
    {
        'error_hash': hash_value,
        'normalized_message': normalized_msg,
        'first_seen': min_timestamp,
        'last_seen': max_timestamp,
        'occurrence_count': count,
        'services': [service_list],
        'max_level': 'ERROR',
        'sample_log_ids': [log_ids[:5]],
    }
])
```

2. **Create `anomaly_alerts` entries:**
```python
# When anomalies detected:
postgres_client.insert('anomaly_alerts', {
    'anomaly_type': 'error_spike',
    'service': service_name,
    'severity': 'high',
    'description': description,
    'metrics': {'z_score': 3.5, 'threshold': 2.0},
    'llm_analysis': analysis_text,
    'suggested_actions': [actions]
})
```

3. **Track analysis jobs:**
```python
# Start of analysis:
job_id = create_analysis_job(job_type='nightly_analysis')

# End of analysis:
update_analysis_job(job_id, {
    'status': 'completed',
    'processing_time_seconds': elapsed,
    'tokens_used': token_count,
    'result': analysis_results
})
```

4. **Populate `anomaly_baselines` (weekly job):**
```python
# Sunday 3 AM:
def update_baselines():
    """Calculate statistical baselines for anomaly detection"""
    for service, env, level in combinations:
        stats = calculate_hourly_stats(service, env, level, last_30_days)
        upsert_baseline(
            service=service,
            mean_count=stats['mean'],
            stddev_count=stats['stddev'],
            p95_count=stats['p95'],
            upper_threshold=stats['mean'] + 2*stats['stddev']
        )
```

### **Priority 2: Vectorization Worker Enhancement**

Add ClickHouse updates after successful vectorization:

```python
# In vectorization-worker after Qdrant insert:
log_ids_str = ','.join([f"'{id}'" for id in processed_log_ids])
clickhouse_client.query(f"""
    ALTER TABLE logs
    UPDATE is_vectorized = 1
    WHERE log_id IN ({log_ids_str})
""")
```

### **Priority 3: Create Dedicated Anomaly Detection Service**

For real-time anomaly detection (future):
- Continuously monitor `logs_hourly_agg`
- Compare against `anomaly_baselines`
- Create alerts in `anomaly_alerts` table
- Trigger notifications

## 🎯 Sample Queries to Test Enhanced Schema

### View Rich Log Data:
```sql
SELECT
    timestamp,
    service,
    host,
    pod_name,
    logger_name,
    level,
    message,
    trace_id,
    span_id,
    thread_name,
    labels,
    metadata,
    source_file,
    source_line
FROM logs
WHERE level = 'ERROR'
    AND timestamp >= now() - INTERVAL 1 HOUR
LIMIT 10;
```

### Analyze by Region (using labels):
```sql
SELECT
    labels['region'] as region,
    count() as log_count,
    countIf(level = 'ERROR') as error_count
FROM logs
WHERE timestamp >= now() - INTERVAL 24 HOUR
GROUP BY region
ORDER BY error_count DESC;
```

### Trace Complete Request Flow:
```sql
SELECT
    timestamp,
    service,
    pod_name,
    level,
    message,
    span_id,
    parent_span_id
FROM logs
WHERE trace_id = 'your-trace-id'
ORDER BY timestamp;
```

### View Metadata:
```sql
SELECT
    service,
    JSONExtractString(metadata, 'http_method') as method,
    JSONExtractString(metadata, 'endpoint') as endpoint,
    JSONExtractInt(metadata, 'status_code') as status,
    JSONExtractInt(metadata, 'duration_ms') as duration_ms,
    count() as request_count
FROM logs
WHERE timestamp >= now() - INTERVAL 1 HOUR
    AND metadata != ''
GROUP BY service, method, endpoint, status, duration_ms
ORDER BY request_count DESC
LIMIT 20;
```

## 🚀 Testing the Changes

### 1. Rebuild Services:
```bash
# Rebuild log-generator with faker
make rebuild-phase1

# Or specifically:
docker compose -f infrastructure/docker-compose.yml build --no-cache log-generator kafka-consumer
docker compose -f infrastructure/docker-compose.yml up -d log-generator kafka-consumer
```

### 2. Install Dependencies:
```bash
# In log-generator directory:
cd services/log-generator
uv sync

# If using pip:
pip install faker>=33.1.0
```

### 3. Verify Enhanced Logs:
```bash
# Check Kafka messages:
# Via Kafka UI: http://localhost:8080

# Check ClickHouse data:
docker exec clickhouse clickhouse-client --query "
SELECT
    service, host, pod_name, logger_name, labels, metadata
FROM logs_db.logs
LIMIT 5
FORMAT Vertical"
```

### 4. Check All Fields Populated:
```sql
-- Count non-empty values for new fields
SELECT
    countIf(host != '') as host_count,
    countIf(pod_name != '') as pod_count,
    countIf(logger_name != '') as logger_count,
    countIf(span_id != '') as span_count,
    countIf(thread_name != '') as thread_count,
    countIf(metadata != '') as metadata_count,
    length(labels) as labels_keys,
    count() as total_logs
FROM logs_db.logs
WHERE timestamp >= now() - INTERVAL 1 HOUR;
```

## 📈 Expected Results

After these changes, you should see:

1. **Rich, Realistic Logs:**
   - Hostnames like `client-2394.local`
   - Pod names like `api-gateway-deploy-3`
   - Logger names like `com.example.api.gateway.controller`
   - Thread names like `http-nio-8080-exec-5`

2. **Complete Tracing:**
   - 70% of logs have trace_id
   - Distributed tracing with span_id and parent_span_id
   - Correlation IDs for related operations

3. **Rich Metadata:**
   - Labels with region, cluster, version, deployment
   - HTTP metadata with method, endpoint, status, IP, user agent
   - Source code locations (file, line number)

4. **Better Analysis Capabilities:**
   - Group by region/cluster from labels
   - Filter by HTTP endpoint from metadata
   - Trace complete request flows
   - Identify code locations for errors

## 🔍 Monitoring Health

### Check Log Generator Stats:
```bash
curl http://localhost:8000/health | jq
```

### Check Consumer Processing:
```bash
curl http://localhost:8001/stats | jq
```

### Verify ClickHouse Writes:
```bash
docker exec clickhouse clickhouse-client --query "
SELECT count()
FROM logs_db.logs
WHERE timestamp >= now() - INTERVAL 5 MINUTE"
```

## 📝 Notes

- The enhanced schema is **backward compatible** - old logs without new fields will still work
- Labels are stored as ClickHouse `Map(String, String)` type
- Metadata is stored as a JSON string for flexible querying
- All new fields are optional with sensible defaults
- The faker library generates realistic but fake data - perfect for testing

## ⚠️ Important

- Run `uv sync` or `pip install faker` in log-generator before rebuilding
- Clear old logs if you want to test only with new enhanced logs
- The materialized view will automatically aggregate all new fields
- Consider adding indexes on frequently queried new fields (labels, metadata) if needed
