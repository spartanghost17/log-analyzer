"""
Metrics Router
Endpoints for system-wide metrics and statistics
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..services.database import DatabaseService
from ..services.cache import CacheService
from ..services.qdrant_service import QdrantService

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class SystemMetrics(BaseModel):
    """Overall system metrics"""
    total_logs: int
    total_errors: int
    total_warnings: int
    total_vectors: int
    services_count: int
    avg_logs_per_hour: float


# ============================================================================
# Dependency Injection
# ============================================================================

def get_db() -> DatabaseService:
    """Get database service from app state"""
    from ..app import db_service
    return db_service


def get_qdrant() -> QdrantService:
    """Get Qdrant service from app state"""
    from ..app import qdrant_service
    return qdrant_service


def get_cache() -> CacheService:
    """Get cache service from app state"""
    from ..app import cache_service
    return cache_service


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/system", response_model=SystemMetrics)
async def get_system_metrics(
        db: DatabaseService = Depends(get_db),
        qdrant: QdrantService = Depends(get_qdrant),
        cache: CacheService = Depends(get_cache)
):
    """Get overall system metrics"""

    # Try cache
    cache_key = "metrics:system"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Get metrics from different sources
    total_logs = db.get_log_count()
    total_errors = db.get_log_count(level="ERROR")
    total_warnings = db.get_log_count(level="WARN")

    # Get vector stats
    vector_stats = await qdrant.get_collection_stats()
    total_vectors = vector_stats.get("points_count", 0)

    # Get service count
    service_stats = db.get_service_stats()
    services_count = len(service_stats)

    # Calculate average logs per hour
    hourly_stats = db.get_hourly_stats(hours=24)
    if hourly_stats:
        avg_logs_per_hour = sum(s["total_logs"] for s in hourly_stats) / len(hourly_stats)
    else:
        avg_logs_per_hour = 0

    response = SystemMetrics(
        total_logs=total_logs,
        total_errors=total_errors,
        total_warnings=total_warnings,
        total_vectors=total_vectors,
        services_count=services_count,
        avg_logs_per_hour=round(avg_logs_per_hour, 2)
    )

    # Cache for 5 minutes
    await cache.set(cache_key, response.model_dump(), ttl=300)

    return response


@router.get("/overview")
async def get_metrics_overview(
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Get overview metrics for dashboard"""

    # Try cache
    cache_key = "metrics:overview"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Get various metrics
    service_stats = db.get_service_stats()
    error_trends = db.get_error_trends(hours=24)

    response = {
        "services": service_stats,
        "error_trends": error_trends,
        "timestamp": "now"
    }

    # Cache for 1 minute
    await cache.set(cache_key, response, ttl=60)

    return response