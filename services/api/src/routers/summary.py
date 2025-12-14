"""
Summary Router
Intelligent summary reports of errors, warnings, and critical issues
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from services.database import DatabaseService
from services.qdrant_service import QdrantService
from services.cache import CacheService


router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class IssueGroup(BaseModel):
    """Group of similar issues"""
    pattern: str
    count: int
    services: List[str]
    first_seen: str
    last_seen: str
    severity: str
    sample_messages: List[str]
    affected_traces: int


class IssueSummary(BaseModel):
    """Summary of issues by severity"""
    severity: str  # ERROR, WARN, FATAL
    total_count: int
    unique_patterns: int
    affected_services: int
    top_issues: List[IssueGroup]


class CommonCause(BaseModel):
    """Common cause analysis"""
    category: str
    description: str
    occurrence_count: int
    services: List[str]
    recommendation: str


class SummaryReport(BaseModel):
    """Complete summary report"""
    generated_at: str
    time_window_hours: int

    # Overview stats
    total_logs: int
    total_errors: int
    total_warnings: int
    total_fatals: int

    # Issue summaries by severity
    errors: Optional[IssueSummary]
    warnings: Optional[IssueSummary]
    fatals: Optional[IssueSummary]

    # Common causes and patterns
    common_causes: List[CommonCause]

    # Service health
    services_with_issues: List[str]
    healthy_services: List[str]

    # Trends
    error_trend: str  # "increasing", "stable", "decreasing"
    compared_to_previous_period: Dict[str, float]


# ============================================================================
# Dependency Injection
# ============================================================================

def get_db() -> DatabaseService:
    from ..app import db_service
    return db_service


def get_qdrant() -> QdrantService:
    from ..app import qdrant_service
    return qdrant_service


def get_cache() -> CacheService:
    from ..app import cache_service
    return cache_service


# ============================================================================
# Helper Functions
# ============================================================================

async def analyze_issue_group(
    db: DatabaseService,
    qdrant: QdrantService,
    level: str,
    hours: int
) -> Optional[IssueSummary]:
    """Analyze issues of a specific severity level"""

    # Get raw logs from ClickHouse
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)

    logs = db.get_logs(
        limit=1000,  # Analyze up to 1000 logs
        level=level,
        start_time=start_time,
        end_time=end_time
    )

    if not logs:
        return None

    # Group similar messages using simple pattern matching
    # In production, you'd use Qdrant clustering here
    patterns = {}

    for log in logs:
        # Simple pattern extraction (first 100 chars)
        pattern_key = log["message"][:100]

        if pattern_key not in patterns:
            patterns[pattern_key] = {
                "messages": [],
                "services": set(),
                "traces": set(),
                "first_seen": log["timestamp"],
                "last_seen": log["timestamp"]
            }

        patterns[pattern_key]["messages"].append(log["message"])
        patterns[pattern_key]["services"].add(log["service"])
        if log.get("trace_id"):
            patterns[pattern_key]["traces"].add(log["trace_id"])

        # Update time range
        if log["timestamp"] < patterns[pattern_key]["first_seen"]:
            patterns[pattern_key]["first_seen"] = log["timestamp"]
        if log["timestamp"] > patterns[pattern_key]["last_seen"]:
            patterns[pattern_key]["last_seen"] = log["timestamp"]

    # Build top issues
    top_issues = []
    for pattern_key, data in sorted(
        patterns.items(),
        key=lambda x: len(x[1]["messages"]),
        reverse=True
    )[:10]:  # Top 10 patterns
        top_issues.append(IssueGroup(
            pattern=pattern_key,
            count=len(data["messages"]),
            services=list(data["services"]),
            first_seen=data["first_seen"],
            last_seen=data["last_seen"],
            severity=level,
            sample_messages=data["messages"][:3],  # 3 samples
            affected_traces=len(data["traces"])
        ))

    return IssueSummary(
        severity=level,
        total_count=len(logs),
        unique_patterns=len(patterns),
        affected_services=len(set(log["service"] for log in logs)),
        top_issues=top_issues
    )


def detect_common_causes(errors: List[Dict], warnings: List[Dict]) -> List[CommonCause]:
    """Detect common causes from error and warning patterns"""

    causes = []

    # Analyze patterns
    all_issues = errors + warnings

    # Database connection issues
    db_issues = [
        log for log in all_issues
        if any(keyword in log["message"].lower() for keyword in [
            "connection", "timeout", "refused", "database", "db", "sql"
        ])
    ]

    if db_issues:
        services = list(set(log["service"] for log in db_issues))
        causes.append(CommonCause(
            category="Database Connectivity",
            description="Database connection timeouts or failures detected",
            occurrence_count=len(db_issues),
            services=services,
            recommendation="Check database connection pool settings, network connectivity, and database server load"
        ))

    # Authentication issues
    auth_issues = [
        log for log in all_issues
        if any(keyword in log["message"].lower() for keyword in [
            "auth", "unauthorized", "forbidden", "token", "jwt", "credential"
        ])
    ]

    if auth_issues:
        services = list(set(log["service"] for log in auth_issues))
        causes.append(CommonCause(
            category="Authentication/Authorization",
            description="Authentication or authorization failures detected",
            occurrence_count=len(auth_issues),
            services=services,
            recommendation="Verify token expiration settings, check auth service health, validate credentials rotation"
        ))

    # Timeout issues
    timeout_issues = [
        log for log in all_issues
        if any(keyword in log["message"].lower() for keyword in [
            "timeout", "timed out", "deadline exceeded"
        ])
    ]

    if timeout_issues:
        services = list(set(log["service"] for log in timeout_issues))
        causes.append(CommonCause(
            category="Timeout Errors",
            description="Service timeout errors detected",
            occurrence_count=len(timeout_issues),
            services=services,
            recommendation="Review timeout configurations, check downstream service health, analyze slow queries"
        ))

    # Memory/Resource issues
    memory_issues = [
        log for log in all_issues
        if any(keyword in log["message"].lower() for keyword in [
            "memory", "oom", "out of memory", "heap", "resource"
        ])
    ]

    if memory_issues:
        services = list(set(log["service"] for log in memory_issues))
        causes.append(CommonCause(
            category="Resource Exhaustion",
            description="Memory or resource exhaustion detected",
            occurrence_count=len(memory_issues),
            services=services,
            recommendation="Increase memory limits, check for memory leaks, review resource quotas"
        ))

    return causes


def calculate_trend(current_count: int, previous_count: int) -> str:
    """Calculate trend direction"""
    if previous_count == 0:
        return "stable"

    change_percent = ((current_count - previous_count) / previous_count) * 100

    if change_percent > 20:
        return "increasing"
    elif change_percent < -20:
        return "decreasing"
    else:
        return "stable"


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/summary", response_model=SummaryReport)
async def get_summary_report(
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    db: DatabaseService = Depends(get_db),
    qdrant: QdrantService = Depends(get_qdrant),
    cache: CacheService = Depends(get_cache)
):
    """
    Get intelligent summary report of errors, warnings, and critical issues

    - **hours**: Time window to analyze (default: 24 hours)

    Returns comprehensive summary with:
    - Issue counts by severity
    - Top error patterns
    - Common causes and recommendations
    - Service health overview
    - Trend analysis
    """

    # Try cache first (5 minute TTL)
    cache_key = cache.cache_key("summary_report", hours=hours)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Calculate time windows
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    previous_start = start_time - timedelta(hours=hours)

    # Get overall stats
    total_logs = db.get_log_count(start_time=start_time, end_time=end_time)
    total_errors = db.get_log_count(level="ERROR", start_time=start_time, end_time=end_time)
    total_warnings = db.get_log_count(level="WARN", start_time=start_time, end_time=end_time)
    total_fatals = db.get_log_count(level="FATAL", start_time=start_time, end_time=end_time)

    # Get previous period stats for trend
    prev_errors = db.get_log_count(level="ERROR", start_time=previous_start, end_time=start_time)
    prev_warnings = db.get_log_count(level="WARN", start_time=previous_start, end_time=start_time)

    # Analyze each severity level
    errors_summary = await analyze_issue_group(db, qdrant, "ERROR", hours)
    warnings_summary = await analyze_issue_group(db, qdrant, "WARN", hours)
    fatals_summary = await analyze_issue_group(db, qdrant, "FATAL", hours)

    # Get raw logs for common cause analysis
    error_logs = db.get_logs(limit=500, level="ERROR", start_time=start_time, end_time=end_time)
    warning_logs = db.get_logs(limit=500, level="WARN", start_time=start_time, end_time=end_time)

    # Detect common causes
    common_causes = detect_common_causes(error_logs, warning_logs)

    # Get service health
    service_stats = db.get_service_stats()
    services_with_issues = [
        s["service"] for s in service_stats
        if s["error_count"] > 0
    ]
    healthy_services = [
        s["service"] for s in service_stats
        if s["error_count"] == 0
    ]

    # Calculate trends
    error_trend = calculate_trend(total_errors, prev_errors)

    # Build report
    report = SummaryReport(
        generated_at=datetime.utcnow().isoformat(),
        time_window_hours=hours,
        total_logs=total_logs,
        total_errors=total_errors,
        total_warnings=total_warnings,
        total_fatals=total_fatals,
        errors=errors_summary,
        warnings=warnings_summary,
        fatals=fatals_summary,
        common_causes=common_causes,
        services_with_issues=services_with_issues,
        healthy_services=healthy_services,
        error_trend=error_trend,
        compared_to_previous_period={
            "errors_change_percent": round(
                ((total_errors - prev_errors) / prev_errors * 100) if prev_errors > 0 else 0,
                2
            ),
            "warnings_change_percent": round(
                ((total_warnings - prev_warnings) / prev_warnings * 100) if prev_warnings > 0 else 0,
                2
            )
        }
    )

    # Cache for 5 minutes
    await cache.set(cache_key, report.model_dump(), ttl=300)

    return report


# ============================================================================
# LLM Executive Summary Endpoint
# ============================================================================

class ExecutiveSummary(BaseModel):
    """LLM-generated executive summary"""
    generated_at: str
    time_window_hours: int

    # High-level summary
    executive_summary: str
    key_insights: List[str]
    critical_issues: List[str]
    recommendations: List[str]

    # Data used for analysis
    total_logs_analyzed: int
    error_patterns_found: int
    services_analyzed: int


@router.get("/executive", response_model=ExecutiveSummary)
async def get_executive_summary(
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    db: DatabaseService = Depends(get_db),
    qdrant: QdrantService = Depends(get_qdrant),
    cache: CacheService = Depends(get_cache)
):
    """
    Get LLM-generated executive summary combining ClickHouse and Qdrant data

    - **hours**: Time window to analyze (default: 24 hours)

    This endpoint:
    1. Gathers comprehensive data from ClickHouse (stats, trends)
    2. Enriches with Qdrant vector search (patterns, clusters)
    3. Sends to Ollama LLM for intelligent analysis
    4. Returns executive-level insights and recommendations
    """

    # Try cache first (10 minute TTL - LLM is expensive)
    cache_key = cache.cache_key("executive_summary", hours=hours)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Calculate time windows
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)

    # ========================================================================
    # PHASE 1: Gather ClickHouse Data
    # ========================================================================

    # Get overall stats
    total_logs = db.get_log_count(start_time=start_time, end_time=end_time)
    total_errors = db.get_log_count(level="ERROR", start_time=start_time, end_time=end_time)
    total_warnings = db.get_log_count(level="WARN", start_time=start_time, end_time=end_time)
    total_fatals = db.get_log_count(level="FATAL", start_time=start_time, end_time=end_time)

    # Get service stats
    service_stats = db.get_service_stats()

    # Get error trends
    error_trends = db.get_error_trends(hours=hours)

    # Get hourly stats
    hourly_stats = db.get_hourly_stats(hours=hours)

    # Get sample errors for context
    error_logs = db.get_logs(limit=50, level="ERROR", start_time=start_time, end_time=end_time)

    # ========================================================================
    # PHASE 2: Enrich with Qdrant Vector Data
    # ========================================================================

    # Find error patterns using clustering
    try:
        error_patterns = await qdrant.cluster_similar_logs(
            service=None,  # All services
            level="ERROR",
            limit=100
        )
    except:
        error_patterns = []

    # Get collection stats
    try:
        qdrant_stats = await qdrant.get_collection_stats()
    except:
        qdrant_stats = {}

    # ========================================================================
    # PHASE 3: Build Context for LLM
    # ========================================================================

    context = f"""You are a senior DevOps engineer analyzing system logs for the past {hours} hours.

## QUANTITATIVE DATA

### Overall Statistics:
- Total logs processed: {total_logs:,}
- Error count: {total_errors:,}
- Warning count: {total_warnings:,}
- Fatal count: {total_fatals:,}
- Error rate: {(total_errors/total_logs*100):.2f}%

### Service Breakdown:
"""

    for service in service_stats[:5]:  # Top 5 services
        context += f"- {service['service']}: {service['total_logs']:,} logs, {service['error_count']:,} errors\n"

    context += f"\n### Temporal Patterns:\n"

    # Analyze hourly trends
    if hourly_stats:
        recent_hours = hourly_stats[:6]  # Last 6 hours
        context += f"Recent hourly error counts: "
        context += ", ".join([f"{h['error_count']}" for h in recent_hours])
        context += "\n"

    context += f"\n### Top Error Messages (samples):\n"

    # Add sample error messages
    for i, log in enumerate(error_logs[:10], 1):
        context += f"{i}. [{log['service']}] {log['message'][:100]}\n"

    context += f"\n### Error Patterns from Vector Analysis:\n"

    # Add pattern information
    if error_patterns:
        for i, pattern in enumerate(error_patterns[:5], 1):
            context += f"{i}. Pattern with {pattern.get('count', 0)} occurrences: {pattern.get('sample_message', '')[:100]}\n"

    context += f"""

## YOUR TASK

As a senior DevOps engineer, provide an executive summary that answers:

1. **Executive Summary**: A concise 2-3 sentence overview of the system health
2. **Key Insights**: 3-5 most important observations from the data
3. **Critical Issues**: Top 2-3 issues that need immediate attention
4. **Recommendations**: Specific, actionable recommendations to address the issues

Be concise, technical, and actionable. Focus on patterns and root causes, not just symptoms.

Format your response EXACTLY as follows:

EXECUTIVE_SUMMARY:
[Your 2-3 sentence summary here]

KEY_INSIGHTS:
- [Insight 1]
- [Insight 2]
- [Insight 3]

CRITICAL_ISSUES:
- [Issue 1]
- [Issue 2]

RECOMMENDATIONS:
- [Recommendation 1]
- [Recommendation 2]
- [Recommendation 3]
"""

    # ========================================================================
    # PHASE 4: Call Ollama LLM
    # ========================================================================

    import httpx

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "http://ollama:11434/api/generate",
                json={
                    "model": "llama2",
                    "prompt": context,
                    "stream": False
                }
            )

            response.raise_for_status()
            llm_response = response.json()["response"]

    except Exception as e:
        # Fallback if LLM fails
        llm_response = f"""EXECUTIVE_SUMMARY:
Unable to generate LLM summary due to error: {str(e)}. However, based on data: System processed {total_logs:,} logs with {total_errors:,} errors ({(total_errors/total_logs*100):.2f}% error rate).

KEY_INSIGHTS:
- Total errors in period: {total_errors:,}
- Top affected service: {service_stats[0]['service'] if service_stats else 'Unknown'}
- Error patterns detected: {len(error_patterns)}

CRITICAL_ISSUES:
- High error count detected
- Multiple services affected

RECOMMENDATIONS:
- Investigate top error patterns
- Review service health
- Check for infrastructure issues
"""

    # ========================================================================
    # PHASE 5: Parse LLM Response
    # ========================================================================

    # Simple parser for the structured response
    def extract_section(text: str, section_name: str) -> List[str]:
        """Extract bullet points from a section"""
        try:
            start = text.find(f"{section_name}:")
            if start == -1:
                return []

            # Find the next section or end of text
            next_section_starts = [
                text.find("EXECUTIVE_SUMMARY:", start + 1),
                text.find("KEY_INSIGHTS:", start + 1),
                text.find("CRITICAL_ISSUES:", start + 1),
                text.find("RECOMMENDATIONS:", start + 1)
            ]

            end = min([pos for pos in next_section_starts if pos > start], default=len(text))
            section_text = text[start:end]

            # Extract bullet points
            lines = section_text.split('\n')
            bullets = [
                line.strip('- ').strip()
                for line in lines
                if line.strip().startswith('-')
            ]

            return bullets
        except:
            return []

    def extract_summary(text: str) -> str:
        """Extract executive summary paragraph"""
        try:
            start = text.find("EXECUTIVE_SUMMARY:")
            if start == -1:
                return "Unable to generate summary"

            # Find next section
            next_section = text.find("KEY_INSIGHTS:", start)
            if next_section == -1:
                next_section = len(text)

            summary_text = text[start+len("EXECUTIVE_SUMMARY:"):next_section]
            return summary_text.strip()
        except:
            return "Unable to generate summary"

    # Parse the LLM response
    executive_summary_text = extract_summary(llm_response)
    key_insights = extract_section(llm_response, "KEY_INSIGHTS")
    critical_issues = extract_section(llm_response, "CRITICAL_ISSUES")
    recommendations = extract_section(llm_response, "RECOMMENDATIONS")

    # Build final response
    summary = ExecutiveSummary(
        generated_at=datetime.utcnow().isoformat(),
        time_window_hours=hours,
        executive_summary=executive_summary_text,
        key_insights=key_insights if key_insights else ["No key insights extracted"],
        critical_issues=critical_issues if critical_issues else ["No critical issues identified"],
        recommendations=recommendations if recommendations else ["Continue monitoring"],
        total_logs_analyzed=total_logs,
        error_patterns_found=len(error_patterns),
        services_analyzed=len(service_stats)
    )

    # Cache for 10 minutes (LLM calls are expensive)
    await cache.set(cache_key, summary.model_dump(), ttl=600)

    return summary