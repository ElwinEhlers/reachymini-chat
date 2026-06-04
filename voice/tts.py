"""Text-to-speech using Piper (de_DE-thorsten-high voice)."""

import logging
import numpy as np
import sounddevice as sd
from pathlib import Path
from piper import PiperVoice

logger = logging.getLogger(__name__)

VOICE_NAME = "de_DE-thorsten-high"
MODELS_DIR = Path("/home/sbin/reachy/voice/models")

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

    def speak(self, text: str) -> None:
        """Synthesize text and play it through the default audio output."""
        if not text.strip():
            return
        audio, sample_rate = self.synthesize(text)
        logger.debug("Speaking %d samples at %d Hz", len(audio), sample_rate)
        sd.play(audio, samplerate=sample_rate)
        sd.wait()


def _maybe_move(base: Path, hf_relative: str, target: Path) -> None:
    """Move a file from its hf_hub_download sub-path to target if needed."""
    if target.exists():
        return
    src = base / hf_relative
    if src.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        src.rename(target)
