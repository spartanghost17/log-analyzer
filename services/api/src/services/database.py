"""
Database Service
Manages connections to ClickHouse and PostgreSQL databases
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import asyncpg
from pydantic_settings import BaseSettings
from pydantic import Field

from settings import get_logger

logger = get_logger(__name__)

class Settings(BaseSettings):
    """Service configuration"""

    # ClickHouse settings
    clickhouse_host: str = Field(default="localhost", validation_alias="CLICKHOUSE_HOST")
    clickhouse_port: int = Field(default=9000, validation_alias="CLICKHOUSE_PORT")
    clickhouse_user: str = Field(default="admin", validation_alias="CLICKHOUSE_USER")
    clickhouse_password: str = Field(default="clickhouse_password", validation_alias="CLICKHOUSE_PASSWORD")
    clickhouse_database: str = Field(default="logs_db", validation_alias="CLICKHOUSE_DATABASE")

    # PostgreSQL settings
    postgres_host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    postgres_user: str = Field(default="admin", validation_alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres_password", validation_alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="log_analysis", validation_alias="POSTGRES_DB")
    
    class Config:
        env_prefix = ""
        case_sensitive = False

settings = Settings()

class DatabaseService:
    """Service for database operations"""

    def __init__(self):
        self.logger = logger.bind(component="database_service")

        # ClickHouse connection (synchronous)
        self.clickhouse_engine = None

        # PostgreSQL connection (async)
        self.postgres_engine = None
        self.postgres_session_maker = None

    async def connect(self):
        """Initialize database connections"""
        self.logger.info("connecting_to_databases")

        # ClickHouse (synchronous engine)
        clickhouse_url = f"clickhouse+native://{settings.clickhouse_user}:{settings.clickhouse_password}@{settings.clickhouse_host}:{settings.clickhouse_port}/{settings.clickhouse_database}"
        self.clickhouse_engine = create_engine(clickhouse_url, pool_pre_ping=True)

        # PostgreSQL (async engine)
        postgres_url = f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        self.postgres_engine = create_async_engine(postgres_url, echo=False)
        self.postgres_session_maker = sessionmaker(
            self.postgres_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        self.logger.info("database_connections_established")

    async def disconnect(self):
        """Close database connections"""
        self.logger.info("disconnecting_from_databases")

        if self.clickhouse_engine:
            self.clickhouse_engine.dispose()

        if self.postgres_engine:
            await self.postgres_engine.dispose()

        self.logger.info("database_connections_closed")

    async def check_clickhouse_health(self) -> bool:
        """Check ClickHouse connection health"""
        try:
            with self.clickhouse_engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                return result.fetchone()[0] == 1
        except Exception as e:
            self.logger.error("clickhouse_health_check_failed", error=str(e))
            return False

    async def check_postgres_health(self) -> bool:
        """Check PostgreSQL connection health"""
        try:
            async with self.postgres_engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                row = result.fetchone()
                return row[0] == 1
        except Exception as e:
            self.logger.error("postgres_health_check_failed", error=str(e))
            return False

    # ========================================================================
    # ClickHouse Queries
    # ========================================================================

    def get_logs(
            self,
            limit: int = 100,
            offset: int = 0,
            service: Optional[str] = None,
            level: Optional[str] = None,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
            search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query logs from ClickHouse

        Args:
            limit: Number of logs to return
            offset: Offset for pagination
            service: Filter by service name
            level: Filter by log level
            start_time: Filter logs after this time
            end_time: Filter logs before this time
            search: Full-text search in message

        Returns:
            List of log records
        """

        # Build query
        query = """
            SELECT 
                log_id,
                timestamp,
                service,
                environment,
                level,
                message,
                trace_id,
                user_id,
                request_id,
                stack_trace,
                metadata
            FROM logs
            WHERE 1=1
        """

        params = {}

        if service:
            query += " AND service = :service"
            params["service"] = service

        if level:
            query += " AND level = :level"
            params["level"] = level

        if start_time:
            query += " AND timestamp >= :start_time"
            params["start_time"] = start_time

        if end_time:
            query += " AND timestamp <= :end_time"
            params["end_time"] = end_time

        if search:
            query += " AND message LIKE :search"
            params["search"] = f"%{search}%"

        query += " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        # Execute query
        with self.clickhouse_engine.connect() as conn:
            result = conn.execute(text(query), params)

            logs = []
            for row in result:
                logs.append({
                    "log_id": row[0],
                    "timestamp": row[1].isoformat() if row[1] else None,
                    "service": row[2],
                    "environment": row[3],
                    "level": row[4],
                    "message": row[5],
                    "trace_id": row[6],
                    "user_id": row[7],
                    "request_id": row[8],
                    "stack_trace": row[9],
                    "metadata": row[10]
                })

            return logs

    async def get_logs_by_ids(
            self,
            log_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Fetch logs from ClickHouse by their log_ids
        
        Args:
            log_ids: List of log IDs to fetch
            
        Returns:
            List of log records with full details matching the logs table schema
        """
        if not log_ids:
            return []
        
        # Build query with IN clause matching the actual logs table schema
        query = """
            SELECT 
                log_id,
                timestamp,
                service,
                environment,
                host,
                pod_name,
                container_id,
                level,
                logger_name,
                message,
                stack_trace,
                trace_id,
                span_id,
                parent_span_id,
                thread_name,
                user_id,
                request_id,
                correlation_id,
                labels,
                metadata,
                is_vectorized,
                is_anomaly,
                anomaly_score,
                source_type,
                source_file,
                source_line,
                ingested_at,
                processed_at
            FROM logs
            WHERE log_id IN :log_ids
            ORDER BY timestamp DESC
        """
        
        # Execute query
        try:
            with self.clickhouse_engine.connect() as conn:
                # Convert log_ids list to tuple for ClickHouse IN clause
                result = conn.execute(
                    text(query),
                    {"log_ids": tuple(log_ids)}
                )
                
                logs = []
                for row in result:
                    logs.append({
                        "log_id": str(row[0]),
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "service": row[2],
                        "environment": row[3],
                        "host": row[4],
                        "pod_name": row[5],
                        "container_id": row[6],
                        "level": row[7],
                        "logger_name": row[8],
                        "message": row[9],
                        "stack_trace": row[10],
                        "trace_id": str(row[11]) if row[11] else None,
                        "span_id": row[12],
                        "parent_span_id": row[13],
                        "thread_name": row[14],
                        "user_id": row[15],
                        "request_id": str(row[16]) if row[16] else None,
                        "correlation_id": str(row[17]) if row[17] else None,
                        "labels": row[18],
                        "metadata": row[19],
                        "is_vectorized": bool(row[20]) if row[20] is not None else False,
                        "is_anomaly": bool(row[21]) if row[21] is not None else False,
                        "anomaly_score": float(row[22]) if row[22] is not None else 0.0,
                        "source_type": row[23],
                        "source_file": row[24],
                        "source_line": int(row[25]) if row[25] is not None else None,
                        "ingested_at": row[26].isoformat() if row[26] else None,
                        "processed_at": row[27].isoformat() if row[27] else None
                    })
                
                self.logger.info("fetched_logs_by_ids", 
                                requested_count=len(log_ids),
                                found_count=len(logs))
                
                return logs
                
        except Exception as e:
            self.logger.error("get_logs_by_ids_failed", error=str(e), log_ids_sample=log_ids[:3])
            return []

    def get_log_count(
            self,
            service: Optional[str] = None,
            level: Optional[str] = None,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None
    ) -> int:
        """Get total count of logs matching filters"""

        query = "SELECT count() FROM logs WHERE 1=1"
        params = {}

        if service:
            query += " AND service = :service"
            params["service"] = service

        if level:
            query += " AND level = :level"
            params["level"] = level

        if start_time:
            query += " AND timestamp >= :start_time"
            params["start_time"] = start_time

        if end_time:
            query += " AND timestamp <= :end_time"
            params["end_time"] = end_time

        with self.clickhouse_engine.connect() as conn:
            result = conn.execute(text(query), params)
            return result.fetchone()[0]

    def get_hourly_stats(
            self,
            hours: int = 24,
            service: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get hourly log statistics"""

        query = """
            SELECT 
                hour,
                service,
                total_logs,
                error_count,
                warn_count,
                info_count,
                uniqMerge(unique_traces) as unique_traces,
                uniqMerge(unique_users) as unique_users,
                avgMerge(avg_message_length) as avg_message_length
            FROM logs_hourly
            WHERE hour >= now() - INTERVAL :hours HOUR
        """

        params = {"hours": hours}

        if service:
            query += " AND service = :service"
            params["service"] = service

        query += " GROUP BY hour, service ORDER BY hour DESC, service"

        with self.clickhouse_engine.connect() as conn:
            result = conn.execute(text(query), params)

            stats = []
            for row in result:
                stats.append({
                    "hour": row[0].isoformat() if row[0] else None,
                    "service": row[1],
                    "total_logs": row[2],
                    "error_count": row[3],
                    "warn_count": row[4],
                    "info_count": row[5],
                    "unique_traces": row[6],
                    "unique_users": row[7],
                    "avg_message_length": float(row[8]) if row[8] else 0
                })

            return stats

    def get_service_stats(self) -> List[Dict[str, Any]]:
        """Get statistics by service"""

        query = """
            SELECT 
                service,
                count() as total_logs,
                countIf(level = 'ERROR') as error_count,
                countIf(level = 'WARN') as warn_count,
                countIf(level = 'INFO') as info_count,
                uniq(trace_id) as unique_traces
            FROM logs
            WHERE timestamp >= now() - INTERVAL 24 HOUR
            GROUP BY service
            ORDER BY total_logs DESC
        """

        with self.clickhouse_engine.connect() as conn:
            result = conn.execute(text(query))

            stats = []
            for row in result:
                stats.append({
                    "service": row[0],
                    "total_logs": row[1],
                    "error_count": row[2],
                    "warn_count": row[3],
                    "info_count": row[4],
                    "unique_traces": row[5]
                })

            return stats

    def get_error_trends(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get error trends over time"""

        query = """
            SELECT 
                toStartOfHour(timestamp) as hour,
                service,
                count() as error_count
            FROM logs
            WHERE level IN ('ERROR', 'FATAL')
              AND timestamp >= now() - INTERVAL :hours HOUR
            GROUP BY hour, service
            ORDER BY hour DESC, service
        """

        with self.clickhouse_engine.connect() as conn:
            result = conn.execute(text(query), {"hours": hours})

            trends = []
            for row in result:
                trends.append({
                    "hour": row[0].isoformat() if row[0] else None,
                    "service": row[1],
                    "error_count": row[2]
                })

            return trends

    # ========================================================================
    # PostgreSQL Queries
    # ========================================================================

    async def get_analysis_reports(
            self,
            limit: int = 10,
            offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get LLM analysis reports from PostgreSQL nightly_reports table"""

        query = """
            SELECT 
                report_id,
                report_date,
                start_time,
                end_time,
                total_logs_processed,
                error_count,
                warning_count,
                unique_error_patterns,
                new_error_patterns,
                anomalies_detected,
                critical_issues,
                executive_summary,
                top_issues,
                recommendations,
                affected_services,
                generation_time_seconds,
                llm_model_used,
                tokens_used,
                status,
                error_message,
                created_at
            FROM nightly_reports
            ORDER BY report_date DESC
            LIMIT :limit OFFSET :offset
        """

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(
                text(query),
                {"limit": limit, "offset": offset}
            )

            reports = []
            for row in result:
                reports.append({
                    "report_id": str(row[0]),
                    "report_date": row[1].isoformat() if row[1] else None,
                    "start_time": row[2].isoformat() if row[2] else None,
                    "end_time": row[3].isoformat() if row[3] else None,
                    "total_logs_processed": row[4] or 0,
                    "error_count": row[5] or 0,
                    "warning_count": row[6] or 0,
                    "unique_error_patterns": row[7] or 0,
                    "new_error_patterns": row[8] or 0,
                    "anomalies_detected": row[9] or 0,
                    "critical_issues": row[10] or 0,
                    "executive_summary": row[11] or "",
                    "top_issues": row[12] if row[12] else [],
                    "recommendations": row[13] if row[13] else [],
                    "affected_services": row[14] if row[14] else [],
                    "generation_time_seconds": float(row[15]) if row[15] else 0.0,
                    "llm_model_used": row[16],
                    "tokens_used": row[17],
                    "status": row[18] or "completed",
                    "error_message": row[19],
                    "created_at": row[20].isoformat() if row[20] else None
                })

            return reports

    async def get_latest_report(self) -> Optional[Dict[str, Any]]:
        """Get the most recent analysis report"""

        reports = await self.get_analysis_reports(limit=1)
        return reports[0] if reports else None

    async def get_report_count(self) -> int:
        """Get total count of analysis reports"""

        query = "SELECT COUNT(*) FROM nightly_reports"

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query))
            return result.fetchone()[0]

    async def get_report_by_id(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific analysis report by ID"""

        query = """
            SELECT
                report_id,
                report_date,
                start_time,
                end_time,
                total_logs_processed,
                error_count,
                warning_count,
                unique_error_patterns,
                new_error_patterns,
                anomalies_detected,
                critical_issues,
                executive_summary,
                top_issues,
                recommendations,
                affected_services,
                generation_time_seconds,
                llm_model_used,
                tokens_used,
                status,
                error_message,
                created_at
            FROM nightly_reports
            WHERE report_id = :report_id
            LIMIT 1
        """

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query), {"report_id": report_id})
            row = result.fetchone()

            if not row:
                return None

            return {
                "report_id": str(row[0]),
                "report_date": row[1].isoformat() if row[1] else None,
                "start_time": row[2].isoformat() if row[2] else None,
                "end_time": row[3].isoformat() if row[3] else None,
                "total_logs_processed": row[4] or 0,
                "error_count": row[5] or 0,
                "warning_count": row[6] or 0,
                "unique_error_patterns": row[7] or 0,
                "new_error_patterns": row[8] or 0,
                "anomalies_detected": row[9] or 0,
                "critical_issues": row[10] or 0,
                "executive_summary": row[11] or "",
                "top_issues": row[12] if row[12] else [],
                "recommendations": row[13] if row[13] else [],
                "affected_services": row[14] if row[14] else [],
                "generation_time_seconds": float(row[15]) if row[15] else 0.0,
                "llm_model_used": row[16],
                "tokens_used": row[17],
                "status": row[18] or "completed",
                "error_message": row[19],
                "created_at": row[20].isoformat() if row[20] else None
            }

    # ========================================================================
    # App Config Queries
    # ========================================================================

    async def get_all_app_configs(self) -> List[Dict[str, Any]]:
        """Get all app configurations"""

        query = """
            SELECT
                config_id,
                config_key,
                config_value,
                description,
                is_encrypted,
                created_at,
                updated_at
            FROM app_config
            ORDER BY config_key
        """

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query))

            configs = []
            for row in result:
                configs.append({
                    "config_id": str(row[0]),
                    "config_key": row[1],
                    "config_value": row[2],
                    "description": row[3],
                    "is_encrypted": row[4],
                    "created_at": row[5].isoformat() if row[5] else None,
                    "updated_at": row[6].isoformat() if row[6] else None
                })

            return configs

    async def get_app_config_by_key(self, config_key: str) -> Optional[Dict[str, Any]]:
        """Get a specific app configuration by key"""

        query = """
            SELECT
                config_id,
                config_key,
                config_value,
                description,
                is_encrypted,
                created_at,
                updated_at
            FROM app_config
            WHERE config_key = :config_key
            LIMIT 1
        """

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query), {"config_key": config_key})
            row = result.fetchone()

            if not row:
                return None

            return {
                "config_id": str(row[0]),
                "config_key": row[1],
                "config_value": row[2],
                "description": row[3],
                "is_encrypted": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None
            }

    async def create_app_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new app configuration"""

        query = """
            INSERT INTO app_config (config_key, config_value, description, is_encrypted)
            VALUES (:config_key, CAST(:config_value AS jsonb), :description, :is_encrypted)
            RETURNING config_id, config_key, config_value, description, is_encrypted, created_at, updated_at
        """

        async with self.postgres_engine.begin() as conn:
            result = await conn.execute(
                text(query),
                {
                    "config_key": config_data["config_key"],
                    "config_value": str(config_data["config_value"]),
                    "description": config_data.get("description"),
                    "is_encrypted": config_data.get("is_encrypted", False)
                }
            )
            row = result.fetchone()

            return {
                "config_id": str(row[0]),
                "config_key": row[1],
                "config_value": row[2],
                "description": row[3],
                "is_encrypted": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None
            }

    async def update_app_config(self, config_key: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing app configuration"""

        # Build dynamic update query
        updates = []
        params = {"config_key": config_key}

        if "config_value" in config_data:
            updates.append("config_value = CAST(:config_value AS jsonb)")
            params["config_value"] = str(config_data["config_value"])

        if "description" in config_data:
            updates.append("description = :description")
            params["description"] = config_data["description"]

        if "is_encrypted" in config_data:
            updates.append("is_encrypted = :is_encrypted")
            params["is_encrypted"] = config_data["is_encrypted"]

        query = f"""
            UPDATE app_config
            SET {", ".join(updates)}
            WHERE config_key = :config_key
            RETURNING config_id, config_key, config_value, description, is_encrypted, created_at, updated_at
        """

        async with self.postgres_engine.begin() as conn:
            result = await conn.execute(text(query), params)
            row = result.fetchone()

            return {
                "config_id": str(row[0]),
                "config_key": row[1],
                "config_value": row[2],
                "description": row[3],
                "is_encrypted": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None
            }

    async def delete_app_config(self, config_key: str):
        """Delete an app configuration"""

        query = "DELETE FROM app_config WHERE config_key = :config_key"

        async with self.postgres_engine.begin() as conn:
            await conn.execute(text(query), {"config_key": config_key})

    # ========================================================================
    # Services Queries
    # ========================================================================

    async def get_all_services(self, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get all services"""

        query = """
            SELECT
                service_id,
                service_name,
                description,
                team,
                owner_email,
                repository_url,
                enabled,
                log_retention_days,
                vectorize_logs,
                vectorize_levels,
                error_rate_threshold,
                anomaly_sensitivity,
                alert_email,
                alert_slack_channel,
                alert_on_new_patterns,
                tags,
                environment_tags,
                created_at,
                updated_at
            FROM services
        """

        params = {}
        if enabled is not None:
            query += " WHERE enabled = :enabled"
            params["enabled"] = enabled

        query += " ORDER BY service_name"

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query), params)

            services = []
            for row in result:
                services.append({
                    "service_id": str(row[0]),
                    "service_name": row[1],
                    "description": row[2],
                    "team": row[3],
                    "owner_email": row[4],
                    "repository_url": row[5],
                    "enabled": row[6],
                    "log_retention_days": row[7],
                    "vectorize_logs": row[8],
                    "vectorize_levels": row[9],
                    "error_rate_threshold": row[10],
                    "anomaly_sensitivity": row[11],
                    "alert_email": row[12],
                    "alert_slack_channel": row[13],
                    "alert_on_new_patterns": row[14],
                    "tags": row[15],
                    "environment_tags": row[16],
                    "created_at": row[17].isoformat() if row[17] else None,
                    "updated_at": row[18].isoformat() if row[18] else None
                })

            return services

    async def get_service_by_name(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific service by name"""

        query = """
            SELECT
                service_id,
                service_name,
                description,
                team,
                owner_email,
                repository_url,
                enabled,
                log_retention_days,
                vectorize_logs,
                vectorize_levels,
                error_rate_threshold,
                anomaly_sensitivity,
                alert_email,
                alert_slack_channel,
                alert_on_new_patterns,
                tags,
                environment_tags,
                created_at,
                updated_at
            FROM services
            WHERE service_name = :service_name
            LIMIT 1
        """

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query), {"service_name": service_name})
            row = result.fetchone()

            if not row:
                return None

            return {
                "service_id": str(row[0]),
                "service_name": row[1],
                "description": row[2],
                "team": row[3],
                "owner_email": row[4],
                "repository_url": row[5],
                "enabled": row[6],
                "log_retention_days": row[7],
                "vectorize_logs": row[8],
                "vectorize_levels": row[9],
                "error_rate_threshold": row[10],
                "anomaly_sensitivity": row[11],
                "alert_email": row[12],
                "alert_slack_channel": row[13],
                "alert_on_new_patterns": row[14],
                "tags": row[15],
                "environment_tags": row[16],
                "created_at": row[17].isoformat() if row[17] else None,
                "updated_at": row[18].isoformat() if row[18] else None
            }

    async def create_service(self, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new service"""

        import json

        query = """
            INSERT INTO services (
                service_name, description, team, owner_email, repository_url,
                enabled, log_retention_days, vectorize_logs, vectorize_levels,
                error_rate_threshold, anomaly_sensitivity, alert_email,
                alert_slack_channel, alert_on_new_patterns, tags, environment_tags
            )
            VALUES (
                :service_name, :description, :team, :owner_email, :repository_url,
                :enabled, :log_retention_days, :vectorize_logs, :vectorize_levels,
                :error_rate_threshold, :anomaly_sensitivity, :alert_email,
                :alert_slack_channel, :alert_on_new_patterns, :tags, CAST(:environment_tags AS jsonb)
            )
            RETURNING service_id, service_name, description, team, owner_email, repository_url,
                      enabled, log_retention_days, vectorize_logs, vectorize_levels,
                      error_rate_threshold, anomaly_sensitivity, alert_email,
                      alert_slack_channel, alert_on_new_patterns, tags, environment_tags,
                      created_at, updated_at
        """

        async with self.postgres_engine.begin() as conn:
            result = await conn.execute(
                text(query),
                {
                    "service_name": service_data["service_name"],
                    "description": service_data.get("description"),
                    "team": service_data.get("team"),
                    "owner_email": service_data.get("owner_email"),
                    "repository_url": service_data.get("repository_url"),
                    "enabled": service_data.get("enabled", True),
                    "log_retention_days": service_data.get("log_retention_days", 90),
                    "vectorize_logs": service_data.get("vectorize_logs", True),
                    "vectorize_levels": service_data.get("vectorize_levels", ['WARN', 'ERROR', 'FATAL']),
                    "error_rate_threshold": service_data.get("error_rate_threshold"),
                    "anomaly_sensitivity": service_data.get("anomaly_sensitivity", 'medium'),
                    "alert_email": service_data.get("alert_email", []),
                    "alert_slack_channel": service_data.get("alert_slack_channel"),
                    "alert_on_new_patterns": service_data.get("alert_on_new_patterns", True),
                    "tags": service_data.get("tags", []),
                    "environment_tags": json.dumps(service_data.get("environment_tags")) if service_data.get("environment_tags") else None
                }
            )
            row = result.fetchone()

            return {
                "service_id": str(row[0]),
                "service_name": row[1],
                "description": row[2],
                "team": row[3],
                "owner_email": row[4],
                "repository_url": row[5],
                "enabled": row[6],
                "log_retention_days": row[7],
                "vectorize_logs": row[8],
                "vectorize_levels": row[9],
                "error_rate_threshold": row[10],
                "anomaly_sensitivity": row[11],
                "alert_email": row[12],
                "alert_slack_channel": row[13],
                "alert_on_new_patterns": row[14],
                "tags": row[15],
                "environment_tags": row[16],
                "created_at": row[17].isoformat() if row[17] else None,
                "updated_at": row[18].isoformat() if row[18] else None
            }

    async def update_service(self, service_name: str, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing service"""

        import json

        # Build dynamic update query
        updates = []
        params = {"service_name": service_name}

        field_mapping = {
            "description": "description",
            "team": "team",
            "owner_email": "owner_email",
            "repository_url": "repository_url",
            "enabled": "enabled",
            "log_retention_days": "log_retention_days",
            "vectorize_logs": "vectorize_logs",
            "vectorize_levels": "vectorize_levels",
            "error_rate_threshold": "error_rate_threshold",
            "anomaly_sensitivity": "anomaly_sensitivity",
            "alert_email": "alert_email",
            "alert_slack_channel": "alert_slack_channel",
            "alert_on_new_patterns": "alert_on_new_patterns",
            "tags": "tags"
        }

        for field, db_field in field_mapping.items():
            if field in service_data:
                updates.append(f"{db_field} = :{field}")
                params[field] = service_data[field]

        if "environment_tags" in service_data:
            updates.append("environment_tags = CAST(:environment_tags AS jsonb)")
            params["environment_tags"] = json.dumps(service_data["environment_tags"]) if service_data["environment_tags"] else None

        query = f"""
            UPDATE services
            SET {", ".join(updates)}
            WHERE service_name = :service_name
            RETURNING service_id, service_name, description, team, owner_email, repository_url,
                      enabled, log_retention_days, vectorize_logs, vectorize_levels,
                      error_rate_threshold, anomaly_sensitivity, alert_email,
                      alert_slack_channel, alert_on_new_patterns, tags, environment_tags,
                      created_at, updated_at
        """

        async with self.postgres_engine.begin() as conn:
            result = await conn.execute(text(query), params)
            row = result.fetchone()

            return {
                "service_id": str(row[0]),
                "service_name": row[1],
                "description": row[2],
                "team": row[3],
                "owner_email": row[4],
                "repository_url": row[5],
                "enabled": row[6],
                "log_retention_days": row[7],
                "vectorize_logs": row[8],
                "vectorize_levels": row[9],
                "error_rate_threshold": row[10],
                "anomaly_sensitivity": row[11],
                "alert_email": row[12],
                "alert_slack_channel": row[13],
                "alert_on_new_patterns": row[14],
                "tags": row[15],
                "environment_tags": row[16],
                "created_at": row[17].isoformat() if row[17] else None,
                "updated_at": row[18].isoformat() if row[18] else None
            }

    async def delete_service(self, service_name: str):
        """Delete a service"""

        query = "DELETE FROM services WHERE service_name = :service_name"

        async with self.postgres_engine.begin() as conn:
            await conn.execute(text(query), {"service_name": service_name})

    # ========================================================================
    # Anomaly Alerts Queries (PostgreSQL)
    # ========================================================================

    async def get_anomalies(
        self,
        limit: int = 50,
        offset: int = 0,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        service: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Query anomaly alerts from PostgreSQL"""

        import json

        # Build WHERE clause
        where_clauses = []
        params = {"limit": limit, "offset": offset}

        if severity:
            where_clauses.append("severity = :severity")
            params["severity"] = severity

        if status:
            where_clauses.append("status = :status")
            params["status"] = status

        if service:
            where_clauses.append("service = :service")
            params["service"] = service

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
            SELECT
                alert_id,
                anomaly_type,
                detected_at,
                service,
                environment,
                severity,
                description,
                confidence_score,
                status,
                metrics,
                llm_analysis,
                suggested_actions,
                acknowledged_by,
                acknowledged_at,
                resolved_by,
                resolved_at
            FROM anomaly_alerts
            {where_sql}
            ORDER BY detected_at DESC
            LIMIT :limit OFFSET :offset
        """

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query), params)
            rows = result.fetchall()

            return [
                {
                    "alert_id": str(row[0]),
                    "anomaly_type": row[1],
                    "detected_at": row[2].isoformat() if row[2] else None,
                    "service": row[3],
                    "environment": row[4],
                    "severity": row[5],
                    "description": row[6],
                    "confidence_score": float(row[7]) if row[7] else 0.0,
                    "status": row[8],
                    "metrics": row[9] if row[9] else {},
                    "llm_analysis": row[10],
                    "suggested_actions": row[11] if row[11] else [],
                    "acknowledged_by": row[12],
                    "acknowledged_at": row[13].isoformat() if row[13] else None,
                    "resolved_by": row[14],
                    "resolved_at": row[15].isoformat() if row[15] else None,
                }
                for row in rows
            ]

    async def get_anomalies_count(
        self,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        service: Optional[str] = None
    ) -> int:
        """Get total count of anomalies matching filters"""

        # Build WHERE clause
        where_clauses = []
        params = {}

        if severity:
            where_clauses.append("severity = :severity")
            params["severity"] = severity

        if status:
            where_clauses.append("status = :status")
            params["status"] = status

        if service:
            where_clauses.append("service = :service")
            params["service"] = service

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
            SELECT COUNT(*) as count
            FROM anomaly_alerts
            {where_sql}
        """

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query), params)
            row = result.fetchone()
            return row[0] if row else 0

    async def get_anomaly_by_id(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific anomaly by ID"""

        import json

        query = """
            SELECT
                alert_id,
                anomaly_type,
                detected_at,
                service,
                environment,
                severity,
                description,
                confidence_score,
                status,
                metrics,
                llm_analysis,
                suggested_actions,
                acknowledged_by,
                acknowledged_at,
                resolved_by,
                resolved_at
            FROM anomaly_alerts
            WHERE alert_id = :alert_id
        """

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query), {"alert_id": alert_id})
            row = result.fetchone()

            if not row:
                return None

            return {
                "alert_id": str(row[0]),
                "anomaly_type": row[1],
                "detected_at": row[2].isoformat() if row[2] else None,
                "service": row[3],
                "environment": row[4],
                "severity": row[5],
                "description": row[6],
                "confidence_score": float(row[7]) if row[7] else 0.0,
                "status": row[8],
                "metrics": row[9] if row[9] else {},
                "llm_analysis": row[10],
                "suggested_actions": row[11] if row[11] else [],
                "acknowledged_by": row[12],
                "acknowledged_at": row[13].isoformat() if row[13] else None,
                "resolved_by": row[14],
                "resolved_at": row[15].isoformat() if row[15] else None,
            }

    async def acknowledge_anomaly(
        self,
        alert_id: str,
        acknowledged_by: str = "system"
    ) -> Dict[str, Any]:
        """Acknowledge an anomaly alert"""

        query = """
            UPDATE anomaly_alerts
            SET
                status = 'acknowledged',
                acknowledged_by = :acknowledged_by,
                acknowledged_at = NOW(),
                updated_at = NOW()
            WHERE alert_id = :alert_id
            RETURNING
                alert_id,
                anomaly_type,
                detected_at,
                service,
                environment,
                severity,
                description,
                confidence_score,
                status,
                metrics,
                llm_analysis,
                suggested_actions,
                acknowledged_by,
                acknowledged_at,
                resolved_by,
                resolved_at
        """

        async with self.postgres_engine.begin() as conn:
            result = await conn.execute(
                text(query),
                {"alert_id": alert_id, "acknowledged_by": acknowledged_by}
            )
            row = result.fetchone()

            return {
                "alert_id": str(row[0]),
                "anomaly_type": row[1],
                "detected_at": row[2].isoformat() if row[2] else None,
                "service": row[3],
                "environment": row[4],
                "severity": row[5],
                "description": row[6],
                "confidence_score": float(row[7]) if row[7] else 0.0,
                "status": row[8],
                "metrics": row[9] if row[9] else {},
                "llm_analysis": row[10],
                "suggested_actions": row[11] if row[11] else [],
                "acknowledged_by": row[12],
                "acknowledged_at": row[13].isoformat() if row[13] else None,
                "resolved_by": row[14],
                "resolved_at": row[15].isoformat() if row[15] else None,
            }

    async def resolve_anomaly(
        self,
        alert_id: str,
        resolved_by: str = "system",
        resolution_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve an anomaly alert"""

        query = """
            UPDATE anomaly_alerts
            SET
                status = 'resolved',
                resolved_by = :resolved_by,
                resolved_at = NOW(),
                resolution_notes = :resolution_notes,
                updated_at = NOW()
            WHERE alert_id = :alert_id
            RETURNING
                alert_id,
                anomaly_type,
                detected_at,
                service,
                environment,
                severity,
                description,
                confidence_score,
                status,
                metrics,
                llm_analysis,
                suggested_actions,
                acknowledged_by,
                acknowledged_at,
                resolved_by,
                resolved_at
        """

        async with self.postgres_engine.begin() as conn:
            result = await conn.execute(
                text(query),
                {
                    "alert_id": alert_id,
                    "resolved_by": resolved_by,
                    "resolution_notes": resolution_notes
                }
            )
            row = result.fetchone()

            return {
                "alert_id": str(row[0]),
                "anomaly_type": row[1],
                "detected_at": row[2].isoformat() if row[2] else None,
                "service": row[3],
                "environment": row[4],
                "severity": row[5],
                "description": row[6],
                "confidence_score": float(row[7]) if row[7] else 0.0,
                "status": row[8],
                "metrics": row[9] if row[9] else {},
                "llm_analysis": row[10],
                "suggested_actions": row[11] if row[11] else [],
                "acknowledged_by": row[12],
                "acknowledged_at": row[13].isoformat() if row[13] else None,
                "resolved_by": row[14],
                "resolved_at": row[15].isoformat() if row[15] else None,
            }

    async def get_anomaly_stats(self) -> Dict[str, Any]:
        """Get anomaly statistics"""

        query = """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE severity = 'critical') as critical_count,
                COUNT(*) FILTER (WHERE severity = 'high') as high_count,
                COUNT(*) FILTER (WHERE severity = 'medium') as medium_count,
                COUNT(*) FILTER (WHERE severity = 'low') as low_count,
                COUNT(*) FILTER (WHERE status = 'new') as new_count,
                COUNT(*) FILTER (WHERE status = 'acknowledged') as acknowledged_count,
                COUNT(*) FILTER (WHERE status = 'resolved') as resolved_count,
                AVG(confidence_score) as avg_confidence
            FROM anomaly_alerts
        """

        async with self.postgres_engine.connect() as conn:
            result = await conn.execute(text(query))
            row = result.fetchone()

            return {
                "total": row[0] if row else 0,
                "by_severity": {
                    "critical": row[1] if row else 0,
                    "high": row[2] if row else 0,
                    "medium": row[3] if row else 0,
                    "low": row[4] if row else 0,
                },
                "by_status": {
                    "new": row[5] if row else 0,
                    "acknowledged": row[6] if row else 0,
                    "resolved": row[7] if row else 0,
                },
                "avg_confidence": float(row[8]) if row and row[8] else 0.0,
            }

    # ========================================================================
    # Z-Score Anomaly Detection Queries (ClickHouse)
    # ========================================================================

    def get_zscore_data(
        self,
        start_time: datetime,
        end_time: datetime,
        level: str,
        service: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query hourly log counts with baseline data for Z-score calculation
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            level: Log level to analyze
            service: Optional service filter
            
        Returns:
            List of hourly data points with baselines
        """
        
        # Build WHERE clause
        where_clauses = [
            "hour >= toDateTime(:start_time)",
            "hour <= toDateTime(:end_time)",
            "level = :level"
        ]
        
        if service:
            where_clauses.append("service = :service")
        
        query = f"""
            SELECT
                h.hour,
                h.service,
                h.environment,
                h.level,
                h.log_count,
                b.mean_count,
                b.stddev_count,
                b.upper_threshold,
                b.lower_threshold
            FROM logs_hourly_agg h
            LEFT JOIN anomaly_baselines b ON (
                h.service = b.service 
                AND h.environment = b.environment
                AND h.level = b.level
                AND toHour(h.hour) = b.hour_of_day
                AND toDayOfWeek(h.hour) = b.day_of_week
            )
            WHERE {' AND '.join(where_clauses)}
            ORDER BY h.hour ASC
        """
        
        params = {
            "start_time": start_time.strftime('%Y-%m-%d %H:00:00'),
            "end_time": end_time.strftime('%Y-%m-%d %H:00:00'),
            "level": level
        }
        
        if service:
            params["service"] = service
        
        # Execute query
        with self.clickhouse_engine.connect() as conn:
            result = conn.execute(text(query), params)
            
            data_points = []
            for row in result:
                data_points.append({
                    "hour": row[0],
                    "service": row[1],
                    "environment": row[2],
                    "level": row[3],
                    "actual_count": int(row[4]),
                    "baseline_mean": float(row[5]) if row[5] is not None else None,
                    "baseline_stddev": float(row[6]) if row[6] is not None else None,
                    "upper_threshold": float(row[7]) if row[7] is not None else None,
                    "lower_threshold": float(row[8]) if row[8] is not None else None,
                })
            
            return data_points

    def get_available_services_with_baselines(self) -> List[str]:
        """
        Get list of services that have anomaly baselines configured in ClickHouse
        
        Returns:
            List of service names
        """
        query = """
            SELECT DISTINCT service
            FROM anomaly_baselines
            ORDER BY service
        """
        
        with self.clickhouse_engine.connect() as conn:
            result = conn.execute(text(query))
            return [row[0] for row in result]