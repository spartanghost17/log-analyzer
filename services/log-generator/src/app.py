"""
Log Generator Service
Generates realistic application logs and produces them to Kafka
Uses FastAPI for control API and Confluent Kafka for production
Enhanced with Faker for realistic data generation
"""

import asyncio
import json
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict

from confluent_kafka import Producer, KafkaException
from faker import Faker
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Gauge, generate_latest
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings

from settings import setup_development_logging, get_logger

setup_development_logging()
logger = get_logger(__name__)

# Initialize Faker
fake = Faker()

# Prometheus metrics
LOGS_GENERATED = Counter('logs_generated_total', 'Total logs generated')
LOGS_SENT = Counter('logs_sent_total', 'Total logs sent to Kafka')
LOGS_FAILED = Counter('logs_send_failed_total', 'Total logs failed to send')
GENERATION_RATE = Gauge('generation_rate_per_second', 'Current generation rate')
ERROR_RATE = Gauge('error_log_rate_percentage', 'Current error rate percentage')


class LogLevel(str, Enum):
    """Log severity levels"""
    TRACE = "TRACE"
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

    # Generation settings
    log_rate_per_second: int = Field(default=50, ge=1, le=10000, validation_alias="LOG_RATE_PER_SECOND")
    error_rate_percentage: int = Field(default=5, ge=0, le=100, validation_alias="ERROR_RATE_PERCENTAGE")
    services: str = Field(default="api-gateway,user-service,payment-service,notification-service,auth-service", validation_alias="SERVICES")

    # Historical data generation settings
    historical_mode: bool = Field(default=False, validation_alias="HISTORICAL_MODE")
    historical_start_date: str = Field(default="01/12/2024", validation_alias="HISTORICAL_START_DATE")  # DD/MM/YYYY
    historical_end_date: str = Field(default="15/12/2024", validation_alias="HISTORICAL_END_DATE")      # DD/MM/YYYY
    
    # Anomaly injection settings (format: "day_of_week-hour,day_of_week-hour" e.g., "1-3,1-15,5-21")
    # day_of_week: 1=Monday, 7=Sunday; hour: 0-23
    anomaly_schedule: str = Field(default="", validation_alias="ANOMALY_SCHEDULE")
    anomaly_multiplier_min: float = Field(default=3.0, ge=1.0, le=20.0, validation_alias="ANOMALY_MULTIPLIER_MIN")
    anomaly_multiplier_max: float = Field(default=8.0, ge=1.0, le=20.0, validation_alias="ANOMALY_MULTIPLIER_MAX")

    # API settings
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")

    # class Config:
    #     env_prefix = ""
    #     case_sensitive = False


class LogEntry(BaseModel):
    """Enhanced log entry model matching ClickHouse schema"""
    # Core fields
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Service identification
    service: str
    environment: str = "production"
    host: Optional[str] = None
    pod_name: Optional[str] = None
    container_id: Optional[str] = None

    # Log metadata
    level: LogLevel
    logger_name: Optional[str] = None
    message: str
    stack_trace: Optional[str] = None

    # Distributed tracing
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None

    # Additional context
    thread_name: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None

    # Structured metadata
    labels: Optional[Dict[str, str]] = None
    metadata: Optional[str] = None  # JSON string

    # Source information
    source_type: Optional[str] = None
    source_file: Optional[str] = None
    source_line: Optional[int] = None

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
    historical_mode: bool
    anomaly_hours_configured: int


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

        # Parse anomaly schedule
        self.anomaly_hours = self._parse_anomaly_schedule(self.settings.anomaly_schedule)
        
        # Parse historical dates
        self.historical_start = None
        self.historical_end = None
        if self.settings.historical_mode:
            self.historical_start = self._parse_date(self.settings.historical_start_date)
            self.historical_end = self._parse_date(self.settings.historical_end_date)
            self.logger.info(
                "historical_mode_enabled",
                start_date=self.historical_start.isoformat(),
                end_date=self.historical_end.isoformat(),
                anomaly_schedule=self.anomaly_hours
            )

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
        
        # Historical generation state
        self.current_historical_time = self.historical_start if self.settings.historical_mode else None

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string in DD/MM/YYYY format"""
        from datetime import datetime
        return datetime.strptime(date_str, "%d/%m/%Y").replace(tzinfo=timezone.utc)
    
    def _parse_anomaly_schedule(self, schedule: str) -> set:
        """
        Parse anomaly schedule string into set of (day_of_week, hour) tuples
        Format: "1-3,1-15,5-21" means Monday-3AM, Monday-3PM, Friday-9PM
        day_of_week: 1=Monday, 7=Sunday (ISO format)
        hour: 0-23
        """
        if not schedule or not schedule.strip():
            return set()
        
        anomaly_hours = set()
        parts = schedule.split(',')
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            try:
                day_str, hour_str = part.split('-')
                day_of_week = int(day_str)
                hour = int(hour_str)
                
                if 1 <= day_of_week <= 7 and 0 <= hour <= 23:
                    anomaly_hours.add((day_of_week, hour))
                else:
                    self.logger.warning(
                        "invalid_anomaly_schedule_entry",
                        entry=part,
                        reason="day_of_week must be 1-7, hour must be 0-23"
                    )
            except (ValueError, IndexError) as e:
                self.logger.warning(
                    "invalid_anomaly_schedule_entry",
                    entry=part,
                    error=str(e)
                )
        
        return anomaly_hours
    
    def _is_anomaly_hour(self, dt: datetime) -> bool:
        """Check if given datetime falls in anomaly schedule"""
        if not self.anomaly_hours:
            return False
        
        # Python datetime: Monday=0, Sunday=6
        # ISO format: Monday=1, Sunday=7
        day_of_week = dt.isoweekday()  # 1-7 (Monday-Sunday)
        hour = dt.hour  # 0-23
        
        return (day_of_week, hour) in self.anomaly_hours
    
    def _get_effective_error_rate(self, dt: datetime) -> int:
        """Get error rate for given datetime, with anomaly multiplier if applicable"""
        base_rate = self.current_error_rate
        
        if self._is_anomaly_hour(dt):
            multiplier = random.uniform(
                self.settings.anomaly_multiplier_min,
                self.settings.anomaly_multiplier_max
            )
            anomaly_rate = int(base_rate * multiplier)
            # Cap at 100%
            anomaly_rate = min(anomaly_rate, 100)
            
            self.logger.debug(
                "anomaly_hour_detected",
                day_of_week=dt.isoweekday(),
                hour=dt.hour,
                base_rate=base_rate,
                multiplier=f"{multiplier:.2f}",
                anomaly_rate=anomaly_rate
            )
            
            return anomaly_rate
        
        return base_rate

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

    def generate_log(self, custom_timestamp: Optional[datetime] = None) -> LogEntry:
        """
        Generate a single enhanced log entry with realistic data
        
        Args:
            custom_timestamp: Optional custom timestamp for historical data generation
        """
        # Use custom timestamp or current time
        log_timestamp = custom_timestamp or datetime.now(timezone.utc)
        
        # Get effective error rate (may be multiplied if anomaly hour)
        effective_error_rate = self._get_effective_error_rate(log_timestamp)
        
        # Determine log level based on effective error rate
        is_error = random.random() * 100 < effective_error_rate

        if is_error:
            level = random.choice([LogLevel.ERROR, LogLevel.WARN, LogLevel.FATAL])
            message_template = random.choice(self.ERROR_MESSAGES)
        else:
            level = random.choice([LogLevel.INFO, LogLevel.DEBUG])
            message_template = random.choice(self.INFO_MESSAGES)

        # Select service
        service = random.choice(self.services)

        # Format message with random values
        message = message_template.format(
            time=random.randint(10, 5000),
            key=f"user:{random.randint(1000, 9999)}",
            user=f"user_{random.randint(1, 1000)}"
        )

        # Generate infrastructure details
        host = fake.hostname()
        pod_name = f"{service}-{fake.slug()}-{random.randint(1, 5)}"
        container_id = fake.sha256()[:12]

        # Generate tracing IDs (70% of requests have traces)
        has_trace = random.random() > 0.3
        trace_id = str(uuid.uuid4()) if has_trace else None
        span_id = fake.sha256()[:16] if has_trace else None
        parent_span_id = fake.sha256()[:16] if has_trace and random.random() > 0.4 else None

        # Generate correlation ID for related requests
        correlation_id = str(uuid.uuid4()) if random.random() > 0.5 else None

        # Generate user context
        user_id = f"user_{random.randint(1, 1000)}" if random.random() > 0.2 else None

        # Generate thread information
        thread_names = ["http-nio-8080-exec-", "async-task-", "kafka-consumer-", "scheduled-"]
        thread_name = f"{random.choice(thread_names)}{random.randint(1, 20)}"

        # Generate logger name based on service
        logger_components = [
            f"com.example.{service.replace('-', '.')}.controller",
            f"com.example.{service.replace('-', '.')}.service",
            f"com.example.{service.replace('-', '.')}.repository",
            f"com.example.{service.replace('-', '.')}.config",
            f"org.springframework.web",
            f"org.hibernate.SQL",
        ]
        logger_name = random.choice(logger_components)

        # Generate source code information
        source_files = [
            f"src/main/java/com/example/{service.replace('-', '/')}/controller/ApiController.java",
            f"src/main/java/com/example/{service.replace('-', '/')}/service/BusinessService.java",
            f"src/main/java/com/example/{service.replace('-', '/')}/repository/DataRepository.java",
            f"app/services/{service.replace('-', '_')}/main.py",
            f"app/api/{service.replace('-', '_')}/routes.py",
        ]
        source_file = random.choice(source_files)
        source_line = random.randint(10, 500)
        source_type = "application"

        # Generate labels (key-value pairs)
        labels = {
            "region": random.choice(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]),
            "cluster": random.choice(["prod-cluster-1", "prod-cluster-2", "prod-cluster-3"]),
            "version": f"v{random.randint(1, 3)}.{random.randint(0, 20)}.{random.randint(0, 10)}",
            "deployment": random.choice(["blue", "green"]),
        }

        # Generate metadata (contextual information)
        metadata_dict = {
            "http_method": random.choice(["GET", "POST", "PUT", "DELETE", "PATCH"]),
            "endpoint": f"/api/v1/{random.choice(['users', 'orders', 'products', 'payments'])}",
            "status_code": random.choice([200, 201, 400, 401, 403, 404, 500, 503]),
            "client_ip": fake.ipv4(),
            "user_agent": fake.user_agent(),
            "duration_ms": random.randint(5, 2000),
        }
        metadata = json.dumps(metadata_dict)

        # Create enhanced log entry
        log = LogEntry(
            timestamp=log_timestamp.isoformat(),  # Use custom or current timestamp
            service=service,
            environment="production",
            host=host,
            pod_name=pod_name,
            container_id=container_id,
            level=level,
            logger_name=logger_name,
            message=message,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            thread_name=thread_name,
            user_id=user_id,
            request_id=str(uuid.uuid4()),
            correlation_id=correlation_id,
            labels=labels,
            metadata=metadata,
            source_type=source_type,
            source_file=source_file,
            source_line=source_line,
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
        """Main log generation loop (real-time or historical)"""
        self.running = True
        
        if self.settings.historical_mode:
            await self._historical_generation_loop()
        else:
            await self._realtime_generation_loop()
        
        # Flush remaining messages
        if self.producer:
            self.producer.flush()

        self.logger.info("generation_stopped")
    
    async def _realtime_generation_loop(self):
        """Real-time log generation loop"""
        self.logger.info(
            "realtime_generation_started",
            rate=self.current_rate,
            error_rate=self.current_error_rate
        )

        while self.running:
            try:
                # Calculate delay between logs
                delay = 1.0 / self.current_rate

                # Generate and produce log (with current timestamp)
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
    
    async def _historical_generation_loop(self):
        """Historical data generation loop - generates logs sequentially through time"""
        from datetime import timedelta
        
        self.logger.info(
            "historical_generation_started",
            start_date=self.historical_start.isoformat(),
            end_date=self.historical_end.isoformat(),
            rate=self.current_rate,
            base_error_rate=self.current_error_rate,
            anomaly_hours=len(self.anomaly_hours)
        )
        
        current_time = self.historical_start
        time_increment = timedelta(seconds=1.0 / self.current_rate)
        logs_in_current_hour = 0
        current_hour = current_time.replace(minute=0, second=0, microsecond=0)
        
        while self.running and current_time <= self.historical_end:
            try:
                # Generate log with historical timestamp
                log = self.generate_log(custom_timestamp=current_time)
                self.produce_log(log)
                
                # Track progress
                logs_in_current_hour += 1
                
                # Move time forward
                current_time += time_increment
                
                # Log progress every hour
                new_hour = current_time.replace(minute=0, second=0, microsecond=0)
                if new_hour != current_hour:
                    is_anomaly = self._is_anomaly_hour(current_hour)
                    self.logger.info(
                        "historical_hour_completed",
                        hour=current_hour.isoformat(),
                        logs_generated=logs_in_current_hour,
                        is_anomaly_hour=is_anomaly,
                        progress_pct=f"{((current_time - self.historical_start).total_seconds() / (self.historical_end - self.historical_start).total_seconds() * 100):.1f}%"
                    )
                    current_hour = new_hour
                    logs_in_current_hour = 0
                
                # Small delay every 100 logs to prevent overwhelming Kafka
                if self.total_generated % 100 == 0:
                    await asyncio.sleep(0.01)
                
                # Update metrics
                GENERATION_RATE.set(self.current_rate)
                ERROR_RATE.set(self.current_error_rate)

            except Exception as e:
                self.logger.error("historical_generation_error", error=str(e))
                await asyncio.sleep(1)
        
        self.logger.info(
            "historical_generation_completed",
            total_logs=self.total_generated,
            start_date=self.historical_start.isoformat(),
            end_date=self.historical_end.isoformat()
        )
        
        # Stop after historical generation completes
        self.running = False

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
        uptime_seconds=uptime,
        historical_mode=generator_service.settings.historical_mode,
        anomaly_hours_configured=len(generator_service.anomaly_hours)
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
        log_config="info"#None
    )