"""
WebSocket ConnectionManager für Content-Autopilot v2 (Issue #58).

Tenant-isolierte Channels: "tenant:{slug}:setup"
"""
import logging
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, channel: str, ws: WebSocket):
        await ws.accept()
        self._connections[channel].append(ws)
        logger.info("WS connect: channel=%s, total=%d", channel, len(self._connections[channel]))

    def disconnect(self, channel: str, ws: WebSocket):
        self._connections[channel] = [c for c in self._connections[channel] if c is not ws]
        logger.info("WS disconnect: channel=%s, remaining=%d", channel, len(self._connections[channel]))

    async def broadcast(self, channel: str, message: dict) -> int:
        """Broadcast JSON to all connections on a channel. Returns number of clients reached."""
        connections = self._connections.get(channel, [])
        sent = 0
        dead = []
        for ws in connections:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(channel, ws)
        return sent


ws_manager = ConnectionManager()  # global singleton

# ---------------------------------------------------------------------------
# FastAPI Router
# ---------------------------------------------------------------------------

ws_router = APIRouter()


@ws_router.websocket("/ws/brand-voice/{tenant_slug}")
async def brand_voice_ws(ws: WebSocket, tenant_slug: str):
    channel = f"tenant:{tenant_slug}:setup"
    await ws_manager.connect(channel, ws)
    try:
        while True:
            await ws.receive_text()  # keep alive, ignore incoming
    except WebSocketDisconnect:
        ws_manager.disconnect(channel, ws)


class NotifyRequest(BaseModel):
    channel: str
    message: dict


@ws_router.post("/internal/notify")
async def internal_notify(req: NotifyRequest):
    """Intern: Celery-Worker ruft diesen Endpoint auf, um WS-Push auszulösen."""
    sent = await ws_manager.broadcast(req.channel, req.message)
    return {"sent": sent, "channel": req.channel}
