import platform
import sys
import argparse
import subprocess
import shutil


def get_platform():
    return platform.system().lower()


def check_command(cmd):
    return shutil.which(cmd) is not None


def run_setup():
    system = get_platform()
    if system == "linux":
        print("Starte Setup für Linux System (Reachy Mini)...")

        if not check_command("uv"):
            print("FEHLER: 'uv' nicht gefunden.")
            print("Installieren mit: curl -LsSf https://astral.sh/uv/install.sh | sh")
            print("Danach neues Terminal öffnen und erneut ausführen.")
            sys.exit(1)

        if not check_command("git"):
            print("FEHLER: 'git' nicht gefunden.")
            print("Installieren mit: sudo apt install git")
            sys.exit(1)

        print("Erstelle virtuelle Umgebung unter /home/sbin/reachy/.venv ...")
        result = subprocess.run(["uv", "venv", ".venv"])
        if result.returncode != 0:
            print("FEHLER: venv konnte nicht erstellt werden.")
            sys.exit(1)

        print("Installiere reachy-mini SDK mit MuJoCo-Unterstützung...")
        result = subprocess.run(["uv", "pip", "install", "reachy-mini[mujoco]"])
        if result.returncode != 0:
            print("FEHLER: SDK-Installation fehlgeschlagen.")
            sys.exit(1)

        print("")
        print("Setup abgeschlossen.")
        print("Simulation starten mit: uv run reachy-mini-daemon --sim")
        print("Dashboard:              http://localhost:8000")
    else:
        print(f"Nicht unterstütztes System: {system}")
        print("Dieses Projekt läuft auf Ubuntu Linux.")
        sys.exit(1)


def run_build():
    system = get_platform()
    if system == "linux":
        print("Build für Linux (Reachy Mini) – aktuell kein separater Build-Schritt nötig.")
        print("SDK wird direkt via uv pip install bezogen.")
    else:
        print(f"Nicht unterstütztes System: {system}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reachy Mini Projekt-Helper")
    parser.add_argument("--action", choices=["setup", "build"], required=True)
    args = parser.parse_args()

    if args.action == "setup":
        run_setup()
    elif args.action == "build":
        run_build()
