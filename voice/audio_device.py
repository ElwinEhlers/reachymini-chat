"""Discovery of the Reachy Mini USB audio device and audio resampling helpers.

The Reachy Mini exposes a single USB audio interface (USB ID 38fb:1001) that
provides both the microphone (input) and the speaker (output). The device index
reported by sounddevice is NOT stable across reboots/replugs, so it must be
resolved at runtime by name instead of being hardcoded.
"""

import re
import logging
import subprocess
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

# Substring of the sounddevice device name (USB ID 38fb:1001, "Reachy Mini Audio").
REACHY_DEVICE_NAME = "Reachy Mini Audio"

# Das Reachy-Mikrofon liefert einen sehr niedrigen Pegel; ohne Anhebung kommen
# Wake-Word und VAD nicht zuverlässig über ihre Schwellen. Empirisch ermittelt.
MIC_GAIN = 4.0


def apply_gain(audio: np.ndarray, gain: float = MIC_GAIN) -> np.ndarray:
    """Pegel anheben und auf [-1, 1] begrenzen (Clipping vermeiden)."""
    if gain == 1.0:
        return audio
    return np.clip(audio * gain, -1.0, 1.0).astype(np.float32)


@dataclass
class ReachyAudioDevice:
    """Resolved indices and native sample rates of the Reachy audio device."""

    input_index: int
    output_index: int
    input_samplerate: int
    output_samplerate: int
    name: str
    card_index: int | None = None   # ALSA-Karte (aus "hw:N,M" im Namen), für amixer


def find_reachy_audio_device(name_hint: str = REACHY_DEVICE_NAME) -> ReachyAudioDevice:
    """Locate the Reachy Mini audio device by name.

    Sucht das erste sounddevice-Gerät, dessen Name den Hinweis enthält und über
    Ein- bzw. Ausgabekanäle verfügt. Wirft RuntimeError mit der Liste aller
    gefundenen Geräte, falls das Reachy-Audio nicht erkannt wird.
    """
    devices = sd.query_devices()
    hint = name_hint.lower()

    input_index: int | None = None
    output_index: int | None = None
    input_sr = 16000
    output_sr = 22050
    matched_name = name_hint

    for idx, dev in enumerate(devices):
        if hint not in dev["name"].lower():
            continue
        matched_name = dev["name"]
        if input_index is None and dev["max_input_channels"] > 0:
            input_index = idx
            input_sr = int(dev["default_samplerate"])
        if output_index is None and dev["max_output_channels"] > 0:
            output_index = idx
            output_sr = int(dev["default_samplerate"])

    if input_index is None or output_index is None:
        available = "\n".join(
            f"  [{i}] {d['name']} "
            f"({d['max_input_channels']} in, {d['max_output_channels']} out)"
            for i, d in enumerate(devices)
        )
        raise RuntimeError(
            f"Reachy-Audio-Gerät '{name_hint}' nicht gefunden "
            f"(Mikro={input_index}, Lautsprecher={output_index}). "
            f"Ist der Roboter per USB angeschlossen? "
            f"Verfügbare Geräte:\n{available}"
        )

    card_match = re.search(r"hw:(\d+)", matched_name)
    card_index = int(card_match.group(1)) if card_match else None

    logger.info(
        "Reachy-Audio gefunden: '%s' (Mikro=%d @%d Hz, Lautsprecher=%d @%d Hz, Karte=%s)",
        matched_name, input_index, input_sr, output_index, output_sr, card_index,
    )
    return ReachyAudioDevice(
        input_index=input_index,
        output_index=output_index,
        input_samplerate=input_sr,
        output_samplerate=output_sr,
        name=matched_name,
        card_index=card_index,
    )


def maximize_reachy_volume(card_index: int | None) -> None:
    """Lautsprecher- und Mikrofon-Pegel der Reachy-ALSA-Karte auf Maximum (0 dB).

    amixer-Einstellungen sind nicht persistent (Reset bei Neustart/Abstecken),
    daher beim App-Start aufrufen. Fehler werden nur geloggt, nicht geworfen.
    """
    if card_index is None:
        logger.warning("Keine ALSA-Karte ermittelt — Pegel nicht angepasst.")
        return
    # 'PCM' = Wiedergabe (Lautsprecher), 'Headset' = Aufnahme (Mikrofon).
    for control in ("PCM", "Headset"):
        try:
            subprocess.run(
                ["amixer", "-c", str(card_index), "sset", control, "100%"],
                check=False, capture_output=True, text=True, timeout=5,
            )
        except Exception as exc:
            logger.warning("amixer %s konnte nicht gesetzt werden: %s", control, exc)
    logger.info("Reachy-Audio-Pegel (Karte %d) auf Maximum gesetzt.", card_index)


def resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Resample a mono float32 signal via linear interpolation."""
    if src_sr == dst_sr or len(audio) == 0:
        return audio.astype(np.float32)
    target_len = int(round(len(audio) * dst_sr / src_sr))
    if target_len <= 0:
        return np.zeros(0, dtype=np.float32)
    resampled = np.interp(
        np.linspace(0, len(audio) - 1, target_len),
        np.arange(len(audio)),
        audio,
    )
    return resampled.astype(np.float32)


def resample_to_16k(audio: np.ndarray, src_sr: int) -> np.ndarray:
    """Resample a mono float32 signal to 16 kHz (Whisper/Silero/openWakeWord)."""
    return resample(audio, src_sr, 16000)
