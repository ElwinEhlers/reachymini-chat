# Reachy Mini – Steuerungsprojekt

## Übersicht
Dieses Repository enthält Setup, Konfiguration und Anwendungscode für den **Reachy Mini Lite** Roboter
(USB-Variante, PC-gebunden) auf Ubuntu Desktop.

Aktueller Stand: **Simulation via MuJoCo** — Hardware wird in ~4 Wochen geliefert.
Umstieg auf echten Roboter erfordert keine Code-Anpassung (SDK auto-detect).

## Voraussetzungen
- Ubuntu Desktop
- `uv` (Python Package Manager)
- Python 3.10+
- Ollama (lokales LLM)
- Arbeitsverzeichnis: `/home/sbin/reachy`

## Erstinstallation

### Phase 1 — Manuell (sudo erforderlich, kein Python vorhanden)

Diese Schritte müssen manuell im Terminal ausgeführt werden. Das Projekt-Script
`scripts/env_helper.py` setzt Python voraus und kann erst danach genutzt werden.

**1. Systemabhängigkeiten installieren:**
```bash
sudo apt update
```
```bash
sudo apt install python3 python3-pip curl git
```

**2. uv installieren:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Danach **neues Terminal öffnen** — erst dann ist `uv` im PATH verfügbar.

**3. uv prüfen:**
```bash
uv --version
```

---

### Phase 2 — Automatisiert via env_helper.py (Python jetzt verfügbar)

Ab hier übernimmt das Projekt-Script. Es erstellt die venv und installiert das SDK:

```bash
cd /home/sbin/reachy
```
```bash
python3 scripts/env_helper.py --action setup
```

**4. udev-Regeln für USB (jetzt einrichten, wird für Hardware gebraucht):**

Datei: `/etc/udev/rules.d/99-reachy-mini.rules`
```bash
sudo tee /etc/udev/rules.d/99-reachy-mini.rules > /dev/null << 'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="55d3", MODE="0666", GROUP="dialout"
SUBSYSTEM=="usb", ATTRS{idVendor}=="38fb", ATTRS{idProduct}=="1001", MODE="0666", GROUP="dialout"
EOF
```
```bash
sudo udevadm control --reload-rules
```
```bash
sudo udevadm trigger
```
```bash
sudo usermod -aG dialout $USER
```

---

### Phase 3 — Ollama installieren (lokales LLM)

**5. Ollama installieren:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**6. Modell laden:**
```bash
ollama pull llama3.1:8b
```

**7. Prüfen:**
```bash
curl http://localhost:11434/v1/models
```

---

### Phase 4 — Chat-App installieren

**8. Chat-App als editierbares Paket installieren:**
```bash
cd /home/sbin/reachy/reachy_chat
```
```bash
uv pip install -e .
```

## Simulation starten

```bash
uv run reachy-mini-daemon --sim
```

Dashboard aufrufen: `http://localhost:8000`

Simulation mit Szene (Tisch + Objekte):
```bash
uv run reachy-mini-daemon --sim --scene minimal
```

## Chat-App starten

Voraussetzung: Daemon und Ollama laufen.

**Wichtig:** Aus `reachy_chat/` starten, damit die `.env` gefunden wird.

```bash
cd /home/sbin/reachy/reachy_chat
```
```bash
uv run reachy-chat
```

Web-UI aufrufen: `http://localhost:8042`

### Features
- Browser-basiertes Chat-Interface (Dark Theme)
- Lokales LLM (Ollama llama3.1:8b) mit Tool-Calling
- Roboter kann tanzen, Emotionen zeigen, Kopf bewegen, sich umschauen
- SSE-Streaming für flüssige Antwort-Ausgabe
- Kein Cloud-API nötig — alles läuft lokal

### Konfiguration
Umgebungsvariablen oder `.env`-Datei in `/home/sbin/reachy/reachy_chat/`:

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama API-Endpunkt |
| `OLLAMA_MODEL` | `llama3.1:8b` | LLM-Modell |

### API-Endpunkte (Port 8042)

| Endpunkt | Methode | Beschreibung |
|----------|---------|-------------|
| `/chat` | POST | Chat-Nachricht senden (SSE-Stream) |
| `/status` | GET | Verbindungsstatus + Modellname |
| `/history` | GET | Chat-Verlauf abrufen |
| `/clear` | POST | Verlauf löschen |

### Verfügbare Tools
| Tool | Beschreibung |
|------|-------------|
| `dance` | Tanz abspielen (zufällig oder benannt) |
| `stop_dance` | Tanz stoppen |
| `play_emotion` | Emotion abspielen (happy, sad, welcoming etc.) |
| `stop_emotion` | Emotion stoppen |
| `move_head` | Kopf bewegen (left, right, up, down, front) |
| `sweep_look` | Kopf von links nach rechts schwenken |

## SDK nutzen (Beispiel)

```python
from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose

with ReachyMini() as mini:
    mini.goto_target(antennas=[0.5, -0.5], duration=0.5)
    mini.goto_target(antennas=[-0.5, 0.5], duration=0.5)
    mini.goto_target(antennas=[0, 0], duration=0.5)
```

## Umstieg auf Hardware (wenn Roboter da)
1. USB-Kabel anschließen
2. Daemon normal starten (kein `--sim` Flag)
3. `ReachyMini()` verbindet automatisch via localhost/USB
4. Chat-App funktioniert ohne Änderung

## Projektstruktur

```
/home/sbin/reachy/
  .venv/                          Python venv (uv)
  scripts/
    env_helper.py                 Setup-Automatisierung
    create_status_report.py       Excel-Report generieren
  reachy_chat/                    Chat-App
    src/reachy_chat/
      main.py                     Einstiegspunkt + FastAPI-Routen
      ollama_chat.py              LLM-Backend (Ollama)
      config.py                   Konfiguration
      moves.py                    MovementManager (100Hz)
      static/                     Browser Chat-UI
      tools/                      Tool-System
      profiles/                   Profil (System-Prompt + Tools)
    pyproject.toml                Dependencies
  agents.local.md                 Session-Kontext für AI Agents
  CLAUDE.md                       Projektbefehle für Claude Code
  README.md                       Diese Datei
```

## Konventionen
- Code und technische Dokumentation in Englisch. Erklärungen in Deutsch.
- Modularer Aufbau, kein überkomplexes Klassendesign.
- Bei direkten Befehlsanfragen keine Skripte, sondern native Binärbefehle.
- Konfigurationsdateien immer mit absolutem Pfad angeben.

## Weiterführende Dokumentation
- SDK Übersicht: `https://huggingface.co/docs/reachy_mini/SDK/readme`
- AI Agent Einstieg: `https://github.com/pollen-robotics/reachy_mini/blob/develop/AGENTS.md`
- Troubleshooting: `https://huggingface.co/docs/reachy_mini/troubleshooting`
- Projektstatus (Excel): `/home/sbin/reachy/reachy_chat_status_2026-03-26.xlsx`
