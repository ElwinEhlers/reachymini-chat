"""Diagnose-Skript für die Wake-Word-Erkennung am Reachy-Mikrofon.

Lädt alle vortrainierten openWakeWord-Modelle parallel, nimmt vom Reachy-Mikro
auf und zeigt live die höchsten Scores. So lässt sich feststellen, welches
Wake-Word bei der eigenen Stimme/Aussprache zuverlässig anschlägt und ob der
Mikropegel ausreicht.

Start (aus dem Projekt-Root):
    /home/sbin/reachy/.venv/bin/python3 voice/_wakeword_debug.py

Dann nacheinander laut und deutlich sagen:
    "Alexa"  …  "Hey Jarvis"  …  "Hey Mycroft"  …  "Hey Marvin"
Das Skript läuft 30 Sekunden und gibt am Ende den jeweils höchsten Score je Modell aus.
"""

import os
import sys
import time

import numpy as np
import sounddevice as sd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice.audio_device import find_reachy_audio_device, resample_to_16k

SAMPLE_RATE = 16000
FRAME = 1280
DURATION_S = 30
GAIN = 4.0   # Pegelanhebung für das leise Reachy-Mikro


def main() -> None:
    import openwakeword
    from openwakeword.model import Model

    dev = find_reachy_audio_device()
    res_dir = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
    model_paths = [
        os.path.join(res_dir, f)
        for f in ("alexa_v0.1.onnx", "hey_jarvis_v0.1.onnx",
                  "hey_mycroft_v0.1.onnx", "hey_marvin_v0.1.onnx")
    ]
    model = Model(wakeword_model_paths=model_paths)
    peaks: dict[str, float] = {}

    native_sr = int(sd.query_devices(dev.input_index)["default_samplerate"])
    native_block = max(1, int(round(FRAME * native_sr / SAMPLE_RATE)))
    pending = np.zeros(0, dtype=np.float32)

    print(f"\nMikro={dev.input_index} @ {native_sr} Hz, Gain={GAIN}x")
    print("Sprich jetzt: 'Alexa', 'Hey Jarvis', 'Hey Mycroft', 'Hey Marvin' …\n")

    t_end = time.time() + DURATION_S
    with sd.InputStream(samplerate=native_sr, channels=1, dtype="float32",
                        device=dev.input_index, blocksize=native_block) as stream:
        while time.time() < t_end:
            chunk, _ = stream.read(native_block)
            mono = chunk[:, 0] if chunk.ndim > 1 else chunk.flatten()
            mono = np.clip(mono * GAIN, -1.0, 1.0)
            res = mono if native_sr == SAMPLE_RATE else resample_to_16k(mono, native_sr)
            pending = np.concatenate([pending, res])

            while len(pending) >= FRAME:
                frame = pending[:FRAME]
                pending = pending[FRAME:]
                rms = float(np.sqrt(np.mean(frame ** 2)))
                i16 = (frame * 32767).astype(np.int16)
                scores = model.predict(i16)
                best = max(scores, key=scores.get)
                best_val = scores[best]
                for k, v in scores.items():
                    if v > peaks.get(k, 0.0):
                        peaks[k] = v
                if best_val >= 0.1:
                    print(f"  RMS={rms:.3f}  →  {best} = {best_val:.2f}")

    print("\n=== Höchste Scores je Modell (über die gesamte Aufnahme) ===")
    for k, v in sorted(peaks.items(), key=lambda kv: -kv[1]):
        marker = "  ✅ würde auslösen (>=0.5)" if v >= 0.5 else ""
        print(f"  {k:22s}  Peak {v:.2f}{marker}")
    print()


if __name__ == "__main__":
    main()
