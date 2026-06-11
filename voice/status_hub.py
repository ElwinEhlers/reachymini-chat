"""Thread-safe broadcast hub for voice pipeline status and chat events.

The wake-word pipeline runs in its own thread and publishes state changes and
chat messages from there, while the FastAPI ``/ws/voice`` endpoint serves browser
clients on the app's asyncio loop. The hub bridges the two: ``publish`` /
``broadcast_message`` may be called from any thread and schedule the actual
WebSocket sends on the app loop via ``call_soon_threadsafe``.
"""

import asyncio
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class VoiceStatusHub:
    """Fan-out of pipeline status/chat events to connected WebSocket clients."""

    def __init__(self) -> None:
        self._clients: set[Any] = set()
        self._lock = threading.Lock()
        self._state: str = "idle"
        self._muted: bool = False
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- App-Loop / Client-Registrierung ------------------------------------

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the app's asyncio loop (set lazily on first WS connection)."""
        self._loop = loop

    def register(self, ws: Any) -> None:
        with self._lock:
            self._clients.add(ws)

    def unregister(self, ws: Any) -> None:
        with self._lock:
            self._clients.discard(ws)

    # -- Mute / State -------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def muted(self) -> bool:
        return self._muted

    def set_mute(self, value: bool) -> None:
        self._muted = bool(value)
        logger.info("TTS %s.", "stummgeschaltet" if self._muted else "aktiv")

    # -- Senden (thread-sicher) ---------------------------------------------

    def publish(self, state: str) -> None:
        """Broadcast a new pipeline state to all clients (from any thread)."""
        self._state = state
        self._dispatch({"type": "status", "value": state})

    def broadcast_message(self, role: str, text: str) -> None:
        """Broadcast a chat message (user transcript / assistant reply)."""
        self._dispatch({"type": "chat", "role": role, "text": text})

    def _dispatch(self, msg: dict) -> None:
        loop = self._loop
        if loop is None:
            return  # Noch kein Client verbunden → nichts zu senden.
        try:
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._broadcast(msg))
            )
        except RuntimeError:
            pass

    async def _broadcast(self, msg: dict) -> None:
        with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_json(msg)
            except Exception:
                self.unregister(ws)
