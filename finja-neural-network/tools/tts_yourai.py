"""
YourAI Voice TTS — Resemble AI (Chatterbox) direct API
======================================================
Synchronous text-to-speech via Resemble AI's own infrastructure.
Noticeably more stable than DeepInfra (no flaky 500s / timeouts).

Voice:  YourAI_EN (uuid: 456c688d) — cloned voice, multilingual
API:    POST https://f.cluster.resemble.ai/synthesize
Limit:  2000 characters per request (vs. 150-350 on DeepInfra)
Price:  $0.0005 per second of generated audio

Config:
    RESEMBLE_API_KEY  — in .env / docker .env
    DEEPINFRA_API_KEY — fallback when Resemble is unavailable

Returns WAV bytes.

Raises:
    YourAIConfigError  — API key not set
    YourAISystemError  — HTTP error or timeout
"""

import base64
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

import httpx
from display import log, Fore
from exceptions import YourAISystemError, YourAIConfigError
from config import DEEPINFRA_API_KEY, MEMORY_API_BASE, MEMORY_API_KEY

# Resemble AI Key (try env first, then config)
RESEMBLE_API_KEY = os.environ.get("RESEMBLE_API_KEY", "")

_MODULE = "tts_yourai"

# ──────────────────────────────────────────────
# Resemble AI Config
# ──────────────────────────────────────────────
_RESEMBLE_ENDPOINT = "https://f.cluster.resemble.ai/synthesize"
_RESEMBLE_VOICE_UUID = "456c688d"  # YourAI_EN — multilingual, also works for DE
_RESEMBLE_TIMEOUT = 60.0

# DeepInfra Fallback Config
_DEEPINFRA_ENDPOINT = "https://api.deepinfra.com/v1/inference/ResembleAI/chatterbox-multilingual"
_DEEPINFRA_TIMEOUT = 90.0

# Resemble AI: 2000 characters per request — almost all YourAI replies fit in 1 call
_MAX_CHUNK_CHARS = 1800


def _clean_for_tts(text: str) -> str:
    """Remove TTS-unfriendly material: emojis, *roleplay actions*, leftover markdown."""
    text = re.sub(r'\*[^*\n]+\*', '', text)
    # Discord custom emojis: :EmojiName: (description) or :EmojiName:
    text = re.sub(r':\w+:\s*\([^)]*\)', '', text)
    text = re.sub(r':\w+:', '', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) not in ('So', 'Cs', 'Co'))
    text = text.replace('…', '...')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text)
    return text.strip()


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Last-resort fallback: forced word-boundary split into <= max_chars pieces."""
    parts: list[str] = []
    words = text.split()
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                parts.append(current)
                current = ""
            for i in range(0, len(word), max_chars):
                parts.append(word[i:i + max_chars])
        elif current and len(current) + 1 + len(word) > max_chars:
            parts.append(current)
            current = word
        else:
            current = (current + " " + word).strip() if current else word
    if current:
        parts.append(current)
    return parts


def _split_chunks(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    """Split text at sentence boundaries into chunks of <= max_chars."""
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r'(?<=[.!?\n])\s*', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for part in re.split(r'(?<=[,;])\s+', sentence):
                if len(part) > max_chars:
                    if current:
                        chunks.append(current)
                        current = ""
                    chunks.extend(_hard_split(part, max_chars))
                elif current and len(current) + len(part) + 1 > max_chars:
                    chunks.append(current)
                    current = part
                else:
                    current = (current + " " + part).strip() if current else part
        elif current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = (current + " " + sentence).strip() if current else sentence

    if current:
        chunks.append(current)
    return chunks


def _detect_lang(text: str) -> str:
    """Detect DE vs EN by umlauts. >=1 umlaut/ß -> German, else English."""
    german_chars = set("äöüßÄÖÜ")
    count = sum(1 for ch in text if ch in german_chars)
    return "de" if count >= 1 else "en"


# ──────────────────────────────────────────────
# Resemble AI TTS (Primary)
# ──────────────────────────────────────────────

def _call_resemble(text: str) -> bytes:
    """Resemble AI sync API: text -> base64 WAV -> bytes."""
    payload = {
        "voice_uuid": _RESEMBLE_VOICE_UUID,
        "data": text,
        "output_format": "wav",
        "sample_rate": 24000,
        "precision": "PCM_16",
    }

    for attempt in range(3):
        try:
            with httpx.Client(timeout=_RESEMBLE_TIMEOUT) as client:
                resp = client.post(
                    _RESEMBLE_ENDPOINT,
                    json=payload,
                    headers={
                        "Authorization": RESEMBLE_API_KEY,
                        "Content-Type": "application/json",
                    },
                )

            if resp.status_code in (401, 403):
                raise YourAIConfigError(
                    message=f"Resemble AI: invalid key (HTTP {resp.status_code})",
                    module=_MODULE,
                )

            if resp.status_code in (500, 502, 503, 429) and attempt < 2:
                delay = [2, 5][min(attempt, 1)]
                log(_MODULE.upper(), f"⚠️ Resemble HTTP {resp.status_code} (attempt {attempt+1}/3) — retry in {delay}s...", Fore.YELLOW)
                time.sleep(delay)
                continue

            if resp.status_code != 200:
                raise YourAISystemError(
                    message=f"Resemble TTS error: HTTP {resp.status_code} — {resp.text[:300]}",
                    module=_MODULE,
                )

            data = resp.json()
            if not data.get("success"):
                issues = data.get("issues", [])
                raise YourAISystemError(
                    message=f"Resemble TTS: success=false — {issues}",
                    module=_MODULE,
                )

            audio_b64 = data.get("audio_content", "")
            if not audio_b64:
                raise YourAISystemError(
                    message="Resemble TTS: no audio_content in response",
                    module=_MODULE,
                )

            audio_bytes = base64.b64decode(audio_b64)
            duration = data.get("duration", 0)
            cost = duration * 0.0005  # $0.0005/sec
            log(_MODULE.upper(), f"✅ Resemble done ({len(audio_bytes) // 1024} KB, {duration:.1f}s, ~${cost:.4f})", Fore.GREEN)
            try:
                import dashboard_analytics
                dashboard_analytics.record_event({
                    "event_type": "system_info",
                    "metric_name": "tts_generation",
                    "node_name": "tts_resemble",
                    "model": "resemble/yourai_voice",
                    "source": "resemble",
                    "duration_ms": int(float(duration or 0) * 1000),
                    "audio_duration_sec": float(duration or 0),
                    "content_chars": len(text or ""),
                    "estimated_cost_usd": round(float(cost or 0), 8),
                    "cost_source": "static_resemble_seconds",
                    "result_count": 1,
                    "status": "success",
                })
            except Exception:
                # Analytics is best-effort telemetry; never let it break TTS.
                pass
            return audio_bytes

        except httpx.TimeoutException:
            if attempt < 2:
                log(_MODULE.upper(), f"⚠️ Resemble timeout (attempt {attempt+1}/3) — retry...", Fore.YELLOW)
                time.sleep(3)
                continue
            raise YourAISystemError(
                message=f"Resemble TTS timeout (>{_RESEMBLE_TIMEOUT}s) — text: {text[:60]!r}",
                module=_MODULE,
            )
        except (YourAISystemError, YourAIConfigError):
            raise
        except Exception as e:
            raise YourAISystemError(
                message=f"Resemble TTS request failed: {e}",
                cause=e,
                module=_MODULE,
            )

    raise YourAISystemError(message="Resemble TTS: 3 attempts failed", module=_MODULE)


# ──────────────────────────────────────────────
# DeepInfra Fallback
# ──────────────────────────────────────────────

# Voice ID cache for DeepInfra (fallback)
_VOICE_ID_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docker_data", "yourai_voice_id.json"
)
_REFS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "best_refs")
_REF_DE = os.path.join(_REFS_DIR, "YOURAI GERMANN!.wav")
_REF_EN = os.path.join(_REFS_DIR, "master_voice.wav")
_voice_id_cache: dict = {}


def _get_deepinfra_voice_id(lang: str) -> str | None:
    """Load or register the DeepInfra voice ID for a language (fallback path)."""
    if lang in _voice_id_cache:
        return _voice_id_cache[lang]
    try:
        if os.path.exists(_VOICE_ID_FILE):
            with open(_VOICE_ID_FILE, "r", encoding="utf-8") as f:
                vid = json.load(f).get(lang)
                if vid:
                    _voice_id_cache[lang] = vid
                    return vid
    except Exception:
        # Cached file unreadable; fall through to (re)registration.
        pass

    # Registration
    ref_path = _REF_DE if lang == "de" else _REF_EN
    if not os.path.isfile(ref_path):
        ref_path = _REF_EN if lang == "de" else _REF_DE
    if not os.path.isfile(ref_path):
        return None

    try:
        with open(ref_path, "rb") as f:
            audio_bytes = f.read()
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.deepinfra.com/v1/voices/add",
                headers={"Authorization": f"bearer {DEEPINFRA_API_KEY}"},
                files={"files": (os.path.basename(ref_path), audio_bytes, "audio/wav")},
                data={"name": f"YourAI_{lang}", "description": f"YourAI ({lang})"},
            )
        if resp.status_code == 200:
            vid = resp.json().get("voice_id", "")
            if vid:
                _voice_id_cache[lang] = vid
                # Persist
                data = {}
                if os.path.exists(_VOICE_ID_FILE):
                    with open(_VOICE_ID_FILE) as f:
                        data = json.load(f)
                data[lang] = vid
                os.makedirs(os.path.dirname(_VOICE_ID_FILE), exist_ok=True)
                with open(_VOICE_ID_FILE, "w") as f:
                    json.dump(data, f, indent=2)
                return vid
    except Exception as e:
        log(_MODULE.upper(), f"⚠️ DeepInfra voice registration failed: {e}", Fore.YELLOW)
    return None


def _call_deepinfra(text: str, lang: str) -> bytes:
    """DeepInfra Chatterbox fallback — single chunk."""
    voice_id = _get_deepinfra_voice_id(lang)
    payload = {
        "text": text,
        "language_id": lang,
        "response_format": "wav",
        "exaggeration": 0.5,
        "cfg": 0.3,
    }
    if voice_id:
        payload["voice_id"] = voice_id

    for attempt in range(3):
        try:
            with httpx.Client(timeout=_DEEPINFRA_TIMEOUT) as client:
                resp = client.post(
                    _DEEPINFRA_ENDPOINT,
                    json=payload,
                    headers={"Authorization": f"bearer {DEEPINFRA_API_KEY}", "Content-Type": "application/json"},
                )
            if resp.status_code in (500, 502, 503) and attempt < 2:
                time.sleep(3)
                continue
            if resp.status_code != 200:
                raise YourAISystemError(
                    message=f"DeepInfra TTS: HTTP {resp.status_code} — {resp.text[:200]}",
                    module=_MODULE,
                )
            data = resp.json()
            audio_b64 = data.get("audio", "")
            if not audio_b64:
                raise YourAISystemError(message="DeepInfra TTS: no audio in response", module=_MODULE)
            if "," in audio_b64:
                audio_b64 = audio_b64.split(",", 1)[1]
            audio_b64 += "=" * (-len(audio_b64) % 4)
            return base64.b64decode(audio_b64)
        except httpx.TimeoutException:
            if attempt < 2:
                continue
            raise YourAISystemError(message=f"DeepInfra TTS timeout (>{_DEEPINFRA_TIMEOUT}s)", module=_MODULE)
        except (YourAISystemError, YourAIConfigError):
            raise
        except Exception as e:
            raise YourAISystemError(message=f"DeepInfra TTS: {e}", cause=e, module=_MODULE)

    raise YourAISystemError(message="DeepInfra TTS: 3 attempts failed", module=_MODULE)


# ──────────────────────────────────────────────
# WAV Concat (Multi-Chunk)
# ──────────────────────────────────────────────

def _concat_wavs(wav_list: list[bytes]) -> bytes:
    """Concatenate multiple WAV byte arrays into one with a correct header."""
    if len(wav_list) == 1:
        return wav_list[0]
    import wave
    with wave.open(io.BytesIO(wav_list[0]), 'rb') as first:
        params = first.getparams()
        frames = [first.readframes(first.getnframes())]
    for wav_bytes in wav_list[1:]:
        try:
            with wave.open(io.BytesIO(wav_bytes), 'rb') as w:
                frames.append(w.readframes(w.getnframes()))
        except Exception as e:
            log(_MODULE.upper(), f"⚠️ WAV chunk error: {e}", Fore.YELLOW)
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setparams(params)
        for f in frames:
            w.writeframes(f)
    return out.getvalue()


# ──────────────────────────────────────────────
# WAV -> MP3 conversion (ffmpeg)
# ──────────────────────────────────────────────

def _wav_to_mp3(wav_bytes: bytes) -> bytes:
    """Convert WAV bytes to MP3 via ffmpeg. 64kbps mono — optimal for speech."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", "pipe:0", "-f", "mp3", "-ab", "64k", "-ac", "1", "-v", "quiet", "pipe:1"],
            input=wav_bytes,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout:
            log(_MODULE.upper(), f"⚠️ WAV->MP3 conversion failed (rc={result.returncode})", Fore.YELLOW)
            return wav_bytes
        ratio = len(wav_bytes) / max(len(result.stdout), 1)
        log(_MODULE.upper(), f"🗜️ WAV->MP3: {len(wav_bytes)//1024}KB → {len(result.stdout)//1024}KB ({ratio:.1f}× smaller)", Fore.CYAN)
        return result.stdout
    except FileNotFoundError:
        log(_MODULE.upper(), "⚠️ ffmpeg not found — keeping WAV", Fore.YELLOW)
        return wav_bytes
    except Exception as e:
        log(_MODULE.upper(), f"⚠️ WAV->MP3 error: {e} — keeping WAV", Fore.YELLOW)
        return wav_bytes


def _is_wav(audio_bytes: bytes) -> bool:
    """Return True if the bytes look like a WAV file (RIFF header)."""
    return len(audio_bytes) > 4 and audio_bytes[:4] == b"RIFF"


# ──────────────────────────────────────────────
# TTS Cache (Memory Server)
# ──────────────────────────────────────────────

def _tts_cache_check(clean_text: str) -> bytes | None:
    """Return cached TTS audio for the text from the memory server, or None."""
    if not MEMORY_API_BASE or not MEMORY_API_KEY:
        return None
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{MEMORY_API_BASE}/get_tts_audio",
                headers={"X-API-Key": MEMORY_API_KEY},
                params={"text": clean_text},
            )
        if resp.status_code == 200:
            log(_MODULE.upper(), f"💾 TTS cache HIT ({len(resp.content) // 1024} KB)", Fore.GREEN)
            return resp.content
    except Exception:
        # Cache lookup is best-effort; on any error we regenerate the audio.
        pass
    return None


def _tts_cache_store(clean_text: str, audio_bytes: bytes) -> None:
    """Store generated TTS audio in the memory-server cache (best-effort)."""
    if not MEMORY_API_BASE or not MEMORY_API_KEY:
        return
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{MEMORY_API_BASE}/upload_tts_cache",
                headers={"X-API-Key": MEMORY_API_KEY},
                data={"text": clean_text},
                files={"file": ("tts.mp3", audio_bytes, "audio/mpeg")},
            )
        if resp.status_code == 200:
            log(_MODULE.upper(), f"💾 TTS cache stored ({len(audio_bytes) // 1024} KB)", Fore.CYAN)
    except Exception as e:
        log(_MODULE.upper(), f"⚠️ TTS cache store: {e}", Fore.YELLOW)


# ──────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────

def generate_speech(text: str, language: str = "de") -> bytes:
    """
    Generate speech — Resemble AI (primary) with a DeepInfra fallback.

    Args:
        text (str): Text to speak (markdown/emojis are cleaned internally).
        language (str): "de" or "en".

    Returns:
        bytes: MP3 audio bytes (WAV fallback if ffmpeg is unavailable).

    Raises:
        YourAIConfigError: No API key available.
        YourAISystemError: All providers failed.
    """
    has_resemble = bool(RESEMBLE_API_KEY)
    has_deepinfra = bool(DEEPINFRA_API_KEY)

    if not has_resemble and not has_deepinfra:
        raise YourAIConfigError(
            message="No TTS API key set (neither RESEMBLE_API_KEY nor DEEPINFRA_API_KEY)",
            module=_MODULE,
        )

    # Detect language (before cleaning — umlauts are relevant)
    lang = _detect_lang(text)
    log(_MODULE.upper(), f"🔍 Language: '{lang}' (text: {text[:40]!r})", Fore.CYAN)

    # Cleaning
    text = _clean_for_tts(text)
    if not text:
        raise YourAISystemError(message="TTS: text empty after cleaning", module=_MODULE)

    # Cache check
    cached = _tts_cache_check(text)
    if cached:
        if _is_wav(cached):
            cached = _wav_to_mp3(cached)
        return cached

    # Chunking (1800 chars for Resemble, rarely needed)
    chunks = _split_chunks(text)

    if len(chunks) == 1:
        log(_MODULE.upper(), f"🎙️ TTS ({len(text)} chars)...", Fore.CYAN)
    else:
        log(_MODULE.upper(), f"🎙️ TTS ({len(chunks)} chunks, {len(text)} chars)...", Fore.CYAN)

    # ── Generate: Resemble AI (primary) → DeepInfra (fallback) ──
    all_audio: list[bytes] = []
    failed = 0
    last_error = ""

    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            log(_MODULE.upper(), f"  Chunk {i+1}/{len(chunks)}: {chunk[:60]!r}", Fore.CYAN)

        audio = None

        # Try 1: Resemble AI
        if has_resemble:
            try:
                audio = _call_resemble(chunk)
            except YourAIConfigError:
                raise
            except Exception as e:
                log(_MODULE.upper(), f"⚠️ Resemble failed: {e} — falling back to DeepInfra...", Fore.YELLOW)

        # Try 2: DeepInfra fallback
        if audio is None and has_deepinfra:
            try:
                audio = _call_deepinfra(chunk, lang)
                log(_MODULE.upper(), f"✅ DeepInfra fallback succeeded", Fore.GREEN)
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                log(_MODULE.upper(), f"❌ DeepInfra fallback also failed: {last_error}", Fore.RED)

        if audio:
            all_audio.append(audio)
        else:
            failed += 1
            if not last_error:
                last_error = "Both providers failed"

    if not all_audio:
        raise YourAISystemError(message=f"TTS: all chunks failed — {last_error}", module=_MODULE)

    # WAV merge → MP3
    audio_bytes = _concat_wavs(all_audio)
    audio_bytes = _wav_to_mp3(audio_bytes)
    suffix = f" ({failed} skipped)" if failed else ""
    log(_MODULE.upper(), f"✅ TTS done ({len(audio_bytes) // 1024} KB){suffix}", Fore.GREEN)

    # Cache store (MP3)
    if not failed:
        _tts_cache_store(text, audio_bytes)

    return audio_bytes
