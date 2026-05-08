"""
YourAI AI - Configuration
=========================
Alle Konfigurationsvariablen und Model-Settings.

NEU: OpenRouter Support für schnellere Responses!
     Lokale Models bleiben als Fallback.

Usage:
    from config import (
        LLM_HOST_STD, LLM_HOST_MAIN,
        OPENROUTER_API_KEY, OPENROUTER_MODEL,
        MODEL_YOURAI_LOCAL_PRIMARY, MODEL_YOURAI_LOCAL_FALLBACK,
        USE_MEMORY, USE_VISION, ...
    )
"""

import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from langchain_ollama import ChatOllama

from display import log, Fore
from exceptions import YourAILLMConnectionError, YourAILLMParseError, YourAIConfigError, YourAIEmptyResponseError, YourAIRateLimitError, YourAIModelNotFoundError

# ==========================================
# EXPERT POOL SETTINGS
# ==========================================
LLM_STATS_API_KEY = os.environ.get("LLM_STATS_API_KEY", "")
LLM_STATS_BASE_URL = os.environ.get("LLM_STATS_BASE_URL", "https://api.zeroeval.com")
EXPERT_POOL_FILE = os.environ.get(
    "EXPERT_POOL_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "expert_model_pool.json")
)
EXPERT_POOL_LOCK_FILE = os.environ.get("EXPERT_POOL_LOCK_FILE", EXPERT_POOL_FILE + ".lock")
EXPERT_POOL_PRICE_CAP_USD_PER_M = float(os.environ.get("EXPERT_POOL_PRICE_CAP_USD_PER_M", "0.60"))
EXPERT_POOL_TOP_N = int(os.environ.get("EXPERT_POOL_TOP_N", "3"))

# ==========================================
# .ENV LADEN (falls vorhanden)
# ==========================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Manueller .env Parser als Fallback
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        for line in _env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip("'\"")
                os.environ.setdefault(key.strip(), value)

LLM_STATS_API_KEY = os.environ.get("LLM_STATS_API_KEY", LLM_STATS_API_KEY)
LLM_STATS_BASE_URL = os.environ.get("LLM_STATS_BASE_URL", LLM_STATS_BASE_URL)
EXPERT_POOL_FILE = os.environ.get("EXPERT_POOL_FILE", EXPERT_POOL_FILE)
EXPERT_POOL_LOCK_FILE = os.environ.get("EXPERT_POOL_LOCK_FILE", EXPERT_POOL_FILE + ".lock")
EXPERT_POOL_PRICE_CAP_USD_PER_M = float(os.environ.get("EXPERT_POOL_PRICE_CAP_USD_PER_M", str(EXPERT_POOL_PRICE_CAP_USD_PER_M)))
EXPERT_POOL_TOP_N = int(os.environ.get("EXPERT_POOL_TOP_N", str(EXPERT_POOL_TOP_N)))

# ==========================================
# HOST CONFIGURATION
# ==========================================

# HOST 1: Standard / Lokal / Docker (für kleine Modelle)
LLM_HOST_STD = "https://ollama.your-domain.example.com/"

# HOST 2: Main PC (für die dicken Biester wie 30B)
LLM_HOST_MAIN = os.environ.get("LLM_HOST_MAIN", "http://YOUR_LLM_HOST:11434")


# ==========================================
# OPENROUTER CONFIGURATION (NEU!)
# ==========================================
# Schneller als lokal, günstig (~0.005$/Request = ~1€/200 Requests)
# API Key: https://openrouter.ai/keys

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1.5"

# Zusätzliche OpenRouter Models (für Nodes die lokal Probleme machen)
OPENROUTER_MODEL_COHERENCE = "microsoft/phi-4"                     # Autonomy Guard (Phi 4, 14B, kein Thinking, pures Reasoning)
OPENROUTER_MODEL_PROMISE = "microsoft/phi-4"                       # Promise Check (Phi 4, gleicher Trick wie Guardian)
OPENROUTER_MODEL_MEMORY = "google/gemma-4-26b-a4b-it"             # Hippocampus Memory (Gemma 4 MoE)
OPENROUTER_MODEL_BIO = "google/gemma-4-26b-a4b-it"                # Bio Expert (Gemma 4 MoE, mehr Wissen als 3-27B)
OPENROUTER_MODEL_MED = "qwen/qwen3-235b-a22b-2507"                      # Med Expert (~0.07$/M in) — bleibt Qwen, med braucht max Qualität
OPENROUTER_MODEL_PHYSICS = "qwen/qwen3.5-9b"                       # Physics Expert (~0.10$/M in) — bleibt Qwen, gut bei STEM
OPENROUTER_MODEL_CODE = "qwen/qwen3.5-9b"                          # Code Expert (~0.10$/M in) — bleibt Qwen, top bei Code
OPENROUTER_MODEL_MATH = "google/gemma-4-26b-a4b-it"               # Math Expert (Gemma 4 MoE)
OPENROUTER_MODEL_ROUTER = "google/gemma-4-26b-a4b-it"             # Router (Gemma 4 MoE, präziser als 3-12B)

# Branding Headers für OpenRouter
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://your-domain.example.com",
    "X-Title": "YourAI",
}

# Fallback-Kette: OpenRouter → Lokal Primary → Lokal Fallback
USE_OPENROUTER = bool(OPENROUTER_API_KEY)  # Automatisch an wenn Key gesetzt


# ==========================================
# FEATURE SWITCHES
# ==========================================

USE_MEMORY = True           # Langzeitgedächtnis (Hippocampus)
USE_VISION = True           # Screenshot-Fähigkeit
USE_VOICE = False           # Sprechen/Hören oder Tippen/Lesen
USE_EPISODIC = True         # Tagebuch (Episodic Diary)
USE_PROMISE_CHECK = True    # Versprechen Erkennung (Action/Mood)
USE_TWITCH = False          # Twitch Integration
USE_DISCORD = True         # Discord Integration
USE_GRANITE = False         # Safety Filter (False = Du darfst sie erziehen!)
USE_USERS = False           # Twitch User Tracking
USE_THINKING = True         # Thinking-Mode für unterstützte Models
USE_COHERENCE_CHECK = True  # Autonomy Guardian
USE_TOOLS = True            # Tool-Aufrufe
USE_SPOTIFY = True          # Spotify Musik-Kontext
USE_STREAMING = True        # Stream YourAI's OpenRouter response → Tools feuern sofort beim ersten Tag-Token
USE_WEB_SEARCH = True       # Web Search via Docker Crawler
USE_PAPERLESS = True        # Paperless-NGX Dokumentenmanagement (Admin-only)
USE_HOME_ASSISTANT = True   # Home Assistant Smart Home (Admin-only)
USE_IMAGE_GEN = True        # Image Generation via OpenRouter
USE_PROMPT_ROUTER = True    # Semantic Prompt Router: inject only relevant sections (token savings)
USE_MAINTENANCE = False     # Maintenance Mode: non-admins sehen Wartungsseite
USE_CONSOLE_LOG = True      # Console-Ausgaben (False = leise, gut für Docker)

# ==========================================
# IMAGE GENERATION
# ==========================================
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "bytedance-seed/seedream-4.5")
IMAGE_SIZE  = "1024x1024"   # Fixed cap — cost control
IMAGE_MODELS = [
    "bytedance-seed/seedream-4.5",              # $0.04/img — ZDR ✅
    # Below require ZDR disabled in OpenRouter settings (openrouter.ai/settings/privacy):
    # "sourceful/riverflow-v2-fast",            # $0.02/img
    # "sourceful/riverflow-v2-standard-preview",# $0.035/img
    # "sourceful/riverflow-v2-max-preview",     # $0.075/img
    # "black-forest-labs/flux.2-pro",           # ~$0.03/MP
]

# Per-role monthly image limits — Budget: ~2.50€/month for images ($0.04/img)
# Worst case 10 users: 5 + 12 + (8×4) + (5×5) = ~74 imgs = ~2.96€
# Realistic (not all max out): ~1.50-2.00€
IMAGE_LIMITS_DEFAULT = {
    "admin":       5,    # 0.20€/month
    "family":     12,    # 0.48€/month
    "friend":      8,    # 0.32€/month each
    "ai_guest":    5,    # 0.20€/month each
    "guest":       5,    # 0.20€/month each
    "human_guest": 5,    # 0.20€/month each
    "default":     5,    # fallback
}
IMAGE_LIMITS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image_usage.json")

# ==========================================
# RUNTIME OVERRIDES (Dashboard Support)
# ==========================================
# Diese Sektion erlaubt es dem Dashboard, die Flags oben zu überschreiben,
# ohne dass die config.py Datei selbst geändert werden muss.
_runtime_file = Path(__file__).parent.parent / "runtime_config.json"  # Projekt-Root, nicht core/

def reload_runtime_flags():
    """
    Hot-Reload: Liest runtime_config.json und überschreibt USE_* Flags.
    Wird von brain.py VOR jeder Pipeline aufgerufen → Toggles wirken sofort!
    """
    import config as _self_module
    if not _runtime_file.exists():
        return
    try:
        import json
        _overrides = json.loads(_runtime_file.read_text(encoding="utf-8"))
        for _k, _v in _overrides.items():
            if _k.startswith("USE_"):
                globals()[_k] = _v
                setattr(_self_module, _k, _v)  # Auch das Module-Objekt updaten
    except Exception as e:
        log("CONFIG", f"⚠️ Failed to parse runtime_config.json: {e}", Fore.RED)

# Beim ersten Import einmal laden
reload_runtime_flags()

# ==========================================
# SPOTIFY / MUSIC SETTINGS
# ==========================================
SPOTIFY_API_URL = "https://youraireact.your-domain.example.com/get/YourAI"
SPOTIFY_STALE_MINUTES = 6   # Nach X Minuten ohne Song-Wechsel → ignorieren

# Spotify Control (nur Admin!)
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN", "")

# ==========================================
# HIPPOCAMPUS / MEMORY SETTINGS
# ==========================================
MEMORY_API_BASE = os.environ.get("MEMORY_API_BASE", "http://YOUR_MEMORY_API:8007")
MEMORY_API_KEY = os.environ.get("MEMORY_API_KEY", "")
HIPPOCAMPUS_USER_ID = "admin"

# Memory Models
HIPPOCAMPUS_EXTRACTION_MODEL = "gemma3:4b"
HIPPOCAMPUS_EMBEDDING_MODEL = "qwen3-embedding:0.6b"       # Lokaler Fallback
HIPPOCAMPUS_EMBEDDING_OPENROUTER = "qwen/qwen3-embedding-8b"  # Primary: OpenRouter (~$0.01/M tokens, 99% benchmark)
HIPPOCAMPUS_RELEVANCE_MODEL = "qwen3:1.7b"

# Memory Thresholds & Limits
HIPPOCAMPUS_ENABLE_PREFILTERING = True
HIPPOCAMPUS_RELEVANCE_THRESHOLD = 0.45
HIPPOCAMPUS_PREFILTER_CAP = 15
HIPPOCAMPUS_MAX_FETCH = 100
HIPPOCAMPUS_DUP_COSINE = 0.92
HIPPOCAMPUS_DUP_LEVENSHTEIN = 90

# ==========================================
# TIMEOUT SETTINGS
# ==========================================

PROMISE_CHECK_TIMEOUT = 60.0    # Sekunden für LLM Promise Check (15 war zu kurz!)
EMBED_TIMEOUT = 30              # Sekunden für Embedding-Calls (Ollama)
EMBED_MAX_RETRIES = 2           # Retries bei Embed-Disconnect

# ==========================================
# WEBSITE AUTONOMY SETTINGS
# ==========================================
# ==========================================
# COHERE RERANKER
# ==========================================
# Training auf OFF gesetzt in dashboard.cohere.com → Data Control
COHERE_API_KEY    = os.environ.get("COHERE_API_KEY", "")
COHERE_RERANK_MODEL = "rerank-multilingual-v3.0"  # DE + EN, $0.0025/search
USE_RERANKER      = bool(COHERE_API_KEY)
COHERE_EMBED_MODEL = os.environ.get("COHERE_EMBED_MODEL", "embed-multilingual-v3.0")
USE_DIARY_SEMANTIC_SEARCH = os.environ.get("USE_DIARY_SEMANTIC_SEARCH", "1") == "1" and bool(COHERE_API_KEY)
DIARY_SEMANTIC_CANDIDATE_LIMIT = int(os.environ.get("DIARY_SEMANTIC_CANDIDATE_LIMIT", "160"))
DIARY_SEMANTIC_TOP_N = int(os.environ.get("DIARY_SEMANTIC_TOP_N", "24"))
DIARY_SEMANTIC_MIN_SCORE = float(os.environ.get("DIARY_SEMANTIC_MIN_SCORE", "0.18"))

# ==========================================
# WEB CRAWLER SETTINGS
# ==========================================
WEB_CRAWLER_URL = os.environ.get("WEB_CRAWLER_URL", "http://YOUR_WEB_CRAWLER:8080/search")
WEB_CRAWLER_TOKEN = os.environ.get("BEARER_WEBCRAWLER", "")
WEB_CRAWLER_TIMEOUT = 15        # Sekunden
WEB_CRAWLER_MAX_RESULTS = 5     # Max Ergebnisse pro Suche

# ==========================================
# PAPERLESS-NGX SETTINGS
# ==========================================
PAPERLESS_URL = "https://paperless.your-domain.example.com"
PAPERLESS_TOKEN = os.environ.get("PAPERLESS", "")
PAPERLESS_TIMEOUT = 15          # Sekunden
PAPERLESS_MAX_RESULTS = 10      # Max Dokumente pro Suche

# ==========================================
# HOME ASSISTANT SETTINGS
# ==========================================
HOMEASSISTANT_URL = os.environ.get("HOMEASSISTANT_URL", "http://YOUR_HOME_ASSISTANT:8123")
HOMEASSISTANT_TOKEN = os.environ.get("HOMEASSISTANT_TOKEN", "")
HOMEASSISTANT_TIMEOUT = 10      # Sekunden

TRIGGER_CHANCE = 0.001          # Chance pro Request (0.001 = 0.1%)
FETCH_TIMEOUT = 15              # Sekunden für Website Fetch
DEPLOY_TIMEOUT = 30             # Sekunden für Deploy API Request

# Maximale Zeichenanzahl, die YourAI verarbeiten darf
MAX_HTML_CHARS = 50000
MAX_CSS_CHARS = 50000
MAX_JS_CHARS = 10000

# LOKALE PFADE (bevorzugt! Umgeht Cloudflare-Manipulation)
# Nutzt die .env Variablen, falls gesetzt (z.B. "/var/www/your-domain.example.com/yourai.html")
LOCAL_HTML_PATH = os.environ.get("YOURAI_HTML_PATH", None) 
LOCAL_CSS_PATH = os.environ.get("YOURAI_CSS_PATH", None)   
LOCAL_JS_PATH = os.environ.get("YOURAI_JS_PATH", None)

# ==========================================
# WEBSITES.PY
# ==========================================
QUOTE_API_TIMEOUT = 10

# ==========================================
# AUTONOMY_GUARD
# ==========================================
MAX_GUARD_LOG_ENTRIES = 50
GUARD_MAX_TOKENS = 2048          # Hoch genug für Reasoning + JSON Output
GUARD_MAX_MEMORIES = 8           # Nur die N relevantesten Memories zum Guard schicken
GUARD_MAX_DIARY_CHARS = 300      # Diary-Kontext kürzen (war 500)
GUARD_MAX_HISTORY_MSGS = 3       # Nur letzte N Chat-Messages (war 4)

# ==========================================
# EYES
# ==========================================
# Das Modell muss Multimodal sein (Bilder verstehen)!
# OpenRouter Vision (ZDR supported, günstig, kein lokaler RAM nötig)
VISION_MODEL = "qwen/qwen3.5-9b"  # Vision + Thinking, Output ~3x billiger als qwen3-vl-8b-instruct ($0.15 vs $0.50/M)
VISION_USE_OPENROUTER = True  # True = OpenRouter, False = lokales Ollama

# Screenshot Einstellungen
VISION_IMG_PATH = "vision_input.png"
VISION_MAX_SIZE = (1024, 1024) # Skalieren spart VRAM und Zeit

# ==========================================
# TWITCH SETTINGS
# ==========================================
TWITCH_TOKEN = os.environ.get("TWITCH_TOKEN", "")
TWITCH_BOT_NICK = os.environ.get("TWITCH_BOT_NICK", "yourai_bot")
TWITCH_CHANNEL = os.environ.get("TWITCH_CHANNEL", "your_streamer_name")
TWITCH_SERVER = "irc.chat.twitch.tv"
TWITCH_PORT = 6667
TWITCH_SOCKET_TIMEOUT = 240
TWITCH_RECV_BUFFER_SIZE = 2048

# ==========================================
# DISCORD SETTINGS
# ==========================================
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
DISCORD_VIP_CHANNEL_ID = int(os.environ.get("DISCORD_VIP_CHANNEL_ID", "0"))
DISCORD_START_CHANNEL_ID = int(os.environ.get("DISCORD_START_CHANNEL_ID", "0"))
DISCORD_PRIVATE_CATEGORY_ID = int(os.environ.get("DISCORD_PRIVATE_CATEGORY_ID", "0"))
DISCORD_MOD_ROLE_IDS: list[int] = [int(x) for x in os.environ.get("DISCORD_MOD_ROLE_IDS", "").split(",") if x.strip().isdigit()]
# Extra privileged role IDs for private channel access (env: DISCORD_PRIVILEGED_ROLE_IDS)
DISCORD_PRIVILEGED_ROLE_IDS: list[int] = [int(x) for x in os.environ.get("DISCORD_PRIVILEGED_ROLE_IDS", "").split(",") if x.strip().isdigit()]
DISCORD_CHANNELS_FILE = str(Path(__file__).parent.parent / "discord_channels.json")
DISCORD_TRIGGER_KEYWORDS = ["yourai", "altpersona"]

# DM Whitelist: Discord User ID (str) -> YourAI User Key
# Nur diese User dürfen proaktive DMs bekommen!
# Rechtsklick auf User in Discord → "ID kopieren" (Developer Mode muss an sein)
DISCORD_DM_WHITELIST = {
    # "DISCORD_USER_ID": "user_key",
    # Only these users can receive proactive DMs from the bot.
    "YOUR_DISCORD_USER_ID_1": "admin",
    "YOUR_DISCORD_USER_ID_2": "user1",
}

# Custom Discord Emojis: Name → Beschreibung für YourAI
# Server-Emojis die YourAI auch BENUTZEN kann: name → description
# Format: "emoji_name": "was es bedeutet/zeigt"
DISCORD_CUSTOM_EMOJIS = {
    # "emoji_name": "description - when and how to use it",
    "example_emoji": "example - a waving hand",
    "another_emoji": "example - a dancing cat",
}

# Discord Server Sticker: Name → Beschreibung
# Sticker sind große Bilder die User in Chats schicken können (wie große Emojis)
DISCORD_SERVER_STICKERS = {
    # "sticker_name": "description of what the sticker shows",
    "example_sticker": "example - a waving cat sticker",
}

# ==========================================
# WHISPER / EARS SETTINGS
# ==========================================
WHISPER_MODEL_SIZE = "small"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_PHRASE_TIME_LIMIT = 10
WHISPER_BEAM_SIZE = 5
WHISPER_AMBIENT_NOISE_DURATION = 0.5

# ==========================================
# TTS / MOUTH SETTINGS
# ==========================================
XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
TTS_MASTER_VOICE_FILE = "master_voice.wav"
TTS_LANGUAGE = "en"
TTS_DEFAULT_VOLUME = 0.5
TTS_VOLUME_CONFIG_FILE = "tts_volume.json"

# ElevenLabs TTS (Web — Tier 3 Premium)
ELEVENLABS_API_KEY     = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID_DE = os.environ.get("ELEVENLABS_VOICE_ID_DE", "")
ELEVENLABS_VOICE_ID_EN = os.environ.get("ELEVENLABS_VOICE_ID_EN", "")  # placeholder, DE als Fallback
ELEVENLABS_MODEL       = "eleven_v3"
YOURAI_TTS_URL          = os.environ.get("YOURAI_TTS_URL", "")  # mouth_server.py auf Windows VM
DEEPINFRA_API_KEY      = os.environ.get("DEEPINFRA_API_KEY", "")  # Zonos Voice Cloning (Middle Tier)
FCM_SERVER_KEY         = os.environ.get("FCM_SERVER_KEY", "")  # Firebase Cloud Messaging legacy key
TTS_PREMIUM_LIMITS     = {
    "admin":  -1,   # unlimitiert
    "family": -1,   # unlimitiert
    "friend":  3,   # 3 gratis/Monat
    "default": 3,   # alle anderen: 3 gratis/Monat
}
TTS_LIMITS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docker_data", "tts_usage.json"
)

# ==========================================
# DASHBOARD SETTINGS
# ==========================================
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:8051")
DASHBOARD_MAX_EVENTS = 2000
DASHBOARD_DEFAULT_USER = "admin"
DASHBOARD_DEFAULT_MODE = "yourai"
DEBUG_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "debug_log.jsonl")
DEBUG_LOG_MAX_LINES = 10000  # Rotate when file exceeds this

# YourAI Output Log — plain .txt, nur YourAIs Antworten, 1:1 mit Emojis
YOURAI_OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "yourai_output.txt")
YOURAI_OUTPUT_MAX_BYTES = 15 * 1024 * 1024  # 15 MB — danach: kein weiteres Schreiben

# ==========================================
# USERS SETTINGS
# ==========================================
USERS_DB_FILE = "users_db.json"
ADMIN_USERNAME = "your_streamer_name"

# ==========================================
# MEMORY SERVER SETTINGS
# ==========================================
MEMORY_MAX_RAM_MEMORIES = 5000
MEMORY_BACKUP_INTERVAL = 600          # Sekunden (10 min)
MEMORY_CACHE_TIMEOUT = 600            # Sekunden (10 min)
MEMORY_CLEANUP_CHECK_INTERVAL = 60    # Sekunden (1 min)
MEMORY_USER_DIR = "user_memories"
MEMORY_AUDIO_DIR = "user_audio"
MEMORY_TTS_CACHE_DIR = "tts_cache"
MEMORY_BACKUP_DIR = "backups"

# ==========================================
# HIPPOCAMPUS TIMEOUTS & LIMITS
# ==========================================
HIPPOCAMPUS_STATS_TIMEOUT = 0.5       # Sekunden für Stats-Request
HIPPOCAMPUS_EMBED_MAX_LENGTH = 500    # Max Zeichen für Embedding-Prompt
HIPPOCAMPUS_KEEP_ALIVE = "5m"         # Ollama Keep-Alive für Embed-Models
HIPPOCAMPUS_LLM_TIMEOUT = 120         # Sekunden für LLM JSON Calls
HIPPOCAMPUS_MIN_TEXT_LENGTH = 10      # Minimum Textlänge für Memory-Extraktion

# ==========================================
# DETECTION SETTINGS
# ==========================================
PROMISE_CHECK_MAX_TOKENS = 400
APOLOGY_MIN_WORDS_FOR_SINCERITY = 8

# ==========================================
# WEBSITE URLS (aus .env)
# ==========================================
WEBSITE_FETCH_URL = os.environ.get("WEBSITE_FETCH_URL", "https://your-domain.example.com/yourai.html")
WEBSITE_CSS_URL = os.environ.get("WEBSITE_CSS_URL", "https://your-domain.example.com/CSS/yourai.css")
WEBSITE_JS_URL = os.environ.get("WEBSITE_JS_URL", "https://your-domain.example.com/scripts/scroll_reveal.js")
WEBSITE_DEPLOY_URL = os.environ.get("WEBSITE_DEPLOY_URL", "https://your-domain.example.com/api/yourai_deploy.php")
YOURAI_DEPLOY_TOKEN = os.environ.get("YOURAI_DEPLOY_TOKEN", "")
QUOTE_API_URL = os.environ.get("QUOTE_API_URL", "https://your-domain.example.com/api/yourai_quote.php")
YOURAI_QUOTE_TOKEN = os.environ.get("YOURAI_QUOTE_TOKEN", "")

# Lab / Playground (keine Content-Restrictions — YourAIs freie Spielwiese)
# Konfigurierbar per .env — Subdomain/Pfade je nach Hosting-Setup setzen
LAB_HTML_PATH   = os.environ.get("LAB_HTML_PATH", None)
LAB_CSS_PATH    = os.environ.get("LAB_CSS_PATH", None)
LAB_JS_PATH     = os.environ.get("LAB_JS_PATH", None)
LAB_FETCH_URL   = os.environ.get("LAB_FETCH_URL", "")        # z.B. https://lab.your-domain.example.com/index.html
LAB_CSS_URL     = os.environ.get("LAB_CSS_URL", "")          # z.B. https://lab.your-domain.example.com/lab.css
LAB_JS_URL      = os.environ.get("LAB_JS_URL", "")           # z.B. https://lab.your-domain.example.com/lab.js
LAB_DEPLOY_URL  = os.environ.get("LAB_DEPLOY_URL", "")       # z.B. https://lab.your-domain.example.com/api/lab_deploy.php
LAB_DEPLOY_TOKEN = os.environ.get("LAB_DEPLOY_TOKEN", "")    # Gleicher oder eigener Token

# ==========================================
# WEBSITE VALIDATION THRESHOLDS
# ==========================================
MIN_HTML_CHARS = 500
MIN_CSS_CHARS = 100
MIN_JS_CHARS = 50
MAX_SIZE_CHANGE_RATIO = 0.5           # 50% max Größenänderung
MIN_EMOJI_RETENTION_RATIO = 0.5       # 50% der Emojis müssen bleiben

# ==========================================
# TWITCH & GRANITE SICHERHEITS-CHECK
# ==========================================
if USE_TWITCH and not USE_GRANITE:
    log("CONFIG", "[CRITICAL] FEHLER IN CONFIG.PY", Fore.RED)
    log("CONFIG", "USE_TWITCH ist auf True, aber USE_GRANITE ist auf False!", Fore.RED)
    log("CONFIG", "Twitch ist öffentlich. YourAI darf nicht ungeschützt streamen.", Fore.RED)
    log("CONFIG", "Bitte setze USE_GRANITE = True, bevor du Twitch startest.", Fore.RED)
    sys.exit(1)


# ==========================================
# CONTEXT SETTINGS
# ==========================================

CONTEXT_WINDOW = 6  # Letzte N Nachrichten merken


# ==========================================
# MODEL CONFIGURATION
# ==========================================

# Safety & Routing (kleine, schnelle Modelle - IMMER lokal)
MODEL_GRANITE = "qwen3.5:2b"        # Safety Filter
MODEL_ROUTER = "gemma3:4b"             # Request Routing (1b zu dumm "Other", e4b nur smalltalk)
MODEL_COHERENCE = "qwen3.5:9b"      # Autonomy Guard - LOKAL FALLBACK (Primary: Phi 4 via OpenRouter)
MODEL_COHERENCE_OPENROUTER = OPENROUTER_MODEL_COHERENCE  # Primary: Phi 4
MODEL_CHECK_PASS = "qwen3.5:0.8b"   # Password Check
MODEL_PROMISE_CHECK = "gemma3:4b"   # Promise Detection (qwen3:1.7b war zu klein, leere Responses)
MODEL_TOOL_ROUTER = "functiongemma"  # Für komplexe Tool-Erkennung

# YourAI Main - OpenRouter (PRIMARY)
# Wird automatisch verwendet wenn OPENROUTER_API_KEY gesetzt ist
MODEL_YOURAI_OPENROUTER = OPENROUTER_MODEL

# YourAI Fallback - Lokale Models
MODEL_YOURAI_LOCAL_PRIMARY = "nemotron-3-nano:30b"   # Main PC (Fallback 1)
MODEL_YOURAI_LOCAL_FALLBACK = "deepseek-r1:14b"      # Standard Host (Fallback 2)

# Legacy Aliases (für Kompatibilität)
MODEL_YOURAI_PRIMARY = MODEL_YOURAI_OPENROUTER if USE_OPENROUTER else MODEL_YOURAI_LOCAL_PRIMARY
MODEL_YOURAI_FALLBACK = MODEL_YOURAI_LOCAL_FALLBACK

# Uncensored Mode
MODEL_UNCENSORED = "thedrummer/unslopnemo-12b"

# Expert Models (Domain-spezifisch - IMMER lokal)
# Expert Models (Domain-spezifisch)
# Bio und Med jetzt OpenRouter-first, Rest lokal
EXPERT_MODELS = {
    "bio": "hf.co/unsloth/Olmo-3-7B-Think-GGUF:q8_0",
    "physics": "qwen3.5:9b",
    "code": "qwen3.5:9b",
    "chemie": "rnj-1",
    "math": "gemma3:4b",                  # Server-Fallback (phi4-mini zu groß für Docker)
    "med": "qwen3.5:9b",
    "baking": "gemma3n:e4b",
    "gaming": "gemma3n:e4b",
    "smalltalk": "gemma3n:e4b",
    "anime": "gemma3:4b",
    "fox_philosophy": "gemma3n:e4b",
    "fallback": "deepseek-r1:7b"
}

# OpenRouter Expert Overrides (Primary, lokal bleibt als Fallback)
EXPERT_OPENROUTER_OVERRIDES = {
    "bio": OPENROUTER_MODEL_BIO,       # OLMo 32B Think statt 7B lokal
    "med": OPENROUTER_MODEL_MED,       # Qwen3 235B statt kaputtes Meditron
    "physics": OPENROUTER_MODEL_PHYSICS,  # qwen3.5 9b - lokal zu langsam (14min!)
    "code": OPENROUTER_MODEL_CODE,     # qwen3.5 9b - lokal zu langsam
    "math": OPENROUTER_MODEL_MATH,     # Gemma 4 MoE
    "anime": "google/gemma-4-26b-a4b-it",  # Gemma 4 MoE, Web-Search für 2023+ als Safety Net
    "fox_philosophy": "google/gemma-4-26b-a4b-it",  # YourAIs persönlicher Philosophie-Experte
    "chemie": "essentialai/rnj-1-instruct",        # RNJ-1 (top bei Chemie laut Reddit, lokal killt die VM!)
}

# Expert Fallback Chains (OpenRouter models array)
# Wenn Primary 👎 kriegt → nächstes Model in der Liste
# Jedes Model ist ein anderer "Typ" → kein Doppel-Routing
# Letzter Eintrag "openrouter/auto" = OpenRouter wählt selbst
EXPERT_FALLBACK_CHAINS = {
    "bio": [
        "google/gemma-4-26b-a4b-it",       # Gemma 4 MoE (Primary)
        "openai/gpt-oss-120b",              # GPT-OSS 120B
        "openrouter/auto",                  # OpenRouter Auto-Route
    ],
    "physics": [
        "qwen/qwen3.5-9b",                 # Qwen 3.5 9B (Primary)
        "google/gemma-4-26b-a4b-it",       # Gemma 4 MoE Fallback
        "openrouter/auto",                  # OpenRouter Auto-Route
    ],
    "code": [
        "qwen/qwen3.5-9b",                 # Qwen 3.5 9B (Primary)
        "openai/gpt-oss-120b",              # GPT-OSS 120B (code is okay)
        "google/gemma-4-26b-a4b-it",       # Gemma 4 MoE Fallback
        "openrouter/auto",                  # OpenRouter Auto-Route
    ],
    "math": [
        "nvidia/nemotron-3-nano-30b-a3b",   # Nemotron Nano 30B (99.2%!)
        "google/gemma-4-26b-a4b-it",       # Gemma 4 MoE Fallback
        "openrouter/auto",                  # OpenRouter Auto-Route
    ],
    "med": [
        "qwen/qwen3-235b-a22b-2507",            # Qwen3 235B (Primary, best)
        "google/gemma-4-26b-a4b-it",       # Gemma 4 MoE Fallback
        "openrouter/auto",                  # OpenRouter Auto-Route
    ],
    "chemie": [
        "essentialai/rnj-1-instruct",       # RNJ-1 (Primary, top bei Chemie)
        "google/gemma-4-26b-a4b-it",       # Gemma 4 MoE Fallback
        "openrouter/auto",                  # OpenRouter Auto-Route
    ],
    "gaming": [
        "google/gemma-4-26b-a4b-it",       # Gemma 4 MoE
        "openrouter/auto",                  # OpenRouter Auto-Route
    ],
    "anime": [
        "google/gemma-4-26b-a4b-it",       # Gemma 4 MoE (Primary)
        "openrouter/auto",                  # OpenRouter Auto-Route
    ],
    "fox_philosophy": [
        "google/gemma-4-26b-a4b-it",       # Gemma 4 MoE (Primary)
        "openrouter/auto",                  # OpenRouter Auto-Route
    ],
    # baking: lokal only, kein Fallback nötig
}


# ==========================================
# THINKING MODE CONFIGURATION
# ==========================================
# Basierend auf echten Model-Docs recherchiert!
# 
# Typen:
#   "native"   = Hat Thinking standardmäßig AN (deepseek-r1, olmo-think)
#   "explicit" = Hat Thinking, aber explizit aktivieren ist besser (nemotron)
#   "qwen"     = Braucht /think prompt (qwen3)
#   "openrouter" = Über API, Thinking wird vom Provider gehandelt
#   "none"     = Kein Thinking Support

THINKING_MODELS = {
    # Qwen3/3.5 Familie - braucht /think trigger
    "qwen3": "qwen",
    "qwen3.5": "qwen",
    
    # Nemotron - Hat natives Thinking, aber explizit aktivieren ist besser
    "nemotron": "explicit",
    "nemotron-3": "explicit",
    "nemotron-3-nano": "explicit",
    
    # OpenRouter Nemotron - Thinking wird serverseitig gehandelt
    "nvidia/llama-3.3-nemotron": "openrouter",
    "nvidia/nemotron-3": "openrouter",
    
    # OpenRouter Qwen3.5 (Coherence Guard)
    "qwen/qwen3.5": "openrouter",
    
    # OpenRouter OLMo 3.1 32B Think (Bio Expert)
    "allenai/olmo-3.1-32b-think": "openrouter",
    
    # OpenRouter Qwen3 235B (Med Expert)
    "qwen/qwen3-235b": "openrouter",
    
    # Deepseek-R1 - Hat natives <think> Reasoning
    "deepseek": "native",
    "deepseek-r1": "native",
    
    # Olmo-3-Think (HuggingFace Version) - Hat natives Thinking
    "olmo-3-7b-think": "native",
    "hf.co/unsloth/olmo-3-7b-think": "native",
    
    # KEIN Thinking Support:
    "olmo-3": "none",
    "olmo3": "none",
    "rnj-1": "none",
    "gemma3": "none",
    "gemma3n": "none",
    "dolphin": "none",
    "meditron": "none",
}


# ==========================================
# THINKING HELPER FUNCTIONS
# ==========================================

def get_thinking_type(model_name: str) -> str:
    """
    Ermittelt den Thinking-Typ für ein Model.
    
    Returns:
        "native", "explicit", "qwen", "openrouter", oder "none"
    """
    model_lower = model_name.lower()
    
    # Exakter Match
    if model_lower in THINKING_MODELS:
        return THINKING_MODELS[model_lower]
    
    # Prefix Match (z.B. "qwen3.5:2b" matcht "qwen3.5")
    for key, value in THINKING_MODELS.items():
        if model_lower.startswith(key):
            return value
    
    # Special: Check for "think" in model name
    if "think" in model_lower:
        return "native"
    
    # Default: none (sicher)
    return "none"


def create_thinking_llm(model: str, base_url: str, temperature: float = 0.7, keep_alive: str = "5m"):
    """
    Erstellt ein ChatOllama LLM (für lokale Models).
    Thinking wird je nach Model automatisch aktiviert.
    """
    return ChatOllama(
        model=model, 
        base_url=base_url, 
        temperature=temperature, 
        keep_alive=keep_alive
    )


def create_openrouter_client():
    """
    Erstellt einen OpenAI-kompatiblen Client für OpenRouter.
    Returns None wenn kein API Key gesetzt ist.
    """
    if not OPENROUTER_API_KEY:
        return None
    
    try:
        from openai import OpenAI
        return OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_API_KEY,
            timeout=60.0,  # 60s Timeout damit wir nie endlos hängen
        )
    except ImportError:
        log("CONFIG", "⚠️ openai package nicht installiert! pip install openai", Fore.YELLOW)
        return None


def call_openrouter(
    system_prompt: str,
    user_message: str,
    model: Optional[str] = None,
    models: Optional[list] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    extra_params: Optional[dict] = None,
) -> tuple:
    """
    Ruft ein Model über OpenRouter auf und wirft passende YourAI-Exceptions bei Fehlern.

    Args:
        model: Single model ID (standard mode)
        models: List of model IDs for auto-fallback (OpenRouter tries in order)
                If provided, takes priority over model parameter.

    Returns:
        Tuple of (content: str, used_model: str|None)
        used_model is the model OpenRouter actually used (from response metadata).
    """
    target_model = model or OPENROUTER_MODEL
    client = create_openrouter_client()

    if not client:
        raise YourAIConfigError("OpenRouter nicht verfügbar (Kein API Key oder 'openai' fehlt)", key="OPENROUTER_API_KEY")

    # Build request kwargs
    request_kwargs = {
        "extra_headers": OPENROUTER_HEADERS,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
    }

    if models and len(models) > 1:
        # Multi-model fallback: OpenRouter tries each in order
        request_kwargs["model"] = models[0]  # SDK requires model field
        request_kwargs["extra_body"] = {"models": models, **(extra_params or {})}
        log_label = f"{models[0]} (+{len(models)-1} fallbacks)"
    else:
        request_kwargs["model"] = target_model
        if extra_params:
            request_kwargs["extra_body"] = extra_params
        log_label = target_model

    try:
        completion = client.chat.completions.create(**request_kwargs)
    except Exception as e:
        err_str = str(e).lower()
        # Rate Limit (429)
        if "429" in str(e) or "rate limit" in err_str or "too many requests" in err_str:
            raise YourAIRateLimitError(log_label, cause=e)
        # Model Not Found (404)
        if "404" in str(e) or "not found" in err_str or "no endpoints" in err_str:
            raise YourAIModelNotFoundError(log_label, host="openrouter.ai", cause=e)
        raise YourAILLMConnectionError(log_label, host="openrouter.ai", cause=e)

    msg = completion.choices[0].message
    content = msg.content

    # Track which model OpenRouter actually used
    used_model = getattr(completion, "model", None)

    # Reasoning-Modelle (qwen3.5, etc.) packen Output manchmal ins reasoning-Feld
    if content is None:
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
        if reasoning:
            content = reasoning

    if content is None:
        raise YourAILLMParseError(log_label, expected="Text Response", raw_preview="None")
    if not content.strip():
        raise YourAIEmptyResponseError(log_label, node="call_openrouter")

    return content, used_model


def call_openrouter_stream(
    system_prompt: str,
    user_message: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096
):
    """
    Streamt ein Model über OpenRouter und liefert Text-Chunks als Generator.
    Nur verwenden wenn USE_STREAMING=True.
    Wirft dieselben YourAI-Exceptions wie call_openrouter.
    """
    target_model = model or OPENROUTER_MODEL
    client = create_openrouter_client()

    if not client:
        raise YourAIConfigError(
            "OpenRouter nicht verfügbar (Kein API Key oder 'openai' fehlt)",
            key="OPENROUTER_API_KEY"
        )

    try:
        stream = client.chat.completions.create(
            extra_headers=OPENROUTER_HEADERS,
            model=target_model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                yield text
    except Exception as e:
        err_str = str(e).lower()
        if "429" in str(e) or "rate limit" in err_str or "too many requests" in err_str:
            raise YourAIRateLimitError(target_model, cause=e)
        if "404" in str(e) or "not found" in err_str or "no endpoints" in err_str:
            raise YourAIModelNotFoundError(target_model, host="openrouter.ai", cause=e)
        raise YourAILLMConnectionError(target_model, host="openrouter.ai", cause=e)


def maybe_add_think_prompt(message: str, model: str) -> str:
    """
    Fügt /think zum Prompt hinzu für Models die es brauchen.
    """
    if not USE_THINKING:
        return message
    
    thinking_type = get_thinking_type(model)
    
    if thinking_type in ["qwen", "explicit"]:
        if "/think" not in message.lower():
            return message + "\n\n/think"
    
    return message


def get_expert_model(domain: str) -> str:
    """Holt das lokale Model für eine Domain, fallback auf fallback."""
    return EXPERT_MODELS.get(domain, EXPERT_MODELS["fallback"])


def get_expert_openrouter_model(domain: str) -> Optional[str]:
    """
    Prüft ob eine Domain ein OpenRouter-Override hat.
    """
    if not USE_OPENROUTER:
        return None
    try:
        from tools.expert_pool import get_primary_model
        pooled = get_primary_model(domain)
        if pooled and pooled != "openrouter/auto":
            return pooled
    except Exception:
        pass
    return EXPERT_OPENROUTER_OVERRIDES.get(domain)


def get_expert_fallback_chain(domain: str, exclude_models: list = None) -> list:
    """
    Returns the fallback chain for an expert domain, excluding bad models.

    Args:
        domain: Expert domain (e.g. "bio", "math", "code")
        exclude_models: List of model IDs to skip (e.g. models with too many 👎)

    Returns:
        List of model IDs for OpenRouter's models array.
        Empty list if no chain exists or all models excluded.
    """
    if not USE_OPENROUTER:
        return []
    try:
        from tools.expert_pool import get_model_chain
        return get_model_chain(domain, exclude_models=exclude_models)
    except Exception:
        pass
    chain = EXPERT_FALLBACK_CHAINS.get(domain, [])
    if not exclude_models:
        return chain
    # Filter out bad models, but always keep "openrouter/auto" as last resort
    return [m for m in chain if m not in exclude_models or m == "openrouter/auto"]
