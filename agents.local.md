# Reachy Mini Session Context

## Robot Type
- Reachy Mini Lite (USB variant, PC-connected)
- Currently: Simulation via MuJoCo

## Environment
- OS: Ubuntu Desktop
- Working directory: /home/sbin/reachy
- Python venv: /home/sbin/reachy/.venv (managed by uv)
- SDK: reachy-mini v1.5.1
- Daemon: uv run reachy-mini-daemon --sim (localhost:8000)

## App: reachy_chat
- Location: /home/sbin/reachy/reachy_chat
- LLM backend: Ollama (localhost:11434), model qwen3:8b-q4km
- Web UI: http://localhost:8042
- Start: cd /home/sbin/reachy/reachy_chat && uv run reachy-chat
- Start dir: reachy_chat/ (required — .env lives there, find_dotenv searches upward)
- Profile: _reachy_chat_locked_profile

## Preferences
- Code in English, explanations in German
- No chained commands
- Absolute paths for config files

## Reference Tools
- Quickstart: /home/sbin/reachy/quickstart.html (start commands, URLs, mic guide)
- Memory status: /home/sbin/reachy/memory_status.html (live DB view via GET /memory)
- DB browser: sqlitebrowser /home/sbin/reachy/memory/reachy.db

## Roadmap
- Phase 2: Person tracking + recognition (when hardware arrives ~April 2026)
