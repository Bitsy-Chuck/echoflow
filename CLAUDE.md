# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EchoFlow is hold-to-talk Hinglish dictation for macOS.
Hold Left Ctrl + Left Shift, speak, release: Gemini Transcribe produces a raw transcript biased with the user's vocabulary, Gemini 3.6 Flash rewrites it as clean Roman-script Hinglish, and the text is pasted at the cursor.
Design and model-choice evidence: `docs/superpowers/specs/2026-09-11-echoflow-hinglish-design.md`.

## Commands

```bash
venv/bin/python main.py                 # run the app
venv/bin/python -m pytest               # unit tests
venv/bin/python eval/make_audio.py      # generate eval clips (once)
venv/bin/python eval/run_eval.py        # accuracy/latency of the pipelines
```

Config is `.env` (see `.env.example`): service account key path, GCP project, location.
This repo is public - never commit `.env`, keys, or `eval/audio/`.

## Architecture

- `echoflow/app.py` - pynput listener callbacks stay fast; a single-thread executor does transcription and paste, so pastes stay in order.
- `echoflow/hotkeys.py` - pure hold-to-talk state machine (START / STOP / CANCEL / ADD_VOCAB).
- `echoflow/transcriber.py` - model IDs, style rules prompt, `transcribe()` pipeline with a Devanagari retry.
- `echoflow/audio.py` - always-open input stream, WAV encoding, silence/too-short detection.
- `echoflow/macos.py` - frontmost app via CGWindowList (NSWorkspace goes stale without a run loop), clipboard snapshot/restore, synthetic Cmd+V/Cmd+C after modifiers are released.
- `echoflow/vocab.py` - `~/.echoflow/vocab.txt`.

## Gotchas

- Gemini Transcribe SMART mode silently ignores `custom_vocabulary`; use VERBATIM.
- `gemini-3.8-flash` rejects `thinking_level=MINIMAL`; `LOW` is its lowest.
- Mixed-script transcripts (Latin + Devanagari) are the case the cleanup model most often fails to transliterate; the cleanup request insists on Roman script and `transcribe()` retries if Devanagari survives.
- Change a model or prompt only with an eval run before and after.
