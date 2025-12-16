"""
Anomaly Baselines Calculator
Weekly scheduled job to calculate statistical baselines for anomaly detection

This module:
1. Queries hourly log counts from ClickHouse for the past 30 days
2. Calculates statistical baselines per service/environment/level/hour/day
3. Updates the anomaly_baselines table in ClickHouse
4. Tracks job execution in PostgreSQL analysis_jobs table
"""

from datetime import datetime, timezone
from typing import List, Dict, Any
from uuid import uuid4

import numpy as np

from settings import get_logger

logger = get_logger(__name__)


class AnomalyBaselineCalculator:
    """Calculate statistical baselines for anomaly detection"""

    def __init__(self, clickhouse_client, postgres_session):
        """
        Initialize the calculator

        Args:
            clickhouse_client: ClickHouse client connection
            postgres_session: PostgreSQL session for job tracking
        """
        self.ch_client = clickhouse_client
        self.pg_session = postgres_session
        self.logger = logger.bind(component="anomaly_baseline_calculator")

    def calculate_baselines(self, lookback_days: int = 30) -> Dict[str, Any]:
        """
        Calculate statistical baselines for all service/environment/level combinations

        Args:
            lookback_days: Number of days to look back for baseline calculation

        Returns:
            Dictionary with job statistics
        """
        self.logger.info("starting_baseline_calculation", lookback_days=lookback_days)
        job_start = datetime.now(timezone.utc)

        # Track job in PostgreSQL
        job_id = str(uuid4())
        self._create_analysis_job(job_id, lookback_days)

        try:
            # Step 1: Get all combinations of service/environment/level
            combinations = self._get_metric_combinations()
            self.logger.info("found_metric_combinations", count=len(combinations))

            # Step 2: Calculate baselines for each combination
            baselines_calculated = 0
            baselines_failed = 0

            for combo in combinations:
                service = combo['service']
                environment = combo['environment']
                level = combo['level']

                try:
                    # Calculate baselines for this combination
                    baseline_results = self._calculate_combination_baselines(
                        service, environment, level, lookback_days
                    )

                    # Insert/update baselines in ClickHouse
                    self._upsert_baselines(baseline_results)
                    baselines_calculated += len(baseline_results)

                except Exception as e:
                    self.logger.error(
                        "failed_to_calculate_baseline",
                        service=service,
                        environment=environment,
                        level=level,
                        error=str(e)
                    )
                    baselines_failed += 1

            # Step 3: Update job status
            job_end = datetime.now(timezone.utc)
            duration = (job_end - job_start).total_seconds()

            result = {
                "job_id": job_id,
                "combinations_processed": len(combinations),
                "baselines_calculated": baselines_calculated,
                "baselines_failed": baselines_failed,
                "duration_seconds": duration,
                "status": "completed"
            }

            self._update_analysis_job(job_id, result)

            self.logger.info(
                "baseline_calculation_completed",
                **result
            )

            return result

        except Exception as e:
            self.logger.error("baseline_calculation_failed", error=str(e))
            self._update_analysis_job(job_id, {
                "status": "failed",
                "error_message": str(e)
            })
            raise

    def _get_metric_combinations(self) -> List[Dict[str, str]]:
        """
        Get all unique combinations of service/environment/level from recent logs

        Returns:
            List of dicts with service, environment, level
        """
        query = """
            SELECT DISTINCT
                service,
                environment,
                toString(level) as level
            FROM logs
            WHERE timestamp >= now() - INTERVAL 7 DAY
            ORDER BY service, environment, level
        """

        result = self.ch_client.query(query)
        combinations = []

        for row in result.result_rows:
            combinations.append({
                "service": row[0],
                "environment": row[1],
                "level": row[2]
            })

        return combinations

    def _calculate_combination_baselines(
        self,
        service: str,
        environment: str,
        level: str,
        lookback_days: int
    ) -> List[Dict[str, Any]]:
        """
        Calculate baselines for a specific service/environment/level combination
        grouped by hour of day and day of week

        Args:
            service: Service name
            environment: Environment name
            level: Log level
            lookback_days: Number of days to analyze

        Returns:
            List of baseline records ready for insertion
        """
        # Query hourly counts grouped by hour_of_day and day_of_week
        query = """
            SELECT
                toDayOfWeek(hour) as day_of_week,
                toHour(hour) as hour_of_day,
                log_count as count
            FROM logs_hourly_agg
            WHERE service = {service:String}
                AND environment = {environment:String}
                AND level = {level:String}
                AND hour >= now() - INTERVAL {lookback_days:UInt32} DAY
            ORDER BY day_of_week, hour_of_day
        """
        try:
            result = self.ch_client.query(
                query,
                parameters={
                    "service": service,
                    "environment": environment,
                    "level": level,
                    "lookback_days": lookback_days
                }
            )
        except Exception as e:
            self.logger.error("failed_to_query_hourly_counts", error=str(e), service=service, environment=environment, level=level, lookback_days=lookback_days)
            raise

        # Group data by (day_of_week, hour_of_day)
        grouped_data = {}
        for row in result.result_rows:
            day_of_week = row[0]  # 1=Monday, 7=Sunday
            hour_of_day = row[1]  # 0-23
            count = row[2]

            key = (day_of_week, hour_of_day)
            if key not in grouped_data:
                grouped_data[key] = []
            grouped_data[key].append(count)

        # Calculate statistics for each group
        baselines = []
        for (day_of_week, hour_of_day), counts in grouped_data.items():
            if len(counts) < 2:  # Need at least 2 samples for stddev
                continue

            stats = self._calculate_statistics(counts)
            # Calculate thresholds (mean ± 2*stddev)
            lower_threshold = max(0, stats['mean'] - 2 * stats['stddev'])
            upper_threshold = stats['mean'] + 2 * stats['stddev']

            baselines.append({
                "service": service,
                "environment": environment,
                "level": level,
                "hour_of_day": hour_of_day,
                "day_of_week": day_of_week,
                "mean_count": stats['mean'],
                "stddev_count": stats['stddev'],
                "median_count": stats['median'],
                "p95_count": stats['p95'],
                "p99_count": stats['p99'],
                "lower_threshold": lower_threshold,
                "upper_threshold": upper_threshold,
                "sample_size": len(counts)
            })

        return baselines

    def _calculate_statistics(self, values: List[float]) -> Dict[str, float]:
        """
        Calculate statistical measures for a list of values

        Args:
            values: List of numeric values

        Returns:
            Dictionary with mean, stddev, median, p95, p99
        """
        if not values:
            return {
                'mean': 0.0,
                'stddev': 0.0,
                'median': 0.0,
                'p95': 0.0,
                'p99': 0.0
            }

        # Use numpy for efficient percentile calculations
        arr = np.array(values)

        return {
            'mean': float(np.mean(arr)),
            'stddev': float(np.std(arr, ddof=1)) if len(values) > 1 else 0.0,
            'median': float(np.median(arr)),
            'p95': float(np.percentile(arr, 95)),
            'p99': float(np.percentile(arr, 99))
        }

    def _upsert_baselines(self, baselines: List[Dict[str, Any]]):
        """
        Insert or update baselines in ClickHouse anomaly_baselines table

        Args:
            baselines: List of baseline records to insert
        """
        if not baselines:
            return

        # Prepare data for insertion
        data = []
        for baseline in baselines:
            data.append([
                baseline['service'],
                baseline['environment'],
                baseline['level'],
                baseline['hour_of_day'],
                baseline['day_of_week'],
                baseline['mean_count'],
                baseline['stddev_count'],
                baseline['median_count'],
                baseline['p95_count'],
                baseline['p99_count'],
                baseline['lower_threshold'],
                baseline['upper_threshold'],
                baseline['sample_size'],
                datetime.now(timezone.utc)  # last_updated
            ])

        # Insert into ClickHouse
        # Using ReplacingMergeTree, newer records replace older ones with same ORDER BY key
        self.ch_client.insert(
            'anomaly_baselines',
            data,
            column_names=[
                'service',
                'environment',
                'level',
                'hour_of_day',
                'day_of_week',
                'mean_count',
                'stddev_count',
                'median_count',
                'p95_count',
                'p99_count',
                'lower_threshold',
                'upper_threshold',
                'sample_size',
                'last_updated'
            ]
        )

        self.logger.info("upserted_baselines", count=len(baselines))

    def _create_analysis_job(self, job_id: str, lookback_days: int):
        """
        Create a new analysis job record in PostgreSQL

        Args:
            job_id: Unique job identifier
            lookback_days: Lookback period used
        """
        from sqlalchemy import text
        import json

        query = text("""
            INSERT INTO analysis_jobs (
                job_id, job_type, status, parameters, started_at, created_at
            ) VALUES (
                :job_id, :job_type, :status, CAST(:parameters AS jsonb), :started_at, :created_at
            )
        """)

        self.pg_session.execute(query, {
            "job_id": job_id,
            "job_type": "anomaly_baseline_calculation",
            "status": "running",
            "parameters": json.dumps({"lookback_days": lookback_days}),
            "started_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc)
        })
        self.pg_session.commit()

        self.logger.info("created_analysis_job", job_id=job_id)

    def _update_analysis_job(self, job_id: str, result: Dict[str, Any]):
        """
        Update analysis job with completion status and results

        Args:
            job_id: Job identifier
            result: Job results
        """
        from sqlalchemy import text
        import json

        completed_at = datetime.now(timezone.utc) if result.get('status') == 'completed' else None
        processing_time = result.get('duration_seconds')

        query = text("""
            UPDATE analysis_jobs
            SET status = :status,
                completed_at = :completed_at,
                result = CAST(:result AS jsonb),
                error_message = :error_message,
                processing_time_seconds = :processing_time
            WHERE job_id = :job_id
        """)

        self.pg_session.execute(query, {
            "job_id": job_id,
            "status": result.get('status', 'completed'),
            "completed_at": completed_at,
            "result": json.dumps(result),
            "error_message": result.get('error_message'),
            "processing_time": processing_time
        })
        self.pg_session.commit()

        self.logger.info("updated_analysis_job", job_id=job_id, status=result.get('status'))


def run_baseline_calculation(clickhouse_client, postgres_session, lookback_days: int = 30) -> Dict[str, Any]:
    """
    Convenience function to run baseline calculation

    Args:
        clickhouse_client: ClickHouse client
        postgres_session: PostgreSQL session
        lookback_days: Number of days to analyze (default: 30)

    Returns:
        Job result dictionary
    """
    calculator = AnomalyBaselineCalculator(clickhouse_client, postgres_session)
    return calculator.calculate_baselines(lookback_days)