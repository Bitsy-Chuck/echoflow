#!/usr/bin/env python3
"""
EchoFlow POC - Voice to Text with Sarvam AI STT + Gemini Pro

Flow:
1. Hold Left Shift + Left Ctrl to start recording
2. Audio chunked every 5s → parallel STT via Sarvam AI
3. Release → Gemini Pro aggregates all transcripts → output

Output modes (set via ECHOFLOW_OUTPUT env var):
- "cursor" (default): Types text at current cursor position
- "print": Prints to console only
- "both": Both cursor typing and console print

Set ECHOFLOW_OUTPUT_DELAY (default 0.5s) to adjust delay before typing.
"""

import os
import queue
import threading
import time
import io
import wave
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import sounddevice as sd
from pynput import keyboard
from pynput.keyboard import Controller as KeyboardController
import requests
import google.generativeai as genai

# Config
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 5  # seconds
TRIGGER_KEYS = {keyboard.Key.shift_l, keyboard.Key.ctrl_l}  # Left Shift + Left Ctrl - hold to talk

# Output mode: "print" (console only), "cursor" (type at cursor), "both"
OUTPUT_MODE = os.environ.get("ECHOFLOW_OUTPUT", "cursor")
OUTPUT_DELAY = float(os.environ.get("ECHOFLOW_OUTPUT_DELAY", "0.5"))  # Delay before typing (seconds)
MAC_PASTE_ENABLED = os.environ.get("ECHOFLOW_MAC_PASTE", "1").lower() not in {"0", "false", "no"}

# Models
AGGREGATION_MODEL = "gemini-2.5-flash-lite"  # Flash model for final aggregation

AGGREGATION_PROMPT = """You are a smart speech-to-text aggregator. You are processing a stream of audio chunks.

Your Mission:
Produce a clean, readable, and accurate transcript of what the user *intended* to say.

Guidelines:
1. **Merge & Repair**: Join the chunks seamlessly. Repair words cut off at chunk boundaries.
2. **Format**: Add proper punctuation and capitalization. Use language-appropriate punctuation (e.g., Devanagari danda for Hindi).
3. **Smart Correction**:
   - If the user stumbles or corrects themselves, output the final intent.
   - Remove filler words unless they convey hesitation important to the context.
4. **Faithfulness**:
   - Do NOT summarize. Keep the content full and detailed.
   - Do NOT rewrite the user's style. If they speak casually, keep it casual.
   - Only "fix" what is clearly an error or a stumble. Don't be too aggressive.
5. **Language Preservation**:
   - PRESERVE the original spoken language. Do NOT translate to English.
   - The user may speak in Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, or any other Indian language.
   - Keep the output in the SAME language and script as the input transcripts.
6. **Output**: Produce ONLY the final text.

Input Transcripts:
{transcripts}
"""

# Sarvam AI config
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY")
SARVAM_ENDPOINT = "https://api.sarvam.ai/speech-to-text"
SARVAM_MODEL = "saaras:v3"
SARVAM_LANGUAGE_CODE = os.environ.get("SARVAM_LANGUAGE_CODE", "unknown")

# State
is_recording = False
audio_buffer = []
audio_queue = queue.Queue()
transcript_results = {}
chunk_counter = 0
executor = ThreadPoolExecutor(max_workers=5)
futures = []
chunk_timer = None
buffer_lock = threading.Lock()
current_pressed_keys = set()

# Keyboard controller for typing at cursor
keyboard_controller = KeyboardController()


def play_sound(sound_name):
    """Play a system sound on macOS."""
    if sys.platform == "darwin":
        try:
            sound_path = f"/System/Library/Sounds/{sound_name}.aiff"
            if os.path.exists(sound_path):
                subprocess.Popen(["afplay", sound_path])
        except Exception:
            pass


def init_gemini():
    """Initialize Gemini with API key from environment."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    genai.configure(api_key=api_key)


def audio_to_wav_bytes(audio_data: np.ndarray) -> bytes:
    """Convert numpy float32 audio array to WAV bytes (16-bit PCM)."""
    audio_int16 = (audio_data * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit = 2 bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


def transcribe_chunk_sarvam(chunk_id: int, audio_data: np.ndarray) -> tuple[int, str]:
    """Transcribe a single audio chunk using Sarvam AI STT."""
    try:
        wav_bytes = audio_to_wav_bytes(audio_data)

        headers = {
            "api-subscription-key": SARVAM_API_KEY,
        }

        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav"),
        }

        data = {
            "model": SARVAM_MODEL,
            "language_code": SARVAM_LANGUAGE_CODE,
            "mode": "transcribe",
        }

        response = requests.post(
            SARVAM_ENDPOINT,
            headers=headers,
            files=files,
            data=data,
            timeout=30,
        )

        if response.status_code != 200:
            print(f"  [Chunk {chunk_id}] Sarvam API error ({response.status_code}): {response.text[:200]}")
            return (chunk_id, "")

        result = response.json()
        transcript = result.get("transcript", "")
        language = result.get("language_code", "unknown")
        print(f"  [Chunk {chunk_id}] Sarvam complete (lang={language}): {transcript}")
        return (chunk_id, transcript)

    except Exception as e:
        print(f"  [Chunk {chunk_id}] Sarvam error: {e}")
        return (chunk_id, "")


def process_chunk():
    """Called every CHUNK_DURATION seconds to process accumulated audio."""
    global chunk_counter, audio_buffer

    with buffer_lock:
        if not audio_buffer:
            return

        # Get current buffer and reset
        chunk_data = np.concatenate(audio_buffer)
        audio_buffer = []
        chunk_id = chunk_counter
        chunk_counter += 1

    print(f"  [Chunk {chunk_id}] Queued for Sarvam STT ({len(chunk_data)/SAMPLE_RATE:.1f}s audio)")

    # Submit for parallel processing
    future = executor.submit(transcribe_chunk_sarvam, chunk_id, chunk_data)
    futures.append(future)


def schedule_chunk_timer():
    """Schedule the next chunk processing."""
    global chunk_timer
    if is_recording:
        chunk_timer = threading.Timer(CHUNK_DURATION, on_chunk_timer)
        chunk_timer.start()


def on_chunk_timer():
    """Timer callback - process chunk and schedule next."""
    if is_recording:
        process_chunk()
        schedule_chunk_timer()


def audio_callback(indata, frames, time_info, status):
    """Called by sounddevice for each audio block."""
    if status:
        print(f"  Audio status: {status}")
    if is_recording:
        with buffer_lock:
            audio_buffer.append(indata.copy().flatten())


def aggregate_transcripts(transcripts: list[str]) -> str:
    """Use Gemini Pro to aggregate all transcripts into clean text."""
    if not transcripts or all(t.strip() == "" for t in transcripts):
        return ""

    # Filter empty transcripts
    non_empty = [t for t in transcripts if t.strip()]
    if not non_empty:
        return ""

    model = genai.GenerativeModel(AGGREGATION_MODEL)

    formatted_transcripts = chr(10).join(f"[Chunk {i}]: {t}" for i, t in enumerate(non_empty))
    prompt = AGGREGATION_PROMPT.format(transcripts=formatted_transcripts)

    response = model.generate_content(prompt)
    return response.text.strip()


def type_at_cursor(text: str):
    """Type text at the current cursor position using keyboard simulation."""
    if not text:
        return

    print(f"  Typing at cursor in {OUTPUT_DELAY}s...")
    time.sleep(OUTPUT_DELAY)  # Give user time to focus target window

    if sys.platform == "darwin" and MAC_PASTE_ENABLED:
        try:
            # macOS: copy to clipboard then paste with Cmd+V for reliability
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"))

            play_sound("Glass")

            keyboard_controller.press(keyboard.Key.cmd)
            keyboard_controller.press("v")
            keyboard_controller.release("v")
            keyboard_controller.release(keyboard.Key.cmd)
            print("  [Typed at cursor via paste]")
            return
        except Exception as e:
            print(f"  macOS paste failed ({e}); falling back to typing")

    # Type the text character by character (default / fallback)
    keyboard_controller.type(text)
    print("  [Typed at cursor]")


def start_recording():
    """Start audio capture."""
    global is_recording, audio_buffer, chunk_counter, futures, transcript_results

    play_sound("Tink")

    # Reset state
    audio_buffer = []
    chunk_counter = 0
    futures = []
    transcript_results = {}

    is_recording = True
    print("\n[Recording started] Hold key and speak...")

    # Start chunk timer
    schedule_chunk_timer()


def stop_recording():
    """Stop recording and process final results."""
    global is_recording, chunk_timer

    is_recording = False
    print("[Recording stopped] Processing...")

    # Cancel chunk timer
    if chunk_timer:
        chunk_timer.cancel()
        chunk_timer = None

    # Process any remaining audio in buffer
    with buffer_lock:
        if audio_buffer:
            chunk_data = np.concatenate(audio_buffer)
            audio_buffer.clear()
            chunk_id = chunk_counter
            print(f"  [Chunk {chunk_id}] Final chunk ({len(chunk_data)/SAMPLE_RATE:.1f}s audio)")
            future = executor.submit(transcribe_chunk_sarvam, chunk_id, chunk_data)
            futures.append(future)

    # Wait for all STT to complete
    print("  Waiting for all Sarvam STT to complete...")
    results = {}
    for future in as_completed(futures):
        chunk_id, transcript = future.result()
        results[chunk_id] = transcript

    # Order transcripts by chunk_id
    ordered_transcripts = [results[i] for i in sorted(results.keys())]

    print(f"  All {len(ordered_transcripts)} chunks transcribed")

    # Aggregate with Gemini Pro
    print("  Aggregating with Gemini Pro...")
    final_text = aggregate_transcripts(ordered_transcripts)

    # Output based on mode
    if OUTPUT_MODE in ("print", "both"):
        print("\n" + "="*60)
        print("FINAL OUTPUT:")
        print("="*60)
        print(final_text)
        print("="*60 + "\n")

    if OUTPUT_MODE in ("cursor", "both"):
        type_at_cursor(final_text)


def on_press(key):
    """Handle key press."""
    global is_recording, current_pressed_keys
    current_pressed_keys.add(key)

    if TRIGGER_KEYS.issubset(current_pressed_keys) and not is_recording:
        start_recording()


def on_release(key):
    """Handle key release."""
    global is_recording, current_pressed_keys
    if key in current_pressed_keys:
        current_pressed_keys.remove(key)

    # If we are recording and the trigger combo is broken, stop
    if is_recording and not TRIGGER_KEYS.issubset(current_pressed_keys):
        stop_recording()


def main():
    print("="*60)
    print("EchoFlow POC - Sarvam AI STT + Gemini Pro")
    print("="*60)
    print(f"Trigger key: Left Shift + Left Ctrl (hold to record)")
    print(f"Chunk duration: {CHUNK_DURATION}s")
    print(f"STT: Sarvam AI ({SARVAM_MODEL})")
    print(f"  Language: {SARVAM_LANGUAGE_CODE}")
    print(f"Aggregation: {AGGREGATION_MODEL}")
    print(f"Output mode: {OUTPUT_MODE}")
    if OUTPUT_MODE in ("cursor", "both"):
        print(f"  Output delay: {OUTPUT_DELAY}s")
    print("="*60)
    print("Use Ctrl+C to exit")
    print("="*60 + "\n")

    # Validate config
    if not SARVAM_API_KEY:
        raise ValueError("SARVAM_API_KEY environment variable not set")

    # Initialize Gemini
    init_gemini()
    print("[Gemini initialized]")

    # Start audio stream
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype='float32',
        callback=audio_callback,
        blocksize=1024
    )

    with stream:
        print("[Audio stream ready]")
        print("\nHold Left Shift + Left Ctrl to record...\n")

        # Start keyboard listener (blocking)
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    # Cleanup
    executor.shutdown(wait=True)
    print("[Done]")


if __name__ == "__main__":
    main()
