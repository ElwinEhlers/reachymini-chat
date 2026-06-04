# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Context

- **OS:** Ubuntu Desktop (Bash only — no PowerShell)
- **Working directory:** `/home/sbin/reachy`
- **Python environment:** `.venv` via `uv` — `/home/sbin/reachy/.venv`
- **Interpreter:** `python3`

## Project: Reachy Mini Chat

Browser-based conversational interface for the Reachy Mini Lite robot using a local LLM (Ollama). The robot SDK auto-detects hardware vs. simulation — no code changes needed when switching.

**Required reading for agents:** https://github.com/pollen-robotics/reachy_mini/blob/develop/AGENTS.md

### Prerequisites (must be running before SDK or chat app)

| Service | Command | URL |
|---------|---------|-----|
| Daemon (simulation) | `uv run reachy-mini-daemon --sim` | `http://localhost:8000` |
| Daemon (simulation + scene) | `uv run reachy-mini-daemon --sim --scene minimal` | `http://localhost:8000` |
| Chat app | `cd /home/sbin/reachy/reachy_chat` then `uv run reachy-chat` | `http://localhost:8042` |
| Ollama (external) | (must be started separately) | `http://localhost:11434` |

**Chat app flags:** `--debug` (verbose logging), `--no-camera` (disable camera), `--head-tracker yolo|mediapipe` (enable head tracking), `--local-vision` (local vision model instead of gpt-realtime), `--robot-name <name>` (multi-robot Zenoh prefix, must match daemon's `--robot-name`).

**Hardware:** Connect USB, then `uv run reachy-mini-daemon` — udev rules already configured at `/etc/udev/rules.d/99-reachy-mini.rules`.

## Commands

```bash
# Setup & install
python3 scripts/env_helper.py --action setup
uv pip install "reachy-mini[mujoco]"
cd /home/sbin/reachy/reachy_chat && uv pip install -e .

# Linting (run from reachy_chat/)
flake8 .
uv run ruff check .
uv run mypy .

# Tests
cd /home/sbin/reachy/reachy_chat
uv run pytest tests/
uv run pytest tests/test_config_name_collisions.py   # single file

# Reports
uv run python3 /home/sbin/reachy/scripts/create_status_report.py
```

## Architecture

The chat app lives in `reachy_chat/src/reachy_chat/`. Request flow:

```
Browser (SSE)
  → FastAPI POST /chat  (main.py)
    → OllamaChatHandler.chat()  (ollama_chat.py)
      → Ollama qwen3:8b with tool specs
      → Tool loop (up to 5 rounds):
          dispatch_tool_call()  (tools/core_tools.py)
            → Tool.__call__(ToolDependencies)
              → MovementManager.queue_move()  (moves.py)
              → ReachyMini SDK calls
      → Stream tokens back via SSE
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `main.py` | FastAPI entrypoint, API routes (`/chat`, `/status`, `/history`, `/clear`, `/memory`, `/ws/voice`) |
| `ollama_chat.py` | `OllamaChatHandler` — OpenAI-compatible API client, streaming, tool-calling loop. No `think` mode (removed — caused silent empty responses with qwen3). |
| `config.py` | Profile/tool loading, `.env` parsing, collision detection |
| `prompts.py` | System prompt loading with `[<name>]` template expansion from `prompts/` library |
| `moves.py` | `MovementManager` — 100 Hz control loop, primary/secondary move queue |
| `dance_emotion_moves.py` | `DanceQueueMove`, `EmotionQueueMove`, `GotoQueueMove` wrappers |
| `tools/core_tools.py` | Tool base class, registry, dynamic loading, `dispatch_tool_call()` |
| `tools/tool_constants.py` | `ToolState` enum (RUNNING, COMPLETED, FAILED, CANCELLED), `SystemTool` enum |
| `tools/background_tool_manager.py` | `BackgroundToolManager` — async task execution |
| `utils.py` | CLI arg parsing (`parse_args()`), vision/camera init (`handle_vision_stuff()`), logger setup |
| `camera_worker.py` | Camera frame buffering |
| `audio/speech_tapper.py` | Audio-reactive head wobble offsets (secondary move source) |

### Movement System (`moves.py`)

Single worker thread owns robot control at ~100 Hz. Two move categories:
- **Primary moves** (mutually exclusive, sequential): emotions, dances, goto, breathing
- **Secondary moves** (additive offsets): speech sway, audio-reactive wobble, face tracking

Idle breathing starts automatically after inactivity. Listening mode freezes antennas.

### Tool System (`tools/`)

Tools are Python classes inheriting from `Tool` (in `tools/core_tools.py`). Dependencies are injected via `ToolDependencies`:

```python
@dataclass
class ToolDependencies:
    reachy_mini: ReachyMini
    movement_manager: MovementManager
    camera_worker: CameraWorker | None
    vision_manager: Any | None
    head_wobbler: Any | None
    motion_duration_s: float = 1.0
```

Built-in tools: `dance`, `stop_dance`, `play_emotion`, `stop_emotion`, `move_head`, `head_tracking`, `camera`, `do_nothing`, `task_status`, `task_cancel`.

`sweep_look` is profile-specific (defined in `profiles/_reachy_chat_locked_profile/sweep_look.py`), not a built-in.

Background tasks use `BackgroundToolManager` (`tools/background_tool_manager.py`) with `ToolState` from `tools/tool_constants.py`.

### Profile System (`profiles/`)

Active profile: `_reachy_chat_locked_profile` (set via `LOCKED_PROFILE` in `config.py`).

Each profile contains:
- `instructions.txt` — system prompt (supports `[<name>]` includes from `prompts/` library)
- `tools.txt` — one tool name per line, specifying which tools to load
- Optional `.py` files — profile-specific tool implementations

**Adding a custom tool:**
1. Edit or copy `profiles/_reachy_chat_locked_profile/custom_tool.py` (ready-to-use template already there)
2. Add the tool name to `tools.txt`
3. Restart the app

External profiles/tools: set `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY` or `REACHY_MINI_CUSTOM_PROFILE` env vars. The `.env` file lives in `reachy_chat/` (not the project root).

### Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.1:8b` | LLM model (must support tool-calling); local `.env` sets `qwen3:8b-q4km` |
| `HF_TOKEN` | — | HuggingFace access token |
| `REACHY_MINI_CUSTOM_PROFILE` | — | Override active profile |
| `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY` | — | External profile root |
| `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` | — | External standalone tools directory |
| `AUTOLOAD_EXTERNAL_TOOLS` | — | Auto-discover external tools |

### Memory System (`memory/`)

Lives at `/home/sbin/reachy/memory/` (outside `reachy_chat`). SQLite database (`memory/reachy.db`) with WAL. Modules: `database.py` (init/schema), `persons.py`, `conversations.py`, `facts.py`, `context.py`. Loaded optionally at startup in `main.py` — app starts normally if unavailable. The `conversation_id` is passed to `OllamaChatHandler` for per-session tracking.

`GET /memory` returns: `persons` (with attributes), `facts`, `conversation_count`, `message_count`, `recent_messages` (last 20). Has `Access-Control-Allow-Origin: *` header so it can be fetched from `file://` pages.

Inspect DB directly: `sqlitebrowser /home/sbin/reachy/memory/reachy.db`

### Voice System (`voice/`)

Lives at `/home/sbin/reachy/voice/` (outside `reachy_chat`). WebSocket endpoint `ws://localhost:8042/ws/voice` handled by `VoiceWebSocketPipeline`.

**Push-to-talk protocol** (browser ↔ server):
- `{"type": "start_recording"}` → mic opens, records at device native rate (44100 Hz), resamples to 16 kHz
- `{"type": "stop_recording"}` → recording stops, Whisper STT runs, sends `{"type": "transcript", "text": "..."}`
- `{"type": "speak", "text": "..."}` → Piper TTS synthesises and plays audio
- Server status messages: `{"type": "status", "value": "listening"|"processing"|"speaking"|null}`

Components: `vad.py` (`VAD.record_until_stop()`), `stt.py` (`STT` — faster-whisper small, German), `tts.py` (`TTS` — Piper `de_DE-thorsten-high`), `_think_filter.py`. German TTS model: `voice/models/de_DE-thorsten-high.onnx`. Standalone run: `/home/sbin/reachy/.venv/bin/python3 /home/sbin/reachy/voice/pipeline.py`.

**Known issue (2026-03-31):** `sd.InputStream` at 16 kHz returns silence via PipeWire. Fix in `vad.py`: record at native device rate (44 kHz) and resample — needs verification after app restart.

### Vision System (`vision/`)

Optional; install with extras: `uv pip install "reachy-chat[local_vision]"`, `[yolo_vision]`, `[mediapipe_vision]`, or `[all_vision]`. Used for head tracking (`head_tracking` tool).

### Reference HTML Tools (project root)

| File | Purpose |
|------|---------|
| `quickstart.html` | Start commands, URLs, microphone guide — dark theme, copy buttons |
| `memory_status.html` | Live DB status (persons, conversations, messages, facts) — fetches from `GET /memory` |

Both work from `file://` and from `http://localhost:8042/static/<file>`.

## Guidelines

- Commands for Bash (Linux) only — no chained `&&` commands, write each command separately.
- Always specify config file paths as absolute paths.
- For direct command requests, use native binaries — do not generate wrapper scripts.
- Code and technical docs in English; explanations to the user in German.
- Keep design modular — avoid complex class hierarchies.
