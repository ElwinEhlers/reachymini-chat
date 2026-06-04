# Reachy Mini Chat

Browser-basiertes Conversational Interface für den **Reachy Mini Lite** Roboter.
Läuft vollständig lokal mit Ollama (`qwen3:8b-q4km`) — kein Cloud-API erforderlich.

Der Roboter versteht natürliche Sprache und kann tanzen, Emotionen zeigen, seinen Kopf bewegen und auf Spracheingaben reagieren.

## Inhalt dieses Repositories

| Verzeichnis | Beschreibung |
|---|---|
| [`reachy_chat/`](reachy_chat/README.md) | Chat-App — FastAPI, Ollama, Browser-UI, Tool-System, Profile |
| `memory/` | SQLite-Gedächtnissystem — Personen, Fakten, Gesprächsverläufe |
| `voice/` | Sprachsystem — Whisper STT, Piper TTS, VAD (Push-to-Talk) |
| `scripts/` | Hilfsskripte (Setup, Status-Report) |

> [!NOTE]
> **Vollständige Installationsanleitung** (Installation, Konfiguration, Voice-Setup, eigene Tools):
> [`reachy_chat/README.md`](reachy_chat/README.md)

## Voraussetzungen

- Ubuntu Desktop, Python 3.10+, [`uv`](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/) mit `qwen3:8b-q4km`
- Reachy Mini SDK + Daemon

## Schnellstart

```bash
# 1. Abhängigkeiten installieren
python3 scripts/env_helper.py --action setup
uv pip install "reachy-mini[mujoco]"
cd reachy_chat && uv pip install -e .
cp .env.example .env

# 2. Dienste starten (je ein Terminal)
uv run reachy-mini-daemon --sim        # Daemon  → http://localhost:8000
cd reachy_chat && uv run reachy-chat   # Chat-App → http://localhost:8042
```

## Features

- **Chat** — SSE-Streaming, Tool-Calling-Loop (bis zu 5 Runden), Mehrsprachigkeit
- **Bewegung** — Tänze, Emotionen, Kopfbewegungen, 100 Hz Control Loop
- **Sprachsteuerung** — Push-to-Talk, Whisper STT, Piper TTS (Deutsch)
- **Gedächtnis** — SQLite-Datenbank für Personen, Fakten und Gespräche
- **Profile & Tools** — vollständig anpassbar ohne Core-Code-Änderungen
- **Hardware/Simulation** — SDK erkennt automatisch, kein Code-Wechsel nötig

## Hardware-Umstieg

USB anschließen, Daemon ohne `--sim` starten — die App läuft ohne Änderung.

## Lizenz

[MIT](reachy_chat/LICENSE) © 2026 Elwin Ehlers

---

*Basiert auf dem [Reachy Mini Conversation App](https://github.com/pollen-robotics/reachy_mini/) Template von Pollen Robotics.*
