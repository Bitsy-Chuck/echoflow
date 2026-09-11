#!/usr/bin/env python3
"""Generate eval audio for eval/cases.json with Gemini TTS.

Each case is spoken by a Gemini TTS voice, resampled to 16 kHz mono (what the app
records), and mixed with light noise so the clips are not studio-clean.
Output: eval/audio/<case id>.wav (gitignored). Existing files are skipped.

    venv/bin/python eval/make_audio.py
"""

import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from echoflow.gcp import make_client

TTS_MODEL = "gemini-3.1-flash-tts-preview"
TTS_RATE = 24000
TARGET_RATE = 16000
SNR_DB = 30

EVAL_DIR = Path(__file__).resolve().parent
AUDIO_DIR = EVAL_DIR / "audio"


def synthesize(client, text: str, voice: str) -> bytes:
    from google.genai import types

    response = client.models.generate_content(
        model=TTS_MODEL,
        contents=f"Say this naturally, like a young Indian professional talking casually in Hinglish: {text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    return response.candidates[0].content.parts[0].inline_data.data


def to_16k_with_noise(pcm_24k: bytes, seed: int) -> np.ndarray:
    resampled = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(TTS_RATE), "-ac", "1", "-i", "-",
         "-ar", str(TARGET_RATE), "-f", "wav", "-"],
        input=pcm_24k, capture_output=True, check=True,
    ).stdout
    audio, _ = sf.read(io.BytesIO(resampled), dtype="float32")
    rng = np.random.default_rng(seed)
    noise_power = np.mean(audio**2) / (10 ** (SNR_DB / 10))
    return np.clip(audio + rng.normal(0, np.sqrt(noise_power), audio.shape), -1, 1).astype(np.float32)


def main():
    cases = json.loads((EVAL_DIR / "cases.json").read_text())["cases"]
    AUDIO_DIR.mkdir(exist_ok=True)
    client = make_client()
    for i, case in enumerate(cases):
        out = AUDIO_DIR / f"{case['id']}.wav"
        if out.exists():
            print(f"skip  {out.name}")
            continue
        audio = to_16k_with_noise(synthesize(client, case["spoken"], case["voice"]), seed=i)
        sf.write(out, audio, TARGET_RATE, subtype="PCM_16")
        print(f"wrote {out.name} ({len(audio) / TARGET_RATE:.1f}s)")


if __name__ == "__main__":
    main()
