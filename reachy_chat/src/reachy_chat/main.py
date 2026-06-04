"""Entrypoint for the Reachy Mini conversation app (Ollama/local LLM)."""

import os
import sys
import time
import asyncio
import logging
import threading
from typing import Optional

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from reachy_mini import ReachyMini, ReachyMiniApp


logger = logging.getLogger(__name__)


def setup_logger(debug: bool = False) -> logging.Logger:
    """Configure logging."""
    log_level = "DEBUG" if debug else "INFO"
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s:%(lineno)d | %(message)s",
    )
    return logging.getLogger(__name__)


def run(
    robot: ReachyMini,
    app_stop_event: Optional[threading.Event] = None,
    settings_app: Optional[FastAPI] = None,
) -> None:
    """Run the conversation app with Ollama backend."""
    from reachy_chat.moves import MovementManager
    from reachy_chat.tools.core_tools import ToolDependencies
    from reachy_chat.ollama_chat import OllamaChatHandler

    setup_logger()
    logger.info("Starting Reachy Chat (Ollama)")

    # Memory system (optional — app starts normally if unavailable)
    _conversation_id: int | None = None
    try:
        if "/home/sbin/reachy" not in sys.path:
            sys.path.insert(0, "/home/sbin/reachy")
        from memory.database import init_db
        from memory.persons import ensure_default_person
        from memory.conversations import start_conversation
        init_db()
        ensure_default_person()
        _conversation_id = start_conversation(person_id=1)
        logger.info("Memory system ready (conversation_id=%d)", _conversation_id)
    except Exception as _e:
        logger.warning("Memory system unavailable: %s", _e)

    # Movement system
    movement_manager = MovementManager(current_robot=robot)

    # Tool dependencies (no camera/vision/audio in Phase 1)
    deps = ToolDependencies(
        reachy_mini=robot,
        movement_manager=movement_manager,
    )

    # Create an asyncio loop for the chat handler
    loop = asyncio.new_event_loop()

    # LLM handler
    chat_handler = OllamaChatHandler(deps, conversation_id=_conversation_id)

    # FastAPI routes
    app = settings_app if settings_app else FastAPI()

    class ChatRequest(BaseModel):
        message: str

    @app.get("/status")
    async def status():
        connected = await chat_handler.check_connection()
        return {
            "connected": connected,
            "model": chat_handler.model,
        }

    @app.get("/history")
    async def history():
        return chat_handler.get_history()

    @app.post("/clear")
    async def clear():
        chat_handler.clear_history()
        return {"status": "ok"}

    @app.get("/memory")
    async def memory(response: Response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        try:
            import sqlite3 as _sqlite3
            from memory.persons import list_persons, get_attributes
            from memory.facts import get_facts
            from memory.database import get_connection

            persons = list_persons()
            for p in persons:
                p["attributes"] = get_attributes(p["id"])

            con = get_connection()
            con.row_factory = _sqlite3.Row
            cur = con.cursor()

            cur.execute("SELECT COUNT(*) AS n FROM conversations")
            conversation_count = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS n FROM messages")
            message_count = cur.fetchone()["n"]

            cur.execute(
                "SELECT m.id, m.conversation_id, m.role, m.content, m.created_at "
                "FROM messages m ORDER BY m.id DESC LIMIT 20"
            )
            recent_messages = [dict(r) for r in cur.fetchall()]

            return {
                "persons": persons,
                "facts": get_facts(person_id=None),
                "conversation_count": conversation_count,
                "message_count": message_count,
                "recent_messages": recent_messages,
            }
        except Exception as e:
            return {"error": str(e), "persons": [], "facts": [],
                    "conversation_count": 0, "message_count": 0, "recent_messages": []}

    @app.websocket("/ws/voice")
    async def voice_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            if "/home/sbin/reachy" not in sys.path:
                sys.path.insert(0, "/home/sbin/reachy")
            from voice.pipeline import VoiceWebSocketPipeline
            pipeline = VoiceWebSocketPipeline()
            await pipeline.run(websocket)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("Voice WebSocket error: %s", e)
            try:
                await websocket.close()
            except Exception:
                pass

    @app.post("/chat")
    async def chat(req: ChatRequest):
        async def generate():
            async for token in chat_handler.chat(req.message):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    # Start movement system
    movement_manager.start()

    # Wait for stop signal
    if app_stop_event:
        def poll_stop():
            app_stop_event.wait()
            logger.info("Stop event received, shutting down...")

        threading.Thread(target=poll_stop, daemon=True).start()

    try:
        # Block until interrupted
        if app_stop_event:
            app_stop_event.wait()
        else:
            # When running standalone, the FastAPI server is started by
            # ReachyMiniApp.wrapped_run() — we just need to keep alive
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, shutting down...")
    finally:
        movement_manager.stop()
        try:
            robot.media.close()
        except Exception:
            pass
        robot.client.disconnect()
        time.sleep(0.5)
        logger.info("Shutdown complete.")


class ReachyChat(ReachyMiniApp):
    """Reachy Mini Apps entry point for the conversation app."""

    custom_app_url = "http://0.0.0.0:8042"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        """Run the conversation app."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        run(
            robot=reachy_mini,
            app_stop_event=stop_event,
            settings_app=self.settings_app,
        )


def main() -> None:
    """Standalone entrypoint (reachy-chat CLI command)."""
    app = ReachyChat()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
