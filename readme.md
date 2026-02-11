# EchoFlow POC

Hold-to-talk voice transcription with Gemini Pro aggregation. Supports two STT engines:

- **Google Chirp 3** — English transcription via Google Cloud Speech-to-Text
- **Sarvam AI** — Indian language transcription (Hindi, Tamil, Telugu, etc.) with auto language detection

## Flow

```
Hold Left Shift + Left Ctrl → Audio chunked every 5s → STT (parallel)
Release Left Shift + Left Ctrl → Gemini Pro aggregates → Final text output
```

## Prerequisites

- Python 3.10+
- Gemini API key

**For Chirp 3 mode:**
- Google Cloud project with Speech-to-Text API enabled
- gcloud CLI installed and authenticated

**For Sarvam mode:**
- Sarvam AI API key (from [sarvam.ai](https://www.sarvam.ai))

## Setup

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2a. Chirp 3 setup

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable speech.googleapis.com

export GOOGLE_CLOUD_PROJECT="your-project-id"
export GEMINI_API_KEY="your-gemini-api-key"

# Optional (defaults shown)
export CHIRP_REGION="us-central1"
export CHIRP_RECOGNIZER="_"
```

### 2b. Sarvam AI setup

```bash
export SARVAM_API_KEY="your-sarvam-api-key"
export GEMINI_API_KEY="your-gemini-api-key"

# Optional — defaults to "unknown" (auto-detect)
export SARVAM_LANGUAGE_CODE="hi-IN"
```

## Run

**Via router** (edit `STT_ENGINE` in `run.py` to switch between `"chirp"` and `"sarvam"`):
```bash
python run.py
```

**Directly:**
```bash
python main.py          # Chirp 3
python sarvam_main.py   # Sarvam AI
```

## Usage

1. **Hold Left Shift + Left Ctrl** to start recording
2. **Speak** - audio is chunked every 5 seconds and sent to Chirp 3
3. **Release Left Shift + Left Ctrl** to stop and get aggregated result
4. **Paste (Cmd+V)** - The final transcribed text is automatically copied to your clipboard. You can paste it anywhere using `Cmd + V`.
5. **Press ESC** to exit

## Platform Notes

### macOS

Grant accessibility permission when prompted:
System Preferences → Privacy & Security → Accessibility → Enable for Terminal/IDE

If cursor typing seems flaky, the app now pastes the final text using Cmd+V on macOS,
so ensure your target window accepts paste operations and that `pbcopy` is available
(it is installed by default). Set `ECHOFLOW_MAC_PASTE=0` to force key-by-key typing
instead of the automatic paste on macOS.

### Linux

May need to add user to input group:
```bash
sudo usermod -aG input $USER
# Log out and back in
```

## Architecture

Single-file per engine. `run.py` routes between them. No tests, no build step.

- **Audio capture**: `sounddevice.InputStream` callback fills buffer
- **Chunking**: Timer thread drains buffer every 5s
- **STT**: `ThreadPoolExecutor(max_workers=5)` sends chunks in parallel
- **Aggregation**: Gemini aggregates all chunk transcripts into clean text
- **Output**: Copies to clipboard and pastes via Cmd+V on macOS
