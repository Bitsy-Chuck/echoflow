# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EchoFlow is a POC for hold-to-talk voice transcription. Hold Left Shift + Left Ctrl to record audio, which gets chunked every 5s and sent to Google Chirp 3 STT in parallel. On release, Gemini aggregates the chunks into clean text and pastes it at the cursor.

## Running

```bash
pip install -r requirements.txt
python main.py
```

**Required env vars:** `GOOGLE_CLOUD_PROJECT`, `GEMINI_API_KEY`
**Optional env vars:** `CHIRP_REGION` (default: us-central1), `CHIRP_RECOGNIZER` (default: _), `ECHOFLOW_OUTPUT` (print/cursor/both, default: cursor), `ECHOFLOW_OUTPUT_DELAY` (default: 0.5), `ECHOFLOW_MAC_PASTE` (default: 1)

Requires `gcloud auth login` for Chirp 3 access tokens.

## Architecture

Single-file app (`main.py`, ~434 lines). No tests, no build step.

**Threading model:**
- Main thread: `pynput` keyboard listener (blocking)
- Audio thread: `sounddevice.InputStream` callback fills buffer
- Timer thread: every 5s, drains buffer into a chunk
- Worker pool: `ThreadPoolExecutor(max_workers=5)` sends chunks to Chirp 3 API in parallel

**Key flow:** `on_press` → `start_recording()` → audio accumulates in `audio_buffer` → timer fires `process_chunk()` → submits `transcribe_chunk_chirp3()` to executor → on key release `stop_recording()` → waits for all futures → `aggregate_transcripts()` via Gemini → `type_at_cursor()` pastes via pbcopy+Cmd+V on macOS.

**Global state:** `is_recording`, `audio_buffer`, `futures`, `transcript_results`, `chunk_counter`, `current_pressed_keys` — protected by `buffer_lock` where needed.

**Output:** On macOS, copies to clipboard and simulates Cmd+V paste. Falls back to character-by-character typing. Plays system sounds (Tink on start, Glass on paste).
