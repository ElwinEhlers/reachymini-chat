"""Text-to-speech using Piper (de_DE-thorsten-high voice)."""

import logging
from typing import Callable, Optional
import numpy as np
import sounddevice as sd
from pathlib import Path
from piper import PiperVoice

logger = logging.getLogger(__name__)

VOICE_NAME = "de_DE-thorsten-high"
MODELS_DIR = Path(__file__).parent / "models"

# HuggingFace repo and file paths for the Thorsten voice
_HF_REPO = "rhasspy/piper-voices"
_HF_MODEL_PATH = "de/de_DE/thorsten/high/de_DE-thorsten-high.onnx"
_HF_CONFIG_PATH = "de/de_DE/thorsten/high/de_DE-thorsten-high.onnx.json"


class TTS:
    """Wraps Piper TTS for German speech synthesis."""

    def __init__(self) -> None:
        self._voice = self._load_voice()

    def _load_voice(self) -> PiperVoice:
        onnx_path = MODELS_DIR / f"{VOICE_NAME}.onnx"
        json_path = MODELS_DIR / f"{VOICE_NAME}.onnx.json"

        if not onnx_path.exists() or not json_path.exists():
            logger.info("Downloading Piper voice '%s' from HuggingFace …", VOICE_NAME)
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            from huggingface_hub import hf_hub_download
            hf_hub_download(repo_id=_HF_REPO, filename=_HF_MODEL_PATH, local_dir=MODELS_DIR, local_dir_use_symlinks=False)
            hf_hub_download(repo_id=_HF_REPO, filename=_HF_CONFIG_PATH, local_dir=MODELS_DIR, local_dir_use_symlinks=False)
            # hf_hub_download keeps sub-directory structure; flatten to MODELS_DIR
            _maybe_move(MODELS_DIR, _HF_MODEL_PATH, onnx_path)
            _maybe_move(MODELS_DIR, _HF_CONFIG_PATH, json_path)
            logger.info("Voice downloaded.")

        logger.info("Loading Piper voice from %s …", onnx_path)
        voice = PiperVoice.load(str(onnx_path), config_path=str(json_path))
        logger.info("Piper TTS ready.")
        return voice

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Return (audio_float32_array, sample_rate) for the given text."""
        chunks = list(self._voice.synthesize(text))
        if not chunks:
            return np.zeros(0, dtype=np.float32), 22050
        sample_rate = chunks[0].sample_rate
        audio = np.concatenate([c.audio_float_array for c in chunks])
        return audio.astype(np.float32), sample_rate

    def speak(
        self,
        text: str,
        output_device: int | None = None,
        on_start: Optional[Callable[[], None]] = None,
        on_end: Optional[Callable[[], None]] = None,
    ) -> None:
        """Synthesize text and play it (blocking) through an audio output.

        output_device: optionaler Index (z.B. Reachy-Lautsprecher); None = Default.
        on_start/on_end: Callbacks für Echo-Unterdrückung (vor/nach Wiedergabe).
        Bei gesetztem output_device wird das 22050-Hz-Piper-Audio auf die native
        Geräte-Rate resampled.
        """
        if not text.strip():
            return
        audio, sample_rate = self.synthesize(text)

        if output_device is not None:
            from voice.audio_device import resample
            device_sr = int(sd.query_devices(output_device)["default_samplerate"])
            if device_sr != sample_rate:
                audio = resample(audio, sample_rate, device_sr)
                sample_rate = device_sr

        logger.debug("Spreche %d Samples @%d Hz (Gerät=%s)", len(audio), sample_rate, output_device)
        if on_start:
            on_start()
        try:
            sd.play(audio, samplerate=sample_rate, device=output_device)
            sd.wait()
        finally:
            if on_end:
                on_end()


def _maybe_move(base: Path, hf_relative: str, target: Path) -> None:
    """Move a file from its hf_hub_download sub-path to target if needed."""
    if target.exists():
        return
    src = base / hf_relative
    if src.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        src.rename(target)
