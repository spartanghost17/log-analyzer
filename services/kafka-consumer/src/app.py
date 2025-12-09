"""
ClickHouse Consumer Service - Robust Implementation
Consumes logs from Kafka and writes to ClickHouse with:
- At-least-once delivery semantics (manual offset commits)
- Proper batch failure handling with DLQ
- Graceful shutdown with in-flight message handling
- Retry logic with exponential backoff
- Thread-safe operations
- Partition-aware rebalance handling
- Circuit breaker pattern for ClickHouse
"""

import asyncio
import json
import signal
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from collections import defaultdict

import clickhouse_connect
from clickhouse_connect.driver.client import Client as ClickHouseClient
from confluent_kafka import Consumer, Producer, KafkaError, TopicPartition
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import pybreaker
import structlog

from settings import setup_development_logging

setup_development_logging()
logger = structlog.get_logger()


# =============================================================================
# Prometheus Metrics
# =============================================================================

MESSAGES_CONSUMED = Counter(
    'messages_consumed_total',
    'Total messages consumed from Kafka',
    ['topic', 'partition']
)
MESSAGES_WRITTEN = Counter(
    'messages_written_total',
    'Total messages written to ClickHouse'
)
MESSAGES_FAILED = Counter(
    'messages_failed_total',
    'Total messages that failed processing'
)
MESSAGES_DLQ = Counter(
    'messages_dlq_total',
    'Total messages sent to DLQ'
)
MESSAGES_VECTORIZATION = Counter(
    'messages_vectorization_total',
    'Messages sent to vectorization queue'
)
PROCESSING_TIME = Histogram(
    'message_processing_seconds',
    'Batch processing time',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)
BATCH_SIZE_METRIC = Gauge('current_batch_size', 'Current batch size')
CONSUMER_LAG = Gauge(
    'consumer_lag',
    'Consumer lag per partition',
    ['topic', 'partition']
)
CLICKHOUSE_CIRCUIT_STATE = Gauge(
    'clickhouse_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)'
)
RETRY_COUNT = Counter(
    'batch_retry_total',
    'Total batch retry attempts'
)


# =============================================================================
# Configuration
# =============================================================================

class Settings(BaseSettings):
    """Service configuration with validation"""

    # Kafka settings
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        validation_alias="KAFKA_BOOTSTRAP_SERVERS",
        description="Kafka bootstrap servers"
    )
    kafka_topic: str = Field(
        default="raw-logs",
        validation_alias="KAFKA_TOPIC",
        description="Kafka topic for raw logs"
    )
    kafka_dlq_topic: str = Field(
        default="raw-logs-dlq",
        validation_alias="KAFKA_DLQ_TOPIC",
        description="Kafka DLQ topic for raw logs"
    )
    kafka_vectorization_topic: str = Field(
        default="vectorization-queue",
        validation_alias="KAFKA_VECTORIZATION_TOPIC",
        description="Kafka vectorization topic for raw logs"
    )
    kafka_group_id: str = Field(
        default="clickhouse-consumer-group",
        validation_alias="KAFKA_GROUP_ID",
        description="Kafka consumer group for raw logs"
    )
    kafka_session_timeout_ms: int = Field(
        default=30000,
        validation_alias="KAFKA_SESSION_TIMEOUT_MS",
        description="Kafka session timeout in milliseconds"
    )
    kafka_max_poll_interval_ms: int = Field(
        default=300000,
        validation_alias="KAFKA_MAX_POLL_INTERVAL_MS",
        description="Kafka poll interval in milliseconds"
    )

    # ClickHouse settings
    clickhouse_host: str = Field(
        default="localhost",
        validation_alias="CLICKHOUSE_HOST",
        description="Clickhouse host name"
    )
    clickhouse_port: int = Field(
        default=8123,
        validation_alias="CLICKHOUSE_PORT",
        description="Clickhouse port number"
    )
    clickhouse_user: str = Field(
        default="admin",
        validation_alias="CLICKHOUSE_USER",
        description="Clickhouse user name"
    )
    clickhouse_password: str = Field(
        default="clickhouse_password",
        validation_alias="CLICKHOUSE_PASSWORD",
        description="Clickhouse password"
    )
    clickhouse_database: str = Field(
        default="logs_db",
        validation_alias="CLICKHOUSE_DATABASE",
        description="Clickhouse database name"
    )
    clickhouse_table: str = Field(
        default="logs",
        validation_alias="CLICKHOUSE_TABLE",
        description="Clickhouse table name for raw logs"
    )

    # Processing settings
    batch_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
        validation_alias="BATCH_SIZE",
        description="batch size"
    )
    flush_interval_seconds: float = Field(
        default=5.0,
        ge=0.5,
        le=60,
        validation_alias="FLUSH_INTERVAL_SECONDS",
        description="Flush interval in seconds"
    )
    poll_timeout_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        validation_alias="POLL_TIMEOUT_SECONDS",
        description="Poll interval in seconds"
    )

    # Retry settings
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        validation_alias="MAX_RETRIES",
        description="Max number of retries"
    )
    retry_base_delay_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=30.0,
        validation_alias="RETRY_BASE_DELAY_SECONDS",
        description="Retry base delay seconds"
    )
    retry_max_delay_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        validation_alias="RETRY_MAX_DELAY_SECONDS",
        description="Retry max delay seconds"
    )

    # Circuit breaker settings
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        ge=1,
        le=100,
        validation_alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        description="Circuit breaker failure threshold"
    )
    circuit_breaker_recovery_timeout: float = Field(
        default=30.0,
        ge=5.0,
        le=300.0,
        validation_alias="CIRCUIT_BREAKER_RECOVERY_TIMEOUT",
        description="Circuit breaker recovery timeout"
    )

    # Vectorization settings
    enable_vectorization: bool = Field(
        default=True,
        validation_alias="ENABLE_VECTORIZATION",
        description="Enable vectorization"
    )
    vectorize_levels: str = Field(
        default="ERROR,WARN,FATAL",
        validation_alias="VECTORIZE_LEVELS",
        description="Logs levels to keep for vectorization "
    )

    # API settings
    api_host: str = Field(
        default="0.0.0.0",
        validation_alias="API_HOST",
        description="API host"
    )
    api_port: int = Field(
        default=8001,
        validation_alias="API_PORT",
        description="API port"
    )

    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
        description="Log level"
    )

    class Config:
        extra = "ignore"
        case_sensitive = False


# =============================================================================
# Pydantic Models
# =============================================================================

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"
    TRACE = "TRACE"


class LogEntry(BaseModel):
    """Incoming log entry with validation - matches enhanced log-generator schema"""
    # Core fields
    log_id: str
    timestamp: str

    # Service identification
    service: str
    environment: str
    host: Optional[str] = ""
    pod_name: Optional[str] = ""
    container_id: Optional[str] = ""

    # Log metadata
    level: str
    logger_name: Optional[str] = ""
    message: str
    stack_trace: Optional[str] = ""

    # Distributed tracing
    trace_id: Optional[str] = ""
    span_id: Optional[str] = ""
    parent_span_id: Optional[str] = ""

    # Additional context
    thread_name: Optional[str] = ""
    user_id: Optional[str] = ""
    request_id: Optional[str] = ""
    correlation_id: Optional[str] = ""

    # Structured metadata
    labels: Optional[dict] = None  # Will be converted to ClickHouse Map
    metadata: Optional[str] = ""   # JSON string

    # Source information
    source_type: Optional[str] = ""
    source_file: Optional[str] = ""
    source_line: Optional[int] = 0

    @field_validator('level')
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = [e.value for e in LogLevel]
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"Level must be one of {valid_levels}, got {v}")
        return upper_v

    @field_validator('log_id', 'service', 'environment')
    @classmethod
    def validate_non_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty")
        return v.strip()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    kafka_connected: bool
    clickhouse_connected: bool
    clickhouse_circuit_breaker: str
    messages_processed: int
    current_batch_size: int
    uptime_seconds: float


class ConsumerStats(BaseModel):
    total_consumed: int
    total_written: int
    total_failed: int
    total_dlq: int
    total_vectorization_sent: int
    current_batch_size: int
    retry_count: int
    circuit_breaker_state: str


# =============================================================================
# Circuit Breaker (using pybreaker)
# =============================================================================

class CircuitBreakerMetricsListener(pybreaker.CircuitBreakerListener):
    """Listener to update Prometheus metrics on circuit breaker state changes"""

    def __init__(self, logger: structlog.BoundLogger = None):
        self.logger = logger or structlog.get_logger()

    def state_change(self, cb, old_state, new_state):
        """Called when circuit breaker state changes"""
        state_values = {
            pybreaker.STATE_CLOSED: 0,
            pybreaker.STATE_OPEN: 1,
            pybreaker.STATE_HALF_OPEN: 2,
        }
        CLICKHOUSE_CIRCUIT_STATE.set(state_values.get(new_state.name, -1))
        self.logger.info(
            "circuit_breaker_state_change",
            old_state=old_state.name,
            new_state=new_state.name
        )

    def failure(self, cb, exc):
        """Called when a function call fails"""
        self.logger.warning("circuit_breaker_failure", error=str(exc))

    def success(self, cb):
        """Called when a function call succeeds"""
        pass  # Don't log every success to avoid noise


# =============================================================================
# Batch Manager
# =============================================================================

@dataclass
class PendingMessage:
    """Tracks a message pending commit"""
    topic: str
    partition: int
    offset: int
    row: tuple
    raw_value: bytes
    log_entry: LogEntry


@dataclass
class PartitionBatch:
    """Batch of messages for a single partition"""
    topic: str
    partition: int
    messages: list = field(default_factory=list)
    min_offset: Optional[int] = None
    max_offset: Optional[int] = None

    def add(self, msg: PendingMessage):
        self.messages.append(msg)
        if self.min_offset is None or msg.offset < self.min_offset:
            self.min_offset = msg.offset
        if self.max_offset is None or msg.offset > self.max_offset:
            self.max_offset = msg.offset

    def clear(self):
        self.messages.clear()
        self.min_offset = None
        self.max_offset = None

    def __len__(self):
        return len(self.messages)


class BatchManager:
    """Thread-safe batch manager with partition awareness"""

    def __init__(self):
        self._batches: dict[tuple[str, int], PartitionBatch] = defaultdict(
            lambda: PartitionBatch("", 0)
        )
        self._lock = threading.Lock()
        self._last_flush_time = datetime.now()

    def add(self, msg: PendingMessage):
        with self._lock:
            key = (msg.topic, msg.partition)
            if key not in self._batches:
                self._batches[key] = PartitionBatch(msg.topic, msg.partition)
            self._batches[key].add(msg)

    def get_all_messages(self) -> list[PendingMessage]:
        with self._lock:
            all_messages = []
            for batch in self._batches.values():
                all_messages.extend(batch.messages)
            return all_messages

    def get_partition_batches(self) -> list[PartitionBatch]:
        with self._lock:
            return list(self._batches.values())

    def total_size(self) -> int:
        with self._lock:
            return sum(len(b) for b in self._batches.values())

    def clear_partition(self, topic: str, partition: int):
        with self._lock:
            key = (topic, partition)
            if key in self._batches:
                self._batches[key].clear()

    def clear_all(self):
        with self._lock:
            for batch in self._batches.values():
                batch.clear()
            self._last_flush_time = datetime.now()

    def revoke_partitions(self, partitions: list[tuple[str, int]]):
        """Remove batches for revoked partitions"""
        with self._lock:
            for key in partitions:
                if key in self._batches:
                    del self._batches[key]

    def seconds_since_last_flush(self) -> float:
        with self._lock:
            return (datetime.now() - self._last_flush_time).total_seconds()

    def mark_flushed(self):
        with self._lock:
            self._last_flush_time = datetime.now()


# =============================================================================
# Main Consumer Service
# =============================================================================

class ClickHouseConsumerService:
    """Robust Kafka consumer that writes to ClickHouse"""

    COLUMN_NAMES = [
        # Core fields
        'log_id', 'timestamp',
        # Service identification
        'service', 'environment', 'host', 'pod_name', 'container_id',
        # Log metadata
        'level', 'logger_name', 'message', 'stack_trace',
        # Distributed tracing
        'trace_id', 'span_id', 'parent_span_id',
        # Additional context
        'thread_name', 'user_id', 'request_id', 'correlation_id',
        # Structured metadata
        'labels', 'metadata',
        # Source information
        'source_type', 'source_file', 'source_line'
    ]

    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = logger.bind(component="clickhouse-consumer")

        # Kafka
        self.consumer: Optional[Consumer] = None
        self.dlq_producer: Optional[Producer] = None
        self.vectorization_producer: Optional[Producer] = None

        # ClickHouse
        self.ch_client: Optional[ClickHouseClient] = None

        # Circuit breaker using pybreaker
        self._cb_listener = CircuitBreakerMetricsListener(logger=self.logger)
        self.circuit_breaker = pybreaker.CircuitBreaker(
            fail_max=settings.circuit_breaker_failure_threshold,
            reset_timeout=settings.circuit_breaker_recovery_timeout,
            listeners=[self._cb_listener],
            name="clickhouse"
        )

        # State
        self._running = threading.Event()
        self._shutdown_complete = threading.Event()
        self.batch_manager = BatchManager()

        # Statistics
        self.total_consumed = 0
        self.total_written = 0
        self.total_failed = 0
        self.total_dlq = 0
        self.total_vectorization_sent = 0
        self.total_retries = 0
        self.start_time = datetime.now()

        # Parse vectorize levels
        self.vectorize_levels = set(
            level.strip().upper()
            for level in settings.vectorize_levels.split(',')
        )

        # Assigned partitions tracking
        self._assigned_partitions: set[tuple[str, int]] = set()
        self._partition_lock = threading.Lock()

    # -------------------------------------------------------------------------
    # Setup Methods
    # -------------------------------------------------------------------------

    def setup_clickhouse(self) -> bool:
        """Setup ClickHouse connection with retry"""
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                self.ch_client = clickhouse_connect.get_client(
                    host=self.settings.clickhouse_host,
                    port=self.settings.clickhouse_port,
                    username=self.settings.clickhouse_user,
                    password=self.settings.clickhouse_password,
                    database=self.settings.clickhouse_database,
                    connect_timeout=10,
                    send_receive_timeout=30,
                )

                # Verify connection
                result = self.ch_client.query("SELECT 1")

                self.logger.info(
                    "clickhouse_connected",
                    host=self.settings.clickhouse_host,
                    port=self.settings.clickhouse_port,
                    database=self.settings.clickhouse_database
                )
                return True

            except Exception as e:
                self.logger.warning(
                    "clickhouse_connection_attempt_failed",
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    error=str(e)
                )
                if attempt < max_attempts - 1:
                    import time
                    time.sleep(2 ** attempt)

        raise ConnectionError("Failed to connect to ClickHouse after retries")

    def setup_kafka(self) -> bool:
        """Setup Kafka consumer and producers"""
        try:
            # Consumer configuration - manual commits for at-least-once
            consumer_config = {
                'bootstrap.servers': self.settings.kafka_bootstrap_servers,
                'group.id': self.settings.kafka_group_id,
                'auto.offset.reset': 'earliest',
                'enable.auto.commit': False,  # Manual commits!
                'session.timeout.ms': self.settings.kafka_session_timeout_ms,
                'max.poll.interval.ms': self.settings.kafka_max_poll_interval_ms,
                'fetch.min.bytes': 1024,
                'fetch.wait.max.ms': 500,
            }

            self.consumer = Consumer(consumer_config)

            # Subscribe with rebalance callbacks
            self.consumer.subscribe(
                [self.settings.kafka_topic],
                on_assign=self._on_partitions_assigned,
                on_revoke=self._on_partitions_revoked
            )

            # DLQ Producer
            producer_config = {
                'bootstrap.servers': self.settings.kafka_bootstrap_servers,
                'acks': 'all',
                'retries': 3,
                'retry.backoff.ms': 1000,
                'linger.ms': 100,  # Batch DLQ messages
            }

            self.dlq_producer = Producer({
                **producer_config,
                'client.id': 'clickhouse-consumer-dlq',
            })

            # Vectorization Producer
            if self.settings.enable_vectorization:
                self.vectorization_producer = Producer({
                    **producer_config,
                    'client.id': 'clickhouse-consumer-vectorization',
                })

            self.logger.info(
                "kafka_connected",
                topic=self.settings.kafka_topic,
                group=self.settings.kafka_group_id
            )
            return True

        except Exception as e:
            self.logger.error("kafka_connection_failed", error=str(e))
            raise

    # -------------------------------------------------------------------------
    # Rebalance Handlers
    # -------------------------------------------------------------------------

    def _on_partitions_assigned(self, consumer, partitions: list[TopicPartition]):
        """Handle partition assignment"""
        with self._partition_lock:
            for tp in partitions:
                self._assigned_partitions.add((tp.topic, tp.partition))

        self.logger.info(
            "partitions_assigned",
            partitions=[(tp.topic, tp.partition) for tp in partitions]
        )

    def _on_partitions_revoked(self, consumer, partitions: list[TopicPartition]):
        """Handle partition revocation - flush and commit before losing partitions"""
        self.logger.info(
            "partitions_revoked",
            partitions=[(tp.topic, tp.partition) for tp in partitions]
        )

        # Flush any pending messages for these partitions
        revoked_keys = [(tp.topic, tp.partition) for tp in partitions]

        # Try to flush before revocation
        try:
            self._flush_batch(commit=True)
        except Exception as e:
            self.logger.error("flush_on_revoke_failed", error=str(e))

        # Remove from tracking
        self.batch_manager.revoke_partitions(revoked_keys)

        with self._partition_lock:
            for key in revoked_keys:
                self._assigned_partitions.discard(key)

    # -------------------------------------------------------------------------
    # Message Processing
    # -------------------------------------------------------------------------

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse ISO timestamp with multiple format support"""
        # Handle common formats
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%f%z',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
        ]

        # Try fromisoformat first (handles most cases)
        try:
            # Normalize 'Z' to '+00:00'
            normalized = timestamp_str.replace('Z', '+00:00')
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass

        # Fallback to strptime
        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue

        # Last resort: current time
        self.logger.warning(
            "timestamp_parse_failed",
            timestamp=timestamp_str,
            using="current_time"
        )
        return datetime.now(timezone.utc)

    def _parse_and_validate(self, message_value: bytes) -> Optional[LogEntry]:
        """Parse and validate Kafka message"""
        try:
            data = json.loads(message_value.decode('utf-8'))
            return LogEntry(**data)
        except json.JSONDecodeError as e:
            self.logger.debug("json_decode_failed", error=str(e))
            return None
        except Exception as e:
            self.logger.debug("validation_failed", error=str(e))
            return None

    def _transform_to_row(self, log_entry: LogEntry) -> tuple:
        """Transform Pydantic model to tuple for batch insert"""
        ts = self._parse_timestamp(log_entry.timestamp)

        # Convert labels dict to ClickHouse Map format (dict)
        # ClickHouse clickhouse-connect handles Python dict → Map automatically
        labels = log_entry.labels if log_entry.labels else {}

        return (
            # Core fields
            log_entry.log_id,
            ts,
            # Service identification
            log_entry.service,
            log_entry.environment,
            log_entry.host or "",
            log_entry.pod_name or "",
            log_entry.container_id or "",
            # Log metadata
            log_entry.level,
            log_entry.logger_name or "",
            log_entry.message,
            log_entry.stack_trace or "",
            # Distributed tracing
            log_entry.trace_id or "",
            log_entry.span_id or "",
            log_entry.parent_span_id or "",
            # Additional context
            log_entry.thread_name or "",
            log_entry.user_id or "",
            log_entry.request_id or "",
            log_entry.correlation_id or "",
            # Structured metadata
            labels,
            log_entry.metadata or "",
            # Source information
            log_entry.source_type or "",
            log_entry.source_file or "",
            log_entry.source_line or 0
        )

    # -------------------------------------------------------------------------
    # DLQ and Vectorization
    # -------------------------------------------------------------------------

    def _send_to_dlq(self, message_value: bytes, error: str, is_batch: bool = False):
        """Send failed message to Dead Letter Queue"""
        try:
            dlq_message = {
                'original_message': message_value.decode('utf-8', errors='replace'),
                'error': error,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'consumer_group': self.settings.kafka_group_id,
                'is_batch_failure': is_batch
            }

            self.dlq_producer.produce(
                topic=self.settings.kafka_dlq_topic,
                value=json.dumps(dlq_message).encode('utf-8'),
                callback=self._dlq_delivery_callback
            )

            # Don't flush every message - let them batch
            self.dlq_producer.poll(0)

        except Exception as e:
            self.logger.error("dlq_send_failed", error=str(e))

    def _dlq_delivery_callback(self, err, msg):
        """Callback for DLQ message delivery"""
        if err:
            self.logger.error("dlq_delivery_failed", error=str(err))
        else:
            self.total_dlq += 1
            MESSAGES_DLQ.inc()

    def _send_to_vectorization(self, log_entry: LogEntry):
        """Send ERROR/WARN/FATAL logs to vectorization queue"""
        if not self.settings.enable_vectorization:
            return
        if not self.vectorization_producer:
            return
        if log_entry.level not in self.vectorize_levels:
            return

        try:
            payload = {
                'log_id': log_entry.log_id,
                'timestamp': log_entry.timestamp,
                'service': log_entry.service,
                'environment': log_entry.environment,
                'level': log_entry.level,
                'message': log_entry.message,
                'stack_trace': log_entry.stack_trace or "",
                'trace_id': log_entry.trace_id or ""
            }

            self.vectorization_producer.produce(
                topic=self.settings.kafka_vectorization_topic,
                value=json.dumps(payload).encode('utf-8'),
                callback=self._vectorization_delivery_callback
            )
            self.vectorization_producer.poll(0)

        except Exception as e:
            self.logger.warning("vectorization_send_failed", error=str(e))

    def _vectorization_delivery_callback(self, err, msg):
        """Callback for vectorization message delivery"""
        if err:
            self.logger.warning("vectorization_delivery_failed", error=str(err))
        else:
            self.total_vectorization_sent += 1
            MESSAGES_VECTORIZATION.inc()

    # -------------------------------------------------------------------------
    # Batch Operations
    # -------------------------------------------------------------------------

    def _write_to_clickhouse_with_retry(self, rows: list[tuple]) -> bool:
        """Write batch to ClickHouse with retry logic and circuit breaker"""
        if not rows:
            return True

        last_error = None

        for attempt in range(self.settings.max_retries + 1):
            try:
                # Use circuit breaker's call method - will raise CircuitBreakerError if open
                self.circuit_breaker.call(self._do_clickhouse_insert, rows)
                return True

            except pybreaker.CircuitBreakerError:
                # Circuit is open, don't retry
                self.logger.warning(
                    "circuit_breaker_open_skipping_write",
                    batch_size=len(rows)
                )
                return False

            except Exception as e:
                last_error = e
                self.logger.warning(
                    "clickhouse_write_failed",
                    attempt=attempt + 1,
                    max_attempts=self.settings.max_retries + 1,
                    error=str(e)
                )

                if attempt < self.settings.max_retries:
                    self.total_retries += 1
                    RETRY_COUNT.inc()

                    # Exponential backoff
                    delay = min(
                        self.settings.retry_base_delay_seconds * (2 ** attempt),
                        self.settings.retry_max_delay_seconds
                    )
                    import time
                    time.sleep(delay)

                    # Try to reconnect
                    self._reconnect_clickhouse()

        # All retries failed
        self.logger.error(
            "clickhouse_write_all_retries_failed",
            error=str(last_error),
            batch_size=len(rows)
        )
        return False

    def _do_clickhouse_insert(self, rows: list[tuple]):
        """Actual ClickHouse insert - wrapped by circuit breaker"""
        self.ch_client.insert(
            table=self.settings.clickhouse_table,
            data=rows,
            column_names=self.COLUMN_NAMES
        )

    def _reconnect_clickhouse(self):
        """Attempt to reconnect to ClickHouse"""
        try:
            self.ch_client = clickhouse_connect.get_client(
                host=self.settings.clickhouse_host,
                port=self.settings.clickhouse_port,
                username=self.settings.clickhouse_user,
                password=self.settings.clickhouse_password,
                database=self.settings.clickhouse_database,
            )
        except Exception as e:
            self.logger.debug("reconnect_failed", error=str(e))

    def _flush_batch(self, commit: bool = True):
        """Flush current batch to ClickHouse"""
        messages = self.batch_manager.get_all_messages()

        if not messages:
            self.batch_manager.mark_flushed()
            return

        batch_size = len(messages)
        rows = [msg.row for msg in messages]

        self.logger.debug("flushing_batch", size=batch_size)

        with PROCESSING_TIME.time():
            success = self._write_to_clickhouse_with_retry(rows)

        if success:
            self.total_written += batch_size
            MESSAGES_WRITTEN.inc(batch_size)
            self.logger.info("batch_written", size=batch_size)

            # Commit offsets for successfully written messages
            if commit and self.consumer:
                self._commit_offsets(messages)

            self.batch_manager.clear_all()

        else:
            # Write failed - send all messages to DLQ
            self.total_failed += batch_size
            MESSAGES_FAILED.inc(batch_size)

            for msg in messages:
                self._send_to_dlq(
                    msg.raw_value,
                    "ClickHouse write failed after retries",
                    is_batch=True
                )

            # Still commit offsets (messages are in DLQ now)
            if commit and self.consumer:
                self._commit_offsets(messages)

            self.batch_manager.clear_all()

        # Flush DLQ producer
        if self.dlq_producer:
            self.dlq_producer.flush(timeout=5.0)

        BATCH_SIZE_METRIC.set(0)
        self.batch_manager.mark_flushed()

    def _commit_offsets(self, messages: list[PendingMessage]):
        """Commit offsets for processed messages"""
        # Group by partition and find max offset for each
        partition_offsets: dict[tuple[str, int], int] = {}

        for msg in messages:
            key = (msg.topic, msg.partition)
            if key not in partition_offsets or msg.offset > partition_offsets[key]:
                partition_offsets[key] = msg.offset

        # Commit offset + 1 (next offset to read)
        offsets = [
            TopicPartition(topic, partition, offset + 1)
            for (topic, partition), offset in partition_offsets.items()
        ]

        try:
            self.consumer.commit(offsets=offsets, asynchronous=False)
            self.logger.debug("offsets_committed", offsets=len(offsets))
        except Exception as e:
            self.logger.error("offset_commit_failed", error=str(e))

    def _should_flush(self) -> bool:
        """Check if batch should be flushed"""
        if self.batch_manager.total_size() >= self.settings.batch_size:
            return True

        if (self.batch_manager.seconds_since_last_flush() >=
                self.settings.flush_interval_seconds and
                self.batch_manager.total_size() > 0):
            return True

        return False

    # -------------------------------------------------------------------------
    # Main Consumer Loop
    # -------------------------------------------------------------------------

    def consume_loop(self):
        """Main consumer loop with proper error handling"""
        self._running.set()
        self.logger.info("consumer_started")

        try:
            while self._running.is_set():
                try:
                    msg = self.consumer.poll(
                        timeout=self.settings.poll_timeout_seconds
                    )

                    if msg is None:
                        if self._should_flush():
                            self._flush_batch()
                        continue

                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            continue
                        self.logger.error("kafka_error", error=msg.error())
                        continue

                    # Process message
                    self._process_message(msg)

                    # Check flush
                    if self._should_flush():
                        self._flush_batch()

                except Exception as e:
                    self.logger.error("consume_loop_iteration_error", error=str(e))
                    import time
                    time.sleep(1)  # Brief pause on error

        except Exception as e:
            self.logger.error("consume_loop_fatal_error", error=str(e))

        finally:
            self._shutdown()

    def _process_message(self, msg):
        """Process a single Kafka message"""
        self.total_consumed += 1
        MESSAGES_CONSUMED.labels(
            topic=msg.topic(),
            partition=str(msg.partition())
        ).inc()

        # Parse and validate
        log_entry = self._parse_and_validate(msg.value())

        if log_entry is None:
            self._send_to_dlq(msg.value(), "Validation failed")
            return

        # Send to vectorization
        self._send_to_vectorization(log_entry)

        # Transform to row
        try:
            row = self._transform_to_row(log_entry)

            pending = PendingMessage(
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
                row=row,
                raw_value=msg.value(),
                log_entry=log_entry
            )

            self.batch_manager.add(pending)
            BATCH_SIZE_METRIC.set(self.batch_manager.total_size())

        except Exception as e:
            self.logger.error("transformation_failed", error=str(e))
            self._send_to_dlq(msg.value(), f"Transformation failed: {str(e)}")

    def _shutdown(self):
        """Clean shutdown"""
        self.logger.info("consumer_shutting_down")

        # Flush remaining batch
        try:
            self._flush_batch()
        except Exception as e:
            self.logger.error("final_flush_failed", error=str(e))

        # Flush producers
        try:
            if self.dlq_producer:
                self.dlq_producer.flush(timeout=10.0)
            if self.vectorization_producer:
                self.vectorization_producer.flush(timeout=10.0)
        except Exception as e:
            self.logger.error("producer_flush_failed", error=str(e))

        # Close consumer
        try:
            if self.consumer:
                self.consumer.close()
        except Exception as e:
            self.logger.error("consumer_close_failed", error=str(e))

        # Close ClickHouse
        try:
            if self.ch_client:
                self.ch_client.close()
        except Exception as e:
            self.logger.error("clickhouse_close_failed", error=str(e))

        self._shutdown_complete.set()
        self.logger.info("consumer_stopped")

    def stop(self):
        """Signal consumer to stop"""
        self._running.clear()

    def wait_for_shutdown(self, timeout: float = 30.0) -> bool:
        """Wait for consumer to finish shutdown"""
        return self._shutdown_complete.wait(timeout=timeout)

    # -------------------------------------------------------------------------
    # Health and Stats
    # -------------------------------------------------------------------------

    def check_clickhouse_health(self) -> bool:
        """Verify ClickHouse connectivity"""
        try:
            if self.ch_client:
                self.ch_client.query("SELECT 1")
                return True
        except Exception:
            pass
        return False

    def get_stats(self) -> ConsumerStats:
        """Get consumer statistics"""
        return ConsumerStats(
            total_consumed=self.total_consumed,
            total_written=self.total_written,
            total_failed=self.total_failed,
            total_dlq=self.total_dlq,
            total_vectorization_sent=self.total_vectorization_sent,
            current_batch_size=self.batch_manager.total_size(),
            retry_count=self.total_retries,
            circuit_breaker_state=self.circuit_breaker.current_state
        )


# =============================================================================
# FastAPI Application
# =============================================================================

settings = Settings()
consumer_service: Optional[ClickHouseConsumerService] = None
consumer_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager with proper startup/shutdown"""
    global consumer_service, consumer_task

    logger.info("application_starting")

    try:
        consumer_service = ClickHouseConsumerService(settings)
        consumer_service.setup_clickhouse()
        consumer_service.setup_kafka()

        # Start consumer in background thread
        consumer_task = asyncio.create_task(
            asyncio.to_thread(consumer_service.consume_loop)
        )

        logger.info("application_started")

        yield

    finally:
        logger.info("application_stopping")

        if consumer_service:
            consumer_service.stop()

            # Wait for graceful shutdown
            shutdown_success = await asyncio.to_thread(
                consumer_service.wait_for_shutdown,
                timeout=30.0
            )

            if not shutdown_success:
                logger.warning("consumer_shutdown_timeout")

        if consumer_task:
            try:
                await asyncio.wait_for(consumer_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("consumer_task_timeout")
            except Exception as e:
                logger.error("consumer_task_error", error=str(e))

        logger.info("application_stopped")


app = FastAPI(
    title="ClickHouse Consumer Service",
    description="Robust Kafka to ClickHouse consumer with at-least-once delivery",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    if consumer_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    uptime = (datetime.now() - consumer_service.start_time).total_seconds()

    return HealthResponse(
        status="healthy" if consumer_service._running.is_set() else "degraded",
        service="clickhouse-consumer",
        version="2.0.0",
        kafka_connected=consumer_service.consumer is not None,
        clickhouse_connected=consumer_service.check_clickhouse_health(),
        clickhouse_circuit_breaker=consumer_service.circuit_breaker.current_state,
        messages_processed=consumer_service.total_written,
        current_batch_size=consumer_service.batch_manager.total_size(),
        uptime_seconds=uptime
    )


@app.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe"""
    if consumer_service is None:
        raise HTTPException(status_code=503, detail="Not ready")

    if not consumer_service._running.is_set():
        raise HTTPException(status_code=503, detail="Consumer not running")

    if not consumer_service.check_clickhouse_health():
        raise HTTPException(status_code=503, detail="ClickHouse unavailable")

    return {"status": "ready"}


@app.get("/live")
async def liveness_check():
    """Kubernetes liveness probe"""
    if consumer_service is None:
        raise HTTPException(status_code=503, detail="Not alive")

    return {"status": "alive"}


@app.get("/stats", response_model=ConsumerStats)
async def get_stats():
    """Get consumer statistics"""
    if consumer_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    return consumer_service.get_stats()


@app.post("/flush")
async def force_flush():
    """Force flush current batch"""
    if consumer_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Run flush in thread to not block
    await asyncio.to_thread(consumer_service._flush_batch)

    return {
        "status": "flushed",
        "batch_size": consumer_service.batch_manager.total_size()
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus metrics endpoint"""
    return generate_latest().decode('utf-8')


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )