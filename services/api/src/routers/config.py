"""
Config Router
CRUD endpoints for services and app_config tables
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.database import DatabaseService
from ..services.cache import CacheService
# from src.services.database import DatabaseService
# from src.services.cache import CacheService

router = APIRouter()


# ============================================================================
# Pydantic Models - App Config
# ============================================================================

class AppConfigBase(BaseModel):
    """Base app config model"""
    config_key: str
    config_value: dict
    description: Optional[str] = None
    is_encrypted: bool = False


class AppConfigCreate(AppConfigBase):
    """App config creation model"""
    pass


class AppConfigUpdate(BaseModel):
    """App config update model"""
    config_value: Optional[dict] = None
    description: Optional[str] = None
    is_encrypted: Optional[bool] = None


class AppConfig(AppConfigBase):
    """App config response model"""
    config_id: UUID
    created_at: str
    updated_at: str


# ============================================================================
# Pydantic Models - Services
# ============================================================================

class ServiceBase(BaseModel):
    """Base service model"""
    service_name: str
    description: Optional[str] = None
    team: Optional[str] = None
    owner_email: Optional[str] = None
    repository_url: Optional[str] = None
    enabled: bool = True
    log_retention_days: int = 90
    vectorize_logs: bool = True
    vectorize_levels: List[str] = Field(default_factory=lambda: ['WARN', 'ERROR', 'FATAL'])
    error_rate_threshold: Optional[float] = None
    anomaly_sensitivity: str = 'medium'
    alert_email: List[str] = Field(default_factory=list)
    alert_slack_channel: Optional[str] = None
    alert_on_new_patterns: bool = True
    tags: List[str] = Field(default_factory=list)
    environment_tags: Optional[dict] = None


class ServiceCreate(ServiceBase):
    """Service creation model"""
    pass


class ServiceUpdate(BaseModel):
    """Service update model"""
    service_name: Optional[str] = None
    description: Optional[str] = None
    team: Optional[str] = None
    owner_email: Optional[str] = None
    repository_url: Optional[str] = None
    enabled: Optional[bool] = None
    log_retention_days: Optional[int] = None
    vectorize_logs: Optional[bool] = None
    vectorize_levels: Optional[List[str]] = None
    error_rate_threshold: Optional[float] = None
    anomaly_sensitivity: Optional[str] = None
    alert_email: Optional[List[str]] = None
    alert_slack_channel: Optional[str] = None
    alert_on_new_patterns: Optional[bool] = None
    tags: Optional[List[str]] = None
    environment_tags: Optional[dict] = None


class Service(ServiceBase):
    """Service response model"""
    service_id: UUID
    created_at: str
    updated_at: str


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
# App Config Endpoints
# ============================================================================

@router.get("/config", response_model=List[AppConfig])
async def list_app_configs(
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Get all app configurations"""

    # Try cache
    cache_key = "config:all"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    configs = await db.get_all_app_configs()

    # Cache for 5 minutes
    await cache.set(cache_key, configs, ttl=300)

    return configs


@router.get("/config/{config_key}", response_model=AppConfig)
async def get_app_config(
        config_key: str,
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Get a specific app configuration by key"""

    # Try cache
    cache_key_str = f"config:{config_key}"
    cached = await cache.get(cache_key_str)
    if cached:
        return cached

    config = await db.get_app_config_by_key(config_key)

    if not config:
        raise HTTPException(status_code=404, detail=f"Config key '{config_key}' not found")

    # Cache for 5 minutes
    await cache.set(cache_key_str, config, ttl=300)

    return config


@router.post("/config", response_model=AppConfig, status_code=201)
async def create_app_config(
        config: AppConfigCreate,
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Create a new app configuration"""

    # Check if config already exists
    existing = await db.get_app_config_by_key(config.config_key)
    if existing:
        raise HTTPException(status_code=409, detail=f"Config key '{config.config_key}' already exists")

    # Create config
    new_config = await db.create_app_config(config.model_dump())

    # Invalidate cache
    await cache.delete("config:all")

    return new_config


@router.put("/config/{config_key}", response_model=AppConfig)
async def update_app_config(
        config_key: str,
        config: AppConfigUpdate,
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Update an existing app configuration"""

    # Check if config exists
    existing = await db.get_app_config_by_key(config_key)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Config key '{config_key}' not found")

    # Update config
    updated_config = await db.update_app_config(config_key, config.model_dump(exclude_unset=True))

    # Invalidate cache
    await cache.delete("config:all")
    await cache.delete(f"config:{config_key}")

    return updated_config


@router.delete("/config/{config_key}", status_code=204)
async def delete_app_config(
        config_key: str,
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Delete an app configuration"""

    # Check if config exists
    existing = await db.get_app_config_by_key(config_key)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Config key '{config_key}' not found")

    # Delete config
    await db.delete_app_config(config_key)

    # Invalidate cache
    await cache.delete("config:all")
    await cache.delete(f"config:{config_key}")

    return None


# ============================================================================
# Services Endpoints
# ============================================================================

@router.get("/services", response_model=List[Service])
async def list_services(
        enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Get all services"""

    # Try cache
    cache_key = cache.cache_key("services:all", enabled=enabled)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    services = await db.get_all_services(enabled=enabled)

    # Cache for 5 minutes
    await cache.set(cache_key, services, ttl=300)

    return services


@router.get("/services/{service_name}", response_model=Service)
async def get_service(
        service_name: str,
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Get a specific service by name"""

    # Try cache
    cache_key = f"service:{service_name}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    service = await db.get_service_by_name(service_name)

    if not service:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")

    # Cache for 5 minutes
    await cache.set(cache_key, service, ttl=300)

    return service


@router.post("/services", response_model=Service, status_code=201)
async def create_service(
        service: ServiceCreate,
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Create a new service"""

    # Check if service already exists
    existing = await db.get_service_by_name(service.service_name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Service '{service.service_name}' already exists")

    # Create service
    new_service = await db.create_service(service.model_dump())

    # Invalidate cache
    await cache.delete("services:all")
    await cache.delete(f"services:all:enabled=None")
    await cache.delete(f"services:all:enabled=True")

    return new_service


@router.put("/services/{service_name}", response_model=Service)
async def update_service(
        service_name: str,
        service: ServiceUpdate,
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Update an existing service"""

    # Check if service exists
    existing = await db.get_service_by_name(service_name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")

    # Update service
    updated_service = await db.update_service(service_name, service.model_dump(exclude_unset=True))

    # Invalidate cache
    await cache.delete("services:all")
    await cache.delete(f"services:all:enabled=None")
    await cache.delete(f"services:all:enabled=True")
    await cache.delete(f"services:all:enabled=False")
    await cache.delete(f"service:{service_name}")

    return updated_service


@router.delete("/services/{service_name}", status_code=204)
async def delete_service(
        service_name: str,
        db: DatabaseService = Depends(get_db),
        cache: CacheService = Depends(get_cache)
):
    """Delete a service"""

    # Check if service exists
    existing = await db.get_service_by_name(service_name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")

    # Delete service
    await db.delete_service(service_name)

    # Invalidate cache
    await cache.delete("services:all")
    await cache.delete(f"services:all:enabled=None")
    await cache.delete(f"services:all:enabled=True")
    await cache.delete(f"services:all:enabled=False")
    await cache.delete(f"service:{service_name}")

    return None
