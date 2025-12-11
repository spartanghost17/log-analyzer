# Table Ownership and Update Responsibilities

## ClickHouse Tables (logs_db)

### 1. `logs` (Main Logs Table)
**Owner:** `kafka-consumer`
**Updates:** Real-time inserts as logs are consumed from Kafka
**Fields Populated By:**
- **log-generator** → All initial fields (via Kafka → kafka-consumer)
- **vectorization-worker** → Sets `is_vectorized=1` after embedding generation (UPDATE)
- **llm-analyzer** → Sets `is_anomaly` and `anomaly_score` during analysis (UPDATE)

**Responsibility Flow:**
```
log-generator → Kafka (raw-logs) → kafka-consumer → ClickHouse logs table
```

### 2. `error_patterns` (Aggregated Error Patterns)
**Owner:** `llm-analyzer`
**Updates:** Batch inserts/updates during nightly analysis
**When:** Nightly analysis job + on-demand analysis
**Purpose:** Track normalized error patterns with occurrence counts

**Responsibility:**
- LLM analyzer identifies patterns from logs
- Calculates `error_hash` from normalized messages
- Tracks first_seen, last_seen, occurrence counts
- Updates `has_embedding` and `qdrant_point_id` after vectorization

### 3. `logs_hourly_agg` (Materialized View Data)
**Owner:** **AUTOMATIC** (ClickHouse Materialized View)
**Updates:** Automatically updated when rows are inserted into `logs` table
**No Service Needed:** This is a materialized view with AggregatingMergeTree engine

**How It Works:**
```sql
CREATE MATERIALIZED VIEW logs_hourly_agg_mv TO logs_hourly_agg
AS SELECT ...
FROM logs
```
Every insert into `logs` automatically updates this table.

### 4. `anomaly_baselines` (Statistical Baselines)
**Owner:** `llm-analyzer` (or dedicated anomaly-detector service)
**Updates:**
- Initial: Weekly batch job to establish baselines
- Ongoing: Daily/weekly updates to refresh statistical measures
**When:** Scheduled job (e.g., Sunday 3 AM)

**Responsibility:**
- Calculate mean, stddev, median, p95, p99 for error counts
- Group by service, environment, level, hour_of_day, day_of_week
- Set upper/lower thresholds for anomaly detection

### 5. Views (`recent_errors`, `error_rate_by_service`, `top_errors`, `logs_hourly_stats`)
**Owner:** **READ-ONLY** (ClickHouse Views)
**Updates:** None - these are views, not tables
**Purpose:** Convenient query interfaces for services to use

---

## PostgreSQL Tables (log_analysis)

### 1. `nightly_reports`
**Owner:** `llm-analyzer`
**Updates:** Daily inserts during nightly analysis
**When:** Nightly at 2 AM + on-demand via API

**Responsibility:**
- Query ClickHouse for last 24 hours of errors
- Generate LLM analysis summary
- Insert report with statistics and recommendations

### 2. `error_catalog`
**Owner:** `llm-analyzer` + Manual (via API in Phase 3)
**Updates:**
- Automatic: LLM creates entries for new unknown patterns
- Manual: Engineers add/update known error patterns
**When:** During analysis when new patterns detected

**Responsibility:**
- LLM analyzer detects novel error patterns
- Creates catalog entry with auto_created=true
- Engineers can update with solutions, documentation

### 3. `anomaly_alerts`
**Owner:** `llm-analyzer` (or dedicated anomaly-detector service)
**Updates:** Real-time or near-real-time inserts when anomalies detected
**When:**
- During nightly analysis
- Continuous monitoring (future enhancement)

**Responsibility:**
- Detect statistical anomalies (z-score > threshold)
- Detect semantic anomalies (novel error patterns via Qdrant)
- Create alert with LLM analysis and suggested actions
- Update status when acknowledged/resolved

### 4. `services`
**Owner:** `api` (Phase 3) + Seed data
**Updates:**
- Initial: Seed data from init.sql
- Ongoing: CRUD via API
**When:** Service onboarding, configuration changes

**Responsibility:**
- API provides CRUD endpoints for service management
- Configuration for monitoring, alerting, retention

### 5. `user_preferences`
**Owner:** `api` (Phase 3) + `frontend` (Phase 3)
**Updates:** User actions via frontend
**When:** User login, settings changes

**Responsibility:**
- Frontend sends updates to API
- API updates user preferences

### 6. `analysis_jobs`
**Owner:** `llm-analyzer`
**Updates:** Inserts at job start, updates on completion
**When:** Every analysis job (nightly, on-demand)

**Responsibility:**
- Create job record when analysis starts (status='pending')
- Update with results/errors when complete (status='completed'/'failed')
- Track tokens used, processing time, model used

### 7. `app_config`
**Owner:** `api` (Phase 3) + Seed data
**Updates:**
- Initial: Seed data from init.sql
- Ongoing: Admin updates via API
**When:** Configuration changes

**Responsibility:**
- API provides admin endpoints for config management
- All services read from this table on startup

---

## Service Responsibilities Summary

### `log-generator`
- **Writes:** Kafka topic `raw-logs`
- **Generates:** Realistic log entries with all fields populated

### `kafka-consumer`
- **Reads:** Kafka topic `raw-logs`
- **Writes:**
  - ClickHouse `logs` table (all fields from log-generator)
  - Kafka topic `vectorization-queue` (ERROR/WARN/FATAL logs)
  - Kafka topic `raw-logs-dlq` (failed messages)

### `vectorization-worker`
- **Reads:** Kafka topic `vectorization-queue`
- **Writes:**
  - Qdrant `log_embeddings` collection
  - **Should UPDATE:** ClickHouse `logs.is_vectorized=1` (not currently implemented)

### `jina-embeddings`
- **Reads:** HTTP requests from vectorization-worker
- **Writes:** Redis cache (embeddings)
- **Returns:** Embedding vectors to vectorization-worker

### `llm-analyzer`
- **Reads:**
  - ClickHouse `logs`, `logs_hourly_stats`, `top_errors`
  - Qdrant `log_embeddings` (for semantic search)
  - PostgreSQL `error_catalog`, `app_config`
- **Writes:**
  - PostgreSQL `nightly_reports`, `error_catalog`, `anomaly_alerts`, `analysis_jobs`
  - ClickHouse `error_patterns`, `anomaly_baselines`
  - **Should UPDATE:** ClickHouse `logs.is_anomaly` and `logs.anomaly_score` (not currently implemented)

### `api` (Phase 3)
- **Reads:** All tables for query endpoints
- **Writes:** PostgreSQL `services`, `app_config`, `user_preferences`

---

## Missing Implementations

### 1. Vectorization Worker Should Update ClickHouse
**Current:** Only writes to Qdrant
**Should:** Also update `logs.is_vectorized=1` for processed logs

**Implementation:**
```python
# After successful Qdrant insert:
ch_client.query(f"""
    ALTER TABLE logs
    UPDATE is_vectorized = 1
    WHERE log_id IN ({log_ids})
""")
```

### 2. LLM Analyzer Should Update More Tables
**Current:** Only writes to `nightly_reports`
**Should Also Write:**
- `error_patterns` - Pattern analysis results
- `anomaly_baselines` - Statistical baselines (weekly job)
- `error_catalog` - New unknown patterns
- `anomaly_alerts` - Detected anomalies
- `analysis_jobs` - Job tracking

### 3. Anomaly Detection Service (Future)
**Needed:** Dedicated service for continuous anomaly monitoring
**Responsibilities:**
- Read from ClickHouse `logs` (stream or periodic)
- Compare against `anomaly_baselines`
- Write to `anomaly_alerts` when anomalies detected
- Real-time alerting vs. batch analysis

---

## Recommended Updates Priority

### **High Priority (Do Now):**
1. ✅ Enhance log-generator to populate all ClickHouse fields
2. ✅ Update kafka-consumer to handle enhanced fields
3. 🔲 Add error_patterns updates to llm-analyzer
4. 🔲 Add analysis_jobs tracking to llm-analyzer

### **Medium Priority (Phase 2.5):**
5. 🔲 Vectorization-worker updates ClickHouse is_vectorized flag
6. 🔲 LLM analyzer creates error_catalog entries
7. 🔲 LLM analyzer populates anomaly_baselines

### **Low Priority (Phase 3):**
8. 🔲 API CRUD endpoints for services, app_config
9. 🔲 Dedicated anomaly detection service for real-time monitoring
10. 🔲 Frontend integration for user_preferences

---

## Data Flow Diagram

```
┌──────────────┐
│log-generator │
└──────┬───────┘
       │ (Kafka: raw-logs)
       v
┌─────────────────┐
│ kafka-consumer  │
└────┬────────┬───┘
     │        │
     │        └─────> (Kafka: vectorization-queue)
     │                         │
     v                         v
┌──────────────┐      ┌────────────────────┐
│  ClickHouse  │      │vectorization-worker│
│  logs table  │      └──────────┬─────────┘
└──────┬───────┘                 │
       │                         v
       │ (auto)          ┌──────────────┐
       v                 │    Qdrant    │
┌──────────────────┐     └──────────────┘
│logs_hourly_agg   │
│ (materialized)   │
└──────────────────┘

       │ (nightly)
       v
┌────────────────┐      ┌──────────────┐
│  llm-analyzer  │─────>│  PostgreSQL  │
└────────────────┘      │- nightly_reports
                        │- error_catalog
                        │- anomaly_alerts
                        │- analysis_jobs
                        └──────────────┘
```
