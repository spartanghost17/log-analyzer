"""
ClickHouse Consumer Service
Consumes logs from Kafka and writes to ClickHouse
Features: Dead Letter Queue, Batching, clickhouse-connect client
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

import clickhouse_connect
from clickhouse_connect.driver.client import Client as ClickHouseClient
from confluent_kafka import Consumer, Producer, KafkaError
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from settings import setup_logging
import structlog

# # Configure structured logging
# structlog.configure(
#     processors=[
#         structlog.stdlib.filter_by_level,
#         structlog.stdlib.add_logger_name,
#         structlog.stdlib.add_log_level,
#         structlog.stdlib.PositionalArgumentsFormatter(),
#         structlog.processors.TimeStamper(fmt="iso"),
#         structlog.processors.StackInfoRenderer(),
#         structlog.processors.format_exc_info,
#         structlog.processors.UnicodeDecoder(),
#         structlog.processors.JSONRenderer()
#     ],
#     wrapper_class=structlog.stdlib.BoundLogger,
#     context_class=dict,
#     logger_factory=structlog.stdlib.LoggerFactory(),
#     cache_logger_on_first_use=True,
# )
setup_logging("DEBUG")
logger = structlog.get_logger()

# Prometheus metrics
MESSAGES_CONSUMED = Counter('messages_consumed_total', 'Total messages consumed')
MESSAGES_WRITTEN = Counter('messages_written_total', 'Total messages written to ClickHouse')
MESSAGES_FAILED = Counter('messages_failed_total', 'Total messages failed')
MESSAGES_DLQ = Counter('messages_dlq_total', 'Total messages sent to DLQ')
MESSAGES_VECTORIZATION = Counter('messages_vectorization_total', 'Messages sent to vectorization')
PROCESSING_TIME = Histogram('message_processing_seconds', 'Message processing time')
BATCH_SIZE_METRIC = Gauge('current_batch_size', 'Current batch size')


class LogLevel(str, Enum):
    """Log severity levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class Settings(BaseSettings):
    """Service configuration"""
    # Kafka settings
    kafka_bootstrap_servers: str = Field(default="localhost:9092", validation_alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_topic: str = Field(default="raw-logs", validation_alias="KAFKA_TOPIC")
    kafka_dlq_topic: str = Field(default="raw-logs-dlq", validation_alias="KAFKA_DLQ_TOPIC")
    kafka_vectorization_topic: str = Field(default="vectorization-queue", validation_alias="KAFKA_VECTORIZATION_TOPIC")
    kafka_group_id: str = Field(default="clickhouse-consumer-group", validation_alias="KAFKA_GROUP_ID")

    # ClickHouse settings - HTTP interface (port 8123)
    clickhouse_host: str = Field(default="localhost", validation_alias="CLICKHOUSE_HOST")
    clickhouse_port: int = Field(default=8123, validation_alias="CLICKHOUSE_PORT")  # HTTP port, not 9000
    clickhouse_user: str = Field(default="admin", validation_alias="CLICKHOUSE_USER")
    clickhouse_password: str = Field(default="clickhouse_password", validation_alias="CLICKHOUSE_PASSWORD")
    clickhouse_database: str = Field(default="logs_db", validation_alias="CLICKHOUSE_DATABASE")

    # Processing settings
    batch_size: int = Field(default=1000, ge=1, le=10000, validation_alias="BATCH_SIZE")
    flush_interval_seconds: int = Field(default=5, ge=1, le=60, validation_alias="FLUSH_INTERVAL_SECONDS")

    # Vectorization settings
    enable_vectorization: bool = Field(default=True, validation_alias="ENABLE_VECTORIZATION")
    vectorize_levels: str = Field(default="ERROR,WARN,FATAL", validation_alias="VECTORIZE_LEVELS")

    # API settings
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8001, validation_alias="API_PORT")

    # model_config = SettingsConfigDict(
    #     extra="ignore",
    #     case_sensitive=False,
    #     populate_by_name=True,
    # )

    # class Config:
    #     env_prefix = ""
    #     case_sensitive = False


# Pydantic Models
class LogEntry(BaseModel):
    """Incoming log entry"""
    log_id: str
    timestamp: str
    service: str
    environment: str
    level: str
    message: str
    trace_id: Optional[str] = ""
    user_id: Optional[str] = ""
    request_id: Optional[str] = ""
    stack_trace: Optional[str] = ""

    @field_validator('level')
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARN", "ERROR", "FATAL", "TRACE"]
        if v not in valid_levels:
            raise ValueError(f"Level must be one of {valid_levels}")
        return v


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    kafka_connected: bool
    clickhouse_connected: bool
    messages_processed: int
    uptime_seconds: float


class ConsumerStats(BaseModel):
    """Consumer statistics"""
    total_consumed: int
    total_written: int
    total_failed: int
    total_dlq: int
    total_vectorization_sent: int
    current_batch_size: int


class ClickHouseConsumerService:
    """Kafka consumer that writes to ClickHouse"""

    # Column names for batch insert (must match table schema)
    COLUMN_NAMES = [
        'log_id', 'timestamp', 'service', 'environment', 'level',
        'message', 'trace_id', 'user_id', 'request_id', 'stack_trace'
    ]

    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = logger.bind(component="clickhouse-consumer")

        # Kafka
        self.consumer: Optional[Consumer] = None
        self.dlq_producer: Optional[Producer] = None
        self.vectorization_producer: Optional[Producer] = None

        # ClickHouse client
        self.ch_client: Optional[ClickHouseClient] = None

        # State
        self.running = False
        self.batch: List[tuple] = []  # List of tuples for batch insert
        self.last_flush_time = datetime.now()

        # Statistics
        self.total_consumed = 0
        self.total_written = 0
        self.total_failed = 0
        self.total_dlq = 0
        self.total_vectorization_sent = 0
        self.start_time = datetime.now()

        # Parse vectorize levels
        self.vectorize_levels = set(
            level.strip() for level in self.settings.vectorize_levels.split(',')
        )

    def setup_clickhouse(self):
        """Setup ClickHouse connection using clickhouse-connect"""
        try:
            self.ch_client = clickhouse_connect.get_client(
                host=self.settings.clickhouse_host,
                port=self.settings.clickhouse_port,  # HTTP port 8123
                username=self.settings.clickhouse_user,
                password=self.settings.clickhouse_password,
                database=self.settings.clickhouse_database
            )

            # Test connection
            result = self.ch_client.query("SELECT 1")

            self.logger.info(
                "clickhouse_connected",
                host=self.settings.clickhouse_host,
                port=self.settings.clickhouse_port,
                database=self.settings.clickhouse_database
            )
            return True

        except Exception as e:
            self.logger.error("clickhouse_connection_failed", error=str(e))
            raise

    def setup_kafka(self):
        """Setup Kafka consumer and producers"""
        try:
            # Consumer configuration
            consumer_config = {
                'bootstrap.servers': self.settings.kafka_bootstrap_servers,
                'group.id': self.settings.kafka_group_id,
                'auto.offset.reset': 'earliest',
                'enable.auto.commit': True,
                'session.timeout.ms': 30000,
            }

            self.consumer = Consumer(consumer_config)
            self.consumer.subscribe([self.settings.kafka_topic])

            # DLQ Producer
            dlq_config = {
                'bootstrap.servers': self.settings.kafka_bootstrap_servers,
                'client.id': 'clickhouse-consumer-dlq',
            }
            self.dlq_producer = Producer(dlq_config)

            # Vectorization Producer (if enabled)
            if self.settings.enable_vectorization:
                vectorization_config = {
                    'bootstrap.servers': self.settings.kafka_bootstrap_servers,
                    'client.id': 'clickhouse-consumer-vectorization',
                }
                self.vectorization_producer = Producer(vectorization_config)

            self.logger.info(
                "kafka_connected",
                topic=self.settings.kafka_topic,
                group=self.settings.kafka_group_id
            )
            return True

        except Exception as e:
            self.logger.error("kafka_connection_failed", error=str(e))
            raise

    def send_to_dlq(self, message_value: bytes, error: str):
        """Send failed message to Dead Letter Queue"""
        try:
            dlq_message = {
                'original_message': message_value.decode('utf-8'),
                'error': error,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'consumer_group': self.settings.kafka_group_id
            }

            self.dlq_producer.produce(
                topic=self.settings.kafka_dlq_topic,
                value=json.dumps(dlq_message).encode('utf-8')
            )
            self.dlq_producer.flush()

            self.total_dlq += 1
            MESSAGES_DLQ.inc()

            self.logger.warning("message_sent_to_dlq", error=error)

        except Exception as e:
            self.logger.error("dlq_send_failed", error=str(e))

    def send_to_vectorization_queue(self, log_entry: LogEntry):
        """Send ERROR/WARN logs to vectorization queue"""
        if not self.settings.enable_vectorization:
            return

        if not self.vectorization_producer:
            return

        if log_entry.level not in self.vectorize_levels:
            return

        try:
            vectorization_payload = {
                'log_id': log_entry.log_id,
                'timestamp': log_entry.timestamp,
                'service': log_entry.service,
                'environment': log_entry.environment,
                'level': log_entry.level,
                'message': log_entry.message,
                'stack_trace': log_entry.stack_trace,
                'trace_id': log_entry.trace_id
            }

            self.vectorization_producer.produce(
                topic=self.settings.kafka_vectorization_topic,
                value=json.dumps(vectorization_payload).encode('utf-8')
            )
            self.vectorization_producer.poll(0)

            self.total_vectorization_sent += 1
            MESSAGES_VECTORIZATION.inc()

        except Exception as e:
            self.logger.warning("vectorization_send_failed", error=str(e))

    def parse_and_validate_message(self, message_value: bytes) -> Optional[LogEntry]:
        """Parse and validate Kafka message"""
        try:
            # Parse JSON
            data = json.loads(message_value.decode('utf-8'))

            # Validate with Pydantic
            log_entry = LogEntry(**data)

            return log_entry

        except json.JSONDecodeError as e:
            self.logger.error("json_decode_failed", error=str(e))
            return None
        except Exception as e:
            self.logger.error("validation_failed", error=str(e))
            return None

    def transform_to_row(self, log_entry: LogEntry) -> tuple:
        """Transform Pydantic model to tuple for batch insert"""
        # Parse timestamp
        ts = datetime.fromisoformat(log_entry.timestamp.replace('Z', '+00:00'))

        return (
            log_entry.log_id,
            ts,
            log_entry.service,
            log_entry.environment,
            log_entry.level,
            log_entry.message,
            log_entry.trace_id or "",
            log_entry.user_id or "",
            log_entry.request_id or "",
            log_entry.stack_trace or ""
        )

    def flush_batch(self):
        """Flush current batch to ClickHouse"""
        if not self.batch:
            return

        batch_size = len(self.batch)

        try:
            with PROCESSING_TIME.time():
                # Use clickhouse-connect's batch insert
                self.ch_client.insert(
                    table='logs',
                    data=self.batch,
                    column_names=self.COLUMN_NAMES
                )

            self.total_written += batch_size
            MESSAGES_WRITTEN.inc(batch_size)

            self.logger.info("batch_written", size=batch_size)

        except Exception as e:
            self.logger.error("batch_write_failed", error=str(e), size=batch_size)
            self.total_failed += batch_size
            MESSAGES_FAILED.inc(batch_size)

        finally:
            self.batch = []
            self.last_flush_time = datetime.now()
            BATCH_SIZE_METRIC.set(0)

    def should_flush_batch(self) -> bool:
        """Check if batch should be flushed"""
        if len(self.batch) >= self.settings.batch_size:
            return True

        elapsed = (datetime.now() - self.last_flush_time).total_seconds()
        if elapsed >= self.settings.flush_interval_seconds and self.batch:
            return True

        return False

    async def consume_loop(self):
        """Main consumer loop"""
        self.running = True
        self.logger.info("consumer_started")

        try:
            while self.running:
                # Poll for message
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    # Check if should flush due to timeout
                    if self.should_flush_batch():
                        self.flush_batch()
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        self.logger.error("kafka_error", error=msg.error())
                        continue

                # Process message
                self.total_consumed += 1
                MESSAGES_CONSUMED.inc()

                # Parse and validate
                log_entry = self.parse_and_validate_message(msg.value())

                if log_entry is None:
                    # Validation failed - send to DLQ
                    self.send_to_dlq(msg.value(), "Validation failed")
                    continue

                # Send to vectorization queue if applicable
                self.send_to_vectorization_queue(log_entry)

                # Transform to row tuple
                try:
                    row = self.transform_to_row(log_entry)
                    self.batch.append(row)
                    BATCH_SIZE_METRIC.set(len(self.batch))

                except Exception as e:
                    self.logger.error("transformation_failed", error=str(e))
                    self.send_to_dlq(msg.value(), f"Transformation failed: {str(e)}")
                    continue

                # Check if should flush
                if self.should_flush_batch():
                    self.flush_batch()

                # Small delay
                await asyncio.sleep(0.001)

        except Exception as e:
            self.logger.error("consume_loop_error", error=str(e))
        finally:
            # Flush remaining batch
            if self.batch:
                self.flush_batch()

            if self.consumer:
                self.consumer.close()

            self.logger.info("consumer_stopped")

    def get_stats(self) -> ConsumerStats:
        """Get consumer statistics"""
        return ConsumerStats(
            total_consumed=self.total_consumed,
            total_written=self.total_written,
            total_failed=self.total_failed,
            total_dlq=self.total_dlq,
            total_vectorization_sent=self.total_vectorization_sent,
            current_batch_size=len(self.batch)
        )


# Global service instance
settings = Settings()
consumer_service: Optional[ClickHouseConsumerService] = None
consumer_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager"""
    global consumer_service, consumer_task

    # Startup
    logger.info("application_starting")

    consumer_service = ClickHouseConsumerService(settings)
    consumer_service.setup_clickhouse()
    consumer_service.setup_kafka()

    # Start consumer
    consumer_task = asyncio.create_task(consumer_service.consume_loop())

    logger.info("application_started")

    yield

    # Shutdown
    logger.info("application_stopping")

    if consumer_service:
        consumer_service.running = False

    if consumer_task:
        await consumer_task

    logger.info("application_stopped")


# FastAPI application
app = FastAPI(
    title="ClickHouse Consumer Service",
    description="Consumes logs from Kafka and writes to ClickHouse",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
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
        status="healthy",
        service="clickhouse-consumer",
        version="1.0.0",
        kafka_connected=consumer_service.consumer is not None,
        clickhouse_connected=consumer_service.ch_client is not None,
        messages_processed=consumer_service.total_written,
        uptime_seconds=uptime
    )


@app.get("/stats", response_model=ConsumerStats)
async def get_stats():
    """Get consumer statistics"""
    if consumer_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    return consumer_service.get_stats()


@app.post("/flush")
async def force_flush():
    """Force flush current batch"""
    if consumer_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    consumer_service.flush_batch()
    return {"status": "flushed", "batch_size": 0}


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
        log_config="debug" #None
    )