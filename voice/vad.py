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
        input_device: int | None = None,
        input_gain: float = 1.0,
    ) -> None:
        from silero_vad import load_silero_vad

        logger.info("Loading silero-vad model …")
        model = load_silero_vad(onnx=False)
        self._model = model
        self._threshold = threshold
        self._silence_duration_ms = silence_duration_ms
        # Optionaler fester Eingabe-Device-Index (z.B. Reachy-Mikro). None = Default.
        self._input_device = input_device
        # Pegelanhebung für record_command (leises Reachy-Mikro). 1.0 = unverändert.
        self._input_gain = input_gain
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
            device=self._input_device,
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
        query_kind = self._input_device if self._input_device is not None else "input"
        native_sr = int(sd.query_devices(query_kind)["default_samplerate"])
        frames: list[np.ndarray] = []
        with sd.InputStream(
            samplerate=native_sr,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SAMPLES,
            device=self._input_device,
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

    def record_command(
        self, stop_event: threading.Event | None = None
    ) -> np.ndarray | None:
        """Record a spoken command from the (Reachy) microphone.

        Nimmt am nativen Device-Rate auf (umgeht den PipeWire-16-kHz-Bug),
        resampled fortlaufend zu 16 kHz und speist Silero-VAD. Blockt bis
        Sprachbeginn und stoppt nach `silence_duration_ms` Stille.
        Gibt float32-mono @16 kHz zurück (None bei Abbruch/keiner Sprache).
        """
        from voice.audio_device import resample_to_16k, apply_gain

        query_kind = self._input_device if self._input_device is not None else "input"
        native_sr = int(sd.query_devices(query_kind)["default_samplerate"])
        native_block = max(1, int(round(CHUNK_SAMPLES * native_sr / SAMPLE_RATE)))

        iterator = self._make_iterator()
        pending = np.zeros(0, dtype=np.float32)   # 16 kHz Restpuffer
        pre_buf: list[np.ndarray] = []            # 512er-Frames vor Sprachbeginn
        speech: list[np.ndarray] = []
        in_speech = False
        max_chunks = int(MAX_SPEECH_SECONDS * SAMPLE_RATE / CHUNK_SAMPLES)

        with sd.InputStream(
            samplerate=native_sr,
            channels=1,
            dtype="float32",
            blocksize=native_block,
            device=self._input_device,
        ) as stream:
            while True:
                if stop_event and stop_event.is_set():
                    return None

                chunk, _ = stream.read(native_block)
                mono = chunk[:, 0] if chunk.ndim > 1 else chunk.flatten()
                mono = apply_gain(mono, self._input_gain)
                resampled = (
                    mono if native_sr == SAMPLE_RATE else resample_to_16k(mono, native_sr)
                )
                pending = np.concatenate([pending, resampled])

                # Vollständige 512-Sample-Frames an Silero geben
                while len(pending) >= CHUNK_SAMPLES:
                    frame = pending[:CHUNK_SAMPLES]
                    pending = pending[CHUNK_SAMPLES:]
                    result = iterator(frame, return_seconds=False)

                    if not in_speech:
                        pre_buf.append(frame)
                        if len(pre_buf) > PRE_SPEECH_CHUNKS:
                            pre_buf.pop(0)

                    if result and "start" in result:
                        in_speech = True
                        speech = list(pre_buf)
                        speech.append(frame)
                    elif result and "end" in result and in_speech:
                        speech.append(frame)
                        logger.debug("Sprachende erkannt (%d Frames).", len(speech))
                        return np.concatenate(speech)
                    elif in_speech:
                        speech.append(frame)
                        if len(speech) > max_chunks:
                            logger.warning("Maximale Sprachdauer erreicht.")
                            return np.concatenate(speech)
