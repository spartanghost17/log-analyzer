.PHONY: help start deploy down build stop logs logs-phase1 logs-phase2 logs-phase3 health health-phase2 health-phase3 rebuild-phase1 rebuild-phase2 rebuild-phase3 rebuild-all status verify-code clean

# Default target - show help
help:
	@echo "================================================"
	@echo "  Log Analysis Platform - Makefile Commands"
	@echo "================================================"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  make start          - Start all services"
	@echo "  make stop           - Stop all services"
	@echo "  make down           - Stop and remove all containers/volumes"
	@echo ""
	@echo "🔧 Build Commands:"
	@echo "  make build          - Build all services (no cache)"
	@echo "  make rebuild-phase1 - Rebuild Phase 1 services (log-generator, consumer, analyzer)"
	@echo "  make rebuild-phase2 - Rebuild Phase 2 services (jina-embeddings, vectorization-worker)"
	@echo "  make rebuild-phase3 - Rebuild Phase 3 services (api, frontend)"
	@echo "  make rebuild-all    - Complete rebuild (down, build, up)"
	@echo ""
	@echo "📊 Monitoring:"
	@echo "  make status         - Show container status"
	@echo "  make logs           - Follow all logs"
	@echo "  make logs-phase1    - Follow Phase 1 service logs"
	@echo "  make logs-phase2    - Follow Phase 2 service logs"
	@echo "  make logs-phase3    - Follow Phase 3 service logs"
	@echo "  make health         - Check health of Phase 1 services"
	@echo "  make health-phase2  - Check health of Phase 2 services"
	@echo "  make health-phase3  - Check health of Phase 3 services"
	@echo ""
	@echo "🔍 Debugging:"
	@echo "  make verify-code    - Verify service code is correct"
	@echo "  make clean          - Clean up Docker system"
	@echo ""
	@echo "🌐 Access Points:"
	@echo "  http://localhost:3000  - Frontend (React)"
	@echo "  http://localhost:8005  - API Gateway"
	@echo "  http://localhost:8080  - Kafka UI"
	@echo ""

# Start all services using the start script
start:
	@echo "🚀 Starting all services..."
	./infrastructure/start.sh

# Deploy using production docker-compose
deploy:
	@echo "🚀 Deploying services..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . up -d

# Stop and remove all containers and volumes
down:
	@echo "🛑 Stopping and removing all containers and volumes..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . down --volumes

# Build all services without cache
build:
	@echo "🔨 Building all services (no cache)..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . build --no-cache

# Stop all services
stop:
	@echo "🛑 Stopping all services..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . stop

# Show all logs (follow mode)
logs:
	@echo "📋 Following all logs (Ctrl+C to exit)..."
	docker compose -f dinfrastructure/docker-compose.yml --project-directory . logs -f

# Show Phase 1 service logs only
logs-phase1:
	@echo "📋 Following Phase 1 logs (Ctrl+C to exit)..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . logs -f log-generator clickhouse-consumer llm-analyzer

# Show Phase 2 service logs only
logs-phase2:
	@echo "📋 Following Phase 2 logs (Ctrl+C to exit)..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . logs -f jina-embeddings vectorization-worker

# Show Phase 3 service logs only
logs-phase3:
	@echo "📋 Following Phase 3 logs (Ctrl+C to exit)..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . logs -f api frontend

# Show container status
status:
	@echo "📊 Container Status:"
	@docker compose -f infrastructure/docker-compose.yml --project-directory . ps

# Check health of all services
health:
	@echo "🏥 Checking service health..."
	@echo ""
	@echo "Log Generator (port 8000):"
	@curl -s http://localhost:8000/health | jq '.' 2>/dev/null || echo "  ❌ Not responding"
	@echo ""
	@echo "Kafka Consumer (port 8001):"
	@curl -s http://localhost:8001/health | jq '.' 2>/dev/null || echo "  ❌ Not responding"
	@echo ""
	@echo "LLM Analyzer (port 8002):"
	@curl -s http://localhost:8002/health | jq '.' 2>/dev/null || echo "  ❌ Not responding"
	@echo ""

# Check health of Phase 2 services
health-phase2:
	@echo "🏥 Checking Phase 2 service health..."
	@echo ""
	@echo "Jina Embeddings (port 8003):"
	@curl -s http://localhost:8003/health | jq '.' 2>/dev/null || echo "  ❌ Not responding"
	@echo ""
	@echo "Vectorization Worker (port 8004):"
	@curl -s http://localhost:8004/health | jq '.' 2>/dev/null || echo "  ❌ Not responding"
	@echo ""

# Check health of Phase 3 services
health-phase3:
	@echo "🏥 Checking Phase 3 service health..."
	@echo ""
	@echo "API Gateway (port 8005):"
	@curl -s http://localhost:8005/health | jq '.' 2>/dev/null || echo "  ❌ Not responding"
	@echo ""
	@echo "Frontend (port 3000):"
	@curl -s http://localhost:3000 > /dev/null 2>&1 && echo "  ✅ Responding" || echo "  ❌ Not responding"
	@echo ""

# Rebuild Phase 1 services (log-generator, clickhouse-consumer, llm-analyzer)
rebuild-phase1:
	@echo "🔧 Rebuilding Phase 1 Services..."
	@echo ""
	@echo "1️⃣  Stopping services..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . stop log-generator clickhouse-consumer llm-analyzer
	@echo ""
	@echo "2️⃣  Removing old containers..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . rm -f log-generator clickhouse-consumer llm-analyzer
	@echo ""
	@echo "3️⃣  Rebuilding services (no cache)..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . build --no-cache log-generator clickhouse-consumer llm-analyzer
	@echo ""
	@echo "4️⃣  Starting services..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . up -d log-generator clickhouse-consumer llm-analyzer
	@echo ""
	@echo "5️⃣  Waiting for services to start..."
	@sleep 10
	@echo ""
	@echo "6️⃣  Checking status..."
	@docker compose -f infrastructure/docker-compose.yml --project-directory . ps log-generator clickhouse-consumer llm-analyzer
	@echo ""
	@echo "✅ Rebuild complete!"
	@echo ""
	@echo "💡 Check logs with: make logs-phase1"
	@echo "💡 Check health with: make health"

# Rebuild Phase 2 services (jina-embeddings, vectorization-worker)
rebuild-phase2:
	@echo "🔧 Rebuilding Phase 2 Services..."
	@echo ""
	@echo "1️⃣  Stopping services..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . stop jina-embeddings vectorization-worker
	@echo ""
	@echo "2️⃣  Removing old containers..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . rm -f jina-embeddings vectorization-worker qdrant-init
	@echo ""
	@echo "3️⃣  Rebuilding services (no cache)..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . build --no-cache jina-embeddings vectorization-worker
	@echo ""
	@echo "4️⃣  Reinitializing Qdrant..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . up -d qdrant-init
	@sleep 5
	@echo ""
	@echo "5️⃣  Starting services..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . up -d jina-embeddings vectorization-worker
	@echo ""
	@echo "6️⃣  Waiting for services to start..."
	@sleep 10
	@echo ""
	@echo "7️⃣  Checking status..."
	@docker compose -f infrastructure/docker-compose.yml --project-directory . ps jina-embeddings vectorization-worker
	@echo ""
	@echo "✅ Rebuild complete!"
	@echo ""
	@echo "💡 Check logs with: make logs-phase2"
	@echo "💡 Check health with: make health-phase2"

# Rebuild Phase 3 services (api, frontend)
rebuild-phase3:
	@echo "🔧 Rebuilding Phase 3 Services..."
	@echo ""
	@echo "1️⃣  Stopping services..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . stop api frontend
	@echo ""
	@echo "2️⃣  Removing old containers..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . rm -f api frontend
	@echo ""
	@echo "3️⃣  Rebuilding services (no cache)..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . build --no-cache api frontend
	@echo ""
	@echo "4️⃣  Starting services..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . up -d api frontend
	@echo ""
	@echo "5️⃣  Waiting for services to start..."
	@sleep 10
	@echo ""
	@echo "6️⃣  Checking status..."
	@docker compose -f infrastructure/docker-compose.yml --project-directory . ps api frontend
	@echo ""
	@echo "✅ Rebuild complete!"
	@echo ""
	@echo "💡 Check logs with: make logs-phase3"
	@echo "💡 Check health with: make health-phase3"
	@echo "💡 Open frontend: http://localhost:3000"

# Complete rebuild (nuclear option)
rebuild-all:
	@echo "🔨 Complete rebuild (down, build, up)..."
	@echo ""
	@echo "1️⃣  Stopping and removing everything..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . down --volumes
	@echo ""
	@echo "2️⃣  Building all services (no cache)..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . build --no-cache
	@echo ""
	@echo "3️⃣  Starting all services..."
	docker compose -f infrastructure/docker-compose.yml --project-directory . up -d
	@echo ""
	@echo "4️⃣  Waiting for services to start..."
	@sleep 15
	@echo ""
	@echo "5️⃣  Checking status..."
	@docker compose -f infrastructure/docker-compose.yml --project-directory . ps
	@echo ""
	@echo "✅ Complete rebuild done!"
	@echo ""
	@echo "💡 Check logs with: make logs"
	@echo "💡 Check health with: make health"

# Verify service code is correct
verify-code:
	@echo "🔍 Verifying Service Code..."
	@echo ""
	@echo "1. Checking log-generator (no faker)..."
	@if grep -q "faker" services/log-generator/app.py 2>/dev/null; then \
		echo "  ❌ FAIL: Found faker import"; \
	else \
		echo "  ✅ PASS: No faker import"; \
	fi
	@echo ""
	@echo "2. Checking log-generator (Confluent Kafka)..."
	@if grep -q "from confluent_kafka import Producer" services/log-generator/app.py 2>/dev/null; then \
		echo "  ✅ PASS: Uses Confluent Kafka"; \
	else \
		echo "  ❌ FAIL: Missing Confluent Kafka"; \
	fi
	@echo ""
	@echo "3. Checking consumer (SQLAlchemy)..."
	@if grep -q "from clickhouse_sqlalchemy import" services/kafka-consumer/app.py 2>/dev/null; then \
		echo "  ✅ PASS: Uses clickhouse-sqlalchemy"; \
	else \
		echo "  ❌ FAIL: Missing clickhouse-sqlalchemy"; \
	fi
	@echo ""
	@echo "4. Checking consumer (port 9000)..."
	@if grep -q "clickhouse_port.*9000" services/kafka-consumer/app.py 2>/dev/null; then \
		echo "  ✅ PASS: Uses port 9000 (native)"; \
	else \
		echo "  ❌ FAIL: Wrong port"; \
	fi
	@echo ""
	@echo "5. Checking analyzer (SQLAlchemy)..."
	@if grep -q "from clickhouse_sqlalchemy import" services/llm-analyzer/app.py 2>/dev/null; then \
		echo "  ✅ PASS: Uses clickhouse-sqlalchemy"; \
	else \
		echo "  ❌ FAIL: Missing clickhouse-sqlalchemy"; \
	fi
	@echo ""
	@echo "6. Checking analyzer (no clickhouse-connect)..."
	@if grep -q "clickhouse_connect" services/llm-analyzer/app.py 2>/dev/null; then \
		echo "  ❌ FAIL: Found clickhouse-connect"; \
	else \
		echo "  ✅ PASS: No clickhouse-connect"; \
	fi
	@echo ""
	@echo "7. Checking analyzer (port 9000)..."
	@if grep -q "clickhouse_port.*9000" services/llm-analyzer/app.py 2>/dev/null; then \
		echo "  ✅ PASS: Uses port 9000 (native)"; \
	else \
		echo "  ❌ FAIL: Wrong port"; \
	fi
	@echo ""
	@echo "📊 Verification Summary"
	@echo "======================="
	@echo "If all checks passed, the code is correct."
	@echo "If errors are in Docker logs, run: make rebuild-phase1"

# Clean up Docker system
clean:
	@echo "🧹 Cleaning up Docker system..."
	@echo ""
	@echo "Removing stopped containers..."
	docker container prune -f
	@echo ""
	@echo "Removing unused images..."
	docker image prune -f
	@echo ""
	@echo "Removing unused volumes..."
	docker volume prune -f
	@echo ""
	@echo "Removing unused networks..."
	docker network prune -f
	@echo ""
	@echo "✅ Cleanup complete!"