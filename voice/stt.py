"""Speech-to-text using faster-whisper (CPU, small model, German)."""

import logging
import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
LANGUAGE = "de"


class STT:
    """Wraps faster-whisper for German transcription on CPU."""

    def __init__(self) -> None:
        logger.info("Loading Whisper model '%s' on %s …", MODEL_SIZE, DEVICE)
        self._model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        logger.info("Whisper ready.")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe a float32 mono audio array and return the text.

        The audio array must be float32, mono, at *sample_rate* Hz.
        If sample_rate != 16000 the array is resampled via linear interpolation.
        """
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Resample to 16 kHz if needed (simple linear interpolation)
        if sample_rate != 16000:
            target_len = int(len(audio) * 16000 / sample_rate)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, target_len),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)

        segments, info = self._model.transcribe(audio, language=LANGUAGE)
        text = " ".join(s.text for s in segments).strip()
        logger.debug("Transcribed (lang=%s, prob=%.2f): %r", info.language, info.language_probability, text)
        return text
