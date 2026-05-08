"""
ElevenLabs TTS — Tier 3 Premium Web Voice
==========================================
Generates audio bytes (MP3) using ElevenLabs API with YourAI's cloned voice.
Called by dashboard_server.py /api/tts endpoint.

Usage:
    from tools.tts_elevenlabs import generate_speech
    audio_bytes = generate_speech("Hallo ich bin YourAI", lang="de")
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAISystemError, YourAIConfigError

from config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID_DE,
    ELEVENLABS_VOICE_ID_EN,
    ELEVENLABS_MODEL,
)

import httpx


def generate_speech(text: str, lang: str = "de") -> bytes:
    """
    Generates speech audio bytes (MP3) via ElevenLabs API.

    Args:
        text: Text to speak (already cleaned — no markdown)
        lang: "de" or "en"

    Returns:
        Raw MP3 bytes

    Raises:
        YourAIConfigError: if API key or voice ID missing
        YourAISystemError: on API error
    """
    if not ELEVENLABS_API_KEY:
        raise YourAIConfigError(
            message="ELEVENLABS_API_KEY nicht gesetzt",
            module="tts_elevenlabs"
        )

    # Voice ID: EN hat Fallback auf DE solange EN nicht hochgeladen
    if lang == "en" and ELEVENLABS_VOICE_ID_EN:
        voice_id = ELEVENLABS_VOICE_ID_EN
    else:
        voice_id = ELEVENLABS_VOICE_ID_DE

    if not voice_id:
        raise YourAIConfigError(
            message=f"ELEVENLABS_VOICE_ID_{lang.upper()} nicht gesetzt",
            module="tts_elevenlabs"
        )

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.80,
            "style": 0.10,
            "use_speaker_boost": True,
        },
    }

    try:
        log("TTS-EL", f"Generating speech ({lang}, {len(text)} chars)...", Fore.CYAN)
        resp = httpx.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        log("TTS-EL", f"Done ({len(resp.content)} bytes)", Fore.GREEN)
        return resp.content
    except httpx.HTTPStatusError as e:
        raise YourAISystemError(
            message=f"ElevenLabs API Error {e.response.status_code}: {e.response.text[:200]}",
            cause=e,
            module="tts_elevenlabs"
        )
    except Exception as e:
        raise YourAISystemError(
            message="ElevenLabs request failed",
            cause=e,
            module="tts_elevenlabs"
        )
