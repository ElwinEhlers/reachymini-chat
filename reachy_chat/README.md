# Reachy Mini Chat

Browser-basiertes Conversational Interface für den **Reachy Mini Lite** Roboter. Der Roboter wird über ein lokales LLM (Ollama) gesteuert und kann tanzen, Emotionen zeigen, seinen Kopf bewegen und auf Spracheingaben reagieren.

## Inhaltsverzeichnis

- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Starten](#starten)
- [Verzeichnisstruktur](#verzeichnisstruktur)
- [Architektur](#architektur)
- [Eigene Tools & Profile](#eigene-tools--profile)
- [Sprachsteuerung (Voice)](#sprachsteuerung-voice)
- [Summary (English)](#summary-english)

---

## Voraussetzungen

| Voraussetzung | Installieren |
|---|---|
| Ubuntu Desktop | Bash, Python 3.10+ |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Ollama](https://ollama.com/) | `curl -fsSL https://ollama.com/install.sh \| sh` |
| Reachy Mini SDK | `uv pip install "reachy-mini[mujoco]"` (nach Repo-Clone) |

**Ollama-Modell installieren** (muss Tool-Calling unterstützen):

```bash
ollama pull qwen3:8b-q4km
```

---

## Installation

```bash
# 1. Repo klonen
git clone https://github.com/ElwinEhlers/reachymini-chat.git
cd reachymini-chat

# 2. Reachy Mini SDK mit MuJoCo-Simulation installieren
uv pip install "reachy-mini[mujoco]"

# 3. Chat-App installieren
cd reachy_chat
uv pip install -e .

# 4. Konfiguration anlegen
cp .env.example .env
# .env nach Bedarf anpassen (siehe Abschnitt Konfiguration)
```

### Optionale Vision-Extras

```bash
uv pip install -e ".[yolo_vision]"       # YOLO-basiertes Head-Tracking
uv pip install -e ".[mediapipe_vision]"  # MediaPipe-basiertes Head-Tracking
uv pip install -e ".[local_vision]"      # Lokales Vision-Modell (Transformer)
uv pip install -e ".[all_vision]"        # Alle Vision-Funktionen
```

---

## Konfiguration

Die Konfiguration erfolgt über eine `.env`-Datei im `reachy_chat/`-Verzeichnis (die App muss von dort gestartet werden, `find_dotenv` sucht aufwärts).

| Variable | Standard | Beschreibung |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama-Endpunkt |
| `OLLAMA_MODEL` | `llama3.1:8b` | LLM-Modell (muss Tool-Calling unterstützen); empfohlen: `qwen3:8b-q4km` |
| `HF_TOKEN` | — | HuggingFace-Token (für Emotion-Bibliothek) |
| `HF_HOME` | `./cache` | Lokaler Cache-Pfad für HF-Modelle |
| `REACHY_MINI_CUSTOM_PROFILE` | — | Alternatives Profil aktivieren |
| `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY` | — | Pfad zu externen Profilen |
| `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` | — | Pfad zu externen Tools |
| `AUTOLOAD_EXTERNAL_TOOLS` | `false` | Alle Tools aus externem Verzeichnis laden |

---

## Starten

Die App benötigt drei laufende Dienste.

> **Voraussetzung:** Alle Befehle gehen davon aus, dass du dich im geklonten Projektverzeichnis befindest (z. B. `~/reachymini-chat`). Terminal 1 und 2 starten vom Projektroot, Terminal 3 wechselt in den Unterordner `reachy_chat/`.

**Terminal 1 — Reachy Mini Daemon (Simulation):**
```bash
# Im Projektroot (z. B. ~/reachymini-chat)
uv run reachy-mini-daemon --sim
# Dashboard: http://localhost:8000
```

Für Hardware statt Simulation einfach `--sim` weglassen (USB angesteckt, udev-Regeln eingerichtet).

**Terminal 2 — Ollama:**

Ollama läuft normalerweise als Systemdienst. Prüfen:
```bash
curl http://localhost:11434/v1/models
```

**Terminal 3 — Chat-App:**
```bash
# Im Projektroot (z. B. ~/reachymini-chat)
cd reachy_chat
uv run reachy-chat
# Web-UI: http://localhost:8042
```

> **Hinweis:** Die Chat-App muss aus dem `reachy_chat/`-Verzeichnis gestartet werden — dort liegt die `.env`-Datei, die beim Start automatisch gefunden wird.

### Startoptionen

| Flag | Beschreibung |
|---|---|
| `--debug` | Ausführliches Logging |
| `--no-camera` | Kamera deaktivieren |
| `--head-tracker yolo\|mediapipe` | Head-Tracking aktivieren |
| `--local-vision` | Lokales Vision-Modell |
| `--robot-name <name>` | Zenoh-Präfix für Multi-Roboter-Setup |

---

## Verzeichnisstruktur

```
reachymini-chat/
├── reachy_chat/                        # Chat-Applikation
│   ├── src/reachy_chat/
│   │   ├── main.py                     # FastAPI-Einstiegspunkt, API-Routen
│   │   ├── ollama_chat.py              # LLM-Handler (Streaming, Tool-Loop)
│   │   ├── config.py                   # Konfiguration & .env-Parsing
│   │   ├── moves.py                    # Bewegungssteuerung (100 Hz Control Loop)
│   │   ├── tools/                      # Eingebaute Tools (dance, emotion, move_head …)
│   │   ├── profiles/                   # Aktives Profil (Instructions + Tool-Liste)
│   │   │   └── _reachy_chat_locked_profile/
│   │   │       ├── instructions.txt    # System-Prompt für den Roboter
│   │   │       ├── tools.txt           # Aktivierte Tools (eine Zeile pro Tool)
│   │   │       ├── sweep_look.py       # Profil-spezifisches Tool
│   │   │       └── custom_tool.py      # Template für eigene Tools
│   │   ├── prompts/                    # Prompt-Bibliothek ([<name>]-Includes)
│   │   └── static/                     # Browser-UI (HTML, JS, CSS)
│   └── tests/
├── memory/                             # SQLite-Gedächtnissystem
│   ├── database.py                     # Schema & Verbindung (WAL-Modus)
│   ├── persons.py                      # Personenerkennung & Attribute
│   ├── conversations.py                # Gesprächsprotokoll
│   ├── facts.py                        # Gespeichertes Wissen
│   └── reachy.db                       # SQLite-Datenbank (wird automatisch angelegt)
└── voice/                              # Sprachsystem
    ├── pipeline.py                     # WebSocket-Pipeline (STT → LLM → TTS)
    ├── stt.py                          # Spracherkennung (faster-whisper, Deutsch)
    ├── tts.py                          # Sprachausgabe (Piper, de_DE-thorsten-high)
    └── vad.py                          # Voice Activity Detection
```

---

## Architektur

```
Browser (SSE)
  → POST /chat  (main.py)
    → OllamaChatHandler.chat()  (ollama_chat.py)
      → Ollama (qwen3) mit Tool-Definitionen
      → Tool-Loop (bis zu 5 Runden):
          dispatch_tool_call()  (tools/core_tools.py)
            → Tool.__call__(ToolDependencies)
              → MovementManager.queue_move()  (moves.py)
              → ReachyMini SDK
      → Token-Stream via SSE zurück an Browser
```

**Bewegungssystem:** Ein Worker-Thread steuert den Roboter mit ~100 Hz. Primärbewegungen (Tänze, Emotionen, Goto) laufen sequenziell. Sekundärbewegungen (Kopftracking, Audio-Wobble) werden additiv überlagert.

**Sprachsystem:** WebSocket-Endpoint `/ws/voice`. Aufnahme per Push-to-Talk im Browser, Whisper-Transkription auf dem Server, Piper-TTS für die Antwort.

**Gedächtnissystem:** SQLite-Datenbank mit WAL. Speichert Personen, Attribute, Gesprächsverläufe und Fakten. Wird optional beim Start geladen — die App startet auch ohne.

---

## Eigene Tools & Profile

Das aktive Profil liegt in `src/reachy_chat/profiles/_reachy_chat_locked_profile/`.

**Neues Tool hinzufügen:**

1. `custom_tool.py` im Profil-Ordner bearbeiten (fertiges Template vorhanden) oder neue `.py`-Datei mit einer Klasse anlegen, die `Tool` aus `reachy_chat.tools.core_tools` ableitet.
2. Tool-Namen in `tools.txt` eintragen (eine Zeile pro Tool).
3. App neu starten.

**Externe Tools & Profile** können über Umgebungsvariablen eingebunden werden:

```bash
REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY=/pfad/zu/profilen
REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY=/pfad/zu/tools
```

**Prompt-Bibliothek:** Neue `.txt`-Dateien in `prompts/` ablegen und per `[<name>]` in `instructions.txt` einbinden.

---

## Sprachsteuerung (Voice)

Die App unterstützt Push-to-Talk über den Browser. Das Sprachsystem läuft serverseitig im `voice/`-Verzeichnis.

### Abhängigkeiten installieren

```bash
uv pip install faster-whisper piper-tts sounddevice silero-vad huggingface-hub
```

### Funktionsweise

| Komponente | Technologie | Hinweis |
|---|---|---|
| Spracherkennung (STT) | faster-whisper (small) | Läuft lokal auf CPU, Deutsch |
| Sprachausgabe (TTS) | Piper (`de_DE-thorsten-high`) | ONNX-Modell, wird beim ersten Start automatisch heruntergeladen |
| Stille-Erkennung (VAD) | Silero VAD | Erkennt Ende der Aufnahme |
| Aufnahme | sounddevice | Nativer Geräterate (44 kHz), Resampling auf 16 kHz |

### Nutzung im Browser

1. Chat-App starten (wie im Abschnitt [Starten](#starten))
2. Mikrofon-Button 🎤 in der Web-UI klicken und halten → Aufnahme läuft
3. Button loslassen → Whisper transkribiert, LLM antwortet, Piper spricht die Antwort

### Standalone-Test (ohne Browser)

```bash
# Im Projektroot (reachymini-chat/)
uv run python3 voice/pipeline.py
```

> **Bekanntes Problem (PipeWire):** `sd.InputStream` bei 16 kHz kann via PipeWire Stille liefern. Fix in `vad.py`: Aufnahme bei nativer Geräterate (44 kHz) mit anschließendem Resampling auf 16 kHz.

---

## Summary (English)

**Reachy Mini Chat** is a browser-based conversational interface for the [Reachy Mini Lite](https://github.com/pollen-robotics/reachy_mini/) robot, powered by a local LLM via [Ollama](https://ollama.com/). The robot responds to natural language and can dance, display emotions, move its head, and interact through voice using Whisper STT and Piper TTS. A SQLite-based memory system optionally tracks persons and conversation history across sessions.

The app runs on Ubuntu and is fully customizable through a profile and tool system — no core code changes needed to add new robot behaviors.

**Recommended model:** `qwen3:8b-q4km` — proven to work well for this use case. Small enough to run locally on consumer hardware, reliable tool-calling, and good multilingual support.

### Quick Install

```bash
# Prerequisites: uv, Ollama, Reachy Mini SDK
ollama pull qwen3:8b-q4km
git clone https://github.com/ElwinEhlers/reachymini-chat.git
cd reachymini-chat
uv pip install "reachy-mini[mujoco]"
cd reachy_chat
uv pip install -e .
cp .env.example .env
```

```bash
# Run (3 terminals)
uv run reachy-mini-daemon --sim          # Terminal 1 — robot daemon
cd reachy_chat && uv run reachy-chat     # Terminal 2 — chat app → http://localhost:8042
```

**License:** MIT
