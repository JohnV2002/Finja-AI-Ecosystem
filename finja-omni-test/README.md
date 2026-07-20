# Finja Omni Test v1.0.0

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

## License

Copyright (c) 2026 J. Apps
Licensed under the MIT License.

Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
