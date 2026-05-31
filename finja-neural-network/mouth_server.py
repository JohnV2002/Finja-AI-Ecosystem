"""
YourAI TTS Server (mouth_server.py)
====================================
Runs on the Windows VM, exposing XTTS v2 as an HTTP microservice.
Called by the Docker container over the local network.

Start:  python mouth_server.py
        or: start_yourai_tts.bat

Endpoint: POST /tts   { "text": "...", "language": "de" | "en" }
          GET  /health

⚠️  STANDALONE — no Docker, no YourAI brain needed!
⚠️  Requires: pip install fastapi uvicorn coqui-tts torch soundfile
"""

import os
import sys
import re
import io
import uuid
import time
import logging
import warnings
from typing import Optional
from unittest.mock import MagicMock

# ─── Path Setup ─────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
REF_DIR       = os.path.join(BASE_DIR, "best_refs")
TEMP_AUDIO    = os.path.join(BASE_DIR, "body", "temp_audio")
XTTS_MODEL    = "tts_models/multilingual/multi-dataset/xtts_v2"
SERVER_PORT   = int(os.environ.get("YOURAI_TTS_PORT", "8052"))

VOICE_FILES = {
    "de": "master_voice_de.wav",
    "en": "master_voice.wav",
}
VOICE_FALLBACK = "master_voice.wav"

os.makedirs(TEMP_AUDIO, exist_ok=True)

# ─── Suppress spam ──────────────────────────────────────────────────
logging.getLogger("TTS").setLevel(logging.ERROR)
logging.getLogger("fairseq").setLevel(logging.ERROR)
logging.getLogger("numba").setLevel(logging.ERROR)
logging.getLogger("matplotlib").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# =====================================================================
# ⚠️ ☢️ GEMINI & JOHN JANK — DO NOT TOUCH! ☢️ ⚠️
# This block keeps XTTS v2 alive on modern PyTorch + Transformers.
# Refactoring = YourAI's voice dies. You have been warned.

import torch

# PyTorch 2.6 weights_only Fix
_orig_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _orig_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

# Fake torchcodec (Coqui expects it, we mock it away)
_mock_tc = MagicMock()
_mock_tc.__spec__ = MagicMock()
_mock_tc.__spec__.name = "torchcodec"
sys.modules['torchcodec'] = _mock_tc

# Registry office: fake version so Transformers is happy
import importlib.metadata
_orig_version = importlib.metadata.version
def _patched_version(pkg_name):
    if pkg_name == "torchcodec":
        return "0.1.0"
    return _orig_version(pkg_name)
importlib.metadata.version = _patched_version

import torchaudio
import soundfile as sf

def _patched_audio_load(filepath, *args, **kwargs):
    data, samplerate = sf.read(filepath, dtype='float32')
    tensor = torch.from_numpy(data)
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)
    else:
        tensor = tensor.transpose(0, 1)
    return tensor, samplerate

class _MockInfo:
    def __init__(self, sr, frames, channels):
        self.sample_rate = sr
        self.num_frames = frames
        self.num_channels = channels

def _patched_audio_info(filepath, *args, **kwargs):
    info = sf.info(filepath)
    return _MockInfo(info.samplerate, info.frames, info.channels)

setattr(torchaudio, 'load', _patched_audio_load)
setattr(torchaudio, 'info', _patched_audio_info)

try:
    import transformers
    import transformers.pytorch_utils
    if not hasattr(transformers.pytorch_utils, 'isin_mps_friendly'):
        transformers.pytorch_utils.isin_mps_friendly = torch.isin
    from transformers.models.gpt2.modeling_gpt2 import GPT2PreTrainedModel, GPT2LMHeadModel
    from transformers.models.gpt2.configuration_gpt2 import GPT2Config
    transformers.GPT2PreTrainedModel = GPT2PreTrainedModel
    transformers.GPT2LMHeadModel = GPT2LMHeadModel
    transformers.GPT2Config = GPT2Config
except Exception:
    # Optional GPT-2 shims; XTTS still works without them on most versions.
    pass
# =====================================================================

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import uvicorn

# ─── XTTS Engine (Lazy) ─────────────────────────────────────────────
_engine = None

def get_engine():
    """Lazily load and cache the XTTS v2 engine (first call may take ~30s)."""
    global _engine
    if _engine is None:
        print(f"[TTS] Loading XTTS v2... (first request — may take 30s)")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[TTS] Device: {device}")
        _real_stdout, _real_stderr = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            from TTS.api import TTS
            _engine = TTS(XTTS_MODEL).to(device)
        finally:
            sys.stdout = _real_stdout
            sys.stderr = _real_stderr
        print(f"[TTS] ✅ XTTS v2 ready! ({device})")
    return _engine


# ─── Text Cleaner ────────────────────────────────────────────────────
def clean_text(text: str) -> str:
    """Strip markdown/symbols for TTS, preserving German umlauts (äöüÄÖÜß)."""
    text = re.sub(r'\*.*?\*', '', text)
    text = re.sub(r'#+', '', text)
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)
    text = re.sub(r'[^\w\s.,!?\'":\-äöüÄÖÜß]', '', text)
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ─── Voice File Resolver ─────────────────────────────────────────────
def get_voice_file(language: str) -> str:
    """Resolve the reference voice WAV for a language, with fallbacks.

    Args:
        language (str): "de" or "en".

    Returns:
        str: Path to a voice reference WAV.

    Raises:
        FileNotFoundError: When no voice reference exists in REF_DIR.
    """
    filename = VOICE_FILES.get(language, VOICE_FALLBACK)
    path = os.path.join(REF_DIR, filename)
    if not os.path.exists(path):
        # Fall back to the first .wav in REF_DIR
        fallback = os.path.join(REF_DIR, VOICE_FALLBACK)
        if os.path.exists(fallback):
            return fallback
        wavs = [f for f in os.listdir(REF_DIR) if f.endswith(".wav")]
        if wavs:
            return os.path.join(REF_DIR, wavs[0])
        raise FileNotFoundError(f"No voice reference found in {REF_DIR}!")
    return path


# ─── FastAPI App ─────────────────────────────────────────────────────
app = FastAPI(title="YourAI TTS Server", version="1.0")

@app.on_event("startup")
def warmup():
    """
    Cold-start warmup: load XTTS and generate 'Hallo' once so the CUDA
    kernels are warm. The engine then stays permanently in RAM.
    """
    import threading
    def _warmup():
        print("[TTS] 🔥 Cold start: loading XTTS engine...")
        try:
            engine = get_engine()
            print("[TTS] 🔥 Engine loaded — generating warmup audio...")
            voice_path = get_voice_file("de")
            temp_path = os.path.join(TEMP_AUDIO, f"warmup_{uuid.uuid4().hex[:6]}.wav")
            _rs, _re = sys.stdout, sys.stderr
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
            try:
                engine.tts_to_file(
                    text="Hallo",
                    speaker_wav=voice_path,
                    language="de",
                    file_path=temp_path
                )
            finally:
                sys.stdout = _rs
                sys.stderr = _re
            if os.path.exists(temp_path):
                os.remove(temp_path)
            print("[TTS] ✅ Warmup done — engine is hot and ready! 🚀")
        except Exception as e:
            print(f"[TTS] ⚠️ Warmup failed: {e}")
    threading.Thread(target=_warmup, daemon=True).start()


class TTSRequest(BaseModel):
    text: str
    language: str = "de"


@app.get("/health")
def health():
    """Health check: report engine load state and compute device."""
    engine_ready = _engine is not None
    return {
        "status": "ok",
        "engine": "loaded" if engine_ready else "not_loaded_yet",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "ref_dir": REF_DIR,
    }


@app.post("/tts")
def tts(req: TTSRequest):
    """Synthesize speech for the request text and return WAV audio bytes."""
    text = clean_text(req.text)
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty after cleaning")

    lang = req.language.lower().strip()
    if lang not in ("de", "en"):
        lang = "de"

    try:
        voice_path = get_voice_file(lang)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Split into sentences (short chunks = better quality)
    chunks = [c.strip() for c in re.split(r'(?<=[.!?])\s+', text) if c.strip()]
    if not chunks:
        chunks = [text]

    engine = get_engine()
    all_audio = []

    for i, chunk in enumerate(chunks):
        temp_path = os.path.join(TEMP_AUDIO, f"srv_{uuid.uuid4().hex[:8]}.wav")
        preview = chunk[:60] + "..." if len(chunk) > 60 else chunk
        print(f"[TTS] [{i+1}/{len(chunks)}] {preview}")
        t0 = time.time()

        _rs, _re = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            engine.tts_to_file(
                text=chunk,
                speaker_wav=voice_path,
                language=lang,
                file_path=temp_path
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"XTTS error: {e}")
        finally:
            sys.stdout = _rs
            sys.stderr = _re

        ms = int((time.time() - t0) * 1000)
        print(f"[TTS] [{i+1}/{len(chunks)}] ✅ {ms}ms")

        # Read WAV bytes
        try:
            with open(temp_path, "rb") as f:
                all_audio.append(f.read())
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    if not all_audio:
        raise HTTPException(status_code=500, detail="No audio generated")

    # Merge chunks: WAV header only once, then all PCM data
    if len(all_audio) == 1:
        audio_bytes = all_audio[0]
    else:
        import wave
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as out:
            # Take parameters from the first chunk
            with wave.open(io.BytesIO(all_audio[0])) as first:
                out.setparams(first.getparams())
            for chunk_bytes in all_audio:
                with wave.open(io.BytesIO(chunk_bytes)) as w:
                    out.writeframes(w.readframes(w.getnframes()))
        audio_bytes = buf.getvalue()

    print(f"[TTS] ✅ Total: {len(chunks)} chunks, {len(audio_bytes)//1024}KB WAV")
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


# ─── Start ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🦊 YourAI TTS Server starting on port {SERVER_PORT}...")
    print(f"   REF_DIR:  {REF_DIR}")
    print(f"   TEMP_DIR: {TEMP_AUDIO}")
    print(f"   Device:   {'CUDA 🚀' if torch.cuda.is_available() else 'CPU (slow!)'}")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
