"""
Search Router
Endpoints for semantic search using Qdrant vector database
"""

from typing import Optional, List, Dict, Any, Union

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from services.qdrant_service import QdrantService
from services.cache import CacheService
from settings import get_logger, setup_development_logging
setup_development_logging()
logger = get_logger(__name__)
router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class SearchResult(BaseModel):
    """Single search result with full log details"""
    # Vector search metadata
    id: str
    score: float = Field(..., ge=0, le=1, description="Similarity score (0-1)")
    similarity_score: float = Field(..., ge=0, le=1, description="Similarity score (0-1)")
    
    # Core log fields
    log_id: str
    timestamp: str
    service: str
    environment: str
    level: str
    message: str
    
    # Infrastructure
    host: Optional[str] = None
    pod_name: Optional[str] = None
    container_id: Optional[str] = None
    logger_name: Optional[str] = None
    
    # Distributed tracing
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    
    # Context
    thread_name: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    
    # Error details
    stack_trace: Optional[str] = None
    
    # Metadata
    labels: Optional[dict] = None
    metadata: Optional[str] = None
    
    # Processing flags
    is_vectorized: Optional[bool] = None
    is_anomaly: Optional[bool] = None
    anomaly_score: Optional[float] = None
    
    # Source information
    source_type: Optional[str] = None
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    
    # Timestamps
    ingested_at: Optional[str] = None
    processed_at: Optional[str] = None


class SemanticSearchResponse(BaseModel):
    """Response for semantic search"""
    query: str
    results: List[SearchResult]
    count: int
    generation_time_seconds: float = Field(0.0, description="Time taken to generate results")


class SimilarLogsResponse(BaseModel):
    """Response for similar logs"""
    reference_log_id: str
    similar_logs: List[SearchResult]
    count: int


class ClusterMetadata(BaseModel):
    """Metadata for a single cluster"""
    environment: str
    service: str
    level: str
    avg_similarity: float
    log_count: int
    time_range: Dict[str, str]  # earliest and latest timestamp
    dominant_message_pattern: str  # Most common message pattern


class LogCluster(BaseModel):
    """A cluster of semantically similar logs"""
    cluster_id: str  # Generated ID: {env}_{service}_{level}_{idx}
    metadata: ClusterMetadata
    logs: List[SearchResult]


class EnvironmentGroup(BaseModel):
    """Logs grouped by environment"""
    environment: str
    total_logs: int
    clusters: List[LogCluster]


class ClusteredSearchResponse(BaseModel):
    """Response with clustered semantic search results"""
    query: str
    total_results: int
    environment_groups: List[EnvironmentGroup]
    generation_time_seconds: float


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

class SemanticSearchRequest(BaseModel):
    """Request model for semantic search"""
    query: str = Field(..., min_length=1, max_length=500, description="Search query text")
    top_k: int = Field(20, ge=1, le=100, description="Maximum number of results")
    level: Optional[str] = Field(None, description="Filter by log level")
    service: Optional[str] = Field(None, description="Filter by service name")
    score_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Minimum similarity score")


@router.post("/semantic", response_model=Union[SemanticSearchResponse, ClusteredSearchResponse])
async def semantic_search(
        request: SemanticSearchRequest,
        return_clusters: bool = Query(False, description="Return results as clusters grouped by environment"),
        qdrant: QdrantService = Depends(get_qdrant),
        cache: CacheService = Depends(get_cache)
):
    """
    Semantic search for similar log messages using AI embeddings
    
    This endpoint:
    1. Converts your search query into a vector embedding using Jina AI
    2. Searches Qdrant vector database for semantically similar logs
    3. Enriches results with full log details from ClickHouse
    4. Returns ranked results with similarity scores
    5. Optionally clusters results by environment, service, level, and pattern

    - **query**: Natural language search query (e.g., "authentication failures")
    - **top_k**: Maximum number of results to return (1-100)
    - **service**: Optional filter by service name
    - **level**: Optional filter by log level (ERROR, WARN, INFO, etc.)
    - **score_threshold**: Minimum similarity score threshold (0-1)
    - **return_clusters**: If true, returns hierarchically clustered results

    Returns logs semantically similar to your query, ranked by relevance.
    """

    # Generate cache key
    cache_key = cache.cache_key(
        "search:semantic",
        query=request.query,
        limit=request.top_k,
        service=request.service,
        level=request.level,
        threshold=request.score_threshold,
        clusters=return_clusters
    )

    # Try cache first
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Perform search
    try:
        import time
        start_time = time.time()
        
        if return_clusters:
            # Return clustered results
            clustered_results = await qdrant.semantic_search_clustered(
                query=request.query,
                top_k=request.top_k,
                service=request.service,
                level=request.level,
                score_threshold=request.score_threshold
            )
            
            response = ClusteredSearchResponse(**clustered_results)
            
            # Cache for 10 minutes
            await cache.set(cache_key, response.model_dump(), ttl=600)
            
            return response
        else:
            # Return flat results
            results = await qdrant.semantic_search(
                query=request.query,
                limit=request.top_k,
                service=request.service,
                level=request.level,
                score_threshold=request.score_threshold,
                enrich_with_clickhouse=True  # Fetch full logs from ClickHouse
            )
            logger.info(f"Results: {results}")
            generation_time = time.time() - start_time

            response = SemanticSearchResponse(
                query=request.query,
                results=[SearchResult(**r) for r in results],
                count=len(results),
                generation_time_seconds=round(generation_time, 3)
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