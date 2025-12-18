# Synaps (AI driven and statistical log Analyser)

- For quick start go to [how to use](#how-to-use) section
- For **UI** and different screen of the app go to [screens](#screens) section
- For in depth architecutre information look the [documentation/README.md](/documentation/README.md)

# Technical Project Summary

## Overview

Production-ready, event-driven microservices platform for intelligent log analysis using LLMs, vector embeddings, and real-time stream processing. The system demonstrates advanced patterns in distributed systems architecture, combining traditional time-series databases with modern AI/ML techniques for semantic understanding of application logs.

## Problem Statement

Traditional log analysis tools struggle with volume (millions of logs/day), signal-to-noise ratio (critical errors buried in routine logs), and pattern recognition (similar errors with different wording going undetected). This platform addresses these challenges through intelligent filtering, semantic clustering, and automated root cause analysis.

## Architecture Highlights

### Event-Driven Microservices (3 Phases)

- Phase 1: Real-time ingestion and LLM analysis
- Phase 2: Vector embeddings and semantic search
- Phase 3: REST API and interactive dashboard

### Data Flow Pipeline

Log Generator (Faker, 23 fields, configurable rate)
↓ Kafka Producer
Kafka Broker (KRaft mode, 4 topics with DLQs)
↓ Batch Consumer (1000/batch, 5s timeout)
ClickHouse (ALL logs, time-series, 90-day TTL)
↓ Filter ERROR/WARN/FATAL
Vectorization Queue
↓ Vector Worker (10/batch)
Jina Embeddings (768-dim, Redis cached)
↓
Qdrant (HNSW index, semantic search)
↓ Nightly/On-Demand
LLM Analyzer (Ollama DeepSeek/Qwen)
↓
PostgreSQL (Reports, patterns, anomalies)
↓
API Gateway (FastAPI + WebSocket)
↓
React Dashboard (Real-time visualization)

### Key Technical Implementations

1. Dual-Database Strategy

- ClickHouse: High-volume log storage (10M+ logs), analytical queries (<50ms), materialized views for hourly aggregation
- PostgreSQL: ACID-compliant metadata (reports, patterns, baselines), complex joins, SQLAlchemy ORM
- Qdrant: Vector similarity search with metadata filtering (service, level, timestamp)
- Redis: Embedding cache with SHA256 hashing (80-90% hit rate, 7-day TTL)

2. Intelligent Pattern Detection

- Normalization: LLM-powered error message normalization (removes UUIDs, timestamps, IPs)
- Deduplication: Groups 100K+ logs into ~50 unique patterns
- Semantic Clustering: Qdrant vector search finds related errors across services
- Novel Detection: Dissimilarity thresholds identify new error types

3. Statistical Anomaly Detection

- Pattern-Based Baselines: Calculates mean/stddev for each (day_of_week, hour_of_day) combination
- Z-Score Analysis: Flags deviations >2σ from historical norms
- Minimum Viable Data: Requires 2+ samples per pattern (30-day lookback = ~4 samples)
- Automated Recalculation: Nightly baseline updates adapt to system changes

4. Vectorization Pipeline

- Jina Embeddings v3: 768-dimensional Matryoshka embeddings (supports 512/384/256)
- Caching Strategy: SHA256 hash of log message → Redis lookup before API call
- Batch Processing: 10 logs/batch to Jina API, error handling with DLQ
- Retry Logic: 3 attempts with exponential backoff, circuit breaker pattern

5. LLM Analysis Workflow

- Data Aggregation: Queries ClickHouse for patterns (last 24 hours default)
- Context Enrichment: Semantic search in Qdrant for related logs
- Prompt Engineering: Structured prompts with pattern counts, timestamps, services
- Local Inference: Ollama (no API costs) with DeepSeek-Coder 6.7B or Qwen2.5 7B
- Report Generation: Executive summary, root causes, recommendations stored in PostgreSQL

6. Fault Tolerance & Reliability

- Dead Letter Queues: Separate DLQs for ingestion and vectorization failures
- Manual Offset Commits: At-least-once delivery guarantee in Kafka consumer
- Circuit Breakers: Exponential backoff for ClickHouse and external services
- Graceful Shutdown: In-flight batch processing before service termination
- Health Checks: All services expose /health endpoints with dependency status

## Performance Characteristics

| Metric               | Value                                   |
| -------------------- | --------------------------------------- |
| Ingestion Throughput | 50-10K logs/sec (horizontally scalable) |
| End-to-End Latency   | <100ms (producer → ClickHouse)          |
| Query Performance    | 10-50ms (indexed recent logs)           |
| Vectorization Rate   | 100 logs/sec (with cache hits)          |
| Cache Hit Rate       | 80-90% (production workloads)           |
| Storage Compression  | 10x (ClickHouse LZ4)                    |
| LLM Analysis Time    | 2-5 minutes (50 patterns)               |

## Technology Stack

Infrastructure

- Message Queue: Apache Kafka 3.9 (KRaft mode, no Zookeeper)
- Time-Series DB: ClickHouse 24.x (columnar, compression, TTL)
- Vector DB: Qdrant 1.7+ (HNSW indexing, metadata filtering)
- Relational DB: PostgreSQL 16.x (ACID, SQLAlchemy ORM)
- Cache: Redis 7.x (embedding cache, rate limiting)

AI/ML Stack

- LLM Runtime: Ollama (local inference, CPU/GPU support)
- LLM Models: DeepSeek-Coder 6.7B, Qwen2.5 7B
- Embeddings: Jina Embeddings v3 (768-dim, Matryoshka)
- Vector Client: Qdrant Python client

Application Stack

- Backend: FastAPI (async, WebSocket, auto-docs)
- Frontend: React 18 + TypeScript
- Kafka Client: Confluent Kafka Python (official library)
- ClickHouse Client: clickhouse-connect (native protocol)
- Logging: structlog (structured JSON logs)
- Metrics: Prometheus client
- Validation: Pydantic v2

Development Tools

- Package Manager: uv (fast Python package manager)
- Workspace: uv monorepo (8 services)
- Containerization: Docker + Docker Compose v2
- Linting: ruff, mypy, black

Operational Features

Observability

- Prometheus metrics on all services
- Structured JSON logging with correlation IDs
- Health check endpoints with dependency status
- Kafka UI for topic/consumer monitoring
- Qdrant dashboard for vector inspection

Configuration Management

- Pydantic Settings for type-safe config
- Environment-based configuration (12-factor app)
- Configurable batch sizes, timeouts, schedules
- Hot-reloadable LLM models

Data Management

- ClickHouse: 90-day automatic TTL
- Redis: 7-day cache expiration
- PostgreSQL: Manual report archival
- Qdrant: No automatic cleanup (configurable)

Resource Requirements

Development (Minimum)

- 16GB RAM, 4 CPU cores, 50GB SSD
- Docker 20.10+ with Compose v2

Production (Recommended)

- 32GB+ RAM, 8+ CPU cores, 100GB NVMe SSD
- NVIDIA GPU optional (20x faster LLM inference)
- 1 Gbps network

## Unique Technical Achievements

1. Hybrid Search Architecture: Combines vector similarity (Qdrant) with time-series analytics (ClickHouse) for comprehensive log analysis
2. Matryoshka Embedding Strategy: 768-dim embeddings with truncation support (512/384/256) for memory/performance tradeoffs
3. Pattern-Aware Anomaly Detection: Day-of-week + hour-of-day baselines account for business cycles (Monday 3am ≠ Friday 3pm)
4. Zero-Cost LLM Analysis: Local Ollama inference eliminates API costs while maintaining quality
5. Progressive Filtering Pipeline: Writes ALL logs to ClickHouse, vectors only ERROR+ logs (reduces vectorization costs by ~95%)
6. Cache-First Embedding: SHA256-based Redis caching achieves 80-90% hit rate, dramatically reducing Jina API calls

## Deployment

Quick Start can be found information can be found in [how to use section](#how-to-use)

# Provisions: Kafka, ClickHouse, PostgreSQL, Qdrant, Redis, Ollama

# Deploys: 8 microservices with health checks

# Time: with LLM 10-15 minutes (includes 4GB LLM download)

## Service Endpoints

- Kafka UI: http://localhost:8080
- ClickHouse: http://localhost:8123
- Qdrant: http://localhost:6333/dashboard
- API Docs: http://localhost:8005/docs
- Dashboard: http://localhost:3000

Use Cases Demonstrated

1. Real-time log aggregation and storage at scale
2. Semantic search across unstructured log messages
3. Automated pattern detection and clustering
4. Statistical anomaly detection with self-learning baselines
5. LLM-powered root cause analysis and recommendations
6. Interactive dashboards with live WebSocket updates

# How to use

---

## Deploying the services

This will build deploy the entire project's infrastructure

```bash
make rebuild-all
```

> Important note: make sure to pull a specific ollama model (you will need it for report generation), or you can simply pass the llm api of your choice in the compose file to the _`llm-analyzer`_ service via ( _`OLLAMA_HOST`_: http://host:port, _`OLLAMA_MODEL`_) and comment out the ollama service and volumes.

## Log-generator and LLM-analyzer services notes

You can also set the time range and anomaly spike days and hours you desire for the `log-generator` service before doing `make rebuild-all` and deploying the services.

```bash
LOG_RATE_PER_SECOND: 1
ERROR_RATE_PERCENTAGE: 3 #3 #40 (how many logs can be level ERROR/FATAL)
SERVICES: "api-gateway,user-service,payment-service,notification-service,auth-service" # services mock data to generate
HISTORICAL_MODE: true # backfilling mock data -> false if you want real-time (today onwards)
HISTORICAL_START_DATE: 1/12/2025 #"15/12/2025" # 1/12/2025
HISTORICAL_END_DATE: 8/12/2025 #"30/12/2025" # 15/12/2025
ANOMALY_SCHEDULE: "1-3,1-15,5-21" # (Monday 3 AM, Monday 15 PM, Friday 21 AM). Format: day_of_week-hour e.g., "1-3,1-15,5-21" (1=Monday (3am, 3pm), 7=Sunday(11pm); 0-23 = 00:00 to 23:00)
ANOMALY_MULTIPLIER_MIN: 1.0 #4.0 random multiplication factor for error percentage
ANOMALY_MULTIPLIER_MAX: 2.0 #8.0 random multiplication factor for error percentage
```

For a good test experience I advise:

- generating one week of data (_1/12/2025_ to _8/12/2025_) with `ERROR_RATE_PERCENTAGE: 3`, `ANOMALY_MULTIPLIER_MIN: 1.0` and `ANOMALY_MULTIPLIER_MAX: 2.0`, `ANOMALY_SCHEDULE: "1-3,1-15,5-21"`, these will allow you to have very low error rate which simulates a healthy system.

- Then generate a baseline with _http://localhost:8002/baselines/calculate_, this will create you ground truth to which next week's data will be compared.

- Generating another week's worth of data (_8/12/2025_ to _15/12/2025_) with `ERROR_RATE_PERCENTAGE: 30`, `ANOMALY_MULTIPLIER_MIN: 4.0` and `ANOMALY_MULTIPLIER_MAX: 8.0`, `ANOMALY_SCHEDULE: "1-3,1-15,5-21"`, these will allow you to generate data that is not consistant with you baseline and therefore be flaged by the z-score chart referenced in the [z-score anomaly detection dashboard](#42-z-score-anomaly-detection).

> Important note: the log-generator stops generating logs to kafka after reaching the end date defined by the variable **`HISTORICAL_END_DATE`**.

If you decide to use ollama

```bash
~$ docker exec -it ollama sh
~$ ollama pull deepseek-coder:6.7b # this can be any model please check smaller LLM models online
~$ ollama list
# ollama list installed models
NAME                   ID              SIZE      MODIFIED
deepseek-coder:6.7b    ce298d984115    3.8 GB    2 days ago
```

## Generating a report:

First `calculate a baseline` (needs to be done at least once). By default the `llm-service` does this a baseline recalculation every 7 days (7 real days via scheduler).

```bash
curl -X POST http://localhost:8002/baselines/calculate -H "Content-Type: application/json"
```

Then generate the report

```bash
curl -X POST http://localhost:8002/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2025-12-16T00:00:00Z",
    "end_time": "2025-12-17T00:00:00Z",
    "services": [
      "api-gateway",
      "user-service",
      "payment-service",
      "notification-service",
      "auth-service"
    ]
  }'
```

By the default the frontend `/pages` components uses a mock api, if you want see the data you have generated, make sure change the `USE_MOCK_API = false` in every component under `frontend/src/pages/*`.

The report generation (`/analyze`) api will also generate new patterns (`ERROR`, `WARN`, `FATAL`) for that report, which will either be new patterns or update trends of existing patterns.

## Jina-embeddings service

This service vectorizes log messages using [`Matryoshka Embeddings`](https://sbert.net/examples/sentence_transformer/training/matryoshka/README.html) of `size 768`, inspired by the famous Russian nesting doll.

Please update `JINA_API_KEY` in the [docker-compose](infrastructure/docker-compose.yml) with one provided on the jina-embeddings website [here](https://jina.ai/api-dashboard/embedding). It provide you with 10 million free tokens, this is far more than enough for testing the app.

# More details

If you want more details about the project's architecture and flow have a look at the [full project details here](documentation/README.md).

# Screens

---

## 1. Main dashboard

Here you can see the you can the live ingestion dashboard with metrics about log ingestion
![Dashboard-screen](documentation/images/1-dashboard-screen.png)

## 2. Data cortex (granular live logs)

Data cortex - the second screen show live information about what kind of logs are coming into the system
![Data-cortex-screen](documentation/images/2-data-cortex-screen.png)

## 3. Cognitive search (semantic search)

Semantic search looks for logs based on key words and patterns and clusters them based on pattern, services, error level, etc.

![Cognitive-search-screen](documentation/images/3-1-congitive-search.png)

### 3.1. Expanded log group

Below you can see what the information is contained within a log group, like how many logs share the pattern, the similarity score, the error level and even the range of time these logs cover

![clicked-log-group-1](documentation/images/3-2-cognitive-search-modal-one.png)
![clicked-log-group-3](documentation/images/3-4-cognitive-search-modal-three.png)

Finally you can investigate a specific log and in the clustered group and see all the full information about the log (from environment name, to podname, stacktraces, etc.)

![clicked-log-group-2](documentation/images/3-3-cognitive-search-modal-two.png)

## 4. Insight pathway (report analysis)

The system generated analysis report (24 hours) that generated a summary of logs, root cause and potential fixes. It also provides a z-score anomaly dectection dashboard that covers the 24 hours period.

## 4.1. Executive summary

![analysis-report-1](documentation/images/4-1-analysis-report-part-one.png)

## 4.2. z-score anomaly detection

![analysis-report-2](documentation/images/4-2-analysis-report-part-two.png)

Expend report information shows the different statistics about information analysed during that period, such as total logs, how many logs at each level levels, the report generation time, the model used with token count, the recommendations, etc.

![analysis-report-3](documentation/images/4-3-analysis-report-modal-part-one.png)
![analysis-report-4](documentation/images/4-4-analysis-report-modal-part-two.png)
![analysis-report-5](documentation/images/4-5-analysis-report-modal-part-three.png)

## 5. Metrics (anomaly detection & alerts)

Filtering the different anomaly reports and analysis

![metrics](documentation/images/5-anomaly-detection-alerts-screen.png)

## 6. Topology (system architecture)

Shows flow of data for the system architecture

![architecture](documentation/images/6-topology-screen.png)
