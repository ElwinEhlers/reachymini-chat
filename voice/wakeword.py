"""Wake-word detection using openWakeWord.

The active wake word is "Hey Jarvis" — the most robust of the pre-trained
openWakeWord models, usable out of the box without any training.

To switch to a real "Hey Reachy" wake word, train a custom openWakeWord model
(see https://github.com/dscripka/openWakeWord#training-new-models — synthetic
TTS data + the provided Colab notebook) and drop the resulting ONNX file at
``voice/models/hey_reachy.onnx``. It is then loaded automatically on next start.
"""

import logging
import os
import threading

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280          # 80 ms @16 kHz — empfohlene openWakeWord-Framegröße
CUSTOM_MODEL_NAME = "hey_reachy.onnx"
FALLBACK_MODEL = "hey_jarvis"   # vortrainiertes openWakeWord-Modell


class WakeWord:
    """Detects a wake word in a continuous microphone stream."""

    def __init__(
        self,
        threshold: float = 0.5,
        input_device: int | None = None,
        gain: float | None = None,
    ) -> None:
        from openwakeword.model import Model
        import openwakeword
        from voice.audio_device import MIC_GAIN

        self._threshold = threshold
        self._input_device = input_device
        self._gain = MIC_GAIN if gain is None else gain

        # Custom "Hey Reachy"-Modell bevorzugen, sonst vortrainiertes Fallback laden.
        custom_path = os.path.join(os.path.dirname(__file__), "models", CUSTOM_MODEL_NAME)
        if os.path.exists(custom_path):
            model_paths = [custom_path]
            self._active = "hey_reachy (custom)"
        else:
            res_dir = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
            model_paths = [os.path.join(res_dir, f"{FALLBACK_MODEL}_v0.1.onnx")]
            self._active = FALLBACK_MODEL

        logger.info("Lade Wake-Word-Modell: %s …", self._active)
        # ONNX-Modelle (onnxruntime installiert); tflite_runtime fehlt in dieser Umgebung.
        self._model = Model(wakeword_model_paths=model_paths)
        logger.info("Wake-Word bereit (aktiv: '%s', Schwelle %.2f).", self._active, threshold)

    @property
    def active_model(self) -> str:
        return self._active

    def wait_for_wakeword(self, stop_event: threading.Event | None = None) -> bool:
        """Block until the wake word is detected.

        Öffnet einen Mikrofon-Stream auf dem (Reachy-)Eingabegerät, nimmt am
        nativen Device-Rate auf, resampled zu 16 kHz und speist 1280-Sample-
        Frames an openWakeWord. Gibt True bei Erkennung zurück, False bei
        gesetztem stop_event.
        """
        from voice.audio_device import resample_to_16k, apply_gain

        if hasattr(self._model, "reset"):
            self._model.reset()

        query_kind = self._input_device if self._input_device is not None else "input"
        native_sr = int(sd.query_devices(query_kind)["default_samplerate"])
        native_block = max(1, int(round(FRAME_SAMPLES * native_sr / SAMPLE_RATE)))
        pending = np.zeros(0, dtype=np.float32)

        # Beobachtbarkeit: alle ~2 s den höchsten Score + Pegel loggen, damit man
        # sieht, ob Audio den Detektor erreicht (auch ohne dass die Schwelle fällt).
        import time as _time
        window_peak = 0.0
        window_rms = 0.0
        next_report = _time.time() + 2.0

        with sd.InputStream(
            samplerate=native_sr,
            channels=1,
            dtype="float32",
            blocksize=native_block,
            device=self._input_device,
        ) as stream:
            while True:
                if stop_event and stop_event.is_set():
                    return False

                chunk, _ = stream.read(native_block)
                mono = chunk[:, 0] if chunk.ndim > 1 else chunk.flatten()
                mono = apply_gain(mono, self._gain)
                resampled = (
                    mono if native_sr == SAMPLE_RATE else resample_to_16k(mono, native_sr)
                )
                pending = np.concatenate([pending, resampled])

                while len(pending) >= FRAME_SAMPLES:
                    frame_f32 = pending[:FRAME_SAMPLES]
                    pending = pending[FRAME_SAMPLES:]
                    frame_i16 = (np.clip(frame_f32, -1.0, 1.0) * 32767).astype(np.int16)
                    scores = self._model.predict(frame_i16)
                    top = max(scores.values()) if scores else 0.0
                    frame_rms = float(np.sqrt(np.mean(frame_f32 ** 2)))
                    window_peak = max(window_peak, top)
                    window_rms = max(window_rms, frame_rms)
                    if top >= self._threshold:
                        logger.info("Wake-Word erkannt (Score %.2f, RMS %.3f).", top, frame_rms)
                        return True
                    if top >= 0.3:
                        # Knapp verfehlt: hilft beim Justieren von Schwelle/Gain (nur --debug).
                        # Hohe RMS (>~0.3) deutet auf Clipping/Übersteuerung hin.
                        logger.debug(
                            "Wake-Word knapp verfehlt: Score %.2f (RMS %.3f, Schwelle %.2f)",
                            top, frame_rms, self._threshold,
                        )

                now = _time.time()
                if now >= next_report:
                    logger.debug(
                        "Wake-Word lauscht … höchster Score (2 s): %.2f, Pegel-RMS: %.3f "
                        "(Schwelle %.2f)",
                        window_peak, window_rms, self._threshold,
                    )
                    window_peak = 0.0
                    window_rms = 0.0
                    next_report = now + 2.0
