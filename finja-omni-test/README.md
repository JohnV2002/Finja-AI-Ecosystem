# Finja Omni Test v1.1.0

This module represents the testbed for Finja's screen observation capabilities (similar to "Omni" but completely local). It uses OCR and Vision-Language Models (VLMs) to read and see what's happening on the screen without using a camera, but rather by capturing the active window.

## Setup

1. Copy `.env.example` to `.env` and fill in your API keys if you plan to use cloud models. Local models do not require an API key.
2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: Ensure you have `pygetwindow`, `mss`, `rapidocr`, `onnxruntime`, `psutil`, `Pillow`, and `requests` installed as per the script requirements.)*

## Usage

### 1. Live Screen Observation

The core pipeline that watches your screen and writes observations to a local SQLite database (`finja_screen.db`).

```bash
python live.py
```

### 2. Speech Bubble Overlay

A floating overlay that uses the screen observation data to generate Finja's thoughts and reactions.

```bash
python bubble.py
```

### 3. Ask Finja

You can ask Finja about what she saw on your screen recently.

```bash
python quatsch.py 5 "What did I just watch?"
```

## Features

- **Active Window Capture:** Only captures the focused window, reducing UI noise and preserving privacy.
- **Local OCR:** Uses RapidOCR (ONNX) to extract text (e.g., subtitles) directly on your CPU.
- **Vision Models:** Supports both local (Ollama) and cloud (OpenRouter) Vision-Language Models for scene understanding.
- **Deduplication:** Uses perceptual hashing (pHash) to avoid saving duplicate frames when the screen is static.

## Flare & Analytics (optional, v1.1.0)

All scripts report errors with structured codes: `FINJA-106` a missing key or setting (Flare asks a person), `FINJA-525` a capture/OCR step in `live.py`, `FINJA-526` a vision or chat model call, `FINJA-527` the diagnostics probe. Loop errors are reported at most once a minute.

With `ANALYTICS_ENABLED=true`, `ANALYTICS_ENDPOINT` and `ANALYTICS_TOKEN` in `.env`, the errors also go to the Analytics Collector, which hands repeated ones to Flare. Off by default: no thread, no network. On Windows only errors and start/stop are sent (CPU/RAM samples need Linux `/proc`).

Test the Flare path: `python probe.py` (three runs within 15 minutes give a repair card). Tests: `python -m pytest`.

## Support & Contact

- **Email:** contact@jappshome.de
- **Website:** [jappshome.de](https://jappshome.de)
- **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)

## License

Copyright (c) 2026 J. Apps
Licensed under the MIT License.

Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
