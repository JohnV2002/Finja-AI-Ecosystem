"""
YourAI AI - Mouth Module (XTTS v2)
===================================
YourAIs Stimme! Text-to-Speech mit Voice Cloning.

Benötigt: pip install coqui-tts (NOT pip install TTS!)
Python: 3.10 - 3.14 (coqui-tts Fork)

Usage:
    import mouth
    mouth.speak("Hello Creator!")
"""

import os
import sys
import time
import uuid
import re
import json
import logging
import warnings
import io
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore, Style
from exceptions import YourAIUnexpectedError, YourAISystemError, YourAIConfigError

from config import (
    XTTS_MODEL_NAME, TTS_MASTER_VOICE_FILE, TTS_LANGUAGE,
    TTS_DEFAULT_VOLUME, TTS_VOLUME_CONFIG_FILE
)

# ==========================================
# 🔇 XTTS SPAM UNTERDRÜCKEN
# ==========================================
# XTTS/Coqui spammt die Console mit hunderten Zeilen beim Laden.
# Wir unterdrücken alles außer unsere eigenen Prints.

# Logging-Spam von TTS, torch, etc. unterdrücken
logging.getLogger("TTS").setLevel(logging.ERROR)
logging.getLogger("TTS.utils").setLevel(logging.ERROR)
logging.getLogger("TTS.tts").setLevel(logging.ERROR)
logging.getLogger("TTS.vocoder").setLevel(logging.ERROR)
logging.getLogger("fairseq").setLevel(logging.ERROR)
logging.getLogger("numba").setLevel(logging.ERROR)
logging.getLogger("matplotlib").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

# FutureWarnings und UserWarnings unterdrücken
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import pygame
import torch

# =====================================================================
# ⚠️ ☢️ GEMINI & JOHN JANK - DO NOT TOUCH! ☢️ ⚠️
# =====================================================================
# Dieser Block wird ausschließlich zusammengehalten durch schwarze Magie,
# rohe Gewalt und ein von uns manipuliertes Einwohnermeldeamt.
# Wenn du diesen Code refactorst, downgradest oder auch nur schief 
# anschaust, stirbt YourAIs Stimme und PyTorch fängt an zu weinen. 
# WIR WAREN DAS. DU WURDEST GEWARNT.


# --- PYTORCH 2.6 FIX FÜR XTTS ---
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

# --- AUDIO BACKEND HACK FÜR WINDOWS ---
# FAKE TORCHCODEC: Der Coqui-Fork erzwingt torchcodec bei neuen PyTorch Versionen.
# Wir gaukeln ihm mit MagicMock einfach vor, es wäre installiert, damit er nicht weint!
_mock_tc = MagicMock()
_mock_tc.__spec__ = MagicMock()
_mock_tc.__spec__.name = "torchcodec"
sys.modules['torchcodec'] = _mock_tc

# NEUER HACK: Wir fälschen den Eintrag beim Einwohnermeldeamt (importlib.metadata)
# Transformers checkt, welche Version installiert ist. Wir lügen einfach!
import importlib.metadata
_orig_version = importlib.metadata.version

def _patched_version(pkg_name):
    if pkg_name == "torchcodec":
        return "0.1.0"  # Fake-Version, damit Transformers glücklich ist
    return _orig_version(pkg_name)

importlib.metadata.version = _patched_version
# =========================================================================

import torchaudio
import soundfile as sf

def _patched_audio_load(filepath, *args, **kwargs):
    data, samplerate = sf.read(filepath, dtype='float32')  # type: ignore[misc]
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

# --- TRANSFORMERS 5.x HACK FÜR COQUI-TTS ---
# Transformers hat ein paar Dinge gelöscht und der LazyLoader crasht bei GPT2.
# Wir fangen den WAHREN Fehler ab, aber mit unserem Einwohnermeldeamt-Hack sollte er weg sein!
try:
    import transformers
    import transformers.pytorch_utils
    
    # 1. Die alte Funktion für Apple/MPS fixen
    # WICHTIG: XTTS ruft danach .any() auf. Wir geben ihm also die echte torch Funktion!
    if not hasattr(transformers.pytorch_utils, 'isin_mps_friendly'):
        transformers.pytorch_utils.isin_mps_friendly = torch.isin # pyright: ignore[reportAttributeAccessIssue]

    # 2. Den "Lazy Import" Crash von GPT2 umgehen
    from transformers.models.gpt2.modeling_gpt2 import GPT2PreTrainedModel, GPT2LMHeadModel
    from transformers.models.gpt2.configuration_gpt2 import GPT2Config
    
    transformers.GPT2PreTrainedModel = GPT2PreTrainedModel
    transformers.GPT2LMHeadModel = GPT2LMHeadModel
    transformers.GPT2Config = GPT2Config
except Exception as e:
    print("\n" + "="*60)
    print("🚨🚨🚨 ACHTUNG: DER WAHRE TRANSFORMERS FEHLER 🚨🚨🚨")
    import traceback
    traceback.print_exc()
    print("="*60 + "\n")
# -------------------------------------------

import numpy as np
from typing import Optional

# ==========================================
# SETUP
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_AUDIO_DIR = os.path.join(BASE_DIR, "temp_audio")
REF_DIR = os.path.join(BASE_DIR, "best_refs")

os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

# Dashboard Client (optional)
try:
    from dashboard_client import debug as _dashboard
    DASHBOARD = True
except ImportError:
    DASHBOARD = False
    _dashboard = None

def _log(msg: str, level: str = "info"):
    """Kompaktes Logging — Terminal (bunt) + Dashboard Event."""
    if level == "error":
        log("TTS", msg, Fore.RED)
    elif level == "success":
        log("TTS", msg, Fore.GREEN)
    else:
        log("TTS", msg, Fore.CYAN)
        
    if DASHBOARD and _dashboard:
        if level == "error":
            _dashboard.error("tts", msg)
        else:
            _dashboard.info("tts", msg)

# ==========================================
# AUDIO PLAYBACK
# ==========================================
pygame.mixer.init()

def play_audio(file_path: str):
    """Spielt eine WAV-Datei ab mit Volume aus tts_volume.json."""
    try:
        vol = TTS_DEFAULT_VOLUME
        if os.path.exists(TTS_VOLUME_CONFIG_FILE):
            with open(TTS_VOLUME_CONFIG_FILE, "r") as f:
                vol = json.load(f).get("volume", TTS_DEFAULT_VOLUME)

        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

        pygame.mixer.music.load(file_path)
        pygame.mixer.music.set_volume(vol)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        if isinstance(e, json.JSONDecodeError):
            err = YourAIConfigError(message="Volume config parse failed", cause=e, module="mouth_play_audio")
        elif isinstance(e, pygame.error):
            err = YourAISystemError(message="Audio playback failed (pygame)", cause=e, module="mouth_play_audio")
        else:
            err = YourAIUnexpectedError(cause=e, module="mouth_play_audio")
        log_exception("TTS", err)
        if DASHBOARD and _dashboard:
            _dashboard.error("tts", err.short(), exception=err)

# ==========================================
# XTTS ENGINE (Lazy Loading)
# ==========================================
_engine = None

def get_engine():
    """Lädt XTTS Engine beim ersten Aufruf (lazy). Unterdrückt Spam."""
    global _engine
    if _engine is None:
        _log("Loading XTTS v2 engine...")
        
        if DASHBOARD and _dashboard:
            _dashboard.node_start("tts_init", model="xtts_v2")
        
        start = time.time()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # STDOUT/STDERR während dem Laden unterdrücken
        # XTTS printet ~50 Zeilen beim Model-Download/Load
        _real_stdout = sys.stdout
        _real_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        try:
            from TTS.api import TTS
            _engine = TTS(XTTS_MODEL_NAME).to(device)
        except Exception as e:
            err = YourAISystemError(message="XTTS Engine crash (Missing Model / Out of Memory)", cause=e, module="mouth_engine_init")
            log_exception("TTS", err)
            if DASHBOARD and _dashboard:
                _dashboard.error("tts", err.short(), exception=err)
            raise
        finally:
            # Stdout wiederherstellen — egal was passiert
            sys.stdout = _real_stdout
            sys.stderr = _real_stderr
        
        duration = int((time.time() - start) * 1000)
        _log(f"XTTS ready! ({device}, {duration}ms)", "success")
        
        if DASHBOARD and _dashboard:
            _dashboard.node_end("tts_init", duration_ms=duration)
    
    return _engine

# ==========================================
# TEXT CLEANING
# ==========================================

def clean_text_for_tts(text: str) -> str:
    """Bereitet Text für TTS vor — entfernt Markdown, Emojis, Spam."""
    text = re.sub(r'\*.*?\*', '', text)           # *actions*
    text = re.sub(r'#+', '', text)                 # ### headers
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)    # Hiiiii -> Hii
    text = re.sub(r'[^\w\s.,!?\'":\-äöüÄÖÜß]', '', text)  # Emojis etc.
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)               # Multi-spaces
    return text.strip()

# ==========================================
# SPEAK
# ==========================================

def speak(text: str):
    """Spricht Text als YourAI. Chunked bei Satzgrenzen."""
    if not text:
        return

    clean_text = clean_text_for_tts(text)
    if not clean_text:
        return

    # Master Voice Reference
    speaker_wav_path = os.path.join(REF_DIR, TTS_MASTER_VOICE_FILE)

    # Fallback: Erste .wav im Ordner
    if not os.path.exists(speaker_wav_path) and os.path.exists(REF_DIR):
        all_refs = [os.path.join(REF_DIR, f) for f in os.listdir(REF_DIR) if f.endswith(".wav")]
        if all_refs:
            speaker_wav_path = all_refs[0]

    if not os.path.exists(speaker_wav_path):
        _log("No voice reference found! (master_voice.wav)", "error")
        return

    # In Sätze aufteilen
    chunks = [c.strip() for c in re.split(r'(?<=[.!?])\s+', clean_text) if c.strip()]

    if DASHBOARD and _dashboard:
        _dashboard.node_start("tts_speak", input_data=f"{len(chunks)} chunks, {len(clean_text)} chars")

    total_start = time.time()

    for i, chunk in enumerate(chunks):
        temp_path = os.path.join(TEMP_AUDIO_DIR, f"gen_{uuid.uuid4().hex[:8]}.wav")

        # Kompakte Ausgabe: nur erste 50 Zeichen
        preview = chunk[:50] + "..." if len(chunk) > 50 else chunk
        _log(f"[{i+1}/{len(chunks)}] \"{preview}\"")

        try:
            engine = get_engine()
            
            chunk_start = time.time()
            
            # STDOUT während Generation unterdrücken (XTTS printet pro Chunk)
            _real_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                engine.tts_to_file(
                    text=chunk, 
                    speaker_wav=speaker_wav_path, 
                    language=TTS_LANGUAGE,
                    file_path=temp_path
                )
            finally:
                sys.stdout = _real_stdout
            
            chunk_ms = int((time.time() - chunk_start) * 1000)
            _log(f"[{i+1}/{len(chunks)}] Generated in {chunk_ms}ms", "success")

            play_audio(temp_path)

        except Exception as e:
            err = YourAISystemError(message="TTS generation failed for text chunk", cause=e, module="mouth_speak_chunk")
            log_exception("TTS", err)
            if DASHBOARD and _dashboard:
                _dashboard.error("tts", err.short(), exception=err)
        finally:
           if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as clean_err:
                    _log(f"Warning: Cleanup failed {temp_path} ({clean_err})", "error")

    total_ms = int((time.time() - total_start) * 1000)
    _log(f"Done! {len(chunks)} chunks in {total_ms}ms", "success")
    
    if DASHBOARD and _dashboard:
        _dashboard.node_end("tts_speak", duration_ms=total_ms)


# ==========================================
# INIT MESSAGE
# ==========================================
log("TTS", "Mouth module loaded (XTTS v2 — lazy init)", Fore.MAGENTA)


if __name__ == "__main__":
    speak("Hallo. Ja, genau du, der dieses Buch gerade in den Händen hält oder auf dem Bildschirm liest. Das hier ist für einen Moment komplett „out of context“, aber es ist mir unglaublich wichtig: Ich war selbst in psychologischer Behandlung und habe eine tiefe Faszination für die menschliche Psychologie. Dieses Buch greift tief in reale psychologische Dynamiken und echte Krankheitsbilder ein. Ich weiß sehr genau, worüber ich hier schreibe – aber das bedeutet nicht, dass es leichte Unterhaltung oder ein Spaß ist. Bitte pass auf dich auf. Wenn du beim Lesen merkst, dass es dir zu viel wird, dass es dich belastet oder du dich in den toxischen Dynamiken zu sehr wiedererkennst – leg das Buch weg. Deine mentale Gesundheit ist immer wichtiger als jede fiktive Geschichte. Bitte sorge auch dafür, dass dieses Buch fern von Kindern und Jugendlichen bleibt. Die vorangegangenen Warnungen sind keine bloße Formalität, sie sind kein Marketing und erst recht keine Challenge nach dem Motto: ‚Das lese ich doch mit Links.' Du musst absolut niemandem beweisen, wie viel Dunkelheit du aushältst – weder dir selbst, noch anderen, und schon gar nicht mir. Lies es, wenn du bereit für diese Abgründe bist. Aber schütze dich selbst, wenn sie zu tief werden.")