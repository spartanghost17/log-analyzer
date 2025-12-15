"""
Patterns Router
Endpoints for error pattern analysis and clustering
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from services.qdrant_service import QdrantService
from services.cache import CacheService

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class ErrorCluster(BaseModel):
    """Cluster of similar errors"""
    service: str
    level: str
    count: int
    samples: List[dict]


# ============================================================================
# Dependency Injection
# ============================================================================

def get_qdrant() -> QdrantService:
    """Get Qdrant service from app state"""
    from app import qdrant_service
    return qdrant_service


def get_cache() -> CacheService:
    """Get cache service from app state"""
    from app import cache_service
    return cache_service


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/clusters", response_model=List[ErrorCluster])
async def get_error_clusters(
        service: Optional[str] = Query(None),
        level: str = Query("ERROR"),
        limit: int = Query(100, ge=1, le=1000),
        qdrant: QdrantService = Depends(get_qdrant),
        cache: CacheService = Depends(get_cache)
):
    """
    Get clusters of similar error messages

    - **service**: Filter by service name
    - **level**: Filter by log level (default: ERROR)
    - **limit**: Maximum number of logs to analyze

    Returns clusters of semantically similar errors.
    """

    # Try cache
    cache_key = cache.cache_key("patterns:clusters", service=service, level=level, limit=limit)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Get clusters
    clusters = await qdrant.cluster_similar_logs(
        service=service,
        level=level,
        limit=limit
    )

    response = [ErrorCluster(**c) for c in clusters]

    # Cache for 10 minutes
    await cache.set(cache_key, [c.model_dump() for c in response], ttl=600)

    return response