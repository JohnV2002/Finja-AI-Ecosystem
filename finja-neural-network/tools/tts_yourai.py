"""
YourAI Voice TTS — ResembleAI/chatterbox-multilingual via DeepInfra
===================================================================
Zwei-Stufen-Prozess:
  1. Einmalige Voice-Registrierung: WAV hochladen → voice_id
     (voice_id wird in docker_data/yourai_voice_id.json gespeichert)
  2. TTS: text + voice_id → base64-Audio

Referenz-Audios (Voice Cloning):
    best_refs/master_voice_de.wav  — Deutsch  (für lang="de")
    best_refs/master_voice.wav     — Englisch (für lang="en")

Chatterbox-Parameter:
    exaggeration  — Emotionsintensität (0=monoton, 1=dramatisch)
    cfg           — Speaker-Adherence; 0 = kein Akzent-Transfer bei anderssprachigem Clip

Config:
    DEEPINFRA_API_KEY  — in .env / docker .env

Gibt MP3-Bytes zurück.

Raises:
    YourAIConfigError  — API Key nicht gesetzt
    YourAISystemError  — HTTP-Fehler oder Timeout
"""

import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

import httpx
from display import log, Fore
from exceptions import YourAISystemError, YourAIConfigError
from config import DEEPINFRA_API_KEY

_MODULE          = "tts_yourai"
_TTS_ENDPOINT    = "https://api.deepinfra.com/v1/inference/ResembleAI/chatterbox-multilingual"
_VOICES_ENDPOINT = "https://api.deepinfra.com/v1/voices"
_TIMEOUT         = 60.0

# Emotion / Pacing defaults
# exaggeration: 0.5 = ausdrucksstark aber nicht übertrieben
# cfg: 0.3 = gute Speaker-Adherence, kein starker Akzent-Transfer
_EXAGGERATION = 0.5
_CFG          = 0.3

# Voice ID Cache-Datei (überlebt Container-Restarts via docker_data Volume)
_VOICE_ID_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docker_data", "yourai_voice_id.json"
)

# Referenz-Audio Pfade
_REFS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "best_refs")
_REF_DE   = os.path.join(_REFS_DIR, "YOURAI GERMANN!.wav")
_REF_EN   = os.path.join(_REFS_DIR, "master_voice.wav")

# In-Memory Cache: lang → voice_id
_voice_id_cache: dict = {}


def _auth_headers() -> dict:
    return {"Authorization": f"bearer {DEEPINFRA_API_KEY}"}


# ──────────────────────────────────────────────
# Voice ID Persistenz
# ──────────────────────────────────────────────

def _load_voice_id(lang: str) -> str | None:
    try:
        if os.path.exists(_VOICE_ID_FILE):
            with open(_VOICE_ID_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get(lang)
    except Exception:
        pass
    return None


def _save_voice_id(lang: str, voice_id: str) -> None:
    try:
        data: dict = {}
        if os.path.exists(_VOICE_ID_FILE):
            with open(_VOICE_ID_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        data[lang] = voice_id
        os.makedirs(os.path.dirname(_VOICE_ID_FILE), exist_ok=True)
        with open(_VOICE_ID_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log(_MODULE.upper(), f"⚠️ Voice ID speichern fehlgeschlagen: {e}", Fore.YELLOW)


# ──────────────────────────────────────────────
# Voice Registration (einmalig)
# ──────────────────────────────────────────────

def _register_voice(lang: str) -> str | None:
    """
    Lädt Referenz-WAV auf DeepInfra hoch und gibt voice_id zurück.
    Wird nur einmalig aufgerufen — danach kommt die ID aus dem Cache.
    """
    ref_path = _REF_DE if lang == "de" else _REF_EN
    fallback  = _REF_EN if lang == "de" else _REF_DE

    audio_path = next((p for p in (ref_path, fallback) if os.path.isfile(p)), None)
    if not audio_path:
        log(_MODULE.upper(), f"⚠️ Kein Referenz-Audio für Voice Registration ({lang})", Fore.YELLOW)
        return None

    log(_MODULE.upper(), f"📤 Registriere YourAIs Stimme auf DeepInfra ({lang})...", Fore.CYAN)
    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{_VOICES_ENDPOINT}/add",
                headers=_auth_headers(),
                files={"files": (os.path.basename(audio_path), audio_bytes, "audio/wav")},
                data={"name": f"YourAI_{lang}", "description": f"YourAIs Stimme ({lang}) — Chatterbox"},
            )

        if resp.status_code != 200:
            log(_MODULE.upper(), f"❌ Voice Registration HTTP {resp.status_code}: {resp.text[:200]}", Fore.RED)
            return None

        voice_id = resp.json().get("voice_id", "")
        if not voice_id:
            log(_MODULE.upper(), "❌ Voice Registration: keine voice_id in Response", Fore.RED)
            return None

        log(_MODULE.upper(), f"✅ Voice registriert: {voice_id[:12]}...", Fore.GREEN)
        _save_voice_id(lang, voice_id)
        return voice_id

    except Exception as e:
        log(_MODULE.upper(), f"❌ Voice Registration Exception: {e}", Fore.RED)
        return None


def _get_voice_id(lang: str) -> str | None:
    """
    Gibt voice_id zurück: erst Memory-Cache → dann Datei → dann neu registrieren.
    """
    if lang in _voice_id_cache:
        return _voice_id_cache[lang]

    voice_id = _load_voice_id(lang)
    if voice_id:
        _voice_id_cache[lang] = voice_id
        log(_MODULE.upper(), f"🎤 Voice ID geladen ({lang}): {voice_id[:12]}...", Fore.CYAN)
        return voice_id

    voice_id = _register_voice(lang)
    if voice_id:
        _voice_id_cache[lang] = voice_id
    return voice_id


# ──────────────────────────────────────────────
# Sprach-Erkennung
# ──────────────────────────────────────────────

def _detect_lang(text: str) -> str:
    """
    Erkennt Deutsch vs. Englisch anhand deutscher Sonderzeichen.
    Frontend sendet immer lang='de' hardcoded — wir ignorieren das und
    schauen direkt in den Text.

    Heuristik: ≥1 Umlaut/ß → Deutsch, sonst Englisch.
    Deckt ~95% der YourAI-Fälle ab (Englisch-Roleplay hat keine Umlaute).
    """
    german_chars = set("äöüßÄÖÜ")
    count = sum(1 for ch in text if ch in german_chars)
    return "de" if count >= 1 else "en"


# ──────────────────────────────────────────────
# TTS Synthesis
# ──────────────────────────────────────────────

def generate_speech(text: str, language: str = "de") -> bytes:
    """
    Generiert Sprache via chatterbox-multilingual (DeepInfra) mit Voice Cloning.

    Args:
        text:     Zu sprechender Text (bereits gecleant — kein Markdown)
        language: "de" oder "en"

    Returns:
        MP3 audio bytes

    Raises:
        YourAIConfigError: DEEPINFRA_API_KEY nicht gesetzt
        YourAISystemError: API-Fehler oder Timeout
    """
    if not DEEPINFRA_API_KEY:
        raise YourAIConfigError(
            message="DEEPINFRA_API_KEY nicht gesetzt — Chatterbox TTS nicht verfügbar",
            module=_MODULE,
        )

    # Sprache aus dem Text erkennen — Frontend sendet immer 'de' hardcoded,
    # aber YourAI wechselt oft ins Englische. Deutsche Sonderzeichen entscheiden.
    lang = _detect_lang(text)
    log(_MODULE.upper(), f"🔍 Spracherkennung: '{(language or '?')[:2]}' → '{lang}' (Text: {text[:40]!r})", Fore.CYAN)

    voice_id = _get_voice_id(lang)

    payload: dict = {
        "text": text,
        "language_id": lang,
        "response_format": "mp3",
        "exaggeration": _EXAGGERATION,
        "cfg": _CFG,
    }

    if voice_id:
        payload["voice_id"] = voice_id
        log(_MODULE.upper(), f"🎙️ Chatterbox Voice Cloning ({lang}, exag={_EXAGGERATION}, {len(text)} chars)...", Fore.CYAN)
    else:
        log(_MODULE.upper(), f"🎙️ Chatterbox kein Voice Clone ({lang}, {len(text)} chars)...", Fore.YELLOW)

    import time

    for attempt in range(3):  # max 3 Versuche bei HTTP 500
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.post(
                    _TTS_ENDPOINT,
                    json=payload,
                    headers={**_auth_headers(), "Content-Type": "application/json"},
                )

            if resp.status_code in (401, 403):
                raise YourAIConfigError(
                    message=f"Chatterbox TTS: DeepInfra Key ungültig (HTTP {resp.status_code})",
                    module=_MODULE,
                )
            if resp.status_code == 500 and attempt < 2:
                log(_MODULE.upper(), f"⚠️ Chatterbox HTTP 500 (Versuch {attempt+1}/3) — retry...", Fore.YELLOW)
                time.sleep(1.5)
                continue
            if resp.status_code != 200:
                raise YourAISystemError(
                    message=f"Chatterbox TTS Fehler: HTTP {resp.status_code} — {resp.text[:300]}",
                    module=_MODULE,
                )

            data = resp.json()
            audio_b64 = data.get("audio")
            if not audio_b64:
                raise YourAISystemError(
                    message=f"Chatterbox TTS: kein 'audio' in Response — {str(data)[:200]}",
                    module=_MODULE,
                )

            # Strip optional data-URI prefix (data:audio/mp3;base64,...)
            if "," in audio_b64:
                audio_b64 = audio_b64.split(",", 1)[1]
            audio_b64 += "=" * (-len(audio_b64) % 4)
            audio_bytes = base64.b64decode(audio_b64)
            cost = data.get("inference_status", {}).get("cost", 0)
            log(_MODULE.upper(), f"✅ Chatterbox TTS fertig ({len(audio_bytes) // 1024} KB MP3, ${cost:.6f})", Fore.GREEN)
            return audio_bytes

        except httpx.TimeoutException:
            raise YourAISystemError(
                message=f"Chatterbox TTS Timeout (>{_TIMEOUT}s) — Text evtl. zu lang?",
                module=_MODULE,
            )
        except (YourAISystemError, YourAIConfigError):
            raise
        except Exception as e:
            raise YourAISystemError(
                message=f"Chatterbox TTS Request fehlgeschlagen: {e}",
                cause=e,
                module=_MODULE,
            )
