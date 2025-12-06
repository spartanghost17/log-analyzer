"""
Log Generator Service
Generates realistic application logs and produces them to Kafka
Uses FastAPI for control API and Confluent Kafka for production
"""

import asyncio
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from confluent_kafka import Producer, KafkaException
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Gauge, generate_latest
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Prometheus metrics
LOGS_GENERATED = Counter('logs_generated_total', 'Total logs generated')
LOGS_SENT = Counter('logs_sent_total', 'Total logs sent to Kafka')
LOGS_FAILED = Counter('logs_send_failed_total', 'Total logs failed to send')
GENERATION_RATE = Gauge('generation_rate_per_second', 'Current generation rate')
ERROR_RATE = Gauge('error_log_rate_percentage', 'Current error rate percentage')


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
    kafka_bootstrap_servers: str = Field(default="localhost:9092")
    kafka_topic: str = Field(default="raw-logs")

    # Generation settings
    log_rate_per_second: int = Field(default=50, ge=1, le=10000)
    error_rate_percentage: int = Field(default=5, ge=0, le=100)
    services: str = Field(default="api-gateway,user-service,payment-service,notification-service,auth-service")

    # API settings
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    class Config:
        env_prefix = ""
        case_sensitive = False


class LogEntry(BaseModel):
    """Log entry model"""
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    service: str
    environment: str = "production"
    level: LogLevel
    message: str
    trace_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    stack_trace: Optional[str] = None

    class Config:
        use_enum_values = True


class GeneratorControl(BaseModel):
    """Generator control parameters"""
    rate_per_second: int = Field(..., ge=1, le=10000)
    error_rate_percentage: int = Field(..., ge=0, le=100)

    @field_validator('rate_per_second')
    @classmethod
    def validate_rate(cls, v: int) -> int:
        if v < 1 or v > 10000:
            raise ValueError("Rate must be between 1 and 10000")
        return v

    @field_validator('error_rate_percentage')
    @classmethod
    def validate_error_rate(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError("Error rate must be between 0 and 100")
        return v


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    kafka_connected: bool
    is_generating: bool
    logs_generated: int
    logs_sent: int
    current_rate: int
    uptime_seconds: float


class GeneratorStats(BaseModel):
    """Generator statistics"""
    total_generated: int
    total_sent: int
    total_failed: int
    current_rate: int
    error_rate: int
    is_running: bool


class LogGeneratorService:
    """Log generator service with Kafka producer"""

    # Realistic log messages
    INFO_MESSAGES = [
        "Request processed successfully",
        "User authentication successful",
        "Database query completed in {time}ms",
        "Cache hit for key: {key}",
        "API response time: {time}ms",
        "Background job completed",
        "Session created for user {user}",
        "Payment processed successfully",
        "Email notification sent",
        "File uploaded successfully"
    ]

    ERROR_MESSAGES = [
        "Connection timeout to database after {time}ms",
        "Failed to authenticate user: invalid credentials",
        "Payment processing failed: insufficient funds",
        "Database query timeout after {time}ms",
        "External API returned 500 error",
        "Failed to send email notification",
        "File upload failed: size limit exceeded",
        "Redis connection lost",
        "Failed to acquire database lock",
        "Rate limit exceeded for user {user}"
    ]

    STACK_TRACES = [
        """Traceback (most recent call last):
  File "app/services/database.py", line 45, in execute_query
    result = await conn.execute(query)
  File "lib/asyncpg/connection.py", line 123, in execute
    raise TimeoutError("Query timeout")
asyncpg.exceptions.QueryTimeout: timeout after 5000ms""",
        """Traceback (most recent call last):
  File "app/api/payment.py", line 78, in process_payment
    response = await payment_gateway.charge(amount)
  File "lib/payment/client.py", line 56, in charge
    raise PaymentError("Insufficient funds")
app.exceptions.PaymentError: Insufficient funds in account""",
        """Traceback (most recent call last):
  File "app/services/cache.py", line 34, in get
    return await redis.get(key)
  File "lib/redis/client.py", line 89, in get
    raise ConnectionError("Connection refused")
redis.exceptions.ConnectionError: Error connecting to Redis"""
    ]

    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = logger.bind(component="log-generator")

        # Parse services
        self.services = [s.strip() for s in self.settings.services.split(',')]

        # Kafka producer
        self.producer: Optional[Producer] = None

        # State
        self.running = False
        self.total_generated = 0
        self.total_sent = 0
        self.total_failed = 0
        self.start_time = time.time()

        # Current settings
        self.current_rate = self.settings.log_rate_per_second
        self.current_error_rate = self.settings.error_rate_percentage

    def setup_kafka(self):
        """Setup Kafka producer"""
        try:
            producer_config = {
                'bootstrap.servers': self.settings.kafka_bootstrap_servers,
                'client.id': 'log-generator',
                'acks': 'all',
                'retries': 3,
                'compression.type': 'snappy',
            }

            self.producer = Producer(producer_config)

            self.logger.info(
                "kafka_producer_created",
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                topic=self.settings.kafka_topic
            )

        except KafkaException as e:
            self.logger.error("kafka_producer_creation_failed", error=str(e))
            raise

    def delivery_callback(self, err, msg):
        """Callback for Kafka delivery reports"""
        if err is not None:
            self.total_failed += 1
            LOGS_FAILED.inc()
            self.logger.error(
                "kafka_delivery_failed",
                error=str(err),
                topic=msg.topic()
            )
        else:
            self.total_sent += 1
            LOGS_SENT.inc()

    def generate_log(self) -> LogEntry:
        """Generate a single log entry"""
        # Determine log level based on error rate
        is_error = random.random() * 100 < self.current_error_rate

        if is_error:
            level = random.choice([LogLevel.ERROR, LogLevel.WARN, LogLevel.FATAL])
            message_template = random.choice(self.ERROR_MESSAGES)
        else:
            level = random.choice([LogLevel.INFO, LogLevel.DEBUG])
            message_template = random.choice(self.INFO_MESSAGES)

        # Format message with random values
        message = message_template.format(
            time=random.randint(10, 5000),
            key=f"user:{random.randint(1000, 9999)}",
            user=f"user_{random.randint(1, 1000)}"
        )

        # Create log entry
        log = LogEntry(
            service=random.choice(self.services),
            level=level,
            message=message,
            trace_id=str(uuid.uuid4()) if random.random() > 0.5 else None,
            user_id=f"user_{random.randint(1, 1000)}" if random.random() > 0.3 else None,
            request_id=str(uuid.uuid4())
        )

        # Add stack trace for ERROR and FATAL
        if level in [LogLevel.ERROR, LogLevel.FATAL]:
            if random.random() > 0.5:
                log.stack_trace = random.choice(self.STACK_TRACES)

        return log

    def produce_log(self, log: LogEntry):
        """Produce log to Kafka"""
        try:
            # Serialize to JSON
            log_json = log.model_dump_json()

            # Produce to Kafka
            self.producer.produce(
                topic=self.settings.kafka_topic,
                value=log_json.encode('utf-8'),
                callback=self.delivery_callback
            )

            # Poll to handle callbacks (non-blocking)
            self.producer.poll(0)

            self.total_generated += 1
            LOGS_GENERATED.inc()

        except Exception as e:
            self.logger.error("log_production_failed", error=str(e))
            self.total_failed += 1
            LOGS_FAILED.inc()

    async def generation_loop(self):
        """Main log generation loop"""
        self.running = True
        self.logger.info(
            "generation_started",
            rate=self.current_rate,
            error_rate=self.current_error_rate
        )

        while self.running:
            try:
                # Calculate delay between logs
                delay = 1.0 / self.current_rate

                # Generate and produce log
                log = self.generate_log()
                self.produce_log(log)

                # Update metrics
                GENERATION_RATE.set(self.current_rate)
                ERROR_RATE.set(self.current_error_rate)

                # Wait before next log
                await asyncio.sleep(delay)

            except Exception as e:
                self.logger.error("generation_loop_error", error=str(e))
                await asyncio.sleep(1)

        # Flush remaining messages
        if self.producer:
            self.producer.flush()

        self.logger.info("generation_stopped")

    def start(self):
        """Start log generation"""
        if not self.running:
            self.running = True
            return True
        return False

    def stop(self):
        """Stop log generation"""
        if self.running:
            self.running = False
            if self.producer:
                self.producer.flush()
            return True
        return False

    def update_settings(self, rate: int, error_rate: int):
        """Update generation settings"""
        self.current_rate = rate
        self.current_error_rate = error_rate

        self.logger.info(
            "settings_updated",
            rate=rate,
            error_rate=error_rate
        )

    def get_stats(self) -> GeneratorStats:
        """Get generator statistics"""
        return GeneratorStats(
            total_generated=self.total_generated,
            total_sent=self.total_sent,
            total_failed=self.total_failed,
            current_rate=self.current_rate,
            error_rate=self.current_error_rate,
            is_running=self.running
        )


# Global service instance
settings = Settings()
generator_service: Optional[LogGeneratorService] = None
generation_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager"""
    global generator_service, generation_task

    # Startup
    logger.info("application_starting")

    generator_service = LogGeneratorService(settings)
    generator_service.setup_kafka()

    # Start generation automatically
    generator_service.start()
    generation_task = asyncio.create_task(generator_service.generation_loop())

    logger.info("application_started")

    yield

    # Shutdown
    logger.info("application_stopping")

    if generator_service:
        generator_service.stop()

    if generation_task:
        await generation_task

    logger.info("application_stopped")


# FastAPI application
app = FastAPI(
    title="Log Generator Service",
    description="Generates realistic application logs and produces to Kafka",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    if generator_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    uptime = time.time() - generator_service.start_time

    return HealthResponse(
        status="healthy",
        service="log-generator",
        version="1.0.0",
        kafka_connected=generator_service.producer is not None,
        is_generating=generator_service.running,
        logs_generated=generator_service.total_generated,
        logs_sent=generator_service.total_sent,
        current_rate=generator_service.current_rate,
        uptime_seconds=uptime
    )


@app.get("/stats", response_model=GeneratorStats)
async def get_stats():
    """Get generator statistics"""
    if generator_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    return generator_service.get_stats()


@app.post("/start")
async def start_generation():
    """Start log generation"""
    if generator_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    if generator_service.start():
        global generation_task
        if generation_task is None or generation_task.done():
            generation_task = asyncio.create_task(generator_service.generation_loop())

        return {
            "status": "started",
            "rate": generator_service.current_rate
        }

    return {
        "status": "already_running",
        "rate": generator_service.current_rate
    }


@app.post("/stop")
async def stop_generation():
    """Stop log generation"""
    if generator_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    if generator_service.stop():
        return {"status": "stopped"}

    return {"status": "already_stopped"}


@app.put("/control")
async def update_control(control: GeneratorControl):
    """Update generation parameters"""
    if generator_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    generator_service.update_settings(
        control.rate_per_second,
        control.error_rate_percentage
    )

    return {
        "status": "updated",
        "rate_per_second": control.rate_per_second,
        "error_rate_percentage": control.error_rate_percentage
    }


@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_config=None
    )