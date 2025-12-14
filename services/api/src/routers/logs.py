"""
Logs Router
Endpoints for querying and filtering logs from ClickHouse
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from services.database import DatabaseService
from services.cache import CacheService

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class LogEntry(BaseModel):
    """Single log entry"""
    log_id: str
    timestamp: str
    service: str
    environment: str
    level: str
    message: str
    trace_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: Optional[dict] = None


class LogsResponse(BaseModel):
    """Response for log queries"""
    logs: List[LogEntry]
    total: int
    limit: int
    offset: int


class ServiceStats(BaseModel):
    """Statistics for a service"""
    service: str
    total_logs: int
    error_count: int
    warn_count: int
    info_count: int
    unique_traces: int


# ============================================================================
# Dependency Injection
# ============================================================================

def get_db() -> DatabaseService:
    """Get database service from app state"""
    from ..app import db_service
    return db_service


def get_cache() -> CacheService:
    """Get cache service from app state"""
    from ..app import cache_service
    return cache_service


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/", response_model=LogsResponse)
async def get_logs(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        service: Optional[str] = Query(None),
        level: Optional[str] = Query(None),
        start_time: Optional[datetime] = Query(None),
        end_time: Optional[datetime] = Query(None),
        search: Optional[str] = Query(None),
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """
    Query logs with filters

    - **limit**: Number of logs to return (1-1000)
    - **offset**: Offset for pagination
    - **service**: Filter by service name
    - **level**: Filter by log level (INFO, WARN, ERROR, FATAL)
    - **start_time**: Filter logs after this time (ISO 8601)
    - **end_time**: Filter logs before this time (ISO 8601)
    - **search**: Search in log message
    """

    # Generate cache key
    cache_key = cache.cache_key(
        "logs",
        limit=limit,
        offset=offset,
        service=service,
        level=level,
        start_time=start_time.isoformat() if start_time else None,
        end_time=end_time.isoformat() if end_time else None,
        search=search
    )

    # Try cache first
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Query database
    logs = db.get_logs(
        limit=limit,
        offset=offset,
        service=service,
        level=level,
        start_time=start_time,
        end_time=end_time,
        search=search
    )

    # Get total count
    total = db.get_log_count(
        service=service,
        level=level,
        start_time=start_time,
        end_time=end_time
    )

    # Build response
    response = LogsResponse(
        logs=[LogEntry(**log) for log in logs],
        total=total,
        limit=limit,
        offset=offset
    )

    # Cache response
    await cache.set(cache_key, response.model_dump(), ttl=60)

    return response


@router.get("/{log_id}", response_model=LogEntry)
async def get_log_by_id(
        log_id: str,
        db: DatabaseService = Depends(get_db)
):
    """Get a specific log by ID"""

    logs = db.get_logs(limit=1, search=log_id)

    if not logs:
        raise HTTPException(status_code=404, detail="Log not found")

    return LogEntry(**logs[0])


@router.get("/stats/services", response_model=List[ServiceStats])
async def get_service_statistics(
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Get statistics by service for the last 24 hours"""

    # Try cache
    cache_key = "stats:services:24h"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Query database
    stats = db.get_service_stats()

    response = [ServiceStats(**s) for s in stats]

    # Cache for 5 minutes
    await cache.set(cache_key, [s.model_dump() for s in response], ttl=300)

    return response


@router.get("/stats/hourly")
async def get_hourly_statistics(
        hours: int = Query(24, ge=1, le=168),
        service: Optional[str] = Query(None),
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Get hourly statistics for the specified time range"""

    # Try cache
    cache_key = cache.cache_key("stats:hourly", hours=hours, service=service)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Query database
    stats = db.get_hourly_stats(hours=hours, service=service)

    # Cache for 5 minutes
    await cache.set(cache_key, stats, ttl=300)

    return stats


@router.get("/trends/errors")
async def get_error_trends(
        hours: int = Query(24, ge=1, le=168),
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Get error trends over time"""

    # Try cache
    cache_key = cache.cache_key("trends:errors", hours=hours)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Query database
    trends = db.get_error_trends(hours=hours)

    # Cache for 5 minutes
    await cache.set(cache_key, trends, ttl=300)

    return trends