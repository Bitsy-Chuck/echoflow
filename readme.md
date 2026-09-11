# EchoFlow

Hold-to-talk dictation for Hinglish on macOS, in the spirit of Wispr Flow.
Hold a hotkey, speak, release, and clean text is pasted at your cursor.

- Speak Hindi, English or any mix; the output is Roman-script Hinglish ("kal ki meeting mein roadmap discuss karte hain").
- Proper punctuation and capitalization, filler words removed, self-corrections resolved ("Tuesday, nahi nahi, Wednesday" becomes "Wednesday").
- Your own vocabulary (names, products, jargon) is spelled exactly the way you want.
- Text appears about 2 seconds after you release the keys.

## How it works

1. **Gemini 3.5 Transcribe** (`gemini-3.5-transcribe-preview`) turns the audio into a raw transcript, biased towards your vocabulary.
2. **Gemini 3.6 Flash** rewrites it into the final text: Roman script, punctuation, cleanup, vocabulary spelling.
3. The text is pasted with Cmd+V and your previous clipboard is restored.

This pair was chosen by measurement, see [Accuracy](#accuracy).

## Setup

Requires macOS, Python 3.11+, and a Google Cloud service account with Vertex AI access.

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in the key path and project
```

Give your terminal app these permissions in System Settings > Privacy & Security:
**Accessibility** (to paste), **Input Monitoring** (to see the hotkey) and **Microphone**.

## Use

```bash
venv/bin/python main.py
```

| Action | Keys |
|---|---|
| Dictate | Hold **Left Ctrl + Left Shift**, speak, release |
| Add a word to your vocabulary | Select it anywhere, press **Left Ctrl + Left Shift + D** |
| Quit | Ctrl+C in the terminal |

Sounds: Tink when listening, Glass when pasted, Pop when a word is added, Basso on errors.
Every result is also printed in the terminal, so nothing is lost if the paste lands in the wrong place.
Pressing any other key while holding Ctrl+Shift cancels, so normal Ctrl+Shift shortcuts keep working.

### Vocabulary

Your vocabulary lives in `~/.echoflow/vocab.txt`, one term per line (lines starting with `#` are comments).
It is re-read on every dictation, so edits apply immediately.
Add names, product names and jargon that get misspelled - not everyday words.

## Accuracy

`eval/` holds 15 Hinglish test clips (generated with Gemini TTS) and their expected text.

```bash
venv/bin/python eval/make_audio.py   # once, writes eval/audio/
venv/bin/python eval/run_eval.py     # compares pipelines
```

| Pipeline | WER | Latency p50 |
|---|---|---|
| **Transcribe + 3.6 Flash (EchoFlow)** | **0.9%** | **~1.9s** |
| Audio directly to gemini-3.1-pro-preview | 1.4% | 5.1s |
| Audio directly to gemini-3.8-flash | 7.6% | 1.7s |
| Transcribe only | 60% (writes Devanagari) | 0.9s |

Rerun it when new models ship.

## Tests

```bash
venv/bin/python -m pytest
```
