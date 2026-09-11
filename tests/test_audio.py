import io
import wave
from pathlib import Path

import numpy as np
import pytest

from echoflow import audio

RATE = audio.SAMPLE_RATE
EVAL_CLIP = Path(__file__).resolve().parent.parent / "eval" / "audio" / "short.wav"


def tone(seconds: float, dbfs: float) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    amplitude = 10 ** (dbfs / 20) * np.sqrt(2)  # sine RMS = amplitude / sqrt(2)
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_to_wav_is_16bit_mono_16k_and_round_trips():
    samples = tone(0.5, -12)
    with wave.open(io.BytesIO(audio.to_wav(samples))) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, RATE)
        decoded = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32767
    assert np.allclose(decoded, samples, atol=1e-3)


def test_to_wav_clips_out_of_range_samples():
    with wave.open(io.BytesIO(audio.to_wav(np.array([2.0, -2.0], dtype=np.float32)))) as w:
        assert list(np.frombuffer(w.readframes(2), dtype=np.int16)) == [32767, -32767]


def test_empty_recording_is_skipped():
    assert audio.has_speech(np.zeros(0, dtype=np.float32)) is False


def test_too_short_recording_is_skipped():
    assert audio.has_speech(tone(0.2, -20)) is False


def test_silence_is_skipped():
    assert audio.has_speech(np.zeros(RATE * 2, dtype=np.float32)) is False


def test_background_noise_is_skipped():
    noise = np.random.default_rng(0).normal(0, 10 ** (-60 / 20), RATE * 2).astype(np.float32)
    assert audio.has_speech(noise) is False


def test_speech_level_signal_is_kept():
    assert audio.has_speech(tone(1.0, -30)) is True


@pytest.mark.skipif(not EVAL_CLIP.exists(), reason="run eval/make_audio.py first")
def test_real_speech_clip_is_kept():
    with wave.open(str(EVAL_CLIP)) as w:
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32767
    assert audio.has_speech(samples) is True
