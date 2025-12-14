"""
Anomalies Router
Endpoints for querying and managing anomaly alerts from PostgreSQL
"""

from typing import Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from services.database import DatabaseService
from services.cache import CacheService

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class Anomaly(BaseModel):
    """Anomaly alert"""
    alert_id: str
    anomaly_type: str
    detected_at: str
    service: str
    environment: str
    severity: str
    description: str
    confidence_score: float
    status: str
    metrics: Optional[dict] = None
    llm_analysis: Optional[str] = None
    suggested_actions: Optional[list] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None


class AnomaliesResponse(BaseModel):
    """Response for anomaly queries"""
    anomalies: list[Anomaly]
    total: int
    limit: int


class AcknowledgeRequest(BaseModel):
    """Request to acknowledge anomaly"""
    acknowledged_by: Optional[str] = Field(default="system", description="User who acknowledged")


class ResolveRequest(BaseModel):
    """Request to resolve anomaly"""
    resolved_by: Optional[str] = Field(default="system", description="User who resolved")
    resolution_notes: Optional[str] = Field(default=None, description="Resolution notes")


# ============================================================================
# Dependencies
# ============================================================================

def get_db() -> DatabaseService:
    """Get database service instance"""
    from ..app import db_service
    return db_service


def get_cache() -> CacheService:
    """Get cache service instance"""
    from ..app import cache_service
    return cache_service


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=AnomaliesResponse)
async def get_anomalies(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    status: Optional[str] = Query(None, description="Filter by status"),
    service: Optional[str] = Query(None, description="Filter by service"),
    db: DatabaseService = Depends(get_db),
    cache: CacheService = Depends(get_cache)
):
    """
    Query anomaly alerts with filters

    - **limit**: Number of anomalies to return (1-100)
    - **offset**: Offset for pagination
    - **severity**: Filter by severity (low, medium, high, critical)
    - **status**: Filter by status (new, acknowledged, resolved)
    - **service**: Filter by service name
    """

    # Generate cache key
    cache_key = cache.cache_key(
        "anomalies",
        limit=limit,
        offset=offset,
        severity=severity,
        status=status,
        service=service
    )

    # Try cache first (30 second TTL for anomalies)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Query database
    anomalies = await db.get_anomalies(
        limit=limit,
        offset=offset,
        severity=severity,
        status=status,
        service=service
    )

    # Get total count
    total = await db.get_anomalies_count(
        severity=severity,
        status=status,
        service=service
    )

    # Build response
    response = AnomaliesResponse(
        anomalies=[Anomaly(**anomaly) for anomaly in anomalies],
        total=total,
        limit=limit
    )

    # Cache response (shorter TTL for real-time data)
    await cache.set(cache_key, response.model_dump(), ttl=30)

    return response


@router.get("/{alert_id}", response_model=Anomaly)
async def get_anomaly_by_id(
    alert_id: str,
    db: DatabaseService = Depends(get_db)
):
    """
    Get a specific anomaly by ID

    - **alert_id**: UUID of the anomaly alert
    """

    anomaly = await db.get_anomaly_by_id(alert_id)

    if not anomaly:
        raise HTTPException(status_code=404, detail=f"Anomaly {alert_id} not found")

    return Anomaly(**anomaly)


@router.patch("/{alert_id}/acknowledge", response_model=Anomaly)
async def acknowledge_anomaly(
    alert_id: str,
    request: AcknowledgeRequest = AcknowledgeRequest(),
    db: DatabaseService = Depends(get_db),
    cache: CacheService = Depends(get_cache)
):
    """
    Acknowledge an anomaly alert

    - **alert_id**: UUID of the anomaly alert
    - **acknowledged_by**: User who acknowledged (defaults to 'system')

    Updates status to 'acknowledged' and sets acknowledged_at timestamp
    """

    # Check if anomaly exists
    anomaly = await db.get_anomaly_by_id(alert_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail=f"Anomaly {alert_id} not found")

    # Check if already acknowledged or resolved
    if anomaly["status"] == "acknowledged":
        return Anomaly(**anomaly)  # Already acknowledged, return as-is

    if anomaly["status"] == "resolved":
        raise HTTPException(
            status_code=400,
            detail="Cannot acknowledge a resolved anomaly"
        )

    # Update anomaly status
    updated = await db.acknowledge_anomaly(
        alert_id=alert_id,
        acknowledged_by=request.acknowledged_by
    )

    # Invalidate cache
    await cache.invalidate_pattern("anomalies:*")

    return Anomaly(**updated)


@router.patch("/{alert_id}/resolve", response_model=Anomaly)
async def resolve_anomaly(
    alert_id: str,
    request: ResolveRequest = ResolveRequest(),
    db: DatabaseService = Depends(get_db),
    cache: CacheService = Depends(get_cache)
):
    """
    Resolve an anomaly alert

    - **alert_id**: UUID of the anomaly alert
    - **resolved_by**: User who resolved (defaults to 'system')
    - **resolution_notes**: Optional notes about the resolution

    Updates status to 'resolved' and sets resolved_at timestamp
    """

    # Check if anomaly exists
    anomaly = await db.get_anomaly_by_id(alert_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail=f"Anomaly {alert_id} not found")

    # Check if already resolved
    if anomaly["status"] == "resolved":
        return Anomaly(**anomaly)  # Already resolved, return as-is

    # Update anomaly status
    updated = await db.resolve_anomaly(
        alert_id=alert_id,
        resolved_by=request.resolved_by,
        resolution_notes=request.resolution_notes
    )

    # Invalidate cache
    await cache.invalidate_pattern("anomalies:*")

    return Anomaly(**updated)


@router.get("/stats/summary")
async def get_anomaly_stats(
    db: DatabaseService = Depends(get_db),
    cache: CacheService = Depends(get_cache)
):
    """
    Get anomaly statistics summary

    Returns counts by severity, status, and recent trends
    """

    cache_key = cache.cache_key("anomaly_stats")

    # Try cache first
    cached = await cache.get(cache_key)
    if cached:
        return cached

    stats = await db.get_anomaly_stats()

    # Cache for 1 minute
    await cache.set(cache_key, stats, ttl=60)

    return stats

