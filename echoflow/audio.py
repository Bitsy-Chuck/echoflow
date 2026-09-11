"""Microphone capture and audio checks."""

import io
import threading
import wave

import numpy as np

SAMPLE_RATE = 16000
MIN_SECONDS = 0.3            # shorter holds are accidental taps
FRAME_SECONDS = 0.03
SPEECH_DBFS = -45.0          # frames louder than this count as voice
MIN_SPEECH_SECONDS = 0.15    # need at least this much voice to transcribe


def to_wav(samples: np.ndarray) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def has_speech(samples: np.ndarray) -> bool:
    """False for accidental taps and silence, so the model never invents text from nothing."""
    if len(samples) < MIN_SECONDS * SAMPLE_RATE:
        return False
    frame = int(FRAME_SECONDS * SAMPLE_RATE)
    frames = samples[: len(samples) // frame * frame].reshape(-1, frame)
    rms_dbfs = 20 * np.log10(np.sqrt(np.mean(frames**2, axis=1)) + 1e-10)
    return bool(np.count_nonzero(rms_dbfs > SPEECH_DBFS) * FRAME_SECONDS >= MIN_SPEECH_SECONDS)


class Recorder:
    """Keeps the input stream open so the first syllable is never cut; buffers only while recording."""

    def __init__(self):
        import sounddevice as sd

        self._lock = threading.Lock()
        self._chunks: list[np.ndarray] = []
        self._recording = False
        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                      blocksize=1024, callback=self._callback)

    def __enter__(self):
        self._stream.start()
        return self

    def __exit__(self, *exc):
        self._stream.stop()
        self._stream.close()

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            if self._recording:
                self._chunks.append(indata[:, 0].copy())

    def start(self):
        with self._lock:
            self._chunks = []
            self._recording = True

    def stop(self) -> np.ndarray:
        with self._lock:
            self._recording = False
            chunks, self._chunks = self._chunks, []
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
