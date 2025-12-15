"""
Search Router
Endpoints for semantic search using Qdrant vector database
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from services.qdrant_service import QdrantService
from services.cache import CacheService

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class SearchResult(BaseModel):
    """Single search result"""
    id: str
    score: float = Field(..., ge=0, le=1, description="Similarity score (0-1)")
    log_id: str
    timestamp: int
    service: str
    environment: str
    level: str
    message: str
    trace_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None


class SemanticSearchResponse(BaseModel):
    """Response for semantic search"""
    query: str
    results: List[SearchResult]
    count: int


class SimilarLogsResponse(BaseModel):
    """Response for similar logs"""
    reference_log_id: str
    similar_logs: List[SearchResult]
    count: int


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

@router.get("/semantic", response_model=SemanticSearchResponse)
async def semantic_search(
        query: str = Query(..., min_length=1, max_length=500),
        limit: int = Query(10, ge=1, le=100),
        service: Optional[str] = Query(None),
        level: Optional[str] = Query(None),
        score_threshold: float = Query(0.7, ge=0.0, le=1.0),
        qdrant: QdrantService = Depends(get_qdrant),
        cache: CacheService = Depends(get_cache)
):
    """
    Semantic search for similar log messages

    - **query**: Search query (natural language)
    - **limit**: Maximum number of results (1-100)
    - **service**: Filter by service name
    - **level**: Filter by log level
    - **score_threshold**: Minimum similarity score (0-1)

    Returns logs semantically similar to the query, ranked by similarity score.
    """

    # Generate cache key
    cache_key = cache.cache_key(
        "search:semantic",
        query=query,
        limit=limit,
        service=service,
        level=level,
        threshold=score_threshold
    )

    # Try cache first
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Perform search
    try:
        results = await qdrant.semantic_search(
            query=query,
            limit=limit,
            service=service,
            level=level,
            score_threshold=score_threshold
        )

        response = SemanticSearchResponse(
            query=query,
            results=[SearchResult(**r) for r in results],
            count=len(results)
        )

        # Cache for 10 minutes
        await cache.set(cache_key, response.model_dump(), ttl=600)

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/similar/{log_id}", response_model=SimilarLogsResponse)
async def find_similar_logs(
        log_id: str,
        limit: int = Query(10, ge=1, le=100),
        qdrant: QdrantService = Depends(get_qdrant),
        cache: CacheService = Depends(get_cache)
):
    """
    Find logs similar to a specific log

    - **log_id**: ID of the reference log
    - **limit**: Maximum number of similar logs to return

    Returns logs that are semantically similar to the specified log.
    """

    # Generate cache key
    cache_key = cache.cache_key("search:similar", log_id=log_id, limit=limit)

    # Try cache first
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Find similar logs
    try:
        similar = await qdrant.find_similar_errors(log_id=log_id, limit=limit)

        if not similar and limit > 0:
            # Log not found in vector database
            raise HTTPException(status_code=404, detail="Log not found in vector database")

        response = SimilarLogsResponse(
            reference_log_id=log_id,
            similar_logs=[SearchResult(**r) for r in similar],
            count=len(similar)
        )

        # Cache for 30 minutes
        await cache.set(cache_key, response.model_dump(), ttl=1800)

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/stats")
async def get_search_stats(
        qdrant: QdrantService = Depends(get_qdrant)
):
    """Get statistics about the vector search database"""

    try:
        stats = await qdrant.get_collection_stats("log_embeddings")
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")