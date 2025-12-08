"""
LLM Analyzer Service
Analyzes log patterns using local LLM (Ollama)
Queries ClickHouse, generates insights, stores reports in PostgreSQL
"""

import hashlib
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from uuid import uuid4

import clickhouse_connect
from clickhouse_connect.driver.client import Client as ClickHouseClient
import httpx
from fastapi import FastAPI, HTTPException, status
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
    Text,
    DateTime,
    Float,
    JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker
from settings import setup_logging
import structlog

# # Configure structured logging
# structlog.configure(
#     processors=[
#         structlog.stdlib.filter_by_level,
#         structlog.stdlib.add_logger_name,
#         structlog.stdlib.add_log_level,
#         structlog.stdlib.PositionalArgumentsFormatter(),
#         structlog.processors.TimeStamper(fmt="iso"),
#         structlog.processors.StackInfoRenderer(),
#         structlog.processors.format_exc_info,
#         structlog.processors.UnicodeDecoder(),
#         structlog.processors.JSONRenderer()
#     ],
#     wrapper_class=structlog.stdlib.BoundLogger,
#     context_class=dict,
#     logger_factory=structlog.stdlib.LoggerFactory(),
#     cache_logger_on_first_use=True,
# )
setup_logging("DEBUG")
logger = structlog.get_logger()

# Prometheus metrics
ANALYSES_TOTAL = Counter('analyses_total', 'Total analyses performed')
ANALYSES_FAILED = Counter('analyses_failed_total', 'Failed analyses')
ANALYSIS_DURATION = Histogram('analysis_duration_seconds', 'Analysis duration')
PATTERNS_DETECTED = Gauge('patterns_detected', 'Number of patterns detected')
ANOMALIES_DETECTED = Gauge('anomalies_detected', 'Number of anomalies detected')


class Settings(BaseSettings):
    """Service configuration"""
    # ClickHouse settings - HTTP interface (port 8123)
    clickhouse_host: str = Field(default="localhost", validation_alias="CLICKHOUSE_HOST")
    clickhouse_port: int = Field(default=8123, validation_alias="CLICKHOUSE_PORT")  # HTTP port, not 9000
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

    # API settings
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8002, validation_alias="API_PORT")

    # class Config:
    #     env_prefix = ""
    #     case_sensitive = False


# PostgreSQL ORM
Base = declarative_base()


class AnalysisReport(Base):
    """Analysis report model"""
    __tablename__ = 'analysis_reports'

    report_id = Column(String(36), primary_key=True)
    report_date = Column(DateTime, nullable=False)
    analysis_start = Column(DateTime, nullable=False)
    analysis_end = Column(DateTime, nullable=False)
    total_logs = Column(Integer, nullable=False)
    error_count = Column(Integer, nullable=False)
    unique_patterns = Column(Integer, nullable=False)
    anomalies_detected = Column(Integer, nullable=False)
    executive_summary = Column(Text, nullable=False)
    top_issues = Column(JSON, nullable=False)
    pattern_analysis = Column(JSON, nullable=False)
    generation_time_seconds = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Pydantic Models
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


class AnalysisResponse(BaseModel):
    """Analysis response"""
    report_id: str
    report_date: str
    total_logs: int
    error_count: int
    unique_patterns: int
    anomalies_detected: int
    executive_summary: str
    generation_time_seconds: float


class ReportResponse(BaseModel):
    """Full report response"""
    report_id: str
    report_date: str
    analysis_start: str
    analysis_end: str
    total_logs: int
    error_count: int
    unique_patterns: int
    anomalies_detected: int
    executive_summary: str
    top_issues: List[Dict[str, Any]]
    pattern_analysis: Dict[str, Any]
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


class LLMAnalyzerService:
    """LLM-powered log analyzer"""

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

    def setup_clickhouse(self):
        """Setup ClickHouse connection using clickhouse-connect"""
        try:
            self.ch_client = clickhouse_connect.get_client(
                host=self.settings.clickhouse_host,
                port=self.settings.clickhouse_port,  # HTTP port 8123
                username=self.settings.clickhouse_user,
                password=self.settings.clickhouse_password,
                database=self.settings.clickhouse_database
            )

            # Test connection
            result = self.ch_client.query("SELECT 1")

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

            self.postgres_engine = create_engine(url)
            self.SessionLocal = sessionmaker(bind=self.postgres_engine)

            # Create tables
            Base.metadata.create_all(self.postgres_engine)

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
            # Test Ollama connection
            response = await self.http_client.get(f"{self.settings.ollama_host}/api/tags")
            if response.status_code == 200:
                self.logger.info("ollama_connected")
            else:
                self.logger.warning("ollama_unhealthy")
        except Exception as e:
            self.logger.error("ollama_connection_failed", error=str(e))

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
        # Normalize whitespace
        message = ' '.join(message.split())

        return message

    def compute_pattern_hash(self, normalized_message: str) -> str:
        """Compute hash for error pattern"""
        return hashlib.md5(normalized_message.encode()).hexdigest()

    async def query_error_logs(
        self,
        start_time: datetime,
        end_time: datetime,
        services: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Query error logs from ClickHouse"""
        query = f"""
        SELECT 
            log_id,
            timestamp,
            service,
            level,
            message,
            stack_trace
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
                    'level': row[3],
                    'message': row[4],
                    'stack_trace': row[5]
                })

            return logs

        except Exception as e:
            self.logger.error("query_failed", error=str(e))
            raise

    def detect_patterns(self, logs: List[Dict[str, Any]]) -> List[PatternInfo]:
        """Detect error patterns"""
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
                    'example_message': log['message']
                }

            pattern_map[pattern_hash]['count'] += 1
            pattern_map[pattern_hash]['services'].add(log['service'])

        # Convert to list and sort by count
        patterns = []
        for pattern_data in pattern_map.values():
            patterns.append(PatternInfo(
                pattern_hash=pattern_data['pattern_hash'],
                normalized_message=pattern_data['normalized_message'],
                count=pattern_data['count'],
                services=list(pattern_data['services']),
                example_message=pattern_data['example_message']
            ))

        patterns.sort(key=lambda x: x.count, reverse=True)

        return patterns

    async def analyze_with_llm(
        self,
        patterns: List[PatternInfo],
        logs_count: int
    ) -> str:
        """Generate analysis using LLM"""
        # Build prompt
        prompt = f"""You are analyzing error logs from a production system.

Total error logs: {logs_count}
Unique error patterns detected: {len(patterns)}

Top error patterns:
"""

        for i, pattern in enumerate(patterns[:10], 1):
            prompt += f"\n{i}. [{pattern.count} occurrences] {pattern.normalized_message}"
            prompt += f"\n   Services affected: {', '.join(pattern.services)}"
            prompt += f"\n   Example: {pattern.example_message[:200]}"

        prompt += """

Please provide:
1. Executive summary of the most critical issues
2. Root cause analysis for top 3 patterns
3. Actionable recommendations

Keep the response concise and focused on actionable insights."""

        try:
            response = await self.http_client.post(
                f"{self.settings.ollama_host}/api/generate",
                json={
                    "model": self.settings.ollama_model,
                    "prompt": prompt,
                    "stream": False
                }
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('response', 'No analysis generated')
            else:
                self.logger.error("llm_request_failed", status=response.status_code)
                return "LLM analysis unavailable"

        except Exception as e:
            self.logger.error("llm_analysis_failed", error=str(e))
            return f"LLM analysis failed: {str(e)}"

    async def perform_analysis(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        services: Optional[List[str]] = None
    ) -> AnalysisResponse:
        """Perform log analysis"""
        import time
        start = time.time()

        try:
            # Set time range
            if end_time is None:
                end_time = datetime.now(timezone.utc)
            if start_time is None:
                start_time = end_time - timedelta(hours=self.settings.analysis_window_hours)

            self.logger.info(
                "analysis_started",
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat()
            )

            # Query logs
            logs = await self.query_error_logs(start_time, end_time, services)

            if not logs:
                self.logger.warning("no_logs_found")
                return AnalysisResponse(
                    report_id=str(uuid4()),
                    report_date=datetime.now(timezone.utc).isoformat(),
                    total_logs=0,
                    error_count=0,
                    unique_patterns=0,
                    anomalies_detected=0,
                    executive_summary="No error logs found in the specified time range.",
                    generation_time_seconds=time.time() - start
                )

            # Detect patterns
            patterns = self.detect_patterns(logs)

            # Analyze with LLM
            analysis = await self.analyze_with_llm(patterns, len(logs))

            # Detect anomalies (patterns with sudden spikes)
            anomalies = [p for p in patterns if p.count > len(logs) * 0.1]

            # Create report
            report_id = str(uuid4())
            generation_time = time.time() - start

            # Store in PostgreSQL
            report = AnalysisReport(
                report_id=report_id,
                report_date=datetime.now(timezone.utc),
                analysis_start=start_time,
                analysis_end=end_time,
                total_logs=len(logs),
                error_count=len(logs),
                unique_patterns=len(patterns),
                anomalies_detected=len(anomalies),
                executive_summary=analysis,
                top_issues=[p.model_dump() for p in patterns[:10]],
                pattern_analysis={
                    'total_patterns': len(patterns),
                    'cross_service_issues': len([p for p in patterns if len(p.services) > 1]),
                    'high_frequency_patterns': len([p for p in patterns if p.count > 10])
                },
                generation_time_seconds=generation_time
            )

            with self.SessionLocal() as session:
                session.add(report)
                session.commit()

            # Update metrics
            ANALYSES_TOTAL.inc()
            ANALYSIS_DURATION.observe(generation_time)
            PATTERNS_DETECTED.set(len(patterns))
            ANOMALIES_DETECTED.set(len(anomalies))

            self.last_analysis_time = datetime.now(timezone.utc)

            self.logger.info(
                "analysis_completed",
                report_id=report_id,
                duration=generation_time,
                patterns=len(patterns)
            )

            return AnalysisResponse(
                report_id=report_id,
                report_date=datetime.now(timezone.utc).isoformat(),
                total_logs=len(logs),
                error_count=len(logs),
                unique_patterns=len(patterns),
                anomalies_detected=len(anomalies),
                executive_summary=analysis,
                generation_time_seconds=generation_time
            )

        except Exception as e:
            ANALYSES_FAILED.inc()
            self.logger.error("analysis_failed", error=str(e))
            raise

    def get_latest_report(self) -> Optional[ReportResponse]:
        """Get the latest analysis report"""
        try:
            with self.SessionLocal() as session:
                report = session.query(AnalysisReport)\
                    .order_by(AnalysisReport.report_date.desc())\
                    .first()

                if report:
                    return ReportResponse(
                        report_id=report.report_id,
                        report_date=report.report_date.isoformat(),
                        analysis_start=report.analysis_start.isoformat(),
                        analysis_end=report.analysis_end.isoformat(),
                        total_logs=report.total_logs,
                        error_count=report.error_count,
                        unique_patterns=report.unique_patterns,
                        anomalies_detected=report.anomalies_detected,
                        executive_summary=report.executive_summary,
                        top_issues=report.top_issues,
                        pattern_analysis=report.pattern_analysis,
                        generation_time_seconds=report.generation_time_seconds
                    )

                return None

        except Exception as e:
            self.logger.error("get_report_failed", error=str(e))
            return None


# Global service instance
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


# FastAPI application
app = FastAPI(
    title="LLM Analyzer Service",
    description="Analyzes log patterns using local LLM (Ollama)",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
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
        version="1.0.0",
        clickhouse_connected=analyzer_service.ch_client is not None,
        postgres_connected=analyzer_service.postgres_engine is not None,
        ollama_connected=ollama_connected,
        last_analysis=analyzer_service.last_analysis_time.isoformat() if analyzer_service.last_analysis_time else None
    )


@app.post("/analyze", response_model=AnalysisResponse)
async def trigger_analysis(request: AnalysisRequest = AnalysisRequest()):
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
        log_config="debug" #None
    )