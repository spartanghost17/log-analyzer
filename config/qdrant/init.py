#!/usr/bin/env python3
"""
Qdrant Vector Database Initialization
Creates collections and indexes for log embeddings

Unlike SQL databases, Qdrant is initialized programmatically via HTTP API.
This script creates the necessary collections for storing log embeddings.
"""

import os
import sys
import time
import requests
from typing import Dict, Any

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
QDRANT_URL = f"http://{QDRANT_HOST}:{QDRANT_PORT}"

# Jina embeddings dimension (jina-embeddings-v2-base-en)
EMBEDDING_DIMENSION = 768

# Retry configuration
MAX_RETRIES = 30
RETRY_DELAY = 2


def wait_for_qdrant():
    """Wait for Qdrant to be ready"""
    print(f"Waiting for Qdrant at {QDRANT_URL}...")

    for i in range(MAX_RETRIES):
        try:
            response = requests.get(f"{QDRANT_URL}/")
            if response.status_code == 200:
                print("✅ Qdrant is ready!")
                return True
        except requests.exceptions.RequestException:
            pass

        print(f"⏳ Attempt {i + 1}/{MAX_RETRIES}: Qdrant not ready, waiting {RETRY_DELAY}s...")
        time.sleep(RETRY_DELAY)

    print("❌ Qdrant failed to start!")
    return False


def collection_exists(collection_name: str) -> bool:
    """Check if a collection exists"""
    try:
        response = requests.get(f"{QDRANT_URL}/collections/{collection_name}")
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def create_collection(collection_name: str, config: Dict[str, Any]) -> bool:
    """Create a Qdrant collection"""
    try:
        response = requests.put(
            f"{QDRANT_URL}/collections/{collection_name}",
            json=config
        )

        if response.status_code in [200, 201]:
            print(f"✅ Created collection: {collection_name}")
            return True
        else:
            print(f"❌ Failed to create collection {collection_name}: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Error creating collection {collection_name}: {e}")
        return False


def create_payload_index(collection_name: str, field_name: str, field_type: str) -> bool:
    """Create an index on a payload field for faster filtering"""
    try:
        response = requests.put(
            f"{QDRANT_URL}/collections/{collection_name}/index",
            json={
                "field_name": field_name,
                "field_schema": field_type
            }
        )

        if response.status_code in [200, 201]:
            print(f"✅ Created index on {collection_name}.{field_name}")
            return True
        else:
            print(f"⚠️  Failed to create index on {field_name}: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"⚠️  Error creating index on {field_name}: {e}")
        return False


def initialize_qdrant():
    """Initialize Qdrant with all required collections"""

    print("=" * 60)
    print("Qdrant Vector Database Initialization")
    print("=" * 60)
    print()

    # Wait for Qdrant to be ready
    if not wait_for_qdrant():
        sys.exit(1)

    print()
    print("Creating collections...")
    print("-" * 60)

    # =========================================================================
    # Collection 1: log_embeddings
    # Primary collection for storing log message embeddings
    # =========================================================================

    log_embeddings_config = {
        "vectors": {
            "size": EMBEDDING_DIMENSION,
            "distance": "Cosine"  # Cosine similarity for semantic search
        },
        "optimizers_config": {
            "default_segment_number": 2
        },
        "replication_factor": 1,
        "write_consistency_factor": 1
    }

    if collection_exists("log_embeddings"):
        print("ℹ️  Collection 'log_embeddings' already exists")
    else:
        if create_collection("log_embeddings", log_embeddings_config):
            # Create indexes for fast filtering
            create_payload_index("log_embeddings", "service", "keyword")
            create_payload_index("log_embeddings", "level", "keyword")
            create_payload_index("log_embeddings", "environment", "keyword")
            create_payload_index("log_embeddings", "timestamp", "integer")

    # =========================================================================
    # Collection 2: error_patterns
    # Store embeddings of normalized error patterns
    # =========================================================================

    error_patterns_config = {
        "vectors": {
            "size": EMBEDDING_DIMENSION,
            "distance": "Cosine"
        },
        "optimizers_config": {
            "default_segment_number": 2
        },
        "replication_factor": 1,
        "write_consistency_factor": 1
    }

    if collection_exists("error_patterns"):
        print("ℹ️  Collection 'error_patterns' already exists")
    else:
        if create_collection("error_patterns", error_patterns_config):
            # Create indexes
            create_payload_index("error_patterns", "pattern_hash", "keyword")
            create_payload_index("error_patterns", "service", "keyword")
            create_payload_index("error_patterns", "first_seen", "integer")
            create_payload_index("error_patterns", "last_seen", "integer")

    print()
    print("-" * 60)
    print("✅ Qdrant initialization complete!")
    print()

    # Print collection info
    try:
        response = requests.get(f"{QDRANT_URL}/collections")
        if response.status_code == 200:
            collections = response.json()
            print("📊 Collections:")
            for collection in collections.get("result", {}).get("collections", []):
                print(f"  - {collection['name']}")
    except:
        pass

    print()
    print("=" * 60)


if __name__ == "__main__":
    initialize_qdrant()