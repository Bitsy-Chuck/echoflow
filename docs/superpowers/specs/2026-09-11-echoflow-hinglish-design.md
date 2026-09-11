# EchoFlow v2 - Hinglish dictation, Wispr Flow style

## Goal

Hold a hotkey, speak Hinglish, release, and clean text appears at the cursor.
Output is Roman-script Hinglish with proper punctuation, the user's own vocabulary spelled right, fillers removed and self-corrections resolved.
Accuracy matters most; latency after release should stay around 1-2 seconds.

## Decisions

- Runs from a local clone at `~/echoflow`, outside Dropbox.
- Uses Vertex AI in project `app-dashtoon`, location `global`, with the service account key used by `~/vid-storyboarding`.
- `.env` points at that key file; the key is never copied into this public repo.
- Output script is Roman Hinglish ("kal ki meeting mein roadmap discuss karte hain"), never Devanagari.
- The old Chirp 3 and Sarvam engines are removed; one pipeline, chosen by measurement.

## Model choice (measured, see `eval/`)

15 synthetic Hinglish clips (Gemini TTS, 16 kHz, light noise) with expected clean text.
WER is lenient to Hinglish spelling variants.

| Pipeline | WER | Devanagari outputs | Latency p50 |
|---|---|---|---|
| Transcribe verbatim only | 60.0% | 7/15 | 0.90s |
| Direct audio -> gemini-3.5-flash-lite | 6.6% | 0 | 1.22s |
| Direct audio -> gemini-3.8-flash | 7.6% | 0 | 1.70s |
| Direct audio -> gemini-3.1-pro-preview | 1.4% | 0 | 5.06s |
| **Transcribe -> gemini-3.6-flash cleanup** | **0.9%** | **0** | **~1.7s total** |

Chosen pipeline:
1. `gemini-3.5-transcribe-preview`, VERBATIM mode, `language_codes=["hi-IN", "en-IN"]`, `custom_vocabulary` = user vocab.
   SMART mode is not used because it silently ignores custom vocabulary.
2. `gemini-3.6-flash` with minimal thinking rewrites the raw transcript into the final text (romanize, punctuate, drop fillers, resolve self-corrections, enforce vocab spelling).

## Components

- `echoflow/gcp.py` - Vertex client from the service account key in `.env`.
- `echoflow/transcriber.py` - the two model calls and the style rules prompt.
- `echoflow/vocab.py` - personal vocabulary file `~/.echoflow/vocab.txt`, one term per line; load and add.
- `echoflow/audio.py` - microphone recorder, WAV encoding, too-short and silence detection.
- `echoflow/hotkeys.py` - pure state machine for hold-to-talk: start, stop, cancel.
- `echoflow/macos.py` - frontmost app name, clipboard snapshot and restore, paste, read selection.
- `echoflow/app.py` - wires everything; a single worker thread does the slow work so the key listener never blocks.
- `main.py` - entry point.

## Behaviour

- Hold Left Ctrl + Left Shift to talk; release to transcribe and paste.
- Pressing any other key during the hold cancels the recording, so ordinary Ctrl+Shift shortcuts never trigger a transcription.
- Holds shorter than 0.3s and silent recordings are ignored, so the model never invents text from silence.
- The name of the frontmost app is passed to the cleanup model as formatting context.
- Paste goes through the clipboard with Cmd+V, then the previous clipboard contents (all types, including images) are restored.
- Vocabulary building: select a word anywhere and press Left Ctrl + Left Shift + D to add it to `~/.echoflow/vocab.txt`; the file can also be edited by hand and is reloaded on every dictation.
- Sounds: Tink on start, Glass on paste, Pop on vocab add, Basso on error.
- Every result is also printed to the terminal, so text is never lost if a paste lands in the wrong place.

## Error handling

- Missing or invalid config fails at startup with a clear message.
- API errors during a dictation play the error sound, print the error, and keep the app running.
- If the cleanup call fails, the raw transcript is pasted instead of nothing.

## Testing

- Unit tests (pytest): vocab file handling, WAV encoding and silence detection, hotkey state machine, prompt building.
- `eval/run_eval.py`: accuracy and latency of the real pipeline on the Hinglish clips; rerun when new models ship.
- End to end: the app process driven with real key events and audio played through the speakers, text pasted into TextEdit and read back.
