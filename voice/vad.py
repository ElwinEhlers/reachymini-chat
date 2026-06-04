"""Voice Activity Detection using silero-vad."""

import logging
import threading
import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512          # silero-vad requirement at 16 kHz (32 ms)
PRE_SPEECH_CHUNKS = 5        # ~160 ms kept before speech onset
MAX_SPEECH_SECONDS = 30


class VAD:
    """Detects speech with silero-vad and returns recorded audio chunks."""

    def __init__(
        self,
        silence_duration_ms: int = 1500,
        threshold: float = 0.5,
    ) -> None:
        from silero_vad import load_silero_vad, VADIterator

        logger.info("Loading silero-vad model …")
        model = load_silero_vad(onnx=False)
        self._model = model
        self._threshold = threshold
        self._silence_duration_ms = silence_duration_ms
        logger.info("silero-vad ready.")

    def _make_iterator(self):
        from silero_vad import VADIterator
        return VADIterator(
            self._model,
            threshold=self._threshold,
            sampling_rate=SAMPLE_RATE,
            min_silence_duration_ms=self._silence_duration_ms,
            speech_pad_ms=100,
        )

    def record(self, stop_event: threading.Event | None = None) -> np.ndarray | None:
        """Block until speech is detected, record until silence, return float32 array.

        Returns None if stop_event is set before speech ends.
        """
        iterator = self._make_iterator()
        pre_buf: list[np.ndarray] = []   # ring buffer before speech onset
        speech: list[np.ndarray] = []
        in_speech = False
        max_chunks = int(MAX_SPEECH_SECONDS * SAMPLE_RATE / CHUNK_SAMPLES)

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SAMPLES,
        ) as stream:
            for _ in range(max_chunks + PRE_SPEECH_CHUNKS * 1000):
                if stop_event and stop_event.is_set():
                    logger.debug("VAD recording cancelled.")
                    return None

                chunk, _ = stream.read(CHUNK_SAMPLES)
                chunk_1d: np.ndarray = (
                    chunk[:, 0] if chunk.ndim > 1 else chunk.flatten()
                )

                result = iterator(chunk_1d, return_seconds=False)

                if not in_speech:
                    pre_buf.append(chunk_1d)
                    if len(pre_buf) > PRE_SPEECH_CHUNKS:
                        pre_buf.pop(0)

                if result:
                    if "start" in result:
                        logger.debug("Speech start detected.")
                        in_speech = True
                        speech = list(pre_buf)
                        speech.append(chunk_1d)
                    elif "end" in result and in_speech:
                        speech.append(chunk_1d)
                        logger.debug("Speech end detected (%d chunks).", len(speech))
                        break
                elif in_speech:
                    speech.append(chunk_1d)
                    if len(speech) > max_chunks:
                        logger.warning("Max speech duration reached.")
                        break

        if not speech:
            return None
        return np.concatenate(speech)

    def record_until_stop(self, stop_event: threading.Event) -> np.ndarray | None:
        """Record microphone audio until stop_event is set.

        Records at the device's native sample rate to avoid PipeWire resampling
        issues, then resamples to 16 kHz for Whisper STT.
        Returns a float32 mono array at SAMPLE_RATE (16 kHz).
        """
        native_sr = int(sd.query_devices(kind="input")["default_samplerate"])
        frames: list[np.ndarray] = []
        with sd.InputStream(
            samplerate=native_sr,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SAMPLES,
        ) as stream:
            while not stop_event.is_set():
                chunk, _ = stream.read(CHUNK_SAMPLES)
                frames.append(chunk[:, 0] if chunk.ndim > 1 else chunk.flatten())
        if not frames:
            return None
        audio = np.concatenate(frames)
        if native_sr != SAMPLE_RATE:
            target_len = int(len(audio) * SAMPLE_RATE / native_sr)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, target_len),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)
        return audio
