"""
Jina Embeddings Service
FastAPI-based service for generating text embeddings using Jina Embeddings v3
Supports Matryoshka dimensions (768 → 256/512) and batch processing
"""

import asyncio
import hashlib
import time
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
from enum import Enum

import numpy as np
import torch
from fastapi import FastAPI, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from transformers import AutoModel, AutoTokenizer
import structlog
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import redis.asyncio as aioredis

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
EMBEDDINGS_GENERATED = Counter('embeddings_generated_total', 'Total embeddings generated')
EMBEDDINGS_CACHED = Counter('embeddings_cached_total', 'Total embeddings served from cache')
EMBEDDING_TIME = Histogram('embedding_generation_seconds', 'Embedding generation time')
BATCH_SIZE_METRIC = Histogram('embedding_batch_size', 'Batch sizes processed')
CACHE_HIT_RATE = Gauge('cache_hit_rate', 'Cache hit rate percentage')


class EmbeddingDimension(int, Enum):
    """Matryoshka embedding dimensions"""
    FULL = 768
    LARGE = 512
    MEDIUM = 384
    SMALL = 256


class Settings(BaseSettings):
    """Application settings"""
    # Model settings
    model_name: str = Field(default="jinaai/jina-embeddings-v3")
    model_cache_dir: str = Field(default="/models")
    device: str = Field(default="cpu")  # or "cuda" if GPU available
    max_length: int = Field(default=8192)

    # Redis cache settings
    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    cache_ttl_seconds: int = Field(default=86400)  # 24 hours
    enable_cache: bool = Field(default=True)

    # Processing settings
    batch_size: int = Field(default=32, ge=1, le=128)
    default_dimension: int = Field(default=512)

    # API settings
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8003)

    class Config:
        env_prefix = "JINA_"
        case_sensitive = False


# Pydantic Models
class EmbeddingRequest(BaseModel):
    """Request for single embedding"""
    text: str = Field(..., min_length=1, max_length=10000)
    dimension: Optional[int] = Field(default=512, ge=256, le=768)
    task: str = Field(default="text-matching")
    normalize: bool = Field(default=True)

    @field_validator('dimension')
    @classmethod
    def validate_dimension(cls, v: int) -> int:
        """Validate dimension is supported"""
        valid_dims = [256, 384, 512, 768]
        if v not in valid_dims:
            raise ValueError(f"Dimension must be one of {valid_dims}")
        return v


class BatchEmbeddingRequest(BaseModel):
    """Request for batch embeddings"""
    texts: List[str] = Field(..., min_length=1, max_length=100)
    dimension: Optional[int] = Field(default=512, ge=256, le=768)
    task: str = Field(default="text-matching")
    normalize: bool = Field(default=True)

    @field_validator('texts')
    @classmethod
    def validate_texts(cls, v: List[str]) -> List[str]:
        """Validate text list"""
        if not v:
            raise ValueError("texts cannot be empty")
        if len(v) > 100:
            raise ValueError("Maximum 100 texts per batch")
        return v


class EmbeddingResponse(BaseModel):
    """Response with embedding"""
    embedding: List[float]
    dimension: int
    model: str
    cached: bool = False
    processing_time_ms: float


class BatchEmbeddingResponse(BaseModel):
    """Response with batch embeddings"""
    embeddings: List[List[float]]
    dimension: int
    model: str
    count: int
    cached_count: int
    processing_time_ms: float


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    model_loaded: bool
    redis_connected: bool
    device: str
    cache_enabled: bool


class ModelStats(BaseModel):
    """Model statistics"""
    total_embeddings: int
    cached_embeddings: int
    cache_hit_rate: float
    avg_processing_time_ms: float
    model_name: str
    device: str


class JinaEmbeddingsService:
    """Jina Embeddings v3 service with caching"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = logger.bind(component="jina-embeddings")

        # Model and tokenizer
        self.model = None
        self.tokenizer = None
        self.device = None

        # Redis cache
        self.redis: Optional[aioredis.Redis] = None

        # Statistics
        self.total_embeddings = 0
        self.cached_embeddings = 0
        self.processing_times = []

    async def setup(self):
        """Initialize model and cache"""
        await self.load_model()
        if self.settings.enable_cache:
            await self.setup_redis()

    async def load_model(self):
        """Load Jina embeddings model"""
        try:
            self.logger.info(
                "loading_model",
                model_name=self.settings.model_name,
                device=self.settings.device
            )

            # Set device
            self.device = torch.device(
                self.settings.device if torch.cuda.is_available()
                else "cpu"
            )

            # Load tokenizer and model
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.settings.model_name,
                cache_dir=self.settings.model_cache_dir,
                trust_remote_code=True
            )

            self.model = AutoModel.from_pretrained(
                self.settings.model_name,
                cache_dir=self.settings.model_cache_dir,
                trust_remote_code=True
            )

            self.model.to(self.device)
            self.model.eval()

            self.logger.info(
                "model_loaded",
                device=str(self.device),
                model_name=self.settings.model_name
            )

        except Exception as e:
            self.logger.error("model_load_failed", error=str(e))
            raise

    async def setup_redis(self):
        """Setup Redis connection for caching"""
        try:
            self.redis = await aioredis.from_url(
                f"redis://{self.settings.redis_host}:{self.settings.redis_port}",
                db=self.settings.redis_db,
                encoding="utf-8",
                decode_responses=False
            )

            # Test connection
            await self.redis.ping()

            self.logger.info("redis_connected", host=self.settings.redis_host)

        except Exception as e:
            self.logger.warning("redis_connection_failed", error=str(e))
            self.redis = None

    def _get_cache_key(
            self,
            text: str,
            dimension: int,
            task: str
    ) -> str:
        """Generate cache key for text"""
        content = f"{text}:{dimension}:{task}"
        return f"jina:emb:{hashlib.md5(content.encode()).hexdigest()}"

    async def _get_cached_embedding(
            self,
            text: str,
            dimension: int,
            task: str
    ) -> Optional[np.ndarray]:
        """Get embedding from cache"""
        if not self.redis:
            return None

        try:
            cache_key = self._get_cache_key(text, dimension, task)
            cached = await self.redis.get(cache_key)

            if cached:
                self.cached_embeddings += 1
                EMBEDDINGS_CACHED.inc()

                # Deserialize numpy array
                embedding = np.frombuffer(cached, dtype=np.float32)
                return embedding

            return None

        except Exception as e:
            self.logger.warning("cache_get_failed", error=str(e))
            return None

    async def _cache_embedding(
            self,
            text: str,
            dimension: int,
            task: str,
            embedding: np.ndarray
    ):
        """Cache embedding"""
        if not self.redis:
            return

        try:
            cache_key = self._get_cache_key(text, dimension, task)

            # Serialize numpy array
            embedding_bytes = embedding.astype(np.float32).tobytes()

            await self.redis.setex(
                cache_key,
                self.settings.cache_ttl_seconds,
                embedding_bytes
            )

        except Exception as e:
            self.logger.warning("cache_set_failed", error=str(e))

    def _truncate_to_dimension(
            self,
            embedding: np.ndarray,
            target_dim: int
    ) -> np.ndarray:
        """Truncate embedding to target dimension (Matryoshka)"""
        if embedding.shape[-1] <= target_dim:
            return embedding

        return embedding[..., :target_dim]

    async def generate_embedding(
            self,
            text: str,
            dimension: int = 512,
            task: str = "text-matching",
            normalize: bool = True
    ) -> tuple[np.ndarray, bool, float]:
        """
        Generate embedding for text

        Returns:
            tuple: (embedding, cached, processing_time_ms)
        """
        start_time = time.time()

        # Check cache
        cached_emb = await self._get_cached_embedding(text, dimension, task)
        if cached_emb is not None:
            processing_time = (time.time() - start_time) * 1000
            return cached_emb, True, processing_time

        # Generate embedding
        try:
            with torch.no_grad():
                # Tokenize
                inputs = self.tokenizer(
                    text,
                    max_length=self.settings.max_length,
                    padding=True,
                    truncation=True,
                    return_tensors="pt"
                )

                # Move to device
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                # Generate embedding
                outputs = self.model(**inputs)

                # Get embedding from last hidden state (mean pooling)
                embedding = outputs.last_hidden_state.mean(dim=1)

                # Move to CPU and convert to numpy
                embedding = embedding.cpu().numpy()[0]

                # Truncate to target dimension (Matryoshka)
                embedding = self._truncate_to_dimension(embedding, dimension)

                # Normalize if requested
                if normalize:
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm

            processing_time = (time.time() - start_time) * 1000

            # Cache the embedding
            await self._cache_embedding(text, dimension, task, embedding)

            # Update metrics
            self.total_embeddings += 1
            self.processing_times.append(processing_time)
            if len(self.processing_times) > 1000:
                self.processing_times = self.processing_times[-1000:]

            EMBEDDINGS_GENERATED.inc()
            EMBEDDING_TIME.observe(processing_time / 1000)

            return embedding, False, processing_time

        except Exception as e:
            self.logger.error("embedding_generation_failed", error=str(e))
            raise

    async def generate_batch_embeddings(
            self,
            texts: List[str],
            dimension: int = 512,
            task: str = "text-matching",
            normalize: bool = True
    ) -> tuple[List[np.ndarray], int, float]:
        """
        Generate embeddings for batch of texts

        Returns:
            tuple: (embeddings, cached_count, processing_time_ms)
        """
        start_time = time.time()
        embeddings = []
        cached_count = 0

        # Check which texts are cached
        uncached_texts = []
        uncached_indices = []

        for i, text in enumerate(texts):
            cached_emb = await self._get_cached_embedding(text, dimension, task)
            if cached_emb is not None:
                embeddings.append((i, cached_emb))
                cached_count += 1
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Generate embeddings for uncached texts
        if uncached_texts:
            try:
                with torch.no_grad():
                    # Tokenize batch
                    inputs = self.tokenizer(
                        uncached_texts,
                        max_length=self.settings.max_length,
                        padding=True,
                        truncation=True,
                        return_tensors="pt"
                    )

                    # Move to device
                    inputs = {k: v.to(self.device) for k, v in inputs.items()}

                    # Generate embeddings
                    outputs = self.model(**inputs)

                    # Mean pooling
                    batch_embeddings = outputs.last_hidden_state.mean(dim=1)

                    # Move to CPU
                    batch_embeddings = batch_embeddings.cpu().numpy()

                    # Process each embedding
                    for i, (text, embedding) in enumerate(zip(uncached_texts, batch_embeddings)):
                        # Truncate to dimension
                        embedding = self._truncate_to_dimension(embedding, dimension)

                        # Normalize
                        if normalize:
                            norm = np.linalg.norm(embedding)
                            if norm > 0:
                                embedding = embedding / norm

                        # Add to results
                        embeddings.append((uncached_indices[i], embedding))

                        # Cache
                        await self._cache_embedding(text, dimension, task, embedding)

                # Update metrics
                self.total_embeddings += len(uncached_texts)
                EMBEDDINGS_GENERATED.inc(len(uncached_texts))
                BATCH_SIZE_METRIC.observe(len(texts))

            except Exception as e:
                self.logger.error("batch_embedding_failed", error=str(e))
                raise

        # Sort embeddings by original index
        embeddings.sort(key=lambda x: x[0])
        embeddings = [emb for _, emb in embeddings]

        processing_time = (time.time() - start_time) * 1000
        EMBEDDING_TIME.observe(processing_time / 1000)

        return embeddings, cached_count, processing_time

    def get_stats(self) -> ModelStats:
        """Get service statistics"""
        cache_hit_rate = (
            (self.cached_embeddings / self.total_embeddings * 100)
            if self.total_embeddings > 0 else 0
        )

        avg_time = (
            sum(self.processing_times) / len(self.processing_times)
            if self.processing_times else 0
        )

        CACHE_HIT_RATE.set(cache_hit_rate)

        return ModelStats(
            total_embeddings=self.total_embeddings,
            cached_embeddings=self.cached_embeddings,
            cache_hit_rate=cache_hit_rate,
            avg_processing_time_ms=avg_time,
            model_name=self.settings.model_name,
            device=str(self.device)
        )


# Global service instance
settings = Settings()
service: Optional[JinaEmbeddingsService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager"""
    global service

    # Startup
    logger.info("application_starting")

    service = JinaEmbeddingsService(settings)
    await service.setup()

    logger.info("application_started")

    yield

    # Shutdown
    logger.info("application_stopping")

    if service and service.redis:
        await service.redis.close()

    logger.info("application_stopped")


# FastAPI application
app = FastAPI(
    title="Jina Embeddings Service",
    description="Text embedding service using Jina Embeddings v3 with Matryoshka support",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    return HealthResponse(
        status="healthy",
        service="jina-embeddings",
        version="1.0.0",
        model_loaded=service.model is not None,
        redis_connected=service.redis is not None,
        device=str(service.device),
        cache_enabled=settings.enable_cache
    )


@app.post("/embed", response_model=EmbeddingResponse)
async def generate_embedding(request: EmbeddingRequest):
    """Generate embedding for single text"""
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    try:
        embedding, cached, processing_time = await service.generate_embedding(
            text=request.text,
            dimension=request.dimension,
            task=request.task,
            normalize=request.normalize
        )

        return EmbeddingResponse(
            embedding=embedding.tolist(),
            dimension=request.dimension,
            model=settings.model_name,
            cached=cached,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error("embedding_request_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding generation failed: {str(e)}"
        )


@app.post("/embed/batch", response_model=BatchEmbeddingResponse)
async def generate_batch_embeddings(request: BatchEmbeddingRequest):
    """Generate embeddings for batch of texts"""
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    try:
        embeddings, cached_count, processing_time = await service.generate_batch_embeddings(
            texts=request.texts,
            dimension=request.dimension,
            task=request.task,
            normalize=request.normalize
        )

        return BatchEmbeddingResponse(
            embeddings=[emb.tolist() for emb in embeddings],
            dimension=request.dimension,
            model=settings.model_name,
            count=len(embeddings),
            cached_count=cached_count,
            processing_time_ms=processing_time
        )

    except Exception as e:
        logger.error("batch_embedding_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch embedding generation failed: {str(e)}"
        )


@app.get("/stats", response_model=ModelStats)
async def get_stats():
    """Get service statistics"""
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    return service.get_stats()


@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()


@app.post("/cache/clear")
async def clear_cache():
    """Clear embedding cache"""
    if service is None or service.redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache not available"
        )

    try:
        # Clear all jina: keys
        cursor = 0
        deleted = 0

        while True:
            cursor, keys = await service.redis.scan(
                cursor=cursor,
                match="jina:*",
                count=100
            )

            if keys:
                deleted += await service.redis.delete(*keys)

            if cursor == 0:
                break

        return {"status": "cleared", "deleted_keys": deleted}

    except Exception as e:
        logger.error("cache_clear_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cache clear failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_config=None
    )