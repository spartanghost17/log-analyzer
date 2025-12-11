"""
Vectorization Worker - Enhanced with Resilience Patterns
Consumes log messages from Kafka, generates embeddings, stores in Qdrant

Features:
- Consumes from vectorization-queue Kafka topic
- Batches messages for efficient embedding generation
- Calls Jina Embeddings Service with circuit breaker and retry
- Stores embeddings in Qdrant vector database
- Updates is_vectorized flag in ClickHouse
- Tracks metadata and deduplication
- Prometheus metrics and structured logging with request IDs
- Circuit breaker pattern for Qdrant and ClickHouse operations
- Retry logic with exponential backoff
"""

import asyncio
import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import List, Dict, Any, Optional

import clickhouse_connect
import httpx
import structlog
from confluent_kafka import Consumer, Producer, KafkaError, KafkaException
from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pybreaker import CircuitBreaker, CircuitBreakerError
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from settings import setup_development_logging, get_logger

setup_development_logging()
logger = get_logger(__name__)

# ============================================================================
# Request ID Context Variable
# ============================================================================

request_id_var: ContextVar[str] = ContextVar('request_id', default='')


# ============================================================================
# Configuration
# ============================================================================

class Settings(BaseSettings):
    """Service configuration"""

    # Service settings
    service_name: str = Field(default="vectorization-worker")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8004)

    # Kafka settings
    kafka_bootstrap_servers: str = Field(default="localhost:9092")
    kafka_topic: str = Field(default="vectorization-queue")
    kafka_group_id: str = Field(default="vectorization-worker-group")
    kafka_auto_offset_reset: str = Field(default="earliest")

    # Dead Letter Queue settings
    dlq_topic: str = Field(default="vectorization-queue-dlq")
    dlq_enabled: bool = Field(default=True)
    max_retries_per_batch: int = Field(default=3)

    # Jina Embeddings Service
    jina_service_url: str = Field(default="http://jina-embeddings:8003")
    jina_timeout: int = Field(default=30)

    # Qdrant settings
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_collection: str = Field(default="log_embeddings")

    # ClickHouse settings
    clickhouse_host: str = Field(default="localhost")
    clickhouse_port: int = Field(default=9000)
    clickhouse_database: str = Field(default="logs_db")
    clickhouse_user: str = Field(default="default")
    clickhouse_password: str = Field(default="")

    # Processing settings
    batch_size: int = Field(default=10)
    batch_timeout_seconds: float = Field(default=5.0)
    max_retries: int = Field(default=3)

    # Circuit breaker settings
    circuit_breaker_fail_max: int = Field(default=5)
    circuit_breaker_timeout: int = Field(default=60)

    # Retry settings
    retry_attempts: int = Field(default=3)
    retry_min_wait: int = Field(default=1)
    retry_max_wait: int = Field(default=10)

    class Config:
        env_prefix = ""
        case_sensitive = False


settings = Settings()


# ============================================================================
# Logging
# ============================================================================

# structlog.configure(
#     processors=[
#         structlog.contextvars.merge_contextvars,
#         structlog.processors.TimeStamper(fmt="iso"),
#         structlog.processors.add_log_level,
#         structlog.processors.JSONRenderer()
#     ]
# )
#
# logger = structlog.get_logger()


# ============================================================================
# Metrics
# ============================================================================

MESSAGES_CONSUMED = Counter(
    'vectorization_messages_consumed_total',
    'Total messages consumed from Kafka'
)

EMBEDDINGS_GENERATED = Counter(
    'vectorization_embeddings_generated_total',
    'Total embeddings generated',
    ['status']
)

QDRANT_WRITES = Counter(
    'vectorization_qdrant_writes_total',
    'Total writes to Qdrant',
    ['status']
)

CLICKHOUSE_UPDATES = Counter(
    'vectorization_clickhouse_updates_total',
    'Total ClickHouse is_vectorized updates',
    ['status']
)

CIRCUIT_BREAKER_STATE = Gauge(
    'vectorization_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)',
    ['breaker_name']
)

CIRCUIT_BREAKER_FAILURES = Counter(
    'vectorization_circuit_breaker_failures_total',
    'Number of circuit breaker failures',
    ['breaker_name']
)

API_RETRIES = Counter(
    'vectorization_api_retries_total',
    'Number of API call retries',
    ['operation']
)

BATCH_PROCESSING_TIME = Histogram(
    'vectorization_batch_processing_seconds',
    'Time to process a batch',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

CURRENT_BATCH_SIZE = Gauge(
    'vectorization_current_batch_size',
    'Current batch size being processed'
)

DLQ_MESSAGES_SENT = Counter(
    'vectorization_dlq_messages_sent_total',
    'Total messages sent to dead letter queue',
    ['reason']
)

BATCH_RETRIES = Counter(
    'vectorization_batch_retries_total',
    'Total number of batch retries'
)


# ============================================================================
# Pydantic Models
# ============================================================================

class LogMessage(BaseModel):
    """Log message from Kafka"""
    log_id: str
    timestamp: str
    service: str
    environment: str
    level: str
    message: str
    trace_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    stack_trace: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    kafka_connected: bool
    qdrant_connected: bool
    clickhouse_connected: bool
    jina_service_connected: bool
    messages_processed: int
    embeddings_stored: int
    clickhouse_updates: int
    dlq_messages_sent: int
    qdrant_circuit_breaker_state: str
    clickhouse_circuit_breaker_state: str
    uptime_seconds: float


class StatsResponse(BaseModel):
    """Service statistics"""
    total_consumed: int
    total_embedded: int
    total_stored: int
    total_failed: int
    total_clickhouse_updates: int
    total_dlq_sent: int
    current_batch_size: int


# ============================================================================
# Vectorization Worker Service
# ============================================================================

class VectorizationWorker:
    """Worker that vectorizes logs and stores in Qdrant"""

    def __init__(self):
        self.settings = settings
        self.logger = logger.bind(component=settings.service_name)

        # Clients
        self.kafka_consumer: Optional[Consumer] = None
        self.kafka_producer: Optional[Producer] = None  # For DLQ
        self.qdrant_client: Optional[QdrantClient] = None
        self.clickhouse_client: Optional[clickhouse_connect.driver.Client] = None
        self.http_client: Optional[httpx.AsyncClient] = None

        # Circuit breakers
        self.qdrant_breaker = CircuitBreaker(
            fail_max=settings.circuit_breaker_fail_max,
            timeout_duration=settings.circuit_breaker_timeout,
            name="Qdrant"
        )
        self.clickhouse_breaker = CircuitBreaker(
            fail_max=settings.circuit_breaker_fail_max,
            timeout_duration=settings.circuit_breaker_timeout,
            name="ClickHouse"
        )

        # State
        self.running = False
        self.start_time = time.time()

        # Stats
        self.total_consumed = 0
        self.total_embedded = 0
        self.total_stored = 0
        self.total_failed = 0
        self.total_clickhouse_updates = 0
        self.total_dlq_sent = 0

        # Batch state
        self.current_batch: List[Dict[str, Any]] = []
        self.last_batch_time = time.time()

        # Retry tracking: maps batch hash to retry count
        self.batch_retry_counts: Dict[str, int] = {}

    def setup_kafka(self):
        """Initialize Kafka consumer and producer"""
        try:
            # Setup consumer
            self.kafka_consumer = Consumer({
                'bootstrap.servers': self.settings.kafka_bootstrap_servers,
                'group.id': self.settings.kafka_group_id,
                'auto.offset.reset': self.settings.kafka_auto_offset_reset,
                'enable.auto.commit': False,
                'max.poll.interval.ms': 300000
            })

            self.kafka_consumer.subscribe([self.settings.kafka_topic])
            self.logger.info("kafka_consumer_connected", topic=self.settings.kafka_topic)

            # Setup producer for DLQ
            if self.settings.dlq_enabled:
                self.kafka_producer = Producer({
                    'bootstrap.servers': self.settings.kafka_bootstrap_servers,
                    'compression.type': 'gzip',
                    'linger.ms': 10
                })
                self.logger.info("kafka_producer_connected", dlq_topic=self.settings.dlq_topic)

        except Exception as e:
            self.logger.error("kafka_connection_failed", error=str(e))
            raise

    def setup_qdrant(self):
        """Initialize Qdrant client"""
        try:
            self.qdrant_client = QdrantClient(
                host=self.settings.qdrant_host,
                port=self.settings.qdrant_port
            )

            # Verify connection
            collections = self.qdrant_client.get_collections()
            self.logger.info("qdrant_connected",
                           collections=[c.name for c in collections.collections])

        except Exception as e:
            self.logger.error("qdrant_connection_failed", error=str(e))
            raise

    def setup_clickhouse(self):
        """Initialize ClickHouse client"""
        try:
            self.clickhouse_client = clickhouse_connect.get_client(
                host=self.settings.clickhouse_host,
                port=self.settings.clickhouse_port,
                database=self.settings.clickhouse_database,
                username=self.settings.clickhouse_user,
                password=self.settings.clickhouse_password
            )

            # Verify connection
            result = self.clickhouse_client.query("SELECT version()")
            version = result.result_rows[0][0] if result.result_rows else "unknown"

            self.logger.info("clickhouse_connected",
                           host=self.settings.clickhouse_host,
                           database=self.settings.clickhouse_database,
                           version=version)

        except Exception as e:
            self.logger.error("clickhouse_connection_failed", error=str(e))
            raise

    async def setup_http_client(self):
        """Initialize HTTP client for Jina service"""
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.jina_timeout)
        )

        # Test connection to Jina service
        try:
            response = await self.http_client.get(
                f"{self.settings.jina_service_url}/health"
            )
            response.raise_for_status()
            self.logger.info("jina_service_connected")
        except Exception as e:
            self.logger.warning("jina_service_connection_failed", error=str(e))

    async def startup(self):
        """Initialize all connections"""
        self.logger.info("worker_starting")

        self.setup_kafka()
        self.setup_qdrant()
        self.setup_clickhouse()
        await self.setup_http_client()

        self.running = True
        self.logger.info("worker_started")

    async def shutdown(self):
        """Cleanup on shutdown"""
        self.logger.info("worker_stopping")
        self.running = False

        # Process any remaining messages in batch
        if self.current_batch:
            self.logger.info("processing_remaining_batch", size=len(self.current_batch))
            await self.process_batch(self.current_batch)

        if self.kafka_consumer:
            self.kafka_consumer.close()

        if self.kafka_producer:
            self.kafka_producer.flush()

        if self.clickhouse_client:
            self.clickhouse_client.close()

        if self.http_client:
            await self.http_client.aclose()

        self.logger.info("worker_stopped",
                       total_processed=self.total_consumed,
                       total_stored=self.total_stored,
                       total_clickhouse_updates=self.total_clickhouse_updates,
                       total_dlq_sent=self.total_dlq_sent)

    def _compute_batch_hash(self, batch: List[Dict[str, Any]]) -> str:
        """Compute unique hash for a batch based on log IDs"""
        log_ids = sorted([msg.get("log_id", "") for msg in batch])
        batch_key = ",".join(log_ids)
        return hashlib.md5(batch_key.encode()).hexdigest()

    def send_to_dlq(self, batch: List[Dict[str, Any]], error_message: str, retry_count: int):
        """
        Send failed batch to Dead Letter Queue

        Each message is sent individually with metadata about the failure
        """
        if not self.settings.dlq_enabled or not self.kafka_producer:
            self.logger.warning("dlq_disabled_messages_lost", batch_size=len(batch))
            return

        for log_data in batch:
            try:
                # Prepare DLQ message with failure metadata
                dlq_message = {
                    "original_message": log_data,
                    "error": error_message,
                    "retry_count": retry_count,
                    "failed_at": datetime.utcnow().isoformat(),
                    "service": self.settings.service_name,
                    "original_topic": self.settings.kafka_topic
                }

                # Send to DLQ topic
                self.kafka_producer.produce(
                    topic=self.settings.dlq_topic,
                    value=json.dumps(dlq_message).encode('utf-8'),
                    key=log_data.get("log_id", "unknown").encode('utf-8')
                )

                DLQ_MESSAGES_SENT.labels(reason="max_retries_exceeded").inc()
                self.total_dlq_sent += 1

            except Exception as e:
                self.logger.error("dlq_send_failed",
                                error=str(e),
                                log_id=log_data.get("log_id"))

        # Flush to ensure messages are sent
        self.kafka_producer.flush(timeout=5)

        self.logger.warning("batch_sent_to_dlq",
                          batch_size=len(batch),
                          retry_count=retry_count,
                          error=error_message[:200])

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(logger, structlog.INFO),
        reraise=True
    )
    async def _call_jina_service(self, texts: List[str]) -> List[List[float]]:
        """
        Call Jina embeddings service with retry logic

        Note: Caching is handled by jina-embeddings service, not here.
        This avoids double caching and keeps responsibilities clear.
        """
        request_id = request_id_var.get()

        try:
            self.logger.info("calling_jina_service",
                           count=len(texts),
                           request_id=request_id)

            response = await self.http_client.post(
                f"{self.settings.jina_service_url}/embeddings",
                json={"texts": texts},
                headers={"X-Request-ID": request_id}
            )
            response.raise_for_status()
            data = response.json()

            embeddings = [item["embedding"] for item in data["embeddings"]]

            # Log cache statistics from jina-embeddings response
            if "cache_hits" in data and "cache_misses" in data:
                self.logger.info("jina_cache_stats",
                               cache_hits=data["cache_hits"],
                               cache_misses=data["cache_misses"],
                               request_id=data.get("request_id"))

            return embeddings

        except Exception as e:
            API_RETRIES.labels(operation="jina_embeddings").inc()
            self.logger.warning("jina_api_retry", error=str(e), request_id=request_id)
            raise

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings by calling Jina Embeddings Service

        Note: Caching is handled by jina-embeddings service.
        This service simply calls the API and trusts that caching
        is handled upstream.
        """
        try:
            embeddings = await self._call_jina_service(texts)
            EMBEDDINGS_GENERATED.labels(status="success").inc(len(embeddings))
            return embeddings

        except Exception as e:
            self.logger.error("embedding_generation_failed", error=str(e))
            EMBEDDINGS_GENERATED.labels(status="failed").inc(len(texts))
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, structlog.INFO),
        reraise=True
    )
    def _store_in_qdrant_with_retry(self, points: List[PointStruct]) -> None:
        """Store points in Qdrant with circuit breaker and retry"""
        try:
            # Update circuit breaker state metric
            state_map = {"closed": 0, "open": 1, "half_open": 2}
            CIRCUIT_BREAKER_STATE.labels(breaker_name="Qdrant").set(
                state_map.get(self.qdrant_breaker.current_state, 0)
            )

            # Call Qdrant through circuit breaker
            self.qdrant_breaker.call(
                self.qdrant_client.upsert,
                collection_name=self.settings.qdrant_collection,
                points=points
            )

        except CircuitBreakerError:
            CIRCUIT_BREAKER_FAILURES.labels(breaker_name="Qdrant").inc()
            self.logger.error("qdrant_circuit_breaker_open")
            raise
        except Exception as e:
            API_RETRIES.labels(operation="qdrant_upsert").inc()
            self.logger.warning("qdrant_upsert_retry", error=str(e))
            raise

    def store_in_qdrant(self, logs: List[LogMessage], embeddings: List[List[float]]) -> List[str]:
        """Store embeddings in Qdrant and return log IDs"""
        try:
            points = []
            log_ids = []

            for log, embedding in zip(logs, embeddings):
                # Create unique point ID
                point_id = hashlib.md5(
                    f"{log.log_id}_{log.timestamp}".encode()
                ).hexdigest()

                # Prepare payload (metadata)
                payload = {
                    "log_id": log.log_id,
                    "timestamp": int(datetime.fromisoformat(
                        log.timestamp.replace('Z', '+00:00')
                    ).timestamp()),
                    "service": log.service,
                    "environment": log.environment,
                    "level": log.level,
                    "message": log.message[:500],  # Truncate for storage
                    "trace_id": log.trace_id,
                    "user_id": log.user_id,
                    "request_id": log.request_id
                }

                # Create point
                point = PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )

                points.append(point)
                log_ids.append(log.log_id)

            # Batch upsert to Qdrant with circuit breaker and retry
            self._store_in_qdrant_with_retry(points)

            QDRANT_WRITES.labels(status="success").inc(len(points))
            self.total_stored += len(points)

            self.logger.info("stored_in_qdrant", count=len(points))

            return log_ids

        except Exception as e:
            self.logger.error("qdrant_storage_failed", error=str(e))
            QDRANT_WRITES.labels(status="failed").inc(len(logs))
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, structlog.INFO),
        reraise=True
    )
    def _update_clickhouse_with_retry(self, log_ids: List[str]) -> None:
        """Update ClickHouse with circuit breaker and retry"""
        try:
            # Update circuit breaker state metric
            state_map = {"closed": 0, "open": 1, "half_open": 2}
            CIRCUIT_BREAKER_STATE.labels(breaker_name="ClickHouse").set(
                state_map.get(self.clickhouse_breaker.current_state, 0)
            )

            # Prepare parameters for safe query
            query = """
                ALTER TABLE logs
                UPDATE is_vectorized = 1
                WHERE log_id IN {log_ids:Array(String)}
            """

            # Call ClickHouse through circuit breaker
            self.clickhouse_breaker.call(
                self.clickhouse_client.command,
                query,
                parameters={"log_ids": log_ids}
            )

        except CircuitBreakerError:
            CIRCUIT_BREAKER_FAILURES.labels(breaker_name="ClickHouse").inc()
            self.logger.error("clickhouse_circuit_breaker_open")
            raise
        except Exception as e:
            API_RETRIES.labels(operation="clickhouse_update").inc()
            self.logger.warning("clickhouse_update_retry", error=str(e))
            raise

    def update_is_vectorized(self, log_ids: List[str]):
        """
        Update is_vectorized flag in ClickHouse

        CRITICAL: This marks logs as vectorized after successful Qdrant storage.
        This allows downstream services to query for vectorized logs.
        """
        if not log_ids:
            return

        try:
            # Update with circuit breaker and retry
            self._update_clickhouse_with_retry(log_ids)

            CLICKHOUSE_UPDATES.labels(status="success").inc(len(log_ids))
            self.total_clickhouse_updates += len(log_ids)

            self.logger.info("clickhouse_updated",
                           count=len(log_ids),
                           log_ids_sample=log_ids[:3])

        except Exception as e:
            self.logger.error("clickhouse_update_failed",
                            error=str(e),
                            count=len(log_ids))
            CLICKHOUSE_UPDATES.labels(status="failed").inc(len(log_ids))
            # Don't raise - we don't want to fail the whole batch if ClickHouse update fails
            # The logs are still in Qdrant, we can retry the update later

    async def process_batch(self, batch: List[Dict[str, Any]]):
        """
        Process a batch of log messages with retry and DLQ support

        Retry Logic:
        1. Track retry count per batch using batch hash
        2. If batch fails and retry_count < max_retries: raise exception (Kafka will redeliver)
        3. If batch fails and retry_count >= max_retries: send to DLQ and succeed (commit offset)
        """
        if not batch:
            return

        start_time = time.time()
        CURRENT_BATCH_SIZE.set(len(batch))
        batch_request_id = str(uuid.uuid4())
        request_id_var.set(batch_request_id)
        structlog.contextvars.bind_contextvars(request_id=batch_request_id)

        # Compute batch hash for retry tracking
        batch_hash = self._compute_batch_hash(batch)
        retry_count = self.batch_retry_counts.get(batch_hash, 0)

        try:
            self.logger.info("processing_batch",
                           size=len(batch),
                           retry_count=retry_count,
                           request_id=batch_request_id)

            # Parse log messages
            logs = [LogMessage(**msg) for msg in batch]

            # Extract text for embedding
            texts = [log.message for log in logs]

            # Generate embeddings (calls jina-embeddings service)
            embeddings = await self.generate_embeddings(texts)
            self.total_embedded += len(embeddings)

            # Store in Qdrant (returns log IDs)
            log_ids = self.store_in_qdrant(logs, embeddings)

            # CRITICAL: Update is_vectorized flag in ClickHouse
            self.update_is_vectorized(log_ids)

            # Success! Remove from retry tracking
            if batch_hash in self.batch_retry_counts:
                del self.batch_retry_counts[batch_hash]

            # Track duration
            duration = time.time() - start_time
            BATCH_PROCESSING_TIME.observe(duration)

            self.logger.info(
                "batch_processed",
                size=len(batch),
                duration_seconds=round(duration, 3),
                embeddings_generated=len(embeddings),
                qdrant_stored=len(log_ids),
                clickhouse_updated=len(log_ids),
                retry_count=retry_count,
                request_id=batch_request_id
            )

        except Exception as e:
            error_message = str(e)
            self.logger.error("batch_processing_failed",
                            error=error_message,
                            size=len(batch),
                            retry_count=retry_count,
                            request_id=batch_request_id)

            # Increment retry count
            self.batch_retry_counts[batch_hash] = retry_count + 1
            BATCH_RETRIES.inc()

            # Check if we've exceeded max retries
            if retry_count + 1 >= self.settings.max_retries_per_batch:
                self.logger.error("max_retries_exceeded_sending_to_dlq",
                                batch_size=len(batch),
                                retry_count=retry_count + 1,
                                error=error_message[:200])

                # Send to DLQ and remove from retry tracking
                self.send_to_dlq(batch, error_message, retry_count + 1)
                del self.batch_retry_counts[batch_hash]
                self.total_failed += len(batch)

                # Don't raise - we want to commit the offset since we sent to DLQ
            else:
                # Still have retries left - raise exception to prevent offset commit
                # Kafka will redeliver this batch
                self.logger.warning("batch_will_retry",
                                  retry_count=retry_count + 1,
                                  max_retries=self.settings.max_retries_per_batch)
                raise  # Re-raise to prevent offset commit

        finally:
            CURRENT_BATCH_SIZE.set(0)
            structlog.contextvars.clear_contextvars()

    async def consume_loop(self):
        """Main consumption loop with retry and DLQ support"""
        self.logger.info("starting_consume_loop")

        while self.running:
            try:
                # Poll Kafka
                msg = self.kafka_consumer.poll(timeout=1.0)

                if msg is None:
                    # Check if we should flush batch due to timeout
                    if (self.current_batch and
                        time.time() - self.last_batch_time > self.settings.batch_timeout_seconds):
                        try:
                            await self.process_batch(self.current_batch)
                            # Only commit if batch processing succeeded (or was sent to DLQ)
                            self.kafka_consumer.commit()
                            self.current_batch = []
                            self.last_batch_time = time.time()
                        except Exception as e:
                            # Batch failed and needs retry - don't commit, don't clear batch
                            # Kafka will redeliver after we poll again
                            self.logger.warning("batch_timeout_retry_needed",
                                              size=len(self.current_batch),
                                              error=str(e))
                            await asyncio.sleep(1)  # Brief delay before retry
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        raise KafkaException(msg.error())

                # Parse message
                try:
                    log_data = json.loads(msg.value().decode('utf-8'))

                    MESSAGES_CONSUMED.inc()
                    self.total_consumed += 1

                    # Add to current batch
                    self.current_batch.append(log_data)

                    # Process batch if full
                    if len(self.current_batch) >= self.settings.batch_size:
                        try:
                            await self.process_batch(self.current_batch)
                            # Only commit if batch processing succeeded (or was sent to DLQ)
                            self.kafka_consumer.commit()
                            self.current_batch = []
                            self.last_batch_time = time.time()
                        except Exception as e:
                            # Batch failed and needs retry - don't commit, don't clear batch
                            # Kafka will redeliver after we poll again
                            self.logger.warning("batch_full_retry_needed",
                                              size=len(self.current_batch),
                                              error=str(e))
                            # Clear batch to allow consuming new messages
                            # The failed batch will be redelivered by Kafka
                            self.current_batch = []
                            await asyncio.sleep(1)  # Brief delay before retry

                except json.JSONDecodeError as e:
                    self.logger.error("invalid_json", error=str(e))
                    # Skip this message - commit to move past it
                    self.kafka_consumer.commit()
                    continue

            except Exception as e:
                self.logger.error("consume_loop_error", error=str(e))
                await asyncio.sleep(1)

    def get_uptime(self) -> float:
        """Get service uptime"""
        return time.time() - self.start_time

    def is_kafka_connected(self) -> bool:
        """Check if Kafka is connected"""
        return self.kafka_consumer is not None

    def is_qdrant_connected(self) -> bool:
        """Check if Qdrant is connected"""
        try:
            if self.qdrant_client:
                self.qdrant_client.get_collections()
                return True
        except:
            pass
        return False

    def is_clickhouse_connected(self) -> bool:
        """Check if ClickHouse is connected"""
        try:
            if self.clickhouse_client:
                self.clickhouse_client.query("SELECT 1")
                return True
        except:
            pass
        return False

    async def is_jina_connected(self) -> bool:
        """Check if Jina service is connected"""
        try:
            if self.http_client:
                response = await self.http_client.get(
                    f"{self.settings.jina_service_url}/health",
                    timeout=5.0
                )
                return response.status_code == 200
        except:
            pass
        return False


# ============================================================================
# FastAPI Application
# ============================================================================

worker = VectorizationWorker()
worker_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager"""
    global worker_task

    # Startup
    await worker.startup()

    # Start consumer loop in background
    worker_task = asyncio.create_task(worker.consume_loop())

    yield

    # Shutdown
    await worker.shutdown()

    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Vectorization Worker",
    description="Consumes logs, generates embeddings, stores in Qdrant, updates ClickHouse",
    version="2.0.0",
    lifespan=lifespan
)


# ============================================================================
# Request ID Middleware
# ============================================================================

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all HTTP requests"""
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request_id_var.set(req_id)
    structlog.contextvars.bind_contextvars(request_id=req_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id

    structlog.contextvars.clear_contextvars()
    return response


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Enhanced health check endpoint with DLQ monitoring"""
    return HealthResponse(
        status="healthy" if worker.running else "stopped",
        service=settings.service_name,
        kafka_connected=worker.is_kafka_connected(),
        qdrant_connected=worker.is_qdrant_connected(),
        clickhouse_connected=worker.is_clickhouse_connected(),
        jina_service_connected=await worker.is_jina_connected(),
        messages_processed=worker.total_consumed,
        embeddings_stored=worker.total_stored,
        clickhouse_updates=worker.total_clickhouse_updates,
        dlq_messages_sent=worker.total_dlq_sent,
        qdrant_circuit_breaker_state=worker.qdrant_breaker.current_state,
        clickhouse_circuit_breaker_state=worker.clickhouse_breaker.current_state,
        uptime_seconds=round(worker.get_uptime(), 2)
    )


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get service statistics including DLQ"""
    return StatsResponse(
        total_consumed=worker.total_consumed,
        total_embedded=worker.total_embedded,
        total_stored=worker.total_stored,
        total_failed=worker.total_failed,
        total_clickhouse_updates=worker.total_clickhouse_updates,
        total_dlq_sent=worker.total_dlq_sent,
        current_batch_size=len(worker.current_batch)
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info"
    )
