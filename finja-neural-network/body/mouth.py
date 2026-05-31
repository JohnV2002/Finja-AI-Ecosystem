"""
Body Mouth - Text to Speech (XTTS v2)
=====================================
Handles speech synthesis using voice cloning and playback on the system speaker.

Main Responsibilities:
- Lazy initialize the Coqui XTTS v2 engine.
- Clean text of formatting and emojis.
- Segment text into sentence chunks and synthesize wav audio.
- Play wav audio using pygame mixer with dynamic volume controls.

Side Effects:
- Accesses system audio output (speakers).
- Reads speaker voice references from best_refs/.
- Writes transient wav audio files to temp_audio/.
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
from typing import Optional
from unittest.mock import MagicMock

import numpy as np
import pygame
import soundfile as sf
import torch
import torchaudio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore, Style
from exceptions import YourAIUnexpectedError, YourAISystemError, YourAIConfigError
from body.audio_temp import remove_temp_audio

from config import (
    XTTS_MODEL_NAME, TTS_MASTER_VOICE_FILE, TTS_LANGUAGE,
    TTS_DEFAULT_VOLUME, TTS_VOLUME_CONFIG_FILE
)

# ==========================================
# SUPPRESS XTTS SPAM
# ==========================================
# XTTS/Coqui spams the console with hundreds of lines during load.
# We suppress everything except our own structured logs.

# Suppress logging spam from TTS, torch, etc.
logging.getLogger("TTS").setLevel(logging.ERROR)
logging.getLogger("TTS.utils").setLevel(logging.ERROR)
logging.getLogger("TTS.tts").setLevel(logging.ERROR)
logging.getLogger("TTS.vocoder").setLevel(logging.ERROR)
logging.getLogger("fairseq").setLevel(logging.ERROR)
logging.getLogger("numba").setLevel(logging.ERROR)
logging.getLogger("matplotlib").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

# Suppress FutureWarnings and UserWarnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# =====================================================================
# XTTS COMPATIBILITY PATCHES - CHANGE WITH EXTREME CARE
# =====================================================================
# This block is held together purely by black magic, raw force, and a
# fake entry we registered. If you refactor this code, downgrade it,
# or even look at it sideways, YourAI's voice dies and PyTorch starts crying.
# WE DID THIS. YOU HAVE BEEN WARNED.


# --- PYTORCH 2.6 FIX FOR XTTS ---
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    """
    Calls torch.load with weights_only disabled for XTTS checkpoint compatibility.

    Args:
        *args: Positional arguments forwarded to torch.load.
        **kwargs: Keyword arguments forwarded to torch.load.

    Returns:
        Any: The object loaded by the original torch.load implementation.
    """
    kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

# --- AUDIO BACKEND HACK FOR WINDOWS ---
# FAKE TORCHCODEC: The Coqui-Fork forces torchcodec in newer PyTorch versions.
# We trick it using MagicMock so it thinks it is installed and doesn't cry!
_mock_tc = MagicMock()
_mock_tc.__spec__ = MagicMock()
_mock_tc.__spec__.name = "torchcodec"
sys.modules['torchcodec'] = _mock_tc

# NEW HACK: We fake the entry in the registry office (importlib.metadata)
# Transformers checks which version is installed. We simply lie!
import importlib.metadata
_orig_version = importlib.metadata.version

def _patched_version(pkg_name):
    """
    Returns a fake torchcodec version while delegating all other package checks.

    Args:
        pkg_name: The package name passed by importlib.metadata.version.

    Returns:
        str: The package version string.
    """
    if pkg_name == "torchcodec":
        return "0.1.0"  # Fake version to keep Transformers happy
    return _orig_version(pkg_name)

importlib.metadata.version = _patched_version
# =========================================================================

def _patched_audio_load(filepath, *args, **kwargs):
    """
    Loads audio through soundfile and returns a torchaudio-compatible tensor.

    Args:
        filepath: Path to the audio file to load.
        *args: Unused compatibility arguments accepted by torchaudio.load callers.
        **kwargs: Unused compatibility keyword arguments accepted by torchaudio.load callers.

    Returns:
        tuple: A tuple containing the audio tensor and sample rate.
    """
    data, samplerate = sf.read(filepath, dtype='float32')  # type: ignore[misc]
    tensor = torch.from_numpy(data)
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)
    else:
        tensor = tensor.transpose(0, 1)
    return tensor, samplerate

class _MockInfo:
    """
    Minimal torchaudio info replacement for soundfile-backed audio metadata.
    """

    def __init__(self, sr, frames, channels):
        """
        Stores audio metadata in the shape expected by torchaudio callers.

        Args:
            sr: Sample rate.
            frames: Number of audio frames.
            channels: Number of audio channels.
        """
        self.sample_rate = sr
        self.num_frames = frames
        self.num_channels = channels

def _patched_audio_info(filepath, *args, **kwargs):
    """
    Reads audio metadata through soundfile and returns a torchaudio-like info object.

    Args:
        filepath: Path to the audio file to inspect.
        *args: Unused compatibility arguments accepted by torchaudio.info callers.
        **kwargs: Unused compatibility keyword arguments accepted by torchaudio.info callers.

    Returns:
        _MockInfo: Metadata object containing sample rate, frame count, and channel count.
    """
    info = sf.info(filepath)
    return _MockInfo(info.samplerate, info.frames, info.channels)

setattr(torchaudio, 'load', _patched_audio_load)
setattr(torchaudio, 'info', _patched_audio_info)

# --- TRANSFORMERS 5.x HACK FOR COQUI-TTS ---
# Transformers deleted some things and the LazyLoader crashes with GPT2.
# We catch the TRUE error, but with our metadata hack it should be gone!
try:
    import transformers
    import transformers.pytorch_utils
    
    # 1. Fix the old function for Apple/MPS
    # IMPORTANT: XTTS calls .any() after this. So we return the real torch function!
    if not hasattr(transformers.pytorch_utils, 'isin_mps_friendly'):
        transformers.pytorch_utils.isin_mps_friendly = torch.isin # pyright: ignore[reportAttributeAccessIssue]

    # 2. Bypass the "Lazy Import" crash of GPT2
    from transformers.models.gpt2.modeling_gpt2 import GPT2PreTrainedModel, GPT2LMHeadModel
    from transformers.models.gpt2.configuration_gpt2 import GPT2Config
    
    transformers.GPT2PreTrainedModel = GPT2PreTrainedModel
    transformers.GPT2LMHeadModel = GPT2LMHeadModel
    transformers.GPT2Config = GPT2Config
except Exception as e:
    err = YourAIUnexpectedError(cause=e, module="mouth_transformers_patch")
    log_exception("TTS", err)
# -------------------------------------------

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
    """
    Writes a compact TTS log entry to the terminal and optional dashboard.

    Args:
        msg (str): Message to log.
        level (str, optional): Log severity hint. Defaults to "info".

    Returns:
        None.
    """
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
    """
    Plays a WAV audio file on the system speaker.

    Args:
        file_path (str): Path to the WAV file.

    Returns:
        None.
    """
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
    """
    Loads the XTTS v2 engine on first call (lazy initialization) while suppressing console spam.

    Returns:
        TTS: The initialized Coqui TTS engine.
    """
    global _engine
    if _engine is None:
        _log("Loading XTTS v2 engine...")
        
        if DASHBOARD and _dashboard:
            _dashboard.node_start("tts_init", model="xtts_v2")
        
        start = time.time()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Suppress STDOUT/STDERR during loading (XTTS prints ~50 lines during model download/load)
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
            # Restore stdout no matter what happens.
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
    """
    Prepares raw text for TTS playback by stripping markdown, emojis, and repeated characters.

    Args:
        text (str): The raw input text.

    Returns:
        str: The cleaned, speech-friendly text.
    """
    text = re.sub(r'\*[^\*]*\*', '', text)           # *actions*
    text = re.sub(r'#+', '', text)                 # ### headers
    text = re.sub(r'(.)\1{2,}', r'\1\1', text)    # Hiiiii -> Hii
    text = re.sub(r'[^\w\s.,!?\'":\-]', '', text)  # Emojis etc.
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)               # Multi-spaces
    return text.strip()

# ==========================================
# SPEAK
# ==========================================

def _resolve_speaker_wav() -> Optional[str]:
    """
    Resolves the voice reference WAV path, checking for fallbacks if master file is missing.

    Returns:
        Optional[str]: Path to the resolved speaker WAV file, or None if not found.
    """
    speaker_wav_path = os.path.join(REF_DIR, TTS_MASTER_VOICE_FILE)

    # Fallback: First .wav in the directory
    if not os.path.exists(speaker_wav_path) and os.path.exists(REF_DIR):
        all_refs = [os.path.join(REF_DIR, f) for f in os.listdir(REF_DIR) if f.endswith(".wav")]
        if all_refs:
            speaker_wav_path = all_refs[0]

    if not os.path.exists(speaker_wav_path):
        _log("No voice reference found! (master_voice.wav)", "error")
        return None
    return speaker_wav_path


def _synthesize_and_play(chunk: str, speaker_wav_path: str, idx: int, total: int):
    """
    Synthesizes a single chunk of text to WAV and plays it on the speaker.

    Args:
        chunk (str): Text segment to speak.
        speaker_wav_path (str): Path to speaker voice reference.
        idx (int): Current chunk index (1-based).
        total (int): Total number of chunks.

    Returns:
        None.
    """
    temp_path = os.path.join(TEMP_AUDIO_DIR, f"gen_{uuid.uuid4().hex[:8]}.wav")

    # Compact output: only first 50 characters
    preview = chunk[:50] + "..." if len(chunk) > 50 else chunk
    _log(f"[{idx}/{total}] \"{preview}\"")

    try:
        engine = get_engine()
        
        chunk_start = time.time()
        
        # Suppress STDOUT during generation (XTTS prints output per chunk)
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
        _log(f"[{idx}/{total}] Generated in {chunk_ms}ms", "success")

        play_audio(temp_path)

    except Exception as e:
        err = YourAISystemError(message="TTS generation failed for text chunk", cause=e, module="mouth_speak_chunk")
        log_exception("TTS", err)
        if DASHBOARD and _dashboard:
            _dashboard.error("tts", err.short(), exception=err)
    finally:
        if os.path.exists(temp_path):
            remove_temp_audio(temp_path, "TTS")


def speak(text: str):
    """
    Speaks the provided text in YourAI's cloned voice.

    Splits the text into sentence chunks to optimize processing time and engine stability.

    Args:
        text (str): The text to speak.

    Returns:
        None.
    """
    if not text:
        return

    clean_text = clean_text_for_tts(text)
    if not clean_text:
        return

    speaker_wav_path = _resolve_speaker_wav()
    if not speaker_wav_path:
        return

    # Split into sentences
    chunks = [c.strip() for c in re.split(r'(?<=[.!?])\s+', clean_text) if c.strip()]
    if not chunks:
        return

    if DASHBOARD and _dashboard:
        _dashboard.node_start("tts_speak", input_data=f"{len(chunks)} chunks, {len(clean_text)} chars")

    total_start = time.time()

    for i, chunk in enumerate(chunks):
        _synthesize_and_play(chunk, speaker_wav_path, i + 1, len(chunks))

    total_ms = int((time.time() - total_start) * 1000)
    _log(f"Done! {len(chunks)} chunks in {total_ms}ms", "success")
    
    if DASHBOARD and _dashboard:
        _dashboard.node_end("tts_speak", duration_ms=total_ms)


# ==========================================
# INIT MESSAGE
# ==========================================
log("TTS", "Mouth module loaded (XTTS v2 - lazy init)", Fore.MAGENTA)


if __name__ == "__main__":
    speak(
        "Hello. Yes, exactly you, who is holding this book in your hands or reading it on the screen. "
        "This is completely 'out of context' for a moment, but it is incredibly important to me: "
        "I was in psychological treatment myself and have a deep fascination for human psychology. "
        "This book reaches deep into real psychological dynamics and real clinical pictures. "
        "I know very well what I am writing about here - but that doesn't mean it's light entertainment or a joke. "
        "Please take care of yourself. If you notice while reading that it gets too much for you, "
        "that it burdens you or that you recognize yourself too much in the toxic dynamics - put the book away. "
        "Your mental health is always more important than any fictional story. "
        "Please also make sure that this book stays away from children and adolescents. "
        "The previous warnings are not a mere formality, they are not marketing, and certainly not a challenge "
        "along the lines of: 'I'll read that with ease.' You don't have to prove to anyone how much darkness you can handle - "
        "not to yourself, not to others, and certainly not to me. Lies it, if you are ready for these abysses. "
        "But protect yourself if they get too deep."
    )
