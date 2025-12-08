"""
Kafka Consumer Transaction Patterns
===================================

This file explains the standard approaches for handling transactions
when consuming from Kafka and writing to external systems.

TLDR: For Kafka → External DB, you MUST handle transactions yourself.
      The key is making writes IDEMPOTENT so duplicates don't matter.
"""

# =============================================================================
# PATTERN 1: At-Least-Once + Idempotent Writes (RECOMMENDED - What we use)
# =============================================================================

"""
This is the MOST COMMON pattern for Kafka → Database pipelines.

Flow:
    1. Consume message
    2. Write to database  
    3. Commit offset (only after successful write)
    
If crash between 2 and 3:
    - Message will be redelivered
    - But idempotent write means no duplicate data
    
Making ClickHouse Writes Idempotent:
"""

CLICKHOUSE_IDEMPOTENT_TABLE = """
-- Option A: ReplacingMergeTree (deduplicates on merge)
CREATE TABLE logs (
    log_id String,
    timestamp DateTime64(3),
    service String,
    environment String,
    level String,
    message String,
    trace_id String,
    user_id String,
    request_id String,
    stack_trace String,
    _version UInt64 DEFAULT toUnixTimestamp64Milli(now64())
) ENGINE = ReplacingMergeTree(_version)
ORDER BY (service, timestamp, log_id)  -- log_id in ORDER BY for dedup
PARTITION BY toYYYYMM(timestamp);

-- Option B: Use INSERT with deduplication token
-- ClickHouse deduplicates within a time window (default 100 inserts)
"""

def pattern_1_at_least_once():
    """Standard at-least-once with manual commits"""
    
    # 1. Consume
    msg = consumer.poll(1.0)
    
    # 2. Write to DB (idempotent via ReplacingMergeTree)
    clickhouse.insert('logs', data=[transform(msg)])
    
    # 3. Commit AFTER write
    consumer.commit(msg)
    
    # If crash here ↑, message redelivered, but ReplacingMergeTree dedupes


# =============================================================================
# PATTERN 2: Kafka Connect (Fully Managed)
# =============================================================================

"""
For standard sinks, Kafka Connect handles everything:
- Offset management
- Retries
- Schema evolution
- Parallelism

ClickHouse has an official connector:
    https://github.com/ClickHouse/clickhouse-kafka-connect

Example configuration:
"""

KAFKA_CONNECT_CONFIG = """
{
  "name": "clickhouse-sink",
  "config": {
    "connector.class": "com.clickhouse.kafka.connect.ClickHouseSinkConnector",
    "tasks.max": "1",
    "topics": "raw-logs",
    "hostname": "clickhouse",
    "port": "8123",
    "database": "logs_db",
    "table": "logs",
    "username": "admin",
    "password": "password",
    
    // Delivery guarantee
    "exactlyOnce": "false",  // At-least-once (recommended)
    
    // Error handling
    "errors.tolerance": "all",
    "errors.deadletterqueue.topic.name": "raw-logs-dlq",
    
    // Batching
    "batch.size": "1000",
    "linger.ms": "5000"
  }
}
"""

"""
When to use Kafka Connect:
✅ Standard database sink (ClickHouse, Postgres, S3, etc.)
✅ Team doesn't want to maintain consumer code
✅ Need schema registry integration
✅ Standard transformations (SMTs)

When NOT to use Kafka Connect:
❌ Complex business logic per message
❌ Need to call external APIs
❌ Custom error handling
❌ Dynamic routing based on content
"""


# =============================================================================
# PATTERN 3: Outbox Pattern (For DB → Kafka, opposite direction)
# =============================================================================

"""
This pattern is for when you need to:
    1. Update your database
    2. Produce to Kafka
    ATOMICALLY

Common in microservices for event publishing.
"""

OUTBOX_PATTERN_SQL = """
-- Transaction in your application DB
BEGIN;

-- 1. Make your business change
UPDATE orders SET status = 'shipped' WHERE id = 123;

-- 2. Write to outbox table (same transaction!)
INSERT INTO outbox (id, topic, payload, created_at)
VALUES (uuid(), 'order-events', '{"order_id": 123, "status": "shipped"}', now());

COMMIT;

-- Separate process (Debezium, custom poller) reads outbox → Kafka
-- Then deletes from outbox after confirmed delivery
"""

"""
This is NOT what we need - we're going Kafka → DB, not DB → Kafka.
But good to know it exists!
"""


# =============================================================================
# PATTERN 4: Two-Phase Commit (Rarely Used)
# =============================================================================

"""
True distributed transaction across Kafka and external DB.

Flow:
    1. Prepare: Both Kafka and DB ready to commit
    2. Commit: Both commit atomically
    3. If either fails: Both rollback

Why it's rarely used:
    - Complex to implement
    - Performance overhead (locks held during prepare)
    - Most DBs don't support XA transactions well
    - Single coordinator is single point of failure
    
Instead: Accept at-least-once and make writes idempotent.
"""


# =============================================================================
# PATTERN 5: Idempotent Keys with Exactly-Once Semantics
# =============================================================================

"""
The pragmatic approach that LOOKS like exactly-once:

1. Include a unique key in each message (we already have log_id)
2. Use database constraints to reject duplicates
3. Use at-least-once delivery

Result: Duplicates are attempted but rejected = effective exactly-once
"""

def pattern_5_idempotent_upsert():
    """Idempotent upsert pattern"""
    
    # ClickHouse approach: ReplacingMergeTree handles this automatically
    # PostgreSQL approach: ON CONFLICT
    
    POSTGRES_UPSERT = """
    INSERT INTO logs (log_id, timestamp, service, message, ...)
    VALUES ($1, $2, $3, $4, ...)
    ON CONFLICT (log_id) DO NOTHING;  -- Silently ignore duplicates
    """
    
    # This makes duplicates harmless!


# =============================================================================
# WHAT WE'RE DOING (Summary)
# =============================================================================

"""
Our Implementation Uses:

┌─────────────────────────────────────────────────────────────────────────┐
│ PATTERN 1: At-Least-Once + Idempotent Writes                           │
│                                                                         │
│ Components:                                                             │
│ ├── Manual offset commits (enable.auto.commit=False)                   │
│ ├── Commit only after successful ClickHouse write                      │
│ ├── DLQ for failed messages (don't block the pipeline)                 │
│ ├── Batching for performance                                           │
│ └── Circuit breaker for resilience                                     │
│                                                                         │
│ To complete the exactly-once APPEARANCE:                               │
│ └── Use ReplacingMergeTree in ClickHouse with log_id in ORDER BY       │
└─────────────────────────────────────────────────────────────────────────┘

This is the INDUSTRY STANDARD for Kafka → Database pipelines.

Companies using this pattern:
- Uber (Kafka → Various DBs)
- Netflix (Kafka → Cassandra, Elasticsearch)  
- LinkedIn (Kafka → Espresso, Voldemort)
- Cloudflare (Kafka → ClickHouse - literally our use case!)

The key insight:
    "Don't fight for exactly-once across systems.
     Make your writes idempotent so duplicates don't matter."
"""


# =============================================================================
# RECOMMENDATION: Add Idempotent ClickHouse Table
# =============================================================================

RECOMMENDED_CLICKHOUSE_SCHEMA = """
-- Use ReplacingMergeTree for automatic deduplication
CREATE TABLE logs_db.logs (
    log_id String,
    timestamp DateTime64(3, 'UTC'),
    service LowCardinality(String),
    environment LowCardinality(String),
    level LowCardinality(String),
    message String,
    trace_id String DEFAULT '',
    user_id String DEFAULT '',
    request_id String DEFAULT '',
    stack_trace String DEFAULT '',
    
    -- Version column for ReplacingMergeTree
    _inserted_at DateTime64(3) DEFAULT now64()
    
) ENGINE = ReplacingMergeTree(_inserted_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (service, environment, timestamp, log_id)  -- log_id ensures uniqueness
TTL timestamp + INTERVAL 90 DAY;

-- Query with FINAL to get deduplicated results immediately
-- (otherwise deduplication happens during merges)
SELECT * FROM logs FINAL WHERE service = 'api-gateway';

-- Or force deduplication manually
OPTIMIZE TABLE logs FINAL;
"""