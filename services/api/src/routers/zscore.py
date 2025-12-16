"""
Z-Score Anomaly Detection Router
Provides time-series Z-score data for anomaly visualization
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from services.database import DatabaseService
from services.cache import CacheService

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class ZScoreDataPoint(BaseModel):
    """Single Z-score data point for visualization"""
    index: int
    timestamp: str
    hour: str
    z_score: float
    actual_count: int
    baseline_mean: float
    baseline_stddev: float
    is_anomaly: bool
    service: Optional[str] = None
    level: Optional[str] = None


class ZScoreResponse(BaseModel):
    """Z-score time-series response"""
    data_points: List[ZScoreDataPoint]
    threshold: float
    time_range: Dict[str, str]
    anomaly_count: int
    baseline_mean: float
    baseline_stddev: float
    metadata: Dict[str, Any]


# ============================================================================
# Dependencies
# ============================================================================

def get_db() -> DatabaseService:
    """Get database service instance"""
    from app import db_service
    return db_service


def get_cache() -> CacheService:
    """Get cache service instance"""
    from app import cache_service
    return cache_service


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/zscore", response_model=ZScoreResponse)
async def get_zscore_anomaly_data(
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    service: Optional[str] = Query(None, description="Filter by service"),
    level: Optional[str] = Query("ERROR", description="Log level to analyze"),
    threshold: float = Query(2.0, ge=1.0, le=5.0, description="Z-score threshold for anomalies"),
    report_start_time: Optional[str] = Query(None, description="Report start time (ISO format) - if provided, used as end_time"),
    db: DatabaseService = Depends(get_db),
    cache: CacheService = Depends(get_cache)
):
    """
    Get Z-score anomaly detection data for visualization
    
    This endpoint:
    1. Queries hourly log counts from ClickHouse
    2. Retrieves baseline statistics from anomaly_baselines table
    3. Calculates Z-scores: (actual - baseline_mean) / baseline_stddev
    4. Returns time-series data for chart visualization
    
    Args:
        hours: Number of hours to analyze (default: 24)
        service: Optional service filter
        level: Log level to analyze (default: ERROR)
        threshold: Z-score threshold for marking anomalies (default: 2.0)
        report_start_time: Optional report start time (ISO format) - if provided, used as end_time for analysis
    
    Returns:
        Time-series Z-score data with anomaly indicators
    """
    
    # Generate cache key
    cache_key = f"zscore:h{hours}:s{service}:l{level}:t{threshold}:rst{report_start_time}"
    
    # Try cache first (2 minute TTL)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    
    # Calculate time range
    # If report_start_time is provided, use it as end_time (report was generated with data up to that time)
    # Otherwise, use current time
    if report_start_time:
        try:
            end_time = datetime.fromisoformat(report_start_time.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            # If parsing fails, fall back to current time
            end_time = datetime.utcnow()
    else:
        end_time = datetime.utcnow()
    
    start_time = end_time - timedelta(hours=hours)
    
    # Query data from database service
    try:
        raw_data = db.get_zscore_data(
            start_time=start_time,
            end_time=end_time,
            level=level,
            service=service
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query ClickHouse: {str(e)}"
        )
    
    # Process results and calculate Z-scores
    data_points = []
    total_z_score = 0
    anomaly_count = 0
    
    for idx, row_data in enumerate(raw_data):
        hour_dt = row_data["hour"]
        service_name = row_data["service"]
        environment = row_data["environment"]
        level_name = row_data["level"]
        actual_count = row_data["actual_count"]
        baseline_mean = row_data["baseline_mean"] if row_data["baseline_mean"] is not None else actual_count
        baseline_stddev = row_data["baseline_stddev"] if row_data["baseline_stddev"] is not None else 1.0
        
        # Calculate Z-score
        # z_score = (actual - mean) / stddev
        # Handle edge case where stddev is 0
        if baseline_stddev > 0:
            z_score = (actual_count - baseline_mean) / baseline_stddev
        else:
            z_score = 0.0
        
        # Determine if this is an anomaly
        is_anomaly = abs(z_score) > threshold
        if is_anomaly:
            anomaly_count += 1
        
        total_z_score += z_score
        
        data_points.append(ZScoreDataPoint(
            index=idx,
            timestamp=hour_dt.isoformat() if hasattr(hour_dt, 'isoformat') else str(hour_dt),
            hour=hour_dt.strftime('%H:00') if hasattr(hour_dt, 'strftime') else str(hour_dt),
            z_score=round(z_score, 3),
            actual_count=actual_count,
            baseline_mean=round(baseline_mean, 2),
            baseline_stddev=round(baseline_stddev, 2),
            is_anomaly=is_anomaly,
            service=service_name,
            level=level_name
        ))
    
    # Calculate overall statistics
    overall_mean = total_z_score / len(data_points) if data_points else 0
    overall_stddev = 0
    
    if len(data_points) > 1:
        variance = sum((dp.z_score - overall_mean) ** 2 for dp in data_points) / len(data_points)
        overall_stddev = variance ** 0.5
    
    # Build response
    response = ZScoreResponse(
        data_points=data_points,
        threshold=threshold,
        time_range={
            "start": start_time.isoformat(),
            "end": end_time.isoformat()
        },
        anomaly_count=anomaly_count,
        baseline_mean=round(overall_mean, 3),
        baseline_stddev=round(overall_stddev, 3),
        metadata={
            "hours": hours,
            "service": service,
            "level": level,
            "data_points_count": len(data_points),
            "anomaly_percentage": round((anomaly_count / len(data_points) * 100) if data_points else 0, 2)
        }
    )
    
    # Cache for 2 minutes
    await cache.set(cache_key, response.model_dump(), ttl=120)
    
    return response


@router.get("/zscore/services", response_model=List[str])
async def get_available_services(
    db: DatabaseService = Depends(get_db)
):
    """
    Get list of services that have anomaly baselines configured
    
    Returns:
        List of service names
    """
    try:
        services = db.get_available_services_with_baselines()
        return services
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query services: {str(e)}"
        )

