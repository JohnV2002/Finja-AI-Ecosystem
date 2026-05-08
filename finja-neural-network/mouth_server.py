"""
YourAI TTS Server (mouth_server.py)
====================================
Läuft auf der Windows VM, stellt XTTS v2 als HTTP Microservice bereit.
Wird vom Docker Container über das lokale Netzwerk aufgerufen.

Start:  python mouth_server.py
        oder: start_yourai_tts.bat

Endpoint: POST /tts   { "text": "...", "language": "de" | "en" }
          GET  /health

⚠️  STANDALONE — kein Docker, kein YourAI-Brain nötig!
⚠️  Braucht: pip install fastapi uvicorn coqui-tts torch soundfile
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

# ─── Spam unterdrücken ──────────────────────────────────────────────
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
# Dieser Block hält XTTS v2 auf modernem PyTorch + Transformers am Leben.
# Refactorn = YourAIs Stimme stirbt. Du wurdest gewarnt.

import torch

# PyTorch 2.6 weights_only Fix
_orig_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _orig_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

# Fake torchcodec (Coqui erwartet es, wir mocken es weg)
_mock_tc = MagicMock()
_mock_tc.__spec__ = MagicMock()
_mock_tc.__spec__.name = "torchcodec"
sys.modules['torchcodec'] = _mock_tc

# Einwohnermeldeamt: Fake-Version damit Transformers glücklich ist
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
    global _engine
    if _engine is None:
        print(f"[TTS] Loading XTTS v2... (first request — kann 30s dauern)")
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
    text = re.sub(r'\*.*?\*', '', text)
    text = re.sub(r'#+', '', text)
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)
    text = re.sub(r'[^\w\s.,!?\'":\-äöüÄÖÜß]', '', text)
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ─── Voice File Resolver ─────────────────────────────────────────────
def get_voice_file(language: str) -> str:
    filename = VOICE_FILES.get(language, VOICE_FALLBACK)
    path = os.path.join(REF_DIR, filename)
    if not os.path.exists(path):
        # Fallback auf erste .wav im REF_DIR
        fallback = os.path.join(REF_DIR, VOICE_FALLBACK)
        if os.path.exists(fallback):
            return fallback
        wavs = [f for f in os.listdir(REF_DIR) if f.endswith(".wav")]
        if wavs:
            return os.path.join(REF_DIR, wavs[0])
        raise FileNotFoundError(f"Keine Voice-Referenz in {REF_DIR} gefunden!")
    return path


# ─── FastAPI App ─────────────────────────────────────────────────────
app = FastAPI(title="YourAI TTS Server", version="1.0")

@app.on_event("startup")
def warmup():
    """
    Cold-Start Warmup: Lädt XTTS + generiert einmal 'Hallo' damit
    CUDA-Kernels aufgewärmt sind. Engine bleibt danach permanent im RAM.
    """
    import threading
    def _warmup():
        print("[TTS] 🔥 Cold-Start: Lade XTTS Engine...")
        try:
            engine = get_engine()
            print("[TTS] 🔥 Engine geladen — generiere Warmup-Audio...")
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
            print("[TTS] ✅ Warmup fertig — Engine ist heiß und bereit! 🚀")
        except Exception as e:
            print(f"[TTS] ⚠️ Warmup fehlgeschlagen: {e}")
    threading.Thread(target=_warmup, daemon=True).start()


class TTSRequest(BaseModel):
    text: str
    language: str = "de"


@app.get("/health")
def health():
    engine_ready = _engine is not None
    return {
        "status": "ok",
        "engine": "loaded" if engine_ready else "not_loaded_yet",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "ref_dir": REF_DIR,
    }


@app.post("/tts")
def tts(req: TTSRequest):
    text = clean_text(req.text)
    if not text:
        raise HTTPException(status_code=400, detail="Text ist leer nach Bereinigung")

    lang = req.language.lower().strip()
    if lang not in ("de", "en"):
        lang = "de"

    try:
        voice_path = get_voice_file(lang)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # In Sätze aufteilen (kurze Chunks = bessere Qualität)
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
            raise HTTPException(status_code=500, detail=f"XTTS Fehler: {e}")
        finally:
            sys.stdout = _rs
            sys.stderr = _re

        ms = int((time.time() - t0) * 1000)
        print(f"[TTS] [{i+1}/{len(chunks)}] ✅ {ms}ms")

        # WAV bytes lesen
        try:
            with open(temp_path, "rb") as f:
                all_audio.append(f.read())
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    if not all_audio:
        raise HTTPException(status_code=500, detail="Kein Audio generiert")

    # Chunks zusammenführen: WAV-Header nur einmal, dann alle PCM-Daten
    if len(all_audio) == 1:
        audio_bytes = all_audio[0]
    else:
        import wave
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as out:
            # Parameter aus erstem Chunk übernehmen
            with wave.open(io.BytesIO(all_audio[0])) as first:
                out.setparams(first.getparams())
            for chunk_bytes in all_audio:
                with wave.open(io.BytesIO(chunk_bytes)) as w:
                    out.writeframes(w.readframes(w.getnframes()))
        audio_bytes = buf.getvalue()

    print(f"[TTS] ✅ Gesamt: {len(chunks)} Chunks, {len(audio_bytes)//1024}KB WAV")
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


# ─── Start ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🦊 YourAI TTS Server startet auf Port {SERVER_PORT}...")
    print(f"   REF_DIR:  {REF_DIR}")
    print(f"   TEMP_DIR: {TEMP_AUDIO}")
    print(f"   Device:   {'CUDA 🚀' if torch.cuda.is_available() else 'CPU (langsam!)'}")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
