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
from datetime import datetime, timezone, timedelta
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

    # Environments to cycle through
    ENVIRONMENTS = ["production", "staging", "development"]

    # Realistic INFO log messages (more detailed and varied)
    INFO_MESSAGES = [
        "Request processed successfully for endpoint /api/v1/users/{user_id} - returned 200 OK in {time}ms",
        "User authentication successful for user {user} via OAuth2 token - session established with TTL 3600s",
        "Database query completed successfully: SELECT * FROM orders WHERE status='pending' LIMIT 100 - execution time: {time}ms",
        "Cache hit for key: {key} - retrieved 2.3KB payload from Redis cluster node redis-prod-02",
        "API response time for GET /api/v1/products: {time}ms - cache hit ratio: 87.3% - served from CDN edge node",
        "Background job 'daily-report-generator' completed successfully - processed 45,892 records in 23.4 seconds",
        "Session created for user {user} with IP 192.168.1.{ip} - device fingerprint: {fingerprint}",
        "Payment transaction processed successfully - amount: ${amount} USD - gateway: Stripe - transaction_id: {tx_id}",
        "Email notification sent to {email} via SendGrid - template: 'order-confirmation' - delivery confirmed in 1.2s",
        "File uploaded successfully to S3 bucket 'prod-user-uploads' - file: {filename} - size: {size}MB - ETag: {etag}",
        "WebSocket connection established from client {client_id} - protocol: ws:// - heartbeat interval: 30s",
        "Message published to Kafka topic 'user-events' - partition: 3 - offset: 891234 - key: {key}",
        "Service health check passed - all dependencies responding - latency: DB={db_latency}ms, Redis={redis_latency}ms",
        "Rate limiter check passed for user {user} - current: 47/1000 requests - window: 60s - burst allowed",
        "Scheduled task 'cleanup-old-sessions' executed - removed 234 expired sessions - next run in 3600s",
        "JWT token validated successfully - issuer: auth.example.com - expiry: 2h - scopes: ['read', 'write']",
        "GraphQL query resolved in {time}ms - query depth: 4 - fields: 23 - resolver cache hits: 18/23",
        "gRPC call completed successfully - method: /user.UserService/GetProfile - duration: {time}ms - status: OK",
        "CircuitBreaker state transition: CLOSED -> CLOSED - success rate: 99.2% - error threshold: 50%",
        "Distributed lock acquired for resource 'payment-processor-lock' - holder: pod-{pod} - TTL: 30s"
    ]

    # Realistic ERROR log messages with context
    ERROR_MESSAGES = [
        ("Connection timeout to PostgreSQL database after {time}ms - host: db-prod-01.internal:5432 - connection pool exhausted (50/50 connections in use)", "db_timeout"),
        ("Failed to authenticate user: invalid credentials provided - username: {user} - attempt 3/3 - account locked for 15 minutes", "auth_failed"),
        ("Payment processing failed: insufficient funds in account - requested: ${amount} USD - available: ${available} USD - gateway response: declined", "payment_insufficient_funds"),
        ("Database query timeout after {time}ms - query: SELECT * FROM transactions WHERE date > '2024-01-01' - affected table: transactions (2.3M rows) - lock wait timeout exceeded", "db_lock_timeout"),
        ("External API call to payment-gateway.example.com failed - HTTP 500 Internal Server Error - response time: {time}ms - retries exhausted (3/3)", "external_api_error"),
        ("Failed to send email notification via SendGrid API - recipient: {email} - error: 'Invalid API key' - status: 401 Unauthorized", "email_send_failed"),
        ("File upload rejected: size limit exceeded - uploaded: {size}MB - max allowed: 10MB - filename: {filename}", "file_size_exceeded"),
        ("Redis connection lost to redis-prod-cluster.internal:6379 - error: 'Connection refused' - failover to replica node failed - cache unavailable", "redis_connection_lost"),
        ("Failed to acquire database lock for table 'inventory' - lock holder: transaction_id={tx_id} - wait time exceeded: 30s - deadlock detected", "db_lock_failed"),
        ("Rate limit exceeded for API key: {key} - current: 1001/1000 requests - window: 60s - client IP: 203.0.113.{ip}", "rate_limit_exceeded"),
        ("Kafka consumer group rebalancing failed - topic: 'order-events' - error: 'Group coordinator not available' - retrying in 5s", "kafka_rebalance_failed"),
        ("S3 bucket operation failed - operation: PutObject - bucket: 'prod-uploads' - error: 'Access Denied' - IAM role: 'app-service-role'", "s3_access_denied"),
        ("JWT token validation failed - token expired at {timestamp} - issued at: {issued_at} - current time: {current_time} - delta: {delta}s", "jwt_expired"),
        ("Circuit breaker opened for service 'payment-service' - failure rate: 67.3% (67/100 requests) - timeout: 60s - fallback activated", "circuit_breaker_open"),
        ("Database migration failed - version: 2024.12.15.001 - error executing SQL: duplicate key violation - constraint: 'users_email_key'", "migration_failed"),
        ("WebSocket connection closed unexpectedly - client_id: {client_id} - reason: 'Ping timeout' - duration: 45s - reconnection attempt 3/5", "websocket_closed"),
        ("Memory allocation failed in worker process pid={pid} - requested: 512MB - available: 128MB - OOMKiller may intervene", "memory_allocation_failed"),
        ("ElasticSearch query failed - index: 'logs-2024.12' - error: 'SearchPhaseExecutionException' - shard failures: 3/5 - query: {query}", "elasticsearch_query_failed"),
        ("Message queue full - queue: 'background-jobs' - current size: 10000/10000 - oldest message age: 3600s - consumers lagging", "queue_full"),
        ("SSL/TLS handshake failed with upstream service - host: api.partner.com:443 - error: 'certificate has expired' - expiry date: {expiry_date}", "tls_handshake_failed")
    ]

    # Detailed stack traces mapped to error types
    STACK_TRACES = {
        "db_timeout": """Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/engine/base.py", line 1900, in _execute_context
    self.dialect.do_execute(
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/engine/default.py", line 736, in do_execute
    cursor.execute(statement, parameters)
  File "/usr/local/lib/python3.11/site-packages/psycopg2/extras.py", line 145, in execute
    return super().execute(query, vars)
  File "/usr/local/lib/python3.11/site-packages/psycopg2/extensions.py", line 234, in execute
    return cursor.execute(query, vars)
psycopg2.errors.QueryCanceled: canceling statement due to statement timeout
[SQL: SELECT transactions.id, transactions.user_id, transactions.amount, transactions.status, transactions.created_at FROM transactions WHERE transactions.date > '2024-01-01' ORDER BY transactions.created_at DESC]
(Background on this error at: https://sqlalche.me/e/14/e3q8)""",

        "auth_failed": """Traceback (most recent call last):
  File "/app/api/auth.py", line 156, in authenticate_user
    user = await user_service.get_by_username(username)
  File "/app/services/user_service.py", line 78, in get_by_username
    if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
  File "/usr/local/lib/python3.11/site-packages/bcrypt/__init__.py", line 120, in checkpw
    raise ValueError("Invalid salt")
bcrypt.InvalidSaltError: Invalid password hash format
  File "/app/api/auth.py", line 162, in authenticate_user
    raise AuthenticationError("Invalid credentials")
app.exceptions.AuthenticationError: Failed to authenticate user: invalid credentials provided""",

        "payment_insufficient_funds": """Traceback (most recent call last):
  File "/app/api/payment.py", line 234, in process_payment
    response = await payment_gateway.charge(
        amount=payment_request.amount,
        currency=payment_request.currency,
        source=payment_request.source
    )
  File "/app/services/payment_gateway.py", line 145, in charge
    result = await self._make_api_call('POST', '/v1/charges', payload)
  File "/app/services/payment_gateway.py", line 89, in _make_api_call
    raise PaymentGatewayError(error_data['message'], code=error_data['code'])
app.exceptions.PaymentGatewayError: insufficient_funds - The card has insufficient funds to complete the purchase
    Requested: $299.99 USD
    Available: $45.23 USD
    Card: **** **** **** 4242
    Decline code: insufficient_funds""",

        "db_lock_timeout": """Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/pool/base.py", line 702, in _finalize_fairy
    fairy._reset(pool)
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/pool/base.py", line 943, in _reset
    pool._dialect.do_rollback(self.dbapi_connection)
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/postgresql/psycopg2.py", line 789, in do_rollback
    dbapi_connection.rollback()
psycopg2.errors.LockNotAvailable: could not obtain lock on relation "inventory"
DETAIL: Process 12845 waits for ShareLock on transaction 2947382; blocked by process 12823.
HINT: See server log for query details.
CONTEXT: while updating tuple (243, 67) in relation "inventory"
[SQL: UPDATE inventory SET quantity = quantity - 1 WHERE product_id = %s AND quantity > 0]""",

        "external_api_error": """Traceback (most recent call last):
  File "/app/services/external_api_client.py", line 234, in make_request
    async with session.post(url, json=payload, timeout=timeout) as response:
  File "/usr/local/lib/python3.11/site-packages/aiohttp/client.py", line 1141, in __aenter__
    self._resp = await self._coro
  File "/usr/local/lib/python3.11/site-packages/aiohttp/client.py", line 560, in _request
    raise ClientResponseError(
aiohttp.client_exceptions.ClientResponseError: 500, message='Internal Server Error', url=URL('https://api.payment-gateway.example.com/v1/charge')
  File "/app/services/external_api_client.py", line 245, in make_request
    raise ExternalAPIError(f"API call failed: {response.status}")
app.exceptions.ExternalAPIError: External API call to payment-gateway.example.com failed - HTTP 500 Internal Server Error""",

        "email_send_failed": """Traceback (most recent call last):
  File "/app/services/notification_service.py", line 178, in send_email
    response = await sendgrid_client.send(message)
  File "/usr/local/lib/python3.11/site-packages/sendgrid/sendgrid.py", line 89, in send
    return self._make_request(self.client.mail.send.post(request_body=message.get()))
  File "/usr/local/lib/python3.11/site-packages/python_http_client/client.py", line 234, in http_request
    raise HTTPError(response.status_code, response.reason, response.content)
python_http_client.exceptions.UnauthorizedError: HTTP Error 401: Unauthorized
{
  "errors": [
    {
      "message": "The provided authorization grant is invalid, expired, or revoked",
      "field": null,
      "help": "https://sendgrid.com/docs/API_Reference/Web_API_v3/Mail/errors.html#message.authentication"
    }
  ]
}""",

        "file_size_exceeded": """Traceback (most recent call last):
  File "/app/api/upload.py", line 123, in upload_file
    file_size_mb = len(file_content) / (1024 * 1024)
  File "/app/api/upload.py", line 126, in upload_file
    if file_size_mb > self.MAX_FILE_SIZE_MB:
  File "/app/api/upload.py", line 127, in upload_file
    raise FileSizeExceededError(
app.exceptions.FileSizeExceededError: File upload rejected: size limit exceeded
    Uploaded: 25.7MB
    Max allowed: 10MB
    Filename: user_document_large_file.pdf
    Content-Type: application/pdf
    Hint: Consider splitting the file or using chunked upload for files > 10MB""",

        "redis_connection_lost": """Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/redis/connection.py", line 614, in connect
    sock = self._connect()
  File "/usr/local/lib/python3.11/site-packages/redis/connection.py", line 654, in _connect
    raise err
  File "/usr/local/lib/python3.11/site-packages/redis/connection.py", line 642, in _connect
    sock.connect(socket_address)
ConnectionRefusedError: [Errno 111] Connection refused
During handling of the above exception, another exception occurred:
Traceback (most recent call last):
  File "/app/services/cache_service.py", line 89, in get
    value = await self.redis_client.get(key)
  File "/usr/local/lib/python3.11/site-packages/redis/asyncio/client.py", line 1234, in get
    return await self.execute_command('GET', name)
  File "/usr/local/lib/python3.11/site-packages/redis/asyncio/client.py", line 567, in execute_command
    conn = await self.connection_pool.get_connection(command_name)
  File "/usr/local/lib/python3.11/site-packages/redis/asyncio/connection.py", line 245, in get_connection
    await connection.connect()
redis.exceptions.ConnectionError: Error connecting to Redis (redis-prod-cluster.internal:6379). Connection refused.""",

        "db_lock_failed": """Traceback (most recent call last):
  File "/app/services/inventory_service.py", line 234, in reserve_inventory
    async with self.db.begin():
        result = await self.db.execute(
            text("SELECT * FROM inventory WHERE product_id = :product_id FOR UPDATE NOWAIT"),
            {"product_id": product_id}
        )
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/dialects/postgresql/asyncpg.py", line 567, in execute
    result = await self._connection.execute(statement, parameters)
sqlalchemy.exc.OperationalError: (asyncpg.exceptions.LockNotAvailableError) could not obtain lock on row in relation "inventory"
DETAIL: Process 12845 tried to lock row but found it already locked by process 12823.
CONTEXT: SQL statement "UPDATE inventory SET reserved_quantity = reserved_quantity + 1 WHERE product_id = $1"
[SQL: SELECT * FROM inventory WHERE product_id = %(product_id)s FOR UPDATE NOWAIT]
[parameters: {'product_id': 'prod_8f7a3b2c'}]
(Background on this error at: https://sqlalche.me/e/14/e3q8)""",

        "rate_limit_exceeded": """Traceback (most recent call last):
  File "/app/middleware/rate_limiter.py", line 145, in __call__
    await self._check_rate_limit(request)
  File "/app/middleware/rate_limiter.py", line 178, in _check_rate_limit
    current_count = await self.redis.incr(rate_limit_key)
  File "/app/middleware/rate_limiter.py", line 185, in _check_rate_limit
    if current_count > self.max_requests:
  File "/app/middleware/rate_limiter.py", line 186, in _check_rate_limit
    raise RateLimitExceededError(
app.exceptions.RateLimitExceededError: Rate limit exceeded for API key
    Key: api_key_prod_8f7a3b2c4d5e6f7a
    Current: 1001/1000 requests
    Window: 60s
    Reset in: 23s
    Client IP: 203.0.113.42
    Hint: Consider implementing exponential backoff or upgrading to higher tier""",

        "kafka_rebalance_failed": """Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/confluent_kafka/consumer.py", line 234, in subscribe
    self._subscribe_impl(topics, on_assign, on_revoke)
  File "/usr/local/lib/python3.11/site-packages/confluent_kafka/consumer.py", line 456, in _subscribe_impl
    raise KafkaException(kafka_error)
confluent_kafka.KafkaException: KafkaError{code=COORDINATOR_NOT_AVAILABLE,val=15,str="Group coordinator not available: broker may be down or network issues"}
  File "/app/consumers/order_consumer.py", line 89, in start_consuming
    self.consumer.subscribe(['order-events'], on_assign=self.on_partition_assigned)
  File "/app/consumers/order_consumer.py", line 93, in start_consuming
    raise ConsumerError("Failed to subscribe to Kafka topic")
app.exceptions.ConsumerError: Kafka consumer group rebalancing failed - topic: 'order-events' - retrying in 5s""",

        "s3_access_denied": """Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/botocore/endpoint.py", line 281, in _do_get_response
    http_response = self._send(request)
  File "/usr/local/lib/python3.11/site-packages/botocore/endpoint.py", line 377, in _send
    return self.http_session.send(request)
botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the PutObject operation: Access Denied
  File "/app/services/storage_service.py", line 156, in upload_to_s3
    response = await s3_client.put_object(
        Bucket='prod-uploads',
        Key=file_key,
        Body=file_content
    )
  File "/app/services/storage_service.py", line 163, in upload_to_s3
    raise StorageError(f"S3 upload failed: {e}")
app.exceptions.StorageError: S3 bucket operation failed - operation: PutObject - bucket: 'prod-uploads' - IAM role: 'app-service-role'
Hint: Check IAM policy permissions for s3:PutObject action""",

        "jwt_expired": """Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/jose/jwt.py", line 234, in decode
    payload = self._decode_complete(token, key, algorithms, options, audience, issuer, subject)
  File "/usr/local/lib/python3.11/site-packages/jose/jwt.py", line 267, in _decode_complete
    self._validate_claims(payload, options, audience, issuer, subject, leeway)
  File "/usr/local/lib/python3.11/site-packages/jose/jwt.py", line 345, in _validate_claims
    self._validate_exp(payload, leeway)
  File "/usr/local/lib/python3.11/site-packages/jose/jwt.py", line 423, in _validate_exp
    raise ExpiredSignatureError('Signature has expired')
jose.exceptions.ExpiredSignatureError: Signature has expired at 2024-12-15T14:30:45Z
  File "/app/middleware/auth_middleware.py", line 123, in verify_token
    payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
  File "/app/middleware/auth_middleware.py", line 128, in verify_token
    raise AuthenticationError("JWT token expired")
app.exceptions.AuthenticationError: JWT token validation failed - token expired""",

        "circuit_breaker_open": """Traceback (most recent call last):
  File "/app/services/payment_service_client.py", line 234, in call_payment_service
    async with self.circuit_breaker.call():
        response = await self._make_request(endpoint, payload)
  File "/usr/local/lib/python3.11/site-packages/circuitbreaker/breaker.py", line 156, in __aenter__
    if self._state == STATE_OPEN:
  File "/usr/local/lib/python3.11/site-packages/circuitbreaker/breaker.py", line 159, in __aenter__
    raise CircuitBreakerError(f"Circuit breaker is OPEN - failure rate: {self.failure_rate}%")
circuitbreaker.CircuitBreakerError: Circuit breaker is OPEN for service 'payment-service'
    State: OPEN
    Failure rate: 67.3% (67/100 requests failed)
    Threshold: 50%
    Timeout: 60s
    Next retry at: 2024-12-15T14:32:15Z
    Fallback: returning cached response
Hint: Check payment-service health and logs""",

        "migration_failed": """Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/alembic/runtime/migration.py", line 234, in run_migrations
    self.execute_migration(step, is_stamp)
  File "/usr/local/lib/python3.11/site-packages/alembic/runtime/migration.py", line 567, in execute_migration
    self.environment_context.get_context().execute_migration(revision)
  File "/usr/local/lib/python3.11/site-packages/sqlalchemy/engine/base.py", line 1900, in execute
    cursor.execute(statement, parameters)
psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "users_email_key"
DETAIL: Key (email)=(user@example.com) already exists.
[SQL: ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email)]
  File "/app/migrations/versions/2024_12_15_001_add_email_unique.py", line 23, in upgrade
    op.create_unique_constraint('users_email_key', 'users', ['email'])
alembic.util.exc.CommandError: Database migration failed - version: 2024.12.15.001
Hint: Check if constraint already exists or if there are duplicate email values in the table"""
    }

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

        # Variables for error type tracking
        error_type = None
        stack_trace = None

        if is_error:
            level = random.choice([LogLevel.ERROR, LogLevel.WARN, LogLevel.FATAL])
            # ERROR_MESSAGES is now a list of tuples: (message_template, error_type)
            message_template, error_type = random.choice(self.ERROR_MESSAGES)
        else:
            level = random.choice([LogLevel.INFO, LogLevel.DEBUG])
            message_template = random.choice(self.INFO_MESSAGES)

        # Select service and environment
        service = random.choice(self.services)
        environment = random.choice(self.ENVIRONMENTS)

        # Format message with random values
        message = message_template.format(
            time=random.randint(1000, 5000),
            key=f"user:{random.randint(1000, 9999)}",
            user=f"user_{random.randint(100, 999)}",
            amount=random.randint(50, 500),
            available=random.randint(10, 100),
            size=random.randint(11, 50),
            filename=f"{fake.word()}_{fake.word()}.{random.choice(['pdf', 'docx', 'xlsx', 'zip'])}",
            email=fake.email(),
            client_id=f"client_{random.randint(1000, 9999)}",
            tx_id=str(uuid.uuid4())[:8],
            ip=random.randint(1, 255),
            timestamp=log_timestamp.isoformat(),
            issued_at=(log_timestamp.timestamp() - 7200),
            current_time=log_timestamp.timestamp(),
            delta=7200 + random.randint(1, 600),
            pid=random.randint(1000, 9999),
            query=f"status:error AND service:{service}",
            expiry_date=(log_timestamp - timedelta(days=random.randint(1, 30))).strftime('%Y-%m-%d'),
            etag=fake.sha256()[:16],
            db_latency=random.randint(5, 50),
            redis_latency=random.randint(1, 10),
            fingerprint=fake.sha256()[:16],
            pod=random.randint(1, 5),
            user_id=random.randint(1000, 9999)
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
        user_id = f"user_{random.randint(100, 999)}" if random.random() > 0.2 else None

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

        # Add stack trace for ERROR and FATAL (100% of the time with matching error type)
        if level in [LogLevel.ERROR, LogLevel.FATAL]:
            if error_type and error_type in self.STACK_TRACES:
                # Use the matching stack trace for this error type
                stack_trace = self.STACK_TRACES[error_type]
            else:
                # Fallback to a random stack trace if no match found
                stack_trace = random.choice(list(self.STACK_TRACES.values()))

        # Create enhanced log entry
        log = LogEntry(
            timestamp=log_timestamp.isoformat(),  # Use custom or current timestamp
            service=service,
            environment=environment,  # Randomly selected environment
            host=host,
            pod_name=pod_name,
            container_id=container_id,
            level=level,
            logger_name=logger_name,
            message=message,
            stack_trace=stack_trace,  # Always present for ERROR/FATAL
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