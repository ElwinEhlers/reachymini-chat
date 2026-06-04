"""Voice pipeline: microphone → STT → Ollama → TTS → speaker.

Standalone run:
    /home/sbin/reachy/.venv/bin/python3 /home/sbin/reachy/voice/pipeline.py

WebSocket pipeline is used by the chat app's /ws/voice endpoint.
"""

import sys
import logging
import asyncio
import threading
import numpy as np
import sounddevice as sd

# Allow importing the memory package from the project root
if "/home/sbin/reachy" not in sys.path:
    sys.path.insert(0, "/home/sbin/reachy")

from openai import AsyncOpenAI

from voice.stt import STT
from voice.tts import TTS
from voice.vad import VAD

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "qwen3:8b-q4km"

SAMPLE_RATE = 16000
CHANNELS = 1
SILENCE_THRESHOLD = 0.01   # RMS below this → silence
SILENCE_DURATION = 1.5     # seconds of silence before stopping
MAX_RECORD_SECONDS = 30    # hard cap to avoid endless recording

PLACEHOLDER_PERSON_ID = 1


def _build_system_prompt() -> str:
    try:
        from memory.database import init_db
        from memory.context import build_system_prompt
        init_db()
        base = open(
            "/home/sbin/reachy/reachy_chat/src/reachy_chat/profiles"
            "/_reachy_chat_locked_profile/instructions.txt"
        ).read()
        return build_system_prompt(base, person_id=PLACEHOLDER_PERSON_ID)
    except Exception as exc:
        logger.warning("Could not load memory context: %s", exc)
        return "You are Reachy, a small expressive robot. Be friendly and concise."


def _start_memory_conversation() -> int | None:
    try:
        from memory.conversations import start_conversation
        return start_conversation(person_id=PLACEHOLDER_PERSON_ID)
    except Exception as exc:
        logger.warning("Could not start memory conversation: %s", exc)
        return None


def _log_memory_message(conversation_id: int | None, role: str, content: str) -> None:
    if conversation_id is None:
        return
    try:
        from memory.conversations import log_message
        log_message(conversation_id, role, content)
    except Exception as exc:
        logger.warning("Could not log message to memory: %s", exc)


class VoicePipeline:
    """Single-speaker voice pipeline with persistent memory context."""

    def __init__(self) -> None:
        self.stt = STT()
        self.tts = TTS()
        self.client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
        self._conversation_id = _start_memory_conversation()
        self._messages: list[dict] = [
            {"role": "system", "content": _build_system_prompt()}
        ]
        logger.info("VoicePipeline ready (conversation_id=%s)", self._conversation_id)

    def record_until_silence(self) -> np.ndarray:
        """Record from the default microphone until silence is detected.

        Returns a float32 mono array at SAMPLE_RATE Hz.
        """
        frames: list[np.ndarray] = []
        silent_chunks = 0
        chunk_size = int(SAMPLE_RATE * 0.1)  # 100 ms chunks
        max_chunks = int(MAX_RECORD_SECONDS / 0.1)
        silence_chunks_needed = int(SILENCE_DURATION / 0.1)

        print("🎤 Ich höre zu …", flush=True)
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32") as stream:
            for _ in range(max_chunks):
                chunk, _ = stream.read(chunk_size)
                mono = chunk[:, 0] if chunk.ndim > 1 else chunk.flatten()
                frames.append(mono)
                rms = float(np.sqrt(np.mean(mono ** 2)))
                if rms < SILENCE_THRESHOLD:
                    silent_chunks += 1
                    if silent_chunks >= silence_chunks_needed and len(frames) > silence_chunks_needed:
                        break
                else:
                    silent_chunks = 0

        audio = np.concatenate(frames)
        print("⏹ Aufnahme beendet.", flush=True)
        return audio

    async def _call_ollama(self, user_text: str) -> str:
        """Send user_text to Ollama and return the full assistant response."""
        self._messages.append({"role": "user", "content": user_text})
        response_text = ""
        stream = await self.client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=self._messages,
            stream=True,
            extra_body={"think": True},
        )
        # Collect and filter thinking blocks
        from voice._think_filter import ThinkFilter
        tf = ThinkFilter()
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                response_text += tf.feed(delta.content)
        response_text += tf.flush()
        self._messages.append({"role": "assistant", "content": response_text})
        return response_text.strip()

    def run_once(self) -> None:
        """One full turn: record → STT → Ollama → TTS → play."""
        audio = self.record_until_silence()
        user_text = self.stt.transcribe(audio, sample_rate=SAMPLE_RATE)
        if not user_text:
            print("(nichts erkannt)", flush=True)
            return
        print(f"👤 {user_text}", flush=True)
        _log_memory_message(self._conversation_id, "user", user_text)

        response = asyncio.run(self._call_ollama(user_text))
        print(f"🤖 {response}", flush=True)
        _log_memory_message(self._conversation_id, "assistant", response)

        self.tts.speak(response)

    def run_loop(self) -> None:
        """Continuous loop until KeyboardInterrupt."""
        print("Sprachsteuerung aktiv. Drücke Ctrl+C zum Beenden.", flush=True)
        try:
            while True:
                self.run_once()
        except KeyboardInterrupt:
            print("\nBeendet.", flush=True)


# ---------------------------------------------------------------------------
# Lazy module-level singletons reused across WebSocket connections
# ---------------------------------------------------------------------------

_ws_stt: STT | None = None
_ws_tts: TTS | None = None
_ws_vad: VAD | None = None


def _get_ws_stt() -> STT:
    global _ws_stt
    if _ws_stt is None:
        _ws_stt = STT()
    return _ws_stt


def _get_ws_tts() -> TTS:
    global _ws_tts
    if _ws_tts is None:
        _ws_tts = TTS()
    return _ws_tts


def _get_ws_vad() -> VAD:
    global _ws_vad
    if _ws_vad is None:
        _ws_vad = VAD(silence_duration_ms=1500)
    return _ws_vad


class VoiceWebSocketPipeline:
    """Push-to-talk voice pipeline for the /ws/voice WebSocket endpoint.

    Protocol (browser → server):
        {"type": "start_recording"}  — begin capturing mic
        {"type": "stop_recording"}   — end capture, run STT → send transcript
        {"type": "speak", "text": "..."}  — TTS request
        {"type": "stop"}             — close pipeline

    Protocol (server → browser):
        {"type": "status", "value": "listening"|"processing"|"speaking"|null}
        {"type": "transcript", "text": "..."}
    """

    def __init__(self) -> None:
        self.stt = _get_ws_stt()
        self.tts = _get_ws_tts()
        self.vad = _get_ws_vad()
        self._recording_stop = threading.Event()
        self._tts_active = False

    async def run(self, websocket: object) -> None:
        self._ws = websocket
        await self._receive_loop()

    async def _send(self, msg: dict) -> None:
        try:
            await self._ws.send_json(msg)  # type: ignore[attr-defined]
        except Exception:
            pass

    async def _receive_loop(self) -> None:
        loop = asyncio.get_running_loop()
        audio_future: asyncio.Future | None = None

        try:
            while True:
                data = await self._ws.receive_json()  # type: ignore[attr-defined]
                msg_type = data.get("type")

                if msg_type == "start_recording":
                    if audio_future and not audio_future.done():
                        continue  # already recording
                    self._recording_stop.clear()
                    await self._send({"type": "status", "value": "listening"})
                    audio_future = loop.run_in_executor(
                        None, self.vad.record_until_stop, self._recording_stop
                    )

                elif msg_type == "stop_recording":
                    self._recording_stop.set()
                    if audio_future is not None:
                        audio = await audio_future
                        audio_future = None
                        if audio is not None and len(audio) > 0:
                            import numpy as _np
                            _rms = float(_np.sqrt(_np.mean(audio ** 2)))
                            logger.info("PTT audio: %.4f s, RMS=%.5f", len(audio) / 16000, _rms)
                            await self._send({"type": "status", "value": "processing"})
                            text = await loop.run_in_executor(None, self.stt.transcribe, audio)
                            logger.info("STT result: %r", text)
                            if text:
                                await self._send({"type": "transcript", "text": text})
                            else:
                                await self._send({"type": "status", "value": None})
                        else:
                            await self._send({"type": "status", "value": None})

                elif msg_type == "speak":
                    text = data.get("text", "").strip()
                    if not text:
                        continue
                    self._recording_stop.set()
                    self._tts_active = True
                    await self._send({"type": "status", "value": "speaking"})
                    await loop.run_in_executor(None, self.tts.speak, text)
                    await asyncio.sleep(0.3)  # brief echo-suppression buffer
                    self._tts_active = False

                elif msg_type == "stop":
                    self._recording_stop.set()
                    break

        except Exception:
            self._recording_stop.set()


if __name__ == "__main__":
    VoicePipeline().run_loop()
