"""
WebSocket Router
Real-time log streaming via WebSocket
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import structlog

from ..services.database import DatabaseService

router = APIRouter()
logger = structlog.get_logger()


# ============================================================================
# WebSocket Connection Manager
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and store new connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected", total_connections=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        """Remove connection"""
        self.active_connections.remove(websocket)
        logger.info("websocket_disconnected", total_connections=len(self.active_connections))

    async def send_log(self, log: dict, websocket: WebSocket):
        """Send log to specific connection"""
        try:
            await websocket.send_json(log)
        except Exception as e:
            logger.error("failed_to_send_log", error=str(e))

    async def broadcast(self, log: dict):
        """Broadcast log to all connections"""
        for connection in self.active_connections:
            try:
                await connection.send_json(log)
            except Exception as e:
                logger.error("failed_to_broadcast", error=str(e))


manager = ConnectionManager()


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@router.websocket("/logs")
async def websocket_logs(
        websocket: WebSocket,
        service: Optional[str] = Query(None),
        level: Optional[str] = Query(None)
):
    """
    Real-time log streaming via WebSocket

    - **service**: Filter by service name
    - **level**: Filter by log level

    Sends new logs as they arrive in real-time.
    """

    await manager.connect(websocket)

    try:
        # Import here to avoid circular dependency
        from ..app import db_service
        db: DatabaseService = db_service

        # Track last seen log ID to avoid duplicates
        last_log_id = None

        while True:
            # Poll for new logs every second
            await asyncio.sleep(1)

            # Get recent logs
            logs = db.get_logs(
                limit=10,
                service=service,
                level=level
            )

            # Send new logs
            for log in reversed(logs):  # Oldest first
                if last_log_id and log["log_id"] == last_log_id:
                    break

                await manager.send_log(log, websocket)

            # Update last seen
            if logs:
                last_log_id = logs[0]["log_id"]

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("client_disconnected")
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        manager.disconnect(websocket)