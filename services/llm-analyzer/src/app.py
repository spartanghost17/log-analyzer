"""
LLM Analyzer Service - ENHANCED VERSION
Analyzes log patterns using local LLM (Ollama)
Queries ClickHouse, generates insights, updates multiple tables
Properly implements all table responsibilities per architecture
"""

import hashlib
import json
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional, Dict, Any
from uuid import uuid4

import clickhouse_connect
from clickhouse_connect.driver.client import Client as ClickHouseClient
import httpx
from fastapi import FastAPI, HTTPException, status, BackgroundTasks
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    BigInteger,
    Text,
    DateTime,
    Date,
    Float,
    Boolean,
    JSON,
    ARRAY
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import IntegrityError
from settings import setup_development_logging
import structlog


setup_development_logging()
logger = structlog.get_logger()

# Prometheus metrics
ANALYSES_TOTAL = Counter('analyses_total', 'Total analyses performed')
ANALYSES_FAILED = Counter('analyses_failed_total', 'Failed analyses')
ANALYSIS_DURATION = Histogram('analysis_duration_seconds', 'Analysis duration')
PATTERNS_DETECTED = Gauge('patterns_detected', 'Number of patterns detected')
ANOMALIES_DETECTED = Gauge('anomalies_detected', 'Number of anomalies detected')
ERROR_PATTERNS_CREATED = Counter('error_patterns_created_total', 'Error patterns created in ClickHouse')
ANOMALY_ALERTS_CREATED = Counter('anomaly_alerts_created_total', 'Anomaly alerts created')


# =============================================================================
# Configuration
# =============================================================================

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

    # Ollama settings
    ollama_host: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_HOST")
    ollama_model: str = Field(default="deepseek-coder:6.7b", validation_alias="OLLAMA_MODEL")
    ollama_timeout: int = Field(default=300, validation_alias="OLLAMA_TIMEOUT")

    # Analysis settings
    analysis_window_hours: int = Field(default=24, ge=1, le=168, validation_alias="ANALYSIS_WINDOW_HOURS")
    anomaly_z_score_threshold: float = Field(default=2.5, validation_alias="ANOMALY_Z_SCORE_THRESHOLD")

    # API settings
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8002, validation_alias="API_PORT")


# =============================================================================
# PostgreSQL ORM Models (matching actual schema)
# =============================================================================

Base = declarative_base()


class NightlyReport(Base):
    """Nightly reports table - matches PostgreSQL schema"""
    __tablename__ = 'nightly_reports'

    report_id = Column(UUID(as_uuid=True), primary_key=True)
    report_date = Column(Date, nullable=False, unique=True)

    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    total_logs_processed = Column(BigInteger)
    error_count = Column(BigInteger)
    warning_count = Column(BigInteger)
    unique_error_patterns = Column(Integer)
    new_error_patterns = Column(Integer)

    anomalies_detected = Column(Integer)
    critical_issues = Column(Integer)

    executive_summary = Column(Text)
    top_issues = Column(JSON)
    recommendations = Column(JSON)

    affected_services = Column(JSON)

    generation_time_seconds = Column(Float)
    llm_model_used = Column(String(100))
    tokens_used = Column(Integer)

    status = Column(String(50), default='completed')
    error_message = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ErrorCatalog(Base):
    """Error catalog table - matches PostgreSQL schema"""
    __tablename__ = 'error_catalog'

    catalog_id = Column(UUID(as_uuid=True), primary_key=True)

    pattern_name = Column(String(255), nullable=False)
    error_hash = Column(String(64), unique=True)
    pattern_regex = Column(Text)

    category = Column(String(100))
    severity = Column(String(50))
    tags = Column(ARRAY(Text))

    description = Column(Text)
    typical_causes = Column(ARRAY(Text))
    common_solutions = Column(ARRAY(Text))
    documentation_links = Column(ARRAY(Text))

    is_known_issue = Column(Boolean, default=False)
    is_expected = Column(Boolean, default=False)
    auto_created = Column(Boolean, default=False)

    related_patterns = Column(ARRAY(UUID(as_uuid=True)))

    avg_resolution_time = Column(String)  # Stored as interval string
    last_occurrence = Column(DateTime(timezone=True))
    total_occurrences = Column(BigInteger, default=0)

    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AnomalyAlert(Base):
    """Anomaly alerts table - matches PostgreSQL schema"""
    __tablename__ = 'anomaly_alerts'

    alert_id = Column(UUID(as_uuid=True), primary_key=True)

    anomaly_type = Column(String(50), nullable=False)
    detected_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    service = Column(String(255))
    environment = Column(String(50))
    time_window = Column(String)  # Stored as interval string

    description = Column(Text)
    metrics = Column(JSON)
    affected_log_ids = Column(ARRAY(UUID(as_uuid=True)))
    sample_logs = Column(JSON)

    clickhouse_query = Column(Text)
    qdrant_point_ids = Column(ARRAY(Text))

    severity = Column(String(50))
    confidence_score = Column(Float)

    llm_analysis = Column(Text)
    suggested_actions = Column(JSON)

    status = Column(String(50), default='new')
    acknowledged_by = Column(String(255))
    acknowledged_at = Column(DateTime(timezone=True))
    resolution_notes = Column(Text)
    resolved_at = Column(DateTime(timezone=True))

    notifications_sent = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AnalysisJob(Base):
    """Analysis jobs table - matches PostgreSQL schema"""
    __tablename__ = 'analysis_jobs'

    job_id = Column(UUID(as_uuid=True), primary_key=True)
    job_type = Column(String(50), nullable=False)

    parameters = Column(JSON)

    status = Column(String(50), default='pending')
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    result = Column(JSON)
    error_message = Column(Text)

    processing_time_seconds = Column(Float)
    tokens_used = Column(Integer)
    model_used = Column(String(100))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# =============================================================================
# Pydantic Models for API
# =============================================================================

class AnalysisRequest(BaseModel):
    """Analysis request parameters"""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    services: Optional[List[str]] = None


class PatternInfo(BaseModel):
    """Error pattern information"""
    pattern_hash: str
    normalized_message: str
    count: int
    services: List[str]
    example_message: str
    first_seen: datetime
    last_seen: datetime
    max_level: str
    sample_log_ids: List[str] = []  # Store sample log IDs for investigation


class AnalysisResponse(BaseModel):
    """Analysis response"""
    job_id: str
    report_id: str
    report_date: str
    total_logs: int
    error_count: int
    unique_patterns: int
    anomalies_detected: int
    executive_summary: str
    generation_time_seconds: float
    status: str


class ReportResponse(BaseModel):
    """Full report response"""
    report_id: str
    report_date: str
    start_time: str
    end_time: str
    total_logs_processed: int
    error_count: int
    unique_error_patterns: int
    anomalies_detected: int
    executive_summary: str
    top_issues: List[Dict[str, Any]]
    recommendations: List[str]
    generation_time_seconds: float


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    clickhouse_connected: bool
    postgres_connected: bool
    ollama_connected: bool
    last_analysis: Optional[str]


# =============================================================================
# Main Analyzer Service
# =============================================================================

class LLMAnalyzerService:
    """Enhanced LLM-powered log analyzer with full table utilization"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = logger.bind(component="llm-analyzer")

        # Database connections
        self.ch_client: Optional[ClickHouseClient] = None
        self.postgres_engine = None
        self.SessionLocal = None

        # HTTP client for Ollama
        self.http_client: Optional[httpx.AsyncClient] = None

        # State
        self.last_analysis_time: Optional[datetime] = None

    # -------------------------------------------------------------------------
    # Setup Methods
    # -------------------------------------------------------------------------

    def setup_clickhouse(self):
        """Setup ClickHouse connection"""
        try:
            self.ch_client = clickhouse_connect.get_client(
                host=self.settings.clickhouse_host,
                port=self.settings.clickhouse_port,
                username=self.settings.clickhouse_user,
                password=self.settings.clickhouse_password,
                database=self.settings.clickhouse_database,
                connect_timeout=10,
                send_receive_timeout=60,
            )

            # Test connection
            self.ch_client.query("SELECT 1")
            self.logger.info("clickhouse_connected")

        except Exception as e:
            self.logger.error("clickhouse_connection_failed", error=str(e))
            raise

    def setup_postgres(self):
        """Setup PostgreSQL connection"""
        try:
            url = (
                f"postgresql://{self.settings.postgres_user}:"
                f"{self.settings.postgres_password}@"
                f"{self.settings.postgres_host}:{self.settings.postgres_port}/"
                f"{self.settings.postgres_db}"
            )

            self.postgres_engine = create_engine(url, pool_pre_ping=True)
            self.SessionLocal = sessionmaker(bind=self.postgres_engine)

            # Create tables if they don't exist (schema should already exist from init.sql)
            # Base.metadata.create_all(self.postgres_engine)

            self.logger.info("postgres_connected")

        except Exception as e:
            self.logger.error("postgres_connection_failed", error=str(e))
            raise

    async def setup_http_client(self):
        """Setup HTTP client for Ollama"""
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.ollama_timeout)
        )

        try:
            response = await self.http_client.get(f"{self.settings.ollama_host}/api/tags")
            if response.status_code == 200:
                self.logger.info("ollama_connected")
            else:
                self.logger.warning("ollama_unhealthy", status=response.status_code)
        except Exception as e:
            self.logger.error("ollama_connection_failed", error=str(e))

    # -------------------------------------------------------------------------
    # Pattern Detection & Normalization
    # -------------------------------------------------------------------------

    def normalize_error_message(self, message: str) -> str:
        """Normalize error message for pattern detection"""
        # Remove UUIDs
        message = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '<UUID>', message, flags=re.IGNORECASE
        )
        # Remove numbers
        message = re.sub(r'\b\d+\b', '<NUM>', message)
        # Remove timestamps
        message = re.sub(
            r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}',
            '<TIMESTAMP>', message
        )
        # Remove IPs
        message = re.sub(
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            '<IP>', message
        )
        # Remove hex strings
        message = re.sub(r'\b0x[0-9a-fA-F]+\b', '<HEX>', message)
        # Normalize whitespace
        message = ' '.join(message.split())

        return message

    def compute_pattern_hash(self, normalized_message: str) -> str:
        """Compute hash for error pattern"""
        return hashlib.md5(normalized_message.encode()).hexdigest()

    # -------------------------------------------------------------------------
    # ClickHouse Queries
    # -------------------------------------------------------------------------

    async def query_error_logs(
        self,
        start_time: datetime,
        end_time: datetime,
        services: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Query error logs from ClickHouse with enhanced fields"""
        query = f"""
        SELECT
            log_id,
            timestamp,
            service,
            environment,
            level,
            message,
            stack_trace,
            trace_id,
            host,
            pod_name,
            logger_name,
            thread_name,
            labels,
            metadata
        FROM logs
        WHERE timestamp >= '{start_time.strftime('%Y-%m-%d %H:%M:%S')}'
          AND timestamp < '{end_time.strftime('%Y-%m-%d %H:%M:%S')}'
          AND level IN ('ERROR', 'WARN', 'FATAL')
        """

        if services:
            services_str = "','".join(services)
            query += f" AND service IN ('{services_str}')"

        query += " ORDER BY timestamp DESC LIMIT 10000"

        try:
            result = self.ch_client.query(query)

            logs = []
            for row in result.result_rows:
                logs.append({
                    'log_id': row[0],
                    'timestamp': row[1],
                    'service': row[2],
                    'environment': row[3],
                    'level': row[4],
                    'message': row[5],
                    'stack_trace': row[6] or '',
                    'trace_id': row[7] or '',
                    'host': row[8] or '',
                    'pod_name': row[9] or '',
                    'logger_name': row[10] or '',
                    'thread_name': row[11] or '',
                    'labels': row[12] or {},
                    'metadata': row[13] or '',
                })

            return logs

        except Exception as e:
            self.logger.error("query_failed", error=str(e))
            raise

    def detect_patterns(self, logs: List[Dict[str, Any]]) -> List[PatternInfo]:
        """Detect error patterns with enhanced tracking including sample log IDs"""
        pattern_map: Dict[str, Dict[str, Any]] = {}

        for log in logs:
            normalized = self.normalize_error_message(log['message'])
            pattern_hash = self.compute_pattern_hash(normalized)

            if pattern_hash not in pattern_map:
                pattern_map[pattern_hash] = {
                    'pattern_hash': pattern_hash,
                    'normalized_message': normalized,
                    'count': 0,
                    'services': set(),
                    'example_message': log['message'],
                    'first_seen': log['timestamp'],
                    'last_seen': log['timestamp'],
                    'max_level': log['level'],
                    'sample_log_ids': [],  # Collect sample log IDs
                }

            pattern_data = pattern_map[pattern_hash]
            pattern_data['count'] += 1
            pattern_data['services'].add(log['service'])

            # Collect up to 5 sample log IDs for investigation
            if len(pattern_data['sample_log_ids']) < 5:
                pattern_data['sample_log_ids'].append(log['log_id'])

            # Update first/last seen
            if log['timestamp'] < pattern_data['first_seen']:
                pattern_data['first_seen'] = log['timestamp']
            if log['timestamp'] > pattern_data['last_seen']:
                pattern_data['last_seen'] = log['timestamp']

            # Update max severity
            level_priority = {'FATAL': 3, 'ERROR': 2, 'WARN': 1}
            if level_priority.get(log['level'], 0) > level_priority.get(pattern_data['max_level'], 0):
                pattern_data['max_level'] = log['level']

        # Convert to list and sort by count
        patterns = []
        for pattern_data in pattern_map.values():
            patterns.append(PatternInfo(
                pattern_hash=pattern_data['pattern_hash'],
                normalized_message=pattern_data['normalized_message'],
                count=pattern_data['count'],
                services=list(pattern_data['services']),
                example_message=pattern_data['example_message'],
                first_seen=pattern_data['first_seen'],
                last_seen=pattern_data['last_seen'],
                max_level=pattern_data['max_level'],
                sample_log_ids=pattern_data['sample_log_ids']
            ))

        patterns.sort(key=lambda x: x.count, reverse=True)

        return patterns

    # -------------------------------------------------------------------------
    # ClickHouse Table Updates
    # -------------------------------------------------------------------------

    def update_error_patterns_clickhouse(self, patterns: List[PatternInfo]):
        """
        Update error_patterns table in ClickHouse with proper metadata preservation,
        trend calculation, sample log IDs, and is_known tracking from error_catalog.

        Since error_patterns uses ReplacingMergeTree(updated_at), we need to:
        1. Query existing patterns to preserve metadata and calculate trends
        2. Query error_catalog (PostgreSQL) to sync is_known status
        3. Update dynamic fields (counts, timestamps, sample_log_ids, trend)
        4. Insert with new updated_at timestamp
        """
        if not patterns:
            return

        try:
            # Step 1: Query existing patterns from ClickHouse
            error_hashes = [p.pattern_hash for p in patterns]
            hash_placeholders = ','.join([f"'{h}'" for h in error_hashes])

            existing_query = f"""
                SELECT
                    error_hash,
                    occurrence_count,
                    is_known,
                    category,
                    tags,
                    has_embedding,
                    qdrant_point_id,
                    sample_stack_trace,
                    updated_at
                FROM error_patterns
                WHERE error_hash IN ({hash_placeholders})
                ORDER BY updated_at DESC
                LIMIT 1 BY error_hash
            """

            existing_patterns = {}
            try:
                result = self.ch_client.query(existing_query)
                for row in result.result_rows:
                    existing_patterns[row[0]] = {
                        'previous_count': row[1],
                        'is_known': row[2],
                        'category': row[3],
                        'tags': row[4],
                        'has_embedding': row[5],
                        'qdrant_point_id': row[6],
                        'sample_stack_trace': row[7],
                        'last_updated': row[8],
                    }
            except Exception as e:
                self.logger.warning("existing_patterns_query_failed", error=str(e))

            # Step 2: Query error_catalog from PostgreSQL to get is_known status
            catalog_known_patterns = {}
            try:
                with self.SessionLocal() as session:
                    catalog_entries = session.query(ErrorCatalog).filter(
                        ErrorCatalog.error_hash.in_(error_hashes),
                        ErrorCatalog.is_known_issue == True
                    ).all()

                    for entry in catalog_entries:
                        catalog_known_patterns[entry.error_hash] = {
                            'is_known': 1,
                            'category': entry.category or '',
                            'tags': entry.tags or [],
                        }
            except Exception as e:
                self.logger.warning("error_catalog_query_failed", error=str(e))

            # Step 3: Prepare rows with preserved metadata, trend calculation, and sample_log_ids
            rows = []
            for pattern in patterns:
                existing = existing_patterns.get(pattern.pattern_hash, {})
                catalog_info = catalog_known_patterns.get(pattern.pattern_hash, {})

                # Calculate trend by comparing current count with historical count
                trend = 'stable'
                if pattern.pattern_hash in existing_patterns:
                    previous_count = existing.get('previous_count', 0)
                    if previous_count > 0:
                        change_ratio = (pattern.count - previous_count) / previous_count
                        if change_ratio > 0.25:  # 25% increase
                            trend = 'increasing'
                        elif change_ratio < -0.25:  # 25% decrease
                            trend = 'decreasing'
                        else:
                            trend = 'stable'
                else:
                    trend = 'new'  # First time seeing this pattern

                # Determine is_known: prefer catalog, fallback to existing clickhouse value
                is_known = catalog_info.get('is_known', existing.get('is_known', 0))

                # Merge category and tags from catalog if available
                category = catalog_info.get('category') or existing.get('category', '')
                tags = catalog_info.get('tags', existing.get('tags', []))

                row = {
                    'error_hash': pattern.pattern_hash,
                    'normalized_message': pattern.normalized_message,
                    'first_seen': pattern.first_seen,
                    'last_seen': pattern.last_seen,
                    'occurrence_count': pattern.count,
                    'services': pattern.services,
                    'environments': ['production'],
                    'max_level': pattern.max_level,
                    'sample_log_ids': pattern.sample_log_ids,  # Store actual sample log IDs

                    # Preserve/update metadata
                    'sample_stack_trace': existing.get('sample_stack_trace', ''),
                    'is_known': is_known,  # Synced from error_catalog
                    'category': category,
                    'tags': tags,
                    'has_embedding': existing.get('has_embedding', 0),
                    'qdrant_point_id': existing.get('qdrant_point_id', ''),

                    # Dynamic fields
                    'avg_occurrences_per_day': pattern.count / max(1, (pattern.last_seen - pattern.first_seen).days or 1),
                    'trend': trend,  # Calculated based on historical data
                    'updated_at': datetime.now(timezone.utc),
                }
                rows.append(row)

            # Step 4: Insert with all fields
            self.ch_client.insert(
                'error_patterns',
                rows,
                column_names=list(rows[0].keys())
            )

            ERROR_PATTERNS_CREATED.inc(len(rows))

            # Enhanced logging with trend breakdown
            trend_counts = {}
            for row in rows:
                trend = row['trend']
                trend_counts[trend] = trend_counts.get(trend, 0) + 1

            self.logger.info("error_patterns_updated",
                           count=len(rows),
                           new_patterns=trend_counts.get('new', 0),
                           increasing=trend_counts.get('increasing', 0),
                           decreasing=trend_counts.get('decreasing', 0),
                           stable=trend_counts.get('stable', 0),
                           known_issues=len([r for r in rows if r['is_known'] == 1]))

        except Exception as e:
            self.logger.error("error_patterns_update_failed", error=str(e))

    # -------------------------------------------------------------------------
    # PostgreSQL Table Updates
    # -------------------------------------------------------------------------

    def create_error_catalog_entries(self, patterns: List[PatternInfo], session):
        """Create error_catalog entries for new unknown patterns"""
        try:
            new_entries = 0

            for pattern in patterns[:20]:  # Top 20 patterns
                # Check if exists
                existing = session.query(ErrorCatalog).filter_by(
                    error_hash=pattern.pattern_hash
                ).first()

                if not existing:
                    # Create new catalog entry
                    catalog_entry = ErrorCatalog(
                        catalog_id=uuid4(),
                        pattern_name=f"Auto-detected: {pattern.normalized_message[:100]}",
                        error_hash=pattern.pattern_hash,
                        pattern_regex=None,
                        category='auto-detected',
                        severity=self._map_level_to_severity(pattern.max_level),
                        tags=['auto-created', pattern.max_level.lower()],
                        description=f"Automatically detected error pattern. Occurred {pattern.count} times.",
                        typical_causes=[],
                        common_solutions=[],
                        documentation_links=[],
                        is_known_issue=False,
                        is_expected=False,
                        auto_created=True,
                        related_patterns=[],
                        last_occurrence=pattern.last_seen,
                        total_occurrences=pattern.count,
                        created_by='llm-analyzer-auto',
                    )
                    session.add(catalog_entry)
                    new_entries += 1
                else:
                    # Update occurrence count
                    existing.total_occurrences += pattern.count
                    existing.last_occurrence = pattern.last_seen

            if new_entries > 0:
                session.commit()
                self.logger.info("error_catalog_entries_created", count=new_entries)

        except Exception as e:
            session.rollback()
            self.logger.error("error_catalog_creation_failed", error=str(e))

    def create_anomaly_alerts(
        self,
        patterns: List[PatternInfo],
        total_logs: int,
        llm_analysis: str,
        session
    ):
        """Create anomaly alerts for suspicious patterns"""
        try:
            alerts_created = 0

            # Detect anomalies (patterns with >10% of total logs)
            anomaly_threshold = total_logs * 0.1
            anomalous_patterns = [p for p in patterns if p.count > anomaly_threshold]

            for pattern in anomalous_patterns:
                # Check if we already have a recent alert for this pattern
                recent_alert = session.query(AnomalyAlert).filter(
                    AnomalyAlert.status == 'new',
                    AnomalyAlert.detected_at >= datetime.now(timezone.utc) - timedelta(hours=24)
                ).filter(
                    AnomalyAlert.description.contains(pattern.pattern_hash)
                ).first()

                if not recent_alert:
                    alert = AnomalyAlert(
                        alert_id=uuid4(),
                        anomaly_type='error_spike',
                        detected_at=datetime.now(timezone.utc),
                        service=pattern.services[0] if pattern.services else None,
                        environment='production',
                        time_window='24 hours',
                        description=f"High frequency error pattern detected: {pattern.normalized_message}",
                        metrics={
                            'occurrence_count': pattern.count,
                            'percentage_of_errors': round((pattern.count / total_logs) * 100, 2),
                            'threshold': anomaly_threshold,
                            'affected_services': pattern.services,
                        },
                        affected_log_ids=[],
                        sample_logs=[],
                        clickhouse_query=f"SELECT * FROM logs WHERE message LIKE '%{pattern.example_message[:50]}%'",
                        qdrant_point_ids=[],
                        severity='high' if pattern.count > anomaly_threshold * 2 else 'medium',
                        confidence_score=min(1.0, pattern.count / anomaly_threshold),
                        llm_analysis=llm_analysis,
                        suggested_actions=[
                            f"Investigate {pattern.services[0]} service logs",
                            "Check for recent deployments",
                            "Review application health metrics",
                        ],
                        status='new',
                        notifications_sent={},
                    )
                    session.add(alert)
                    alerts_created += 1
                    ANOMALY_ALERTS_CREATED.inc()

            if alerts_created > 0:
                session.commit()
                self.logger.info("anomaly_alerts_created", count=alerts_created)

            return alerts_created

        except Exception as e:
            session.rollback()
            self.logger.error("anomaly_alerts_creation_failed", error=str(e))
            return 0

    def _map_level_to_severity(self, level: str) -> str:
        """Map log level to severity"""
        mapping = {
            'FATAL': 'critical',
            'ERROR': 'high',
            'WARN': 'medium',
        }
        return mapping.get(level, 'low')

    # -------------------------------------------------------------------------
    # LLM Analysis
    # -------------------------------------------------------------------------

    async def analyze_with_llm(
        self,
        patterns: List[PatternInfo],
        logs_count: int
    ) -> tuple[str, int]:
        """Generate analysis using LLM - returns (analysis, tokens_used)"""
        # Build comprehensive prompt
        prompt = f"""You are a senior DevOps engineer analyzing production error logs.

CONTEXT:
- Total error/warning logs: {logs_count:,}
- Unique error patterns detected: {len(patterns)}
- Time window: Last 24 hours

TOP ERROR PATTERNS:
"""

        for i, pattern in enumerate(patterns[:10], 1):
            prompt += f"\n{i}. [{pattern.count} occurrences across {len(pattern.services)} service(s)]"
            prompt += f"\n   Pattern: {pattern.normalized_message}"
            prompt += f"\n   Services: {', '.join(pattern.services)}"
            prompt += f"\n   Severity: {pattern.max_level}"
            prompt += f"\n   Example: {pattern.example_message[:150]}"

        prompt += """

ANALYSIS REQUIRED:
1. Executive Summary (2-3 sentences) - What's the overall health?
2. Top 3 Critical Issues - What needs immediate attention?
3. Root Cause Hypotheses - What might be causing these errors?
4. Actionable Recommendations - Specific steps to resolve issues

Format your response clearly with sections. Be concise and actionable."""

        try:
            response = await self.http_client.post(
                f"{self.settings.ollama_host}/api/generate",
                json={
                    "model": self.settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                    }
                }
            )

            if response.status_code == 200:
                data = response.json()
                analysis_text = data.get('response', 'No analysis generated')

                # Estimate tokens (rough approximation)
                tokens_used = len(prompt.split()) + len(analysis_text.split())

                return analysis_text, tokens_used
            else:
                self.logger.error("llm_request_failed", status=response.status_code)
                return "LLM analysis unavailable", 0

        except Exception as e:
            self.logger.error("llm_analysis_failed", error=str(e))
            return f"LLM analysis failed: {str(e)}", 0

    # -------------------------------------------------------------------------
    # Main Analysis Orchestration
    # -------------------------------------------------------------------------

    async def perform_analysis(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        services: Optional[List[str]] = None
    ) -> AnalysisResponse:
        """Perform comprehensive log analysis with full table updates"""

        # Create analysis job first
        job_id = uuid4()
        job_start_time = time.time()

        with self.SessionLocal() as session:
            job = AnalysisJob(
                job_id=job_id,
                job_type='nightly_analysis' if not services else 'on_demand_analysis',
                parameters={
                    'start_time': start_time.isoformat() if start_time else None,
                    'end_time': end_time.isoformat() if end_time else None,
                    'services': services,
                },
                status='running',
                started_at=datetime.now(timezone.utc),
                model_used=self.settings.ollama_model,
            )
            session.add(job)
            session.commit()

        try:
            # Set time range
            if end_time is None:
                end_time = datetime.now(timezone.utc)
            if start_time is None:
                start_time = end_time - timedelta(hours=self.settings.analysis_window_hours)

            self.logger.info(
                "analysis_started",
                job_id=str(job_id),
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat()
            )

            # Query logs
            logs = await self.query_error_logs(start_time, end_time, services)

            if not logs:
                self.logger.warning("no_logs_found")

                # Update job as completed with no data
                with self.SessionLocal() as session:
                    job = session.query(AnalysisJob).filter_by(job_id=job_id).first()
                    if job:
                        job.status = 'completed'
                        job.completed_at = datetime.now(timezone.utc)
                        job.processing_time_seconds = time.time() - job_start_time
                        job.result = {'message': 'No logs found'}
                        session.commit()

                return AnalysisResponse(
                    job_id=str(job_id),
                    report_id='',
                    report_date=datetime.now(timezone.utc).date().isoformat(),
                    total_logs=0,
                    error_count=0,
                    unique_patterns=0,
                    anomalies_detected=0,
                    executive_summary="No error logs found in the specified time range.",
                    generation_time_seconds=time.time() - job_start_time,
                    status='completed'
                )

            # Detect patterns
            patterns = self.detect_patterns(logs)

            # Count warnings vs errors
            error_count = sum(1 for log in logs if log['level'] == 'ERROR' or log['level'] == 'FATAL')
            warning_count = sum(1 for log in logs if log['level'] == 'WARN')

            # Update ClickHouse error_patterns table
            self.update_error_patterns_clickhouse(patterns)

            # Analyze with LLM
            llm_analysis, tokens_used = await self.analyze_with_llm(patterns, len(logs))

            # Extract recommendations from LLM analysis
            recommendations = self._extract_recommendations(llm_analysis)

            # Detect anomalies
            with self.SessionLocal() as session:
                # Create error catalog entries
                self.create_error_catalog_entries(patterns, session)

                # Create anomaly alerts
                anomalies_count = self.create_anomaly_alerts(
                    patterns,
                    len(logs),
                    llm_analysis,
                    session
                )

                # Count services affected
                affected_services = list(set(log['service'] for log in logs))

                # Create nightly report
                report_id = uuid4()
                report = NightlyReport(
                    report_id=report_id,
                    report_date=datetime.now(timezone.utc).date(),
                    start_time=start_time,
                    end_time=end_time,
                    total_logs_processed=len(logs),
                    error_count=error_count,
                    warning_count=warning_count,
                    unique_error_patterns=len(patterns),
                    new_error_patterns=len([p for p in patterns if p.count == 1]),
                    anomalies_detected=anomalies_count,
                    critical_issues=len([p for p in patterns if p.max_level == 'FATAL']),
                    executive_summary=llm_analysis,
                    top_issues=[p.model_dump(mode='json') for p in patterns[:10]],
                    recommendations=recommendations,
                    affected_services={'services': affected_services, 'count': len(affected_services)},
                    generation_time_seconds=time.time() - job_start_time,
                    llm_model_used=self.settings.ollama_model,
                    tokens_used=tokens_used,
                    status='completed',
                )

                try:
                    session.add(report)
                    session.commit()
                except IntegrityError:
                    # Report for this date already exists, update it
                    session.rollback()
                    existing = session.query(NightlyReport).filter_by(
                        report_date=datetime.now(timezone.utc).date()
                    ).first()
                    if existing:
                        for key, value in report.__dict__.items():
                            if not key.startswith('_'):
                                setattr(existing, key, value)
                        session.commit()
                        report_id = existing.report_id

                # Update job as completed
                job = session.query(AnalysisJob).filter_by(job_id=job_id).first()
                if job:
                    job.status = 'completed'
                    job.completed_at = datetime.now(timezone.utc)
                    job.processing_time_seconds = time.time() - job_start_time
                    job.tokens_used = tokens_used
                    job.result = {
                        'report_id': str(report_id),
                        'patterns_detected': len(patterns),
                        'anomalies_detected': anomalies_count,
                    }
                    session.commit()

            # Update metrics
            ANALYSES_TOTAL.inc()
            ANALYSIS_DURATION.observe(time.time() - job_start_time)
            PATTERNS_DETECTED.set(len(patterns))
            ANOMALIES_DETECTED.set(anomalies_count)

            self.last_analysis_time = datetime.now(timezone.utc)

            self.logger.info(
                "analysis_completed",
                job_id=str(job_id),
                report_id=str(report_id),
                duration=time.time() - job_start_time,
                patterns=len(patterns),
                anomalies=anomalies_count
            )

            return AnalysisResponse(
                job_id=str(job_id),
                report_id=str(report_id),
                report_date=datetime.now(timezone.utc).date().isoformat(),
                total_logs=len(logs),
                error_count=error_count,
                unique_patterns=len(patterns),
                anomalies_detected=anomalies_count,
                executive_summary=llm_analysis,
                generation_time_seconds=time.time() - job_start_time,
                status='completed'
            )

        except Exception as e:
            ANALYSES_FAILED.inc()
            self.logger.error("analysis_failed", job_id=str(job_id), error=str(e))

            # Update job as failed
            with self.SessionLocal() as session:
                job = session.query(AnalysisJob).filter_by(job_id=job_id).first()
                if job:
                    job.status = 'failed'
                    job.completed_at = datetime.now(timezone.utc)
                    job.processing_time_seconds = time.time() - job_start_time
                    job.error_message = str(e)
                    session.commit()

            raise

    def _extract_recommendations(self, llm_analysis: str) -> List[str]:
        """Extract actionable recommendations from LLM analysis"""
        # Simple extraction - look for numbered lists or bullet points
        recommendations = []
        lines = llm_analysis.split('\n')

        in_recommendations = False
        for line in lines:
            line = line.strip()
            if 'recommendation' in line.lower():
                in_recommendations = True
                continue

            if in_recommendations and line:
                # Extract numbered or bulleted items
                if line[0].isdigit() or line.startswith('-') or line.startswith('•'):
                    rec = re.sub(r'^[\d\.\-•\*\s]+', '', line).strip()
                    if rec:
                        recommendations.append(rec)

        return recommendations[:5]  # Top 5

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    def get_latest_report(self) -> Optional[ReportResponse]:
        """Get the latest analysis report"""
        try:
            with self.SessionLocal() as session:
                report = session.query(NightlyReport)\
                    .order_by(NightlyReport.report_date.desc())\
                    .first()

                if report:
                    return ReportResponse(
                        report_id=str(report.report_id),
                        report_date=report.report_date.isoformat(),
                        start_time=report.start_time.isoformat(),
                        end_time=report.end_time.isoformat(),
                        total_logs_processed=report.total_logs_processed or 0,
                        error_count=report.error_count or 0,
                        unique_error_patterns=report.unique_error_patterns or 0,
                        anomalies_detected=report.anomalies_detected or 0,
                        executive_summary=report.executive_summary or '',
                        top_issues=report.top_issues or [],
                        recommendations=report.recommendations or [],
                        generation_time_seconds=report.generation_time_seconds or 0.0
                    )

                return None

        except Exception as e:
            self.logger.error("get_report_failed", error=str(e))
            return None


# =============================================================================
# FastAPI Application
# =============================================================================

settings = Settings()
analyzer_service: Optional[LLMAnalyzerService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager"""
    global analyzer_service

    # Startup
    logger.info("application_starting")

    analyzer_service = LLMAnalyzerService(settings)
    analyzer_service.setup_clickhouse()
    analyzer_service.setup_postgres()
    await analyzer_service.setup_http_client()

    logger.info("application_started")

    yield

    # Shutdown
    logger.info("application_stopping")

    if analyzer_service and analyzer_service.http_client:
        await analyzer_service.http_client.aclose()

    logger.info("application_stopped")


app = FastAPI(
    title="LLM Analyzer Service - Enhanced",
    description="Comprehensive log analysis with LLM, multi-table updates",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    if analyzer_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    # Check Ollama
    ollama_connected = False
    try:
        response = await analyzer_service.http_client.get(
            f"{settings.ollama_host}/api/tags",
            timeout=5.0
        )
        ollama_connected = response.status_code == 200
    except:
        pass

    return HealthResponse(
        status="healthy",
        service="llm-analyzer",
        version="2.0.0",
        clickhouse_connected=analyzer_service.ch_client is not None,
        postgres_connected=analyzer_service.postgres_engine is not None,
        ollama_connected=ollama_connected,
        last_analysis=analyzer_service.last_analysis_time.isoformat() if analyzer_service.last_analysis_time else None
    )


@app.post("/analyze", response_model=AnalysisResponse)
async def trigger_analysis(
    request: AnalysisRequest = AnalysisRequest(),
    background_tasks: BackgroundTasks = None
):
    """Trigger manual analysis"""
    if analyzer_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    try:
        # Parse times if provided
        start_time = None
        end_time = None

        if request.start_time:
            start_time = datetime.fromisoformat(request.start_time.replace('Z', '+00:00'))
        if request.end_time:
            end_time = datetime.fromisoformat(request.end_time.replace('Z', '+00:00'))

        result = await analyzer_service.perform_analysis(
            start_time=start_time,
            end_time=end_time,
            services=request.services
        )

        return result

    except Exception as e:
        logger.error("analysis_request_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )


@app.get("/reports/latest", response_model=Optional[ReportResponse])
async def get_latest_report():
    """Get the latest analysis report"""
    if analyzer_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not initialized"
        )

    report = analyzer_service.get_latest_report()

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No reports found"
        )

    return report


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Prometheus metrics endpoint"""
    return generate_latest().decode('utf-8')


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
