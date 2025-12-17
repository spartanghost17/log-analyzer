"""
Qdrant Service
Handles vector search operations with Qdrant
"""

import hashlib
import re
import time
from collections import Counter
from typing import List, Dict, Any, Optional

import httpx

from pydantic_settings import BaseSettings
from pydantic import Field

from settings import get_logger

logger = get_logger(__name__)

class Settings(BaseSettings):
    """Service configuration"""

    # Qdrant settings
    qdrant_host: str = Field(default="qdrant", validation_alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, validation_alias="QDRANT_PORT")

    # Jina embeddings settings
    jina_service_url: str = Field(default="http://jina-embeddings:8003", validation_alias="JINA_SERVICE_URL")
    jina_timeout: int = Field(default=30, validation_alias="JINA_TIMEOUT")

    class Config:
        env_prefix = ""
        case_sensitive = False

settings = Settings()

class QdrantService:
    """Service for Qdrant vector search operations"""

    def __init__(self):
        self.logger = logger.bind(component="qdrant_service")
        self.qdrant_host = settings.qdrant_host #"qdrant"
        self.qdrant_port = settings.qdrant_port #6333
        self.qdrant_url = f"http://{self.qdrant_host}:{self.qdrant_port}"
        self.jina_service_url = settings.jina_service_url #"http://jina-embeddings:8003"
        self.http_client: Optional[httpx.AsyncClient] = None

    async def connect(self):
        """Initialize HTTP client"""
        self.logger.info("connecting_to_qdrant")

        self.http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

        # Test connection
        try:
            response = await self.http_client.get(f"{self.qdrant_url}/collections")
            if response.status_code == 200:
                self.logger.info("qdrant_connected")
            else:
                self.logger.warning("qdrant_connection_failed", status=response.status_code)
        except Exception as e:
            self.logger.error("qdrant_connection_error", error=str(e))

    async def disconnect(self):
        """Close HTTP client"""
        self.logger.info("disconnecting_from_qdrant")

        if self.http_client:
            await self.http_client.aclose()

        self.logger.info("qdrant_disconnected")

    def _normalize_message(self, message: str) -> str:
        """
        Normalize log message for pattern detection
        Enhanced version matching llm-analyzer's normalize_error_message
        
        This parameterizes variable data (UUIDs, numbers, IPs, etc.) to enable
        pattern-based clustering of similar log messages.
        
        IMPORTANT: This must match llm-analyzer's normalization exactly for
        consistent pattern clustering across services.
        """
        # 1. Remove UUIDs (before other number patterns)
        message = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '<UUID>', message, flags=re.IGNORECASE
        )
        
        # 2. Remove full timestamps (ISO format, etc.)
        message = re.sub(
            r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?',
            '<TIMESTAMP>', message
        )
        
        # 3. Remove IP addresses (before general numbers)
        message = re.sub(
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            '<IP>', message
        )
        
        # 4. Remove hex strings
        message = re.sub(r'\b0x[0-9a-fA-F]+\b', '<HEX>', message)
        
        # 5. Normalize numbers with units (e.g., 45s, 100ms, 2GB, 5.5MB)
        message = re.sub(
            r'\b\d+(?:\.\d+)?(?:ms|s|m|h|d|MB|GB|KB|TB|%)\b',
            '<NUM_UNIT>', message, flags=re.IGNORECASE
        )
        
        # 6. Normalize IDs with numbers (e.g., client_8111, user_id_42, session-123)
        # Match: word + separator + digits
        message = re.sub(
            r'\b([a-zA-Z_]+[_-])(\d+)\b',
            r'\1<NUM>', message
        )
        
        # 7. Normalize port numbers (e.g., :8080, :5432)
        message = re.sub(r':(\d{2,5})\b', r':<PORT>', message)
        
        # 8. Normalize version numbers (e.g., v1.2.3, version 2.0)
        message = re.sub(
            r'\bv?\d+\.\d+(?:\.\d+)?(?:\.\d+)?\b',
            '<VERSION>', message, flags=re.IGNORECASE
        )
        
        # 9. Normalize memory addresses (e.g., 0x7ffe1234abcd)
        message = re.sub(r'\b0x[0-9a-fA-F]{8,}\b', '<ADDR>', message)
        
        # 10. Normalize standalone numbers (catch-all for remaining numbers)
        # This should come LAST to avoid conflicts
        message = re.sub(r'\b\d+\b', '<NUM>', message)
        
        # 11. Normalize file paths (optional - can help cluster file-related errors)
        message = re.sub(
            r'[/\\][\w\-./\\]+\.(py|java|js|ts|go|rb|php|cpp|c|h)',
            '<FILE>', message, flags=re.IGNORECASE
        )
        
        # 12. Normalize whitespace (multiple spaces/tabs → single space)
        message = ' '.join(message.split())
        
        return message

    async def check_health(self) -> bool:
        """Check Qdrant health"""
        try:
            response = await self.http_client.get(f"{self.qdrant_url}/health")
            return response.status_code == 200
        except Exception as e:
            self.logger.error("qdrant_health_check_failed", error=str(e))
            return False

    async def get_embedding(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Get embedding for a text query using Jina service with Redis caching

        Args:
            text: Text to embed
            use_cache: Whether to use Redis cache (default: True)

        Returns:
            768-dimensional embedding vector
        """
        # Normalize text for cache key
        normalized_text = text.lower().strip()
        cache_key = f"embedding:{hashlib.sha256(normalized_text.encode()).hexdigest()[:16]}"

        # Try cache first
        if use_cache:
            try:
                # Import cache service
                from app import cache_service

                cached = await cache_service.get(cache_key)
                if cached:
                    self.logger.info("embedding_cache_hit", text_preview=text[:50])
                    return cached["embedding"]
            except Exception as e:
                self.logger.warning("cache_get_failed", error=str(e))

        # Cache miss - generate embedding
        try:
            response = await self.http_client.post(
                f"{self.jina_service_url}/embeddings",
                json={"texts": [text]}
            )

            response.raise_for_status()
            data = response.json()

            embedding = data["embeddings"][0]["embedding"]
            # Cache the embedding (24 hour TTL)
            if use_cache:
                try:
                    from app import cache_service

                    await cache_service.set(
                        cache_key,
                        {"text": text, "embedding": embedding},
                        ttl=86400  # 24 hours
                    )
                    self.logger.info("embedding_cached", text_preview=text[:50])
                except Exception as e:
                    self.logger.warning("cache_set_failed", error=str(e))

            return embedding

        except Exception as e:
            self.logger.error("embedding_generation_failed", error=str(e))
            raise

    def _calculate_adaptive_threshold(self, query: str, user_threshold: Optional[float] = None) -> float:
        """
        Calculate adaptive similarity threshold based on query characteristics
        
        Research-backed thresholds based on query type:
        - Exact paraphrase (long, detailed): 0.70–0.95
        - Same topic, fewer words: 0.45–0.65
        - Short query vs long log: 0.35–0.55
        - Keyword-style query: 0.25–0.45
        
        Args:
            query: Search query text
            user_threshold: User-specified threshold (overrides adaptive)
            
        Returns:
            Recommended similarity threshold
        """
        # If user explicitly set threshold, respect it
        if user_threshold is not None:
            return user_threshold
        
        # Analyze query characteristics
        word_count = len(query.split())
        char_count = len(query.strip())
        has_sentence_structure = any(p in query for p in ['.', '!', '?', 'the', 'a', 'an', 'is', 'are', 'was', 'were'])
        
        # Adaptive threshold logic
        if word_count >= 15 or (word_count >= 10 and has_sentence_structure):
            # Long descriptive query - high threshold
            # Example: "Error sending email notification through SendGrid API with timeout"
            threshold = 0.70
            query_type = "descriptive"
        elif word_count >= 7 and has_sentence_structure:
            # Medium query with structure - medium-high threshold
            # Example: "The email service failed to send notification"
            threshold = 0.55
            query_type = "structured"
        elif word_count >= 4:
            # Short query - medium threshold
            # Example: "email notification SendGrid error"
            threshold = 0.40
            query_type = "short"
        else:
            # Keyword query - low threshold
            # Example: "email SendGrid"
            threshold = 0.30
            query_type = "keywords"
        
        self.logger.info("adaptive_threshold_calculated",
                        query_preview=query[:50],
                        word_count=word_count,
                        query_type=query_type,
                        threshold=threshold)
        
        return threshold

    async def semantic_search(
        self,
        query: str,
        limit: int = 10,
        service: Optional[str] = None,
        level: Optional[str] = None,
        score_threshold: Optional[float] = None,  # Now optional - will use adaptive if None
        enrich_with_clickhouse: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search on log embeddings with adaptive thresholding
        
        The search automatically adjusts similarity thresholds based on query type:
        - Long descriptive queries: High threshold (0.70) for precise matches
        - Medium queries: Medium threshold (0.55) for relevant matches
        - Short queries: Lower threshold (0.40) for broader matches
        - Keyword queries: Low threshold (0.30) for topic-based matches

        Args:
            query: Search query text (can be descriptive or keywords)
            limit: Maximum number of results
            service: Filter by service name
            level: Filter by log level
            score_threshold: Manual threshold override (if None, uses adaptive)
            enrich_with_clickhouse: Whether to fetch full log details from ClickHouse

        Returns:
            List of similar logs with scores
        """
        
        # Calculate adaptive threshold if not explicitly provided
        adaptive_threshold = self._calculate_adaptive_threshold(query, score_threshold)

        # Get embedding for query
        query_vector = await self.get_embedding(query)

        # Build filter
        filter_conditions = []

        if service:
            filter_conditions.append({
                "key": "service",
                "match": {"value": service}
            })

        if level:
            filter_conditions.append({
                "key": "level",
                "match": {"value": level}
            })

        # Build search request with adaptive threshold
        search_request = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
            "score_threshold": adaptive_threshold
        }

        if filter_conditions:
            search_request["filter"] = {
                "must": filter_conditions
            }

        # Execute search
        try:
            response = await self.http_client.post(
                f"{self.qdrant_url}/collections/log_embeddings/points/search",
                json=search_request
            )

            response.raise_for_status()
            data = response.json()

            # Format results from Qdrant
            results = []
            log_ids_to_enrich = []
            
            for point in data.get("result", []):
                # Convert Unix timestamp to ISO format string if it's an integer
                timestamp = point["payload"]["timestamp"]
                if isinstance(timestamp, int):
                    from datetime import datetime
                    timestamp = datetime.fromtimestamp(timestamp).isoformat()
                
                result = {
                    "id": point["id"],
                    "score": point["score"],
                    "similarity_score": point["score"],  # Alias for frontend
                    "log_id": point["payload"]["log_id"],
                    "timestamp": timestamp,
                    "service": point["payload"]["service"],
                    "environment": point["payload"]["environment"],
                    "level": point["payload"]["level"],
                    "message": point["payload"]["message"],
                    "trace_id": point["payload"].get("trace_id"),
                    "user_id": point["payload"].get("user_id"),
                    "request_id": point["payload"].get("request_id")
                }
                results.append(result)
                log_ids_to_enrich.append(point["payload"]["log_id"])

            # Enrich with full log data from ClickHouse if requested
            if enrich_with_clickhouse and log_ids_to_enrich:
                try:
                    from app import db_service
                    
                    # Fetch full logs from ClickHouse
                    full_logs = await db_service.get_logs_by_ids(log_ids_to_enrich)
                    
                    # Create a lookup map
                    logs_map = {log["log_id"]: log for log in full_logs}
                    
                    # Enrich results with full log details from ClickHouse
                    for result in results:
                        full_log = logs_map.get(result["log_id"])
                        if full_log:
                            # Merge all ClickHouse fields (complete log data)
                            result.update({
                                "message": full_log.get("message", result["message"]),  # Full message (not truncated)
                                "stack_trace": full_log.get("stack_trace"),
                                "host": full_log.get("host"),
                                "pod_name": full_log.get("pod_name"),
                                "container_id": full_log.get("container_id"),
                                "logger_name": full_log.get("logger_name"),
                                "span_id": full_log.get("span_id"),
                                "parent_span_id": full_log.get("parent_span_id"),
                                "thread_name": full_log.get("thread_name"),
                                "correlation_id": full_log.get("correlation_id"),
                                "labels": full_log.get("labels"),
                                "metadata": full_log.get("metadata"),  # JSON string with HTTP details, etc.
                                "is_vectorized": full_log.get("is_vectorized"),
                                "is_anomaly": full_log.get("is_anomaly"),
                                "anomaly_score": full_log.get("anomaly_score"),
                                "source_type": full_log.get("source_type"),
                                "source_file": full_log.get("source_file"),
                                "source_line": full_log.get("source_line"),
                                "ingested_at": full_log.get("ingested_at"),
                                "processed_at": full_log.get("processed_at")
                            })
                    
                    self.logger.info("semantic_search_enriched", 
                                    query_preview=query[:50], 
                                    result_count=len(results),
                                    enriched_count=len(full_logs))
                except Exception as e:
                    self.logger.warning("clickhouse_enrichment_failed", error=str(e))
                    # Continue with Qdrant data only

            return results

        except Exception as e:
            self.logger.error("semantic_search_failed", error=str(e))
            raise

    async def find_similar_errors(
        self,
        log_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find logs similar to a specific log

        Args:
            log_id: ID of the reference log
            limit: Maximum number of similar logs to return

        Returns:
            List of similar logs with scores
        """

        # Get the reference log's vector
        try:
            # First, search for the log to get its vector
            # TODO: for later (real) implementation, you might store the vector ID separately
            # For now, we'll retrieve the point by filtering on log_id

            search_request = {
                "filter": {
                    "must": [
                        {
                            "key": "log_id",
                            "match": {"value": log_id}
                        }
                    ]
                },
                "limit": 1,
                "with_vector": True,
                "with_payload": True
            }

            response = await self.http_client.post(
                f"{self.qdrant_url}/collections/log_embeddings/points/scroll",
                json=search_request
            )

            response.raise_for_status()
            data = response.json()

            if not data.get("result", {}).get("points"):
                return []

            reference_point = data["result"]["points"][0]
            reference_vector = reference_point["vector"]

            # Now search for similar vectors
            similar_request = {
                "vector": reference_vector,
                "limit": limit + 1,  # +1 to exclude the reference itself
                "with_payload": True
            }

            response = await self.http_client.post(
                f"{self.qdrant_url}/collections/log_embeddings/points/search",
                json=similar_request
            )

            response.raise_for_status()
            data = response.json()

            # Format results (exclude the reference log itself)
            results = []
            for point in data.get("result", []):
                if point["payload"]["log_id"] != log_id:
                    results.append({
                        "id": point["id"],
                        "score": point["score"],
                        "similarity_score": point["score"],  # Alias for frontend
                        "log_id": point["payload"]["log_id"],
                        "timestamp": point["payload"]["timestamp"],
                        "service": point["payload"]["service"],
                        "level": point["payload"]["level"],
                        "message": point["payload"]["message"]
                    })

            return results[:limit]

        except Exception as e:
            self.logger.error("find_similar_errors_failed", error=str(e))
            raise

    async def get_collection_stats(self, collection: str = "log_embeddings") -> Dict[str, Any]:
        """Get statistics about a collection"""

        try:
            response = await self.http_client.get(
                f"{self.qdrant_url}/collections/{collection}"
            )

            response.raise_for_status()
            data = response.json()

            result = data.get("result", {})

            return {
                "name": collection,
                "points_count": result.get("points_count", 0),
                "vectors_count": result.get("vectors_count", 0),
                "indexed_vectors_count": result.get("indexed_vectors_count", 0),
                "status": result.get("status", "unknown")
            }

        except Exception as e:
            self.logger.error("get_collection_stats_failed", error=str(e))
            return {
                "name": collection,
                "points_count": 0,
                "status": "error"
            }

    async def cluster_similar_logs(
        self,
        service: Optional[str] = None,
        level: str = "ERROR",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find clusters of similar error messages

        This is a simplified clustering - in production you'd use proper clustering algorithms
        """

        try:
            # Scroll through logs with filter
            scroll_request = {
                "limit": limit,
                "with_payload": True,
                "with_vector": False
            }

            if service or level:
                filter_conditions = []
                if service:
                    filter_conditions.append({
                        "key": "service",
                        "match": {"value": service}
                    })
                if level:
                    filter_conditions.append({
                        "key": "level",
                        "match": {"value": level}
                    })

                scroll_request["filter"] = {"must": filter_conditions}

            response = await self.http_client.post(
                f"{self.qdrant_url}/collections/log_embeddings/points/scroll",
                json=scroll_request
            )

            response.raise_for_status()
            data = response.json()

            # Group by message similarity (simple approach)
            # In production, use proper clustering algorithms
            points = data.get("result", {}).get("points", [])

            # For now, return grouped by service and level
            clusters = {}
            for point in points:
                payload = point["payload"]
                key = f"{payload['service']}_{payload['level']}"

                if key not in clusters:
                    clusters[key] = {
                        "service": payload["service"],
                        "level": payload["level"],
                        "count": 0,
                        "samples": []
                    }

                clusters[key]["count"] += 1
                if len(clusters[key]["samples"]) < 5:  # Keep max 5 samples
                    clusters[key]["samples"].append({
                        "message": payload["message"],
                        "timestamp": payload["timestamp"]
                    })

            return list(clusters.values())

        except Exception as e:
            self.logger.error("cluster_similar_logs_failed", error=str(e))
            return []

    async def semantic_search_clustered(
        self,
        query: str,
        top_k: int = 20,
        service: Optional[str] = None,
        level: Optional[str] = None,
        score_threshold: Optional[float] = None,  # Now optional - uses adaptive
        similarity_threshold: float = 0.85
    ) -> Dict[str, Any]:
        """
        Perform semantic search and return clustered results with adaptive thresholding
        
        The search automatically adjusts similarity thresholds based on query type:
        - Long queries → High precision (threshold ~0.70)
        - Short queries → Broader matches (threshold ~0.30-0.40)
        
        Clustering hierarchy:
        1. Environment (production, staging, dev)
        2. Service (api-gateway, auth-service, etc.)
        3. Level (ERROR, WARN, etc.)
        4. Normalized Pattern (parameterized messages)
        5. Similarity (group logs with score > similarity_threshold)
        
        Args:
            query: Search query (descriptive or keywords)
            top_k: Maximum number of results
            service: Optional service filter
            level: Optional level filter
            score_threshold: Manual threshold override (if None, uses adaptive)
            similarity_threshold: Not used in pattern-based clustering
            
        Returns:
            Clustered search results grouped by environment
        """
        start_time = time.time()
        
        # Step 1: Get raw search results with adaptive thresholding
        results = await self.semantic_search(
            query=query,
            limit=top_k,
            service=service,
            level=level,
            score_threshold=score_threshold,  # Will use adaptive if None
            enrich_with_clickhouse=True
        )
        
        # Step 2: Normalize messages for pattern extraction
        for log in results:
            log["normalized_message"] = self._normalize_message(log["message"])
        
        # Step 3: Group by environment
        env_groups = {}
        for log in results:
            env = log["environment"]
            if env not in env_groups:
                env_groups[env] = []
            env_groups[env].append(log)
        
        # Step 4: Within each environment, cluster by service + level + pattern
        environment_clusters = []
        
        for env, env_logs in env_groups.items():
            # Group by service
            service_groups = {}
            for log in env_logs:
                svc = log["service"]
                if svc not in service_groups:
                    service_groups[svc] = []
                service_groups[svc].append(log)
            
            clusters = []
            cluster_idx = 0
            
            for svc, svc_logs in service_groups.items():
                # Group by level
                level_groups = {}
                for log in svc_logs:
                    lvl = log["level"]
                    if lvl not in level_groups:
                        level_groups[lvl] = []
                    level_groups[lvl].append(log)
                
                for lvl, lvl_logs in level_groups.items():
                    # Group by normalized pattern
                    pattern_groups = {}
                    for log in lvl_logs:
                        pattern = log["normalized_message"]
                        if pattern not in pattern_groups:
                            pattern_groups[pattern] = []
                        pattern_groups[pattern].append(log)
                    
                    # Create clusters for each pattern group
                    for pattern, pattern_logs in pattern_groups.items():
                        # Sort by similarity score within pattern
                        pattern_logs.sort(key=lambda x: x["similarity_score"], reverse=True)
                        
                        clusters.append(self._create_cluster(
                            env, svc, lvl, pattern_logs, cluster_idx, pattern
                        ))
                        cluster_idx += 1
            
            environment_clusters.append({
                "environment": env,
                "total_logs": len(env_logs),
                "clusters": clusters
            })
        
        generation_time = time.time() - start_time
        
        return {
            "query": query,
            "total_results": len(results),
            "environment_groups": environment_clusters,
            "generation_time_seconds": round(generation_time, 3)
        }

    def _create_cluster(
        self,
        environment: str,
        service: str,
        level: str,
        logs: List[Dict],
        idx: int,
        normalized_pattern: str
    ) -> Dict:
        """Helper to create a cluster object with pattern info"""
        avg_similarity = sum(log["similarity_score"] for log in logs) / len(logs)
        
        # Use normalized pattern as dominant pattern (first 80 chars)
        dominant_pattern = normalized_pattern[:80] + "..." if len(normalized_pattern) > 80 else normalized_pattern
        
        timestamps = [log["timestamp"] for log in logs]
        
        return {
            "cluster_id": f"{environment}_{service}_{level}_{idx}",
            "metadata": {
                "environment": environment,
                "service": service,
                "level": level,
                "avg_similarity": round(avg_similarity, 3),
                "log_count": len(logs),
                "time_range": {
                    "earliest": min(timestamps),
                    "latest": max(timestamps)
                },
                "dominant_message_pattern": dominant_pattern
            },
            "logs": logs
        }