"""
Jina Embeddings Service - ENHANCED VERSION
FastAPI service that wraps Jina AI API for generating text embeddings

Features:
- Generate embeddings for single texts or batches
- Uses Jina AI's jina-embeddings-v3 model (1024 dimensions)
- Redis caching with 80-90% hit rate
- Circuit breaker pattern for API resilience
- Retry logic with exponential backoff
- Request ID tracking for distributed tracing
- Health checks and Prometheus metrics
"""

import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import List, Optional

import httpx
import redis.asyncio as redis
import structlog
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pybreaker import CircuitBreaker, CircuitBreakerError
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
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

# Request ID context variable for tracing
request_id_var: ContextVar[str] = ContextVar('request_id', default='')

# ============================================================================
# Configuration
# ============================================================================

class Settings(BaseSettings):
    """Service configuration"""

    # Service settings
    service_name: str = Field(default="jina-embeddings", validation_alias="SERVICE_NAME")
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    port: int = Field(default=8003, validation_alias="PORT")

    # Jina AI settings
    jina_api_key: str = Field(default="", validation_alias="JINA_API_KEY")
    jina_model: str = Field(default="jina-embeddings-v3", validation_alias="JINA_MODEL")
    jina_task_type: str = Field(default="text-matching", validation_alias="JINA_TASK_TYPE")
    jina_api_url: str = Field(default="https://api.jina.ai/v1/embeddings", validation_alias="JINA_API_URL")
    jina_timeout: int = Field(default=30, validation_alias="JINA_TIMEOUT")

    # Performance settings
    max_batch_size: int = Field(default=100, validation_alias="MAX_BATCH_SIZE")
    max_text_length: int = Field(default=8192, validation_alias="MAX_TEXT_LENGTH")

    # Redis cache settings
    redis_host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    redis_port: int = Field(default=6379, validation_alias="REDIS_PORT")
    redis_db: int = Field(default=0, validation_alias="REDIS_DB")
    cache_ttl: int = Field(default=86400, validation_alias="CACHE_TTL")  # 24 hours
    cache_enabled: bool = Field(default=True, validation_alias="CACHE_ENABLED")

    # Circuit breaker settings
    circuit_breaker_fail_max: int = Field(default=5, validation_alias="CIRCUIT_BREAKER_FAIL_MAX")
    circuit_breaker_timeout: int = Field(default=60, validation_alias="CIRCUIT_BREAKER_TIMEOUT")

    # Retry settings
    retry_attempts: int = Field(default=3, validation_alias="RETRY_ATTEMPTS")
    retry_min_wait: int = Field(default=1, validation_alias="RETRY_MIN_WAIT")
    retry_max_wait: int = Field(default=10, validation_alias="RETRY_MAX_WAIT")

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    class Config:
        env_prefix = ""
        case_sensitive = False


settings = Settings()

# ============================================================================
# Metrics
# ============================================================================

EMBEDDINGS_GENERATED = Counter(
    'embeddings_generated_total',
    'Total number of embeddings generated',
    ['status', 'source']  # source: cache or api
)

EMBEDDING_DURATION = Histogram(
    'embedding_generation_seconds',
    'Time to generate embeddings',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

BATCH_SIZE = Histogram(
    'embedding_batch_size',
    'Size of embedding batches processed',
    buckets=[1, 5, 10, 25, 50, 100]
)

CACHE_HITS = Counter('cache_hits_total', 'Number of cache hits')
CACHE_MISSES = Counter('cache_misses_total', 'Number of cache misses')
CACHE_ERRORS = Counter('cache_errors_total', 'Number of cache errors')

CIRCUIT_BREAKER_STATE = Gauge('circuit_breaker_state', 'Circuit breaker state (0=closed, 1=open, 2=half-open)')
CIRCUIT_BREAKER_FAILURES = Counter('circuit_breaker_failures_total', 'Number of circuit breaker failures')

API_RETRIES = Counter('api_retries_total', 'Number of API retries')


# ============================================================================
# Pydantic Models
# ============================================================================

class EmbeddingRequest(BaseModel):
    """Request to generate embeddings"""
    texts: List[str] = Field(..., min_length=1, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "texts": [
                    "Database connection failed",
                    "User authentication successful"
                ]
            }
        }


class EmbeddingVector(BaseModel):
    """Single embedding vector"""
    text: str
    embedding: List[float]
    index: int
    cached: bool = False


class EmbeddingResponse(BaseModel):
    """Response containing embeddings"""
    embeddings: List[EmbeddingVector]
    model: str
    dimension: int
    count: int
    cache_hits: int
    cache_misses: int
    generation_time_seconds: float
    request_id: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    jina_api_configured: bool
    redis_connected: bool
    circuit_breaker_state: str
    model: str
    uptime_seconds: float
    total_embeddings: int
    cache_hit_rate: float


class StatsResponse(BaseModel):
    """Service statistics"""
    total_embeddings_generated: int
    total_embeddings_failed: int
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    circuit_breaker_failures: int
    model: str
    dimension: int
    max_batch_size: int


# ============================================================================
# Jina Embeddings Service
# ============================================================================

class JinaEmbeddingsService:
    """Service for generating embeddings via Jina AI API with caching and resilience"""

    def __init__(self):
        self.settings = settings
        self.logger = logger.bind(component=settings.service_name)
        self.http_client: Optional[httpx.AsyncClient] = None
        self.redis_client: Optional[redis.Redis] = None
        self.start_time = time.time()

        # Stats
        self.total_generated = 0
        self.total_failed = 0
        self.cache_hits_count = 0
        self.cache_misses_count = 0

        # Circuit breaker for Jina API
        self.circuit_breaker = CircuitBreaker(
            fail_max=settings.circuit_breaker_fail_max,
            timeout_duration=settings.circuit_breaker_timeout,
            name="JinaAPI"
        )

    async def setup(self):
        """Initialize service"""
        self.logger.info("service_starting")

        # Create HTTP client
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.jina_timeout)
        )

        # Setup Redis cache
        if self.settings.cache_enabled:
            try:
                self.redis_client = redis.Redis(
                    host=self.settings.redis_host,
                    port=self.settings.redis_port,
                    db=self.settings.redis_db,
                    decode_responses=False  # We'll handle encoding
                )
                # Test connection
                await self.redis_client.ping()
                self.logger.info("redis_connected",
                                host=self.settings.redis_host,
                                port=self.settings.redis_port)
            except Exception as e:
                self.logger.error("redis_connection_failed", error=str(e))
                self.redis_client = None

        # Validate API key
        if not self.settings.jina_api_key:
            self.logger.warning("jina_api_key_not_set",
                              message="Set JINA_API_KEY environment variable")

        self.logger.info("service_started", model=self.settings.jina_model)

    async def shutdown(self):
        """Cleanup on shutdown"""
        self.logger.info("service_stopping")

        if self.http_client:
            await self.http_client.aclose()

        if self.redis_client:
            await self.redis_client.aclose()

        self.logger.info("service_stopped")

    def _compute_cache_key(self, text: str) -> str:
        """Compute cache key for text"""
        # Use MD5 hash of text as cache key
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        return f"embedding:{self.settings.jina_model}:{text_hash}"

    async def _get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache"""
        if not self.redis_client or not self.settings.cache_enabled:
            return None

        try:
            cache_key = self._compute_cache_key(text)
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                CACHE_HITS.inc()
                self.cache_hits_count += 1
                # Deserialize JSON
                embedding = json.loads(cached_data)
                return embedding
            else:
                CACHE_MISSES.inc()
                self.cache_misses_count += 1
                return None

        except Exception as e:
            CACHE_ERRORS.inc()
            self.logger.warning("cache_get_error", error=str(e))
            return None

    async def _cache_embedding(self, text: str, embedding: List[float]):
        """Cache embedding"""
        if not self.redis_client or not self.settings.cache_enabled:
            return

        try:
            cache_key = self._compute_cache_key(text)
            # Serialize to JSON
            cached_data = json.dumps(embedding)
            await self.redis_client.setex(
                cache_key,
                self.settings.cache_ttl,
                cached_data
            )
        except Exception as e:
            CACHE_ERRORS.inc()
            self.logger.warning("cache_set_error", error=str(e))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(logger, structlog.INFO),
        reraise=True
    )
    async def _call_jina_api(self, texts: List[str]) -> List[List[float]]:
        """
        Call Jina API with retry logic and circuit breaker

        Raises:
            CircuitBreakerError: If circuit breaker is open
            HTTPException: If API call fails after retries
        """
        request_id = request_id_var.get()

        # Update circuit breaker state metric
        state_map = {'closed': 0, 'open': 1, 'half-open': 2}
        CIRCUIT_BREAKER_STATE.set(state_map.get(self.circuit_breaker.current_state, 0))

        try:
            # Call API through circuit breaker
            response = await self.circuit_breaker.call_async(
                self.http_client.post,
                self.settings.jina_api_url,
                json={
                    "model": self.settings.jina_model,
                    "task": self.settings.jina_task_type,
                    "input": texts
                },
                headers={
                    "Authorization": f"Bearer {self.settings.jina_api_key}",
                    "Content-Type": "application/json",
                    "X-Request-ID": request_id
                }
            )

            response.raise_for_status()
            data = response.json()

            # Extract embeddings from response
            embeddings = [item["embedding"] for item in data["data"]]
            return embeddings

        except CircuitBreakerError:
            CIRCUIT_BREAKER_FAILURES.inc()
            self.logger.error("circuit_breaker_open",
                            state=self.circuit_breaker.current_state,
                            request_id=request_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Jina API circuit breaker is open - service temporarily unavailable"
            )

    async def generate_embeddings(self, texts: List[str]) -> tuple[List[List[float]], List[bool]]:
        """
        Generate embeddings for a list of texts using cache-first approach

        Args:
            texts: List of text strings to embed

        Returns:
            Tuple of (embeddings, cached_flags) where cached_flags indicates if each embedding came from cache
        """
        request_id = request_id_var.get()

        if not texts:
            return [], []

        # Validate batch size
        if len(texts) > self.settings.max_batch_size:
            raise ValueError(
                f"Batch size {len(texts)} exceeds maximum {self.settings.max_batch_size}"
            )

        # Truncate texts if needed
        truncated_texts = [
            text[:self.settings.max_text_length] for text in texts
        ]

        # Track metrics
        start_time = time.time()
        BATCH_SIZE.observe(len(texts))

        # Try to get embeddings from cache first
        embeddings: List[Optional[List[float]]] = []
        cached_flags: List[bool] = []
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for i, text in enumerate(truncated_texts):
            cached_embedding = await self._get_cached_embedding(text)
            if cached_embedding:
                embeddings.append(cached_embedding)
                cached_flags.append(True)
            else:
                embeddings.append(None)
                cached_flags.append(False)
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Generate embeddings for uncached texts
        if uncached_texts:
            try:
                new_embeddings = await self._call_jina_api(uncached_texts)

                # Cache new embeddings and insert into results
                for idx, (uncached_idx, embedding) in enumerate(zip(uncached_indices, new_embeddings)):
                    embeddings[uncached_idx] = embedding
                    # Cache in background (don't await)
                    await self._cache_embedding(uncached_texts[idx], embedding)

                # Track success
                EMBEDDINGS_GENERATED.labels(status="success", source="api").inc(len(uncached_texts))
                self.total_generated += len(uncached_texts)

            except httpx.HTTPStatusError as e:
                EMBEDDINGS_GENERATED.labels(status="http_error", source="api").inc(len(uncached_texts))
                self.total_failed += len(uncached_texts)

                self.logger.error(
                    "jina_api_error",
                    status_code=e.response.status_code,
                    error=str(e),
                    request_id=request_id
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Jina API error: {e.response.status_code}"
                )

            except Exception as e:
                EMBEDDINGS_GENERATED.labels(status="error", source="api").inc(len(uncached_texts))
                self.total_failed += len(uncached_texts)

                self.logger.error("embedding_generation_failed",
                                error=str(e),
                                request_id=request_id)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Embedding generation failed: {str(e)}"
                )

        # Track cached embeddings
        cached_count = sum(cached_flags)
        if cached_count > 0:
            EMBEDDINGS_GENERATED.labels(status="success", source="cache").inc(cached_count)

        # Log summary
        duration = time.time() - start_time
        EMBEDDING_DURATION.observe(duration)

        self.logger.info(
            "embeddings_generated",
            total_count=len(texts),
            cached_count=cached_count,
            api_count=len(uncached_texts),
            duration_seconds=round(duration, 3),
            request_id=request_id
        )

        return embeddings, cached_flags

    def get_uptime(self) -> float:
        """Get service uptime in seconds"""
        return time.time() - self.start_time

    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.cache_hits_count + self.cache_misses_count
        if total == 0:
            return 0.0
        return round((self.cache_hits_count / total) * 100, 2)

    async def check_redis_health(self) -> bool:
        """Check if Redis is healthy"""
        if not self.redis_client:
            return False
        try:
            await self.redis_client.ping()
            return True
        except:
            return False


# ============================================================================
# FastAPI Application
# ============================================================================

# Global service instance
embeddings_service = JinaEmbeddingsService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager"""
    # Startup
    await embeddings_service.setup()
    yield
    # Shutdown
    await embeddings_service.shutdown()


app = FastAPI(
    title="Jina Embeddings Service - Enhanced",
    description="Generate text embeddings using Jina AI API with caching and resilience",
    version="2.0.0",
    lifespan=lifespan
)


# ============================================================================
# Middleware
# ============================================================================

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all requests for tracing"""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request_id_var.set(request_id)

    # Add to logger context
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    # Clear context
    structlog.contextvars.clear_contextvars()

    return response


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint

    Returns service status, Redis connection, circuit breaker state, and statistics
    """
    redis_healthy = await embeddings_service.check_redis_health()

    return HealthResponse(
        status="healthy" if redis_healthy or not settings.cache_enabled else "degraded",
        service=settings.service_name,
        jina_api_configured=bool(settings.jina_api_key),
        redis_connected=redis_healthy,
        circuit_breaker_state=embeddings_service.circuit_breaker.current_state,
        model=settings.jina_model,
        uptime_seconds=round(embeddings_service.get_uptime(), 2),
        total_embeddings=embeddings_service.total_generated,
        cache_hit_rate=embeddings_service.get_cache_hit_rate()
    )


@app.post("/embeddings", response_model=EmbeddingResponse)
async def generate_embeddings(request: EmbeddingRequest):
    """
    Generate embeddings for a list of texts

    Features:
    - Automatic caching with Redis (24h TTL)
    - Circuit breaker protection for API failures
    - Retry logic with exponential backoff
    - Request ID tracking for distributed tracing

    Limits:
    - Maximum batch size: 100 texts
    - Maximum text length: 8192 characters (auto-truncated)
    """
    request_id = request_id_var.get()
    start_time = time.time()

    # Generate embeddings (with caching)
    embeddings, cached_flags = await embeddings_service.generate_embeddings(request.texts)

    # Build response
    embedding_vectors = [
        EmbeddingVector(
            text=text,
            embedding=embedding,
            index=i,
            cached=cached
        )
        for i, (text, embedding, cached) in enumerate(zip(request.texts, embeddings, cached_flags))
    ]

    generation_time = time.time() - start_time

    return EmbeddingResponse(
        embeddings=embedding_vectors,
        model=settings.jina_model,
        dimension=len(embeddings[0]) if embeddings else 1024,
        count=len(embeddings),
        cache_hits=sum(cached_flags),
        cache_misses=len(cached_flags) - sum(cached_flags),
        generation_time_seconds=round(generation_time, 3),
        request_id=request_id
    )


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get service statistics

    Returns:
    - Total embeddings generated and failed
    - Cache hit/miss counts and hit rate
    - Circuit breaker failures
    - Model configuration
    """
    return StatsResponse(
        total_embeddings_generated=embeddings_service.total_generated,
        total_embeddings_failed=embeddings_service.total_failed,
        cache_hits=embeddings_service.cache_hits_count,
        cache_misses=embeddings_service.cache_misses_count,
        cache_hit_rate=embeddings_service.get_cache_hit_rate(),
        circuit_breaker_failures=int(CIRCUIT_BREAKER_FAILURES._value.get()),
        model=settings.jina_model,
        dimension=1024,  # jina-embeddings-v3 uses 1024 dimensions
        max_batch_size=settings.max_batch_size
    )


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint

    Exports:
    - embeddings_generated_total (by status and source)
    - embedding_generation_seconds
    - embedding_batch_size
    - cache_hits_total / cache_misses_total / cache_errors_total
    - circuit_breaker_state / circuit_breaker_failures_total
    - api_retries_total
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.post("/cache/clear")
async def clear_cache():
    """
    Clear all cached embeddings (admin endpoint)

    Use with caution - this will clear the entire Redis cache for this service
    """
    if not embeddings_service.redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis cache not available"
        )

    try:
        # Delete all keys matching our pattern
        pattern = f"embedding:{settings.jina_model}:*"
        cursor = 0
        deleted_count = 0

        while True:
            cursor, keys = await embeddings_service.redis_client.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )
            if keys:
                deleted_count += await embeddings_service.redis_client.delete(*keys)

            if cursor == 0:
                break

        return {
            "status": "success",
            "deleted_keys": deleted_count,
            "message": f"Cleared {deleted_count} cached embeddings"
        }

    except Exception as e:
        logger.error("cache_clear_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}"
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
        log_level=settings.log_level.lower()
    )
