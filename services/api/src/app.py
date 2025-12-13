"""
API Gateway
FastAPI backend providing unified API for the log analysis platform

Features:
- Log search and filtering (ClickHouse)
- Semantic search (Qdrant)
- Pattern analysis (PostgreSQL + Qdrant)
- Real-time log streaming (WebSocket)
- Metrics and statistics
- CORS enabled for React frontend
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from routers import logs, search, patterns, reports, metrics, websocket, config, anomalies
from services.cache import CacheService
from services.database import DatabaseService
from services.qdrant_service import QdrantService
from settings import setup_development_logging, get_logger

setup_development_logging()
logger = get_logger(__name__)
# ============================================================================
# Logging
# ============================================================================
#
# structlog.configure(
#     processors=[
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

API_REQUESTS = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

API_LATENCY = Histogram(
    'api_request_duration_seconds',
    'API request latency',
    ['method', 'endpoint']
)


# ============================================================================
# Global Services
# ============================================================================

db_service: Optional[DatabaseService] = None
qdrant_service: Optional[QdrantService] = None
cache_service: Optional[CacheService] = None


# ============================================================================
# Lifespan
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""

    logger.info("api_starting")

    # Initialize services
    db_service = DatabaseService()
    await db_service.connect()

    qdrant_service = QdrantService()
    await qdrant_service.connect()

    cache_service = CacheService()
    await cache_service.connect()

    logger.info("api_started")

    yield

    # Cleanup
    logger.info("api_stopping")

    if db_service:
        await db_service.disconnect()

    if qdrant_service:
        await qdrant_service.disconnect()

    if cache_service:
        await cache_service.disconnect()

    logger.info("api_stopped")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Log Analysis Platform API",
    description="Unified API for log search, semantic search, and pattern analysis",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# CORS Middleware
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Include Routers
# ============================================================================

app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(patterns.router, prefix="/api/patterns", tags=["patterns"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(websocket.router, prefix="/api/ws", tags=["websocket"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(anomalies.router, prefix="/api/anomalies", tags=["anomalies"])

# Import summary router
from routers import summary
app.include_router(summary.router, prefix="/api/summary", tags=["summary"])


# ============================================================================
# Root Endpoints
# ============================================================================

@app.get("/")
async def root():
    """API root"""
    return {
        "name": "Log Analysis Platform API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "logs": "/api/logs",
            "search": "/api/search",
            "patterns": "/api/patterns",
            "reports": "/api/reports",
            "anomalies": "/api/anomalies",
            "metrics": "/api/metrics",
            "summary": "/api/summary",
            "config": "/api/config",
            "websocket": "/api/ws",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""

    # Check service health
    clickhouse_healthy = await db_service.check_clickhouse_health() if db_service else False
    postgres_healthy = await db_service.check_postgres_health() if db_service else False
    qdrant_healthy = await qdrant_service.check_health() if qdrant_service else False
    redis_healthy = await cache_service.check_health() if cache_service else False

    all_healthy = all([clickhouse_healthy, postgres_healthy, qdrant_healthy, redis_healthy])

    return {
        "status": "healthy" if all_healthy else "degraded",
        "services": {
            "clickhouse": "healthy" if clickhouse_healthy else "unhealthy",
            "postgresql": "healthy" if postgres_healthy else "unhealthy",
            "qdrant": "healthy" if qdrant_healthy else "unhealthy",
            "redis": "healthy" if redis_healthy else "unhealthy"
        }
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc)
        }
    )


# ============================================================================
# Dependency Injection
# ============================================================================

def get_db_service() -> DatabaseService:
    """Get database service instance"""
    return db_service


def get_qdrant_service() -> QdrantService:
    """Get Qdrant service instance"""
    return qdrant_service


def get_cache_service() -> CacheService:
    """Get cache service instance"""
    return cache_service


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8005,
        reload=True,
        log_level="info"
    )