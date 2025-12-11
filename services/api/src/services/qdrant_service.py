"""
Qdrant Service
Handles vector search operations with Qdrant
"""

import hashlib
from typing import List, Dict, Any, Optional

import httpx

from ..settings import get_logger

logger = get_logger(__name__)


class QdrantService:
    """Service for Qdrant vector search operations"""

    def __init__(self):
        self.logger = logger.bind(component="qdrant_service")
        self.qdrant_host = "qdrant"
        self.qdrant_port = 6333
        self.qdrant_url = f"http://{self.qdrant_host}:{self.qdrant_port}"
        self.jina_service_url = "http://jina-embeddings:8003"
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

    async def semantic_search(
        self,
        query: str,
        limit: int = 10,
        service: Optional[str] = None,
        level: Optional[str] = None,
        score_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search on log embeddings

        Args:
            query: Search query text
            limit: Maximum number of results
            service: Filter by service name
            level: Filter by log level
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of similar logs with scores
        """

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

        # Build search request
        search_request = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
            "score_threshold": score_threshold
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

            # Format results
            results = []
            for point in data.get("result", []):
                results.append({
                    "id": point["id"],
                    "score": point["score"],
                    "log_id": point["payload"]["log_id"],
                    "timestamp": point["payload"]["timestamp"],
                    "service": point["payload"]["service"],
                    "environment": point["payload"]["environment"],
                    "level": point["payload"]["level"],
                    "message": point["payload"]["message"],
                    "trace_id": point["payload"].get("trace_id"),
                    "user_id": point["payload"].get("user_id"),
                    "request_id": point["payload"].get("request_id")
                })

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
            # In a real implementation, you might store the vector ID separately
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