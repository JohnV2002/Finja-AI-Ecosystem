"""
YourAI Runtime Configuration
===========================
Central configuration values, model selectors, feature flags, and model factory helpers.

Main Responsibilities:
- Load environment configuration and expose runtime feature flags.
- Define local and OpenRouter model IDs for YourAI, routing, experts, memory, and utility nodes.
- Provide helper functions that create configured chat model clients.

Side Effects:
- Reads environment variables and optional .env files.
- Instantiates model client helpers that may connect to local or remote LLM providers when used.
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
# .ENV LADEN (falls vorhanden)
# ==========================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Manueller .env Parser als Fallback (kein python-dotenv installiert)
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        for line in _env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip("'\"")
                os.environ.setdefault(key.strip(), value)

# ==========================================
# EXPERT POOL SETTINGS
# ==========================================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLM_STATS_API_KEY = os.environ.get("LLM_STATS_API_KEY", "")
LLM_STATS_BASE_URL = os.environ.get("LLM_STATS_BASE_URL", "https://api.zeroeval.com")
EXPERT_POOL_FILE = os.environ.get("EXPERT_POOL_FILE", os.path.join(_PROJECT_ROOT, "expert_model_pool.json"))
EXPERT_POOL_LOCK_FILE = os.environ.get("EXPERT_POOL_LOCK_FILE", EXPERT_POOL_FILE + ".lock")
EXPERT_POOL_PRICE_CAP_USD_PER_M = float(os.environ.get("EXPERT_POOL_PRICE_CAP_USD_PER_M", "0.60"))
EXPERT_POOL_TOP_N = int(os.environ.get("EXPERT_POOL_TOP_N", "3"))

# ==========================================
# HOST CONFIGURATION
# ==========================================

# HOST 1: standard/local/Docker endpoint for smaller models.
LLM_HOST_STD = "https://ollama.your-domain.example.com/"

# HOST 2: main PC endpoint for larger models.
LLM_HOST_MAIN = os.environ.get("LLM_HOST_MAIN", "http://YOUR_LLM_HOST:11434")  # NOSONAR


# ==========================================
# OPENROUTER CONFIGURATION (NEU!)
# ==========================================
# Schneller als lokal, günstig (~0.005$/Request = ~1€/200 Requests)
# API Key: https://openrouter.ai/keys

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_HOST = "openrouter.ai"
OPENROUTER_BASE_URL = f"https://{OPENROUTER_HOST}/api/v1"
OPENROUTER_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
OPENROUTER_AUTO = "openrouter/auto"

GEMMA_4 = "google/gemma-4-26b-a4b-it"
QWEN_35_9B = "qwen/qwen3.5-9b"
KIMI_26 = "moonshotai/kimi-k2.6"
GEMINI_31_PRO = "google/gemini-3.1-pro-preview"
GPT_OSS_120B = "openai/gpt-oss-120b"

# Additional OpenRouter models for nodes that are unreliable locally.
OPENROUTER_MODEL_COHERENCE = "microsoft/phi-4"                     # Autonomy Guard (Phi 4, 14B, kein Thinking, pures Reasoning)
OPENROUTER_MODEL_PROMISE = "microsoft/phi-4"                       # Promise Check (Phi 4, gleicher Trick wie Guardian)
OPENROUTER_MODEL_MEMORY = GEMMA_4                                 # Hippocampus Memory (Gemma 4 MoE)
OPENROUTER_MODEL_STYLE = "qwen/qwen-2.5-72b-instruct"             # User writing style analysis / Mood-Snapshot (Qwen2.5 72B — #9 Writing, $0.36/$0.40/M)
OPENROUTER_MODEL_BIO = GEMMA_4                                    # Bio Expert (Gemma 4 MoE, mehr Wissen als 3-27B)
OPENROUTER_MODEL_MED = "qwen/qwen3-235b-a22b-2507"                      # Med Expert (~0.07$/M in) — bleibt Qwen, med braucht max Qualität
OPENROUTER_MODEL_PHYSICS = QWEN_35_9B                       # Physics Expert (~0.10$/M in) — bleibt Qwen, gut bei STEM
OPENROUTER_MODEL_CODE = QWEN_35_9B                          # Code Expert (~0.10$/M in) — bleibt Qwen, top bei Code
OPENROUTER_MODEL_MATH = GEMMA_4                                   # Math Expert (Gemma 4 MoE)
OPENROUTER_MODEL_PSYCHOLOGY = "google/gemini-2.5-flash"          # Psychology Expert (best in Admin's real-case tests)
OPENROUTER_MODEL_WRITING = GEMMA_4                               # Writing Expert (cheap Gemma family)
OPENROUTER_MODEL_SOCIAL_MEDIA = GEMMA_4                          # Social Media Expert (cheap Gemma family)
OPENROUTER_MODEL_HOMELAB = OPENROUTER_MODEL_CODE                 # Homelab Expert (same models as code, different prompt)
OPENROUTER_MODEL_NUTRITION = KIMI_26              # Nutrition Expert (Kimi K2.6)
OPENROUTER_MODEL_MUSIC = GEMMA_4                                 # Music Expert (cheap Gemma family)
OPENROUTER_MODEL_MYTHOLOGY = KIMI_26              # Mythology Expert (Kimi K2.6)
OPENROUTER_MODEL_PETS = GEMMA_4                                  # Pets Expert (cheap Gemma family)
OPENROUTER_MODEL_PLANTS = GEMMA_4                                # Plants Expert (cheap Gemma family)
OPENROUTER_MODEL_FINANCE_BASIC = GEMMA_4                         # Finance Basic Expert (education only)
OPENROUTER_MODEL_LAW_RESEARCH = GEMINI_31_PRO   # Law Research Expert (source-first)
OPENROUTER_MODEL_MECHANIC = GEMMA_4                              # Mechanic Expert (two-pass search when needed)
OPENROUTER_MODEL_GEO = GEMINI_31_PRO           # Geo Expert (Gemini 3.1 Pro Preview)
OPENROUTER_MODEL_HISTORY = KIMI_26                # History Expert (Kimi K2.6, optional search)
OPENROUTER_MODEL_ROUTER = GEMMA_4                                 # Router (Gemma 4 MoE, präziser als 3-12B)
OPENROUTER_MODEL_SUBCONSCIOUS = "qwen/qwen3-8b"                   # thought generator (klein, kreativ, billig — $0.05/M in)

# Branding headers for OpenRouter.
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
USE_EPISODIC = True         # Diary (episodic diary).
USE_PROMISE_CHECK = True    # promise detection (Action/Mood)
USE_TWITCH = False          # Twitch Integration
USE_DISCORD = True         # Discord Integration
USE_GRANITE = False         # Safety Filter (False = training mode enabled)
USE_USERS = False           # Twitch User Tracking
USE_THINKING = True         # Thinking mode for supported models
USE_COHERENCE_CHECK = True  # Autonomy Guardian
USE_TOOLS = True            # tool calls
USE_SPOTIFY = True          # Spotify music context
USE_STREAMING = True        # Stream YourAI's OpenRouter response → Tools feuern sofort beim ersten Tag-Token
USE_WEB_SEARCH = True       # Web Search via Docker Crawler
USE_PAPERLESS = True        # Paperless-NGX document management (Admin-only)
USE_HOME_ASSISTANT = True   # Home Assistant Smart Home (Admin-only)
USE_IMAGE_GEN = True        # Image Generation via OpenRouter
USE_PROMPT_ROUTER = True    # Semantic Prompt Router: inject only relevant sections (token savings)
USE_SUBCONSCIOUS = True     # YourAI Active subconscious loop for proactive DMs.
USE_MAINTENANCE = False     # Maintenance Mode: non-admins see maintenance page
USE_CONSOLE_LOG = True      # Console output (False = quiet, useful for Docker)

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
IMAGE_LIMITS_FILE = os.path.join(_PROJECT_ROOT, "image_usage.json")

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
# SUBCONSCIOUS / YOURAI AKTIV SETTINGS
# ==========================================
SUBCONSCIOUS_DAILY_LIMIT = 5        # Max autonome DMs pro Tag
SUBCONSCIOUS_COOLDOWN_MIN = 60      # Minuten Cooldown zwischen Triggers
SUBCONSCIOUS_THOUGHT_TEMP = 1.0     # Temperature for thought generation (1.0 = maximum creativity)
SUBCONSCIOUS_THOUGHT_MAX_TOKENS = 150  # Max Tokens pro Gedanke
SUBCONSCIOUS_BOREDOM_IDLE_MIN = 30      # Vorher zaehlt aktive Chat-Session als nicht gelangweilt
SUBCONSCIOUS_BOREDOM_FULL_MIN = 360     # Ab hier ist Boredom nahe 100%
SUBCONSCIOUS_CATEGORY_COOLDOWNS_MIN = {
    "care_ping": 180,
    "promise_check": 120,
    "memory_link": 90,
    "reflection": 60,
    "creative": 45,
}

# ==========================================
# HIPPOCAMPUS / MEMORY SETTINGS
# ==========================================
MEMORY_API_BASE = os.environ.get("MEMORY_API_BASE", "http://YOUR_MEMORY_API:8007")  # NOSONAR
MEMORY_API_KEY = os.environ.get("MEMORY_API_KEY", "")

# Embedding Model (OpenRouter)
HIPPOCAMPUS_EMBEDDING_OPENROUTER = "qwen/qwen3-embedding-8b"

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

PROMISE_CHECK_TIMEOUT = 60.0    # seconds for LLM promise checks (15 was too short)

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
WEB_CRAWLER_URL = os.environ.get("WEB_CRAWLER_URL", "http://YOUR_WEB_CRAWLER:8080/search")  # NOSONAR
WEB_CRAWLER_TOKEN = os.environ.get("BEARER_WEBCRAWLER", "")
WEB_CRAWLER_TIMEOUT = 15        # seconds
WEB_CRAWLER_MAX_RESULTS = 5     # max results per search

# ==========================================
# PAPERLESS-NGX SETTINGS
# ==========================================
PAPERLESS_URL = "https://paperless.your-domain.example.com"
PAPERLESS_TOKEN = os.environ.get("PAPERLESS", "")
PAPERLESS_TIMEOUT = 15          # seconds
PAPERLESS_MAX_RESULTS = 10      # max documents per search

# ==========================================
# HOME ASSISTANT SETTINGS
# ==========================================
HOMEASSISTANT_URL = os.environ.get("HOMEASSISTANT_URL", "http://YOUR_HOME_ASSISTANT:8123")  # NOSONAR
HOMEASSISTANT_TOKEN = os.environ.get("HOMEASSISTANT_TOKEN", "")
HOMEASSISTANT_TIMEOUT = 10      # seconds

TRIGGER_CHANCE = 0.001          # Chance pro Request (0.001 = 0.1%)
FETCH_TIMEOUT = 15              # seconds for website fetch
DEPLOY_TIMEOUT = 30             # seconds for deploy API requests

# Maximum number of characters YourAI may process.
MAX_HTML_CHARS = 50000
MAX_CSS_CHARS = 50000
MAX_JS_CHARS = 10000

# LOCAL PATHS (preferred; bypasses Cloudflare manipulation)
# Uses .env variables when set (e.g. "/var/www/your-domain.example.com/yourai.html")
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
GUARD_MAX_TOKENS = 2048          # High enough for reasoning plus JSON output
GUARD_MAX_MEMORIES = 8           # Send only the N most relevant memories to the guard
GUARD_MAX_DIARY_CHARS = 300      # Diary-Kontext kürzen (war 500)
GUARD_MAX_HISTORY_MSGS = 3       # Only last N chat messages (war 4)

# ==========================================
# EYES
# ==========================================
# Das Modell muss Multimodal sein (Bilder verstehen)!
# OpenRouter Vision (ZDR supported, günstig, kein lokaler RAM nötig)
VISION_MODEL = QWEN_35_9B  # Vision + Thinking, Output ~3x billiger als qwen3-vl-8b-instruct ($0.15 vs $0.50/M)
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

# Custom Discord emojis: name -> description for YourAI.
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
TTS_LIMITS_FILE = os.path.join(_PROJECT_ROOT, "docker_data", "tts_usage.json")

# ==========================================
# DASHBOARD SETTINGS
# ==========================================
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:8051")
DASHBOARD_MAX_EVENTS = 2000
DASHBOARD_DEFAULT_USER = "admin"
DASHBOARD_DEFAULT_MODE = "yourai"
DEBUG_LOG_FILE = os.path.join(_PROJECT_ROOT, "debug_log.jsonl")
DEBUG_LOG_MAX_LINES = 10000  # Rotate when file exceeds this

# YourAI Output Log — plain .txt, nur YourAIs Antworten, 1:1 mit Emojis
YOURAI_OUTPUT_FILE = os.path.join(_PROJECT_ROOT, "yourai_output.txt")
YOURAI_OUTPUT_MAX_BYTES = 15 * 1024 * 1024  # 15 MB; stop writing after this limit

# ==========================================
# USERS SETTINGS
# ==========================================
USERS_DB_FILE = "users_db.json"
ADMIN_USERNAME = "your_streamer_name"

# ==========================================
# MEMORY SERVER SETTINGS
# ==========================================
MEMORY_MAX_RAM_MEMORIES = 5000
MEMORY_BACKUP_INTERVAL = 600          # seconds (10 min)
MEMORY_CACHE_TIMEOUT = 600            # seconds (10 min)
MEMORY_CLEANUP_CHECK_INTERVAL = 60    # seconds (1 min)
MEMORY_USER_DIR = "user_memories"
MEMORY_AUDIO_DIR = "user_audio"
MEMORY_TTS_CACHE_DIR = "tts_cache"
MEMORY_BACKUP_DIR = "backups"

# ==========================================
# HIPPOCAMPUS TIMEOUTS & LIMITS
# ==========================================
HIPPOCAMPUS_STATS_TIMEOUT = 0.5       # seconds for stats requests
HIPPOCAMPUS_EMBED_MAX_LENGTH = 500    # Maximum characters for embedding prompts
HIPPOCAMPUS_MIN_TEXT_LENGTH = 10      # Minimum text length for memory extraction

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
LAB_FETCH_URL   = os.environ.get("LAB_FETCH_URL", "")        # e.g. https://lab.your-domain.example.com/index.html
LAB_CSS_URL     = os.environ.get("LAB_CSS_URL", "")          # e.g. https://lab.your-domain.example.com/lab.css
LAB_JS_URL      = os.environ.get("LAB_JS_URL", "")           # e.g. https://lab.your-domain.example.com/lab.js
LAB_DEPLOY_URL  = os.environ.get("LAB_DEPLOY_URL", "")       # e.g. https://lab.your-domain.example.com/api/lab_deploy.php
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
TOKEN_SOFT_LIMIT = 80000  # Auto-Flush wenn Session dieses Limit ueberschreitet


# ==========================================
# MODEL CONFIGURATION
# ==========================================

# Safety & Routing (kleine, schnelle Modelle - IMMER lokal)
MODEL_GEMMA3_4B = "gemma3:4b"
MODEL_QWEN35_9B = "qwen3.5:9b"
MODEL_GEMMA3_E4B = "gemma3n:e4b"
MODEL_GRANITE = "qwen3.5:2b"        # Safety Filter
MODEL_ROUTER = MODEL_GEMMA3_4B             # Request Routing (1b zu dumm "Other", e4b nur smalltalk)
MODEL_COHERENCE = MODEL_QWEN35_9B      # Autonomy Guard - LOKAL FALLBACK (Primary: Phi 4 via OpenRouter)
MODEL_COHERENCE_OPENROUTER = OPENROUTER_MODEL_COHERENCE  # Primary: Phi 4
MODEL_CHECK_PASS = "qwen3.5:0.8b"   # Password Check
MODEL_PROMISE_CHECK = MODEL_GEMMA3_4B   # Promise Detection (qwen3:1.7b war zu klein, leere Responses)
MODEL_TOOL_ROUTER = "functiongemma"  # Für komplexe Tool-Erkennung

# YourAI Main - OpenRouter (PRIMARY)
# Wird automatisch verwendet wenn OPENROUTER_API_KEY gesetzt ist
MODEL_YOURAI_OPENROUTER = OPENROUTER_MODEL

# YourAI Fallback - Lokale Models
MODEL_YOURAI_LOCAL_PRIMARY = "nemotron-3-nano:30b"   # Main PC (Fallback 1)
MODEL_YOURAI_LOCAL_FALLBACK = "deepseek-r1:14b"      # Standard Host (Fallback 2)

# Legacy aliases for compatibility.
MODEL_YOURAI_PRIMARY = MODEL_YOURAI_OPENROUTER if USE_OPENROUTER else MODEL_YOURAI_LOCAL_PRIMARY
MODEL_YOURAI_FALLBACK = MODEL_YOURAI_LOCAL_FALLBACK

# Uncensored Mode
MODEL_UNCENSORED = "thedrummer/unslopnemo-12b"

# Expert Models (Domain-spezifisch, OpenRouter-first mit lokalem Fallback)
EXPERT_MODELS = {
    "bio": "hf.co/unsloth/Olmo-3-7B-Think-GGUF:q8_0",
    "physics": MODEL_QWEN35_9B,
    "code": MODEL_QWEN35_9B,
    "chemie": "rnj-1",
    "math": MODEL_GEMMA3_4B,                  # Server-Fallback (phi4-mini too large for Docker)
    "med": MODEL_QWEN35_9B,
    "psychology": MODEL_GEMMA3_4B,
    "writing": MODEL_GEMMA3_4B,
    "social_media": MODEL_GEMMA3_4B,
    "homelab": MODEL_QWEN35_9B,
    "nutrition": MODEL_GEMMA3_4B,
    "music": MODEL_GEMMA3_4B,
    "mythology": MODEL_GEMMA3_4B,
    "pets": MODEL_GEMMA3_4B,
    "plants": MODEL_GEMMA3_4B,
    "finance_basic": MODEL_GEMMA3_4B,
    "law_research": MODEL_GEMMA3_4B,
    "mechanic": MODEL_GEMMA3_4B,
    "geo": MODEL_GEMMA3_4B,
    "history": MODEL_GEMMA3_4B,
    "baking": MODEL_GEMMA3_E4B,
    "gaming": MODEL_GEMMA3_E4B,
    "smalltalk": MODEL_GEMMA3_E4B,
    "anime": MODEL_GEMMA3_4B,
    "fox_philosophy": MODEL_GEMMA3_E4B,
    "fallback": "deepseek-r1:7b"
}

# OpenRouter Expert Overrides (Primary, lokal bleibt als Fallback)
EXPERT_OPENROUTER_OVERRIDES = {
    "bio": OPENROUTER_MODEL_BIO,       # OLMo 32B Think statt 7B lokal
    "med": OPENROUTER_MODEL_MED,       # Qwen3 235B statt kaputtes Meditron
    "physics": OPENROUTER_MODEL_PHYSICS,  # qwen3.5 9b - lokal zu langsam (14min!)
    "code": OPENROUTER_MODEL_CODE,     # qwen3.5 9b - lokal zu langsam
    "math": OPENROUTER_MODEL_MATH,     # Gemma 4 MoE
    "psychology": OPENROUTER_MODEL_PSYCHOLOGY,  # Gemini 2.5 Flash
    "writing": OPENROUTER_MODEL_WRITING,  # Gemma 4 MoE
    "social_media": OPENROUTER_MODEL_SOCIAL_MEDIA,  # Gemma 4 MoE
    "homelab": OPENROUTER_MODEL_HOMELAB,  # same as code
    "nutrition": OPENROUTER_MODEL_NUTRITION,  # Kimi K2.6
    "music": OPENROUTER_MODEL_MUSIC,  # Gemma 4 MoE
    "mythology": OPENROUTER_MODEL_MYTHOLOGY,  # Kimi K2.6
    "pets": OPENROUTER_MODEL_PETS,  # Gemma 4 MoE
    "plants": OPENROUTER_MODEL_PLANTS,  # Gemma 4 MoE
    "finance_basic": OPENROUTER_MODEL_FINANCE_BASIC,  # Gemma 4 MoE
    "law_research": OPENROUTER_MODEL_LAW_RESEARCH,  # Gemini 3.1 Pro Preview
    "mechanic": OPENROUTER_MODEL_MECHANIC,  # Gemma 4 MoE
    "geo": OPENROUTER_MODEL_GEO,  # Gemini 3.1 Pro Preview
    "history": OPENROUTER_MODEL_HISTORY,  # Kimi K2.6
    "anime": GEMMA_4,  # Gemma 4 MoE, web search for 2023+ as safety net
    "fox_philosophy": GEMMA_4,  # YourAIs persönlicher Philosophie-Experte
    "chemie": "essentialai/rnj-1-instruct",        # RNJ-1 (top bei Chemie laut Reddit, lokal killt die VM!)
}

# Expert Fallback Chains (OpenRouter models array)
# If the primary model receives negative feedback, use the next model in the list.
# Jedes Model ist ein anderer "Typ" → kein Doppel-Routing
# Letzter Eintrag "openrouter/auto" = OpenRouter wählt selbst
EXPERT_FALLBACK_CHAINS = {
    "bio": [
        GEMMA_4,       # Gemma 4 MoE (Primary)
        GPT_OSS_120B,              # GPT-OSS 120B
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "physics": [
        QWEN_35_9B,                 # Qwen 3.5 9B (Primary)
        GEMMA_4,       # Gemma 4 MoE Fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "code": [
        QWEN_35_9B,                 # Qwen 3.5 9B (Primary)
        GPT_OSS_120B,              # GPT-OSS 120B (code is okay)
        GEMMA_4,       # Gemma 4 MoE Fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "math": [
        "nvidia/nemotron-3-nano-30b-a3b",   # Nemotron Nano 30B (99.2%!)
        GEMMA_4,       # Gemma 4 MoE Fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "med": [
        "qwen/qwen3-235b-a22b-2507",            # Qwen3 235B (Primary, best)
        GEMMA_4,       # Gemma 4 MoE Fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "psychology": [
        "google/gemini-2.5-flash",          # Gemini 2.5 Flash (Primary)
        GEMMA_4,        # Gemma 4 MoE fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "writing": [
        GEMMA_4,        # Gemma 4 MoE (Primary)
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "social_media": [
        GEMMA_4,        # Gemma 4 MoE (Primary)
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "homelab": [
        QWEN_35_9B,                 # same as code
        GPT_OSS_120B,              # GPT-OSS 120B
        GEMMA_4,       # Gemma 4 MoE Fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "nutrition": [
        KIMI_26,             # Kimi K2.6 (Primary)
        GEMMA_4,        # Gemma 4 MoE fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "music": [
        GEMMA_4,        # Gemma 4 MoE (Primary)
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "mythology": [
        KIMI_26,             # Kimi K2.6 (Primary)
        GEMMA_4,        # Gemma 4 MoE fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "pets": [
        GEMMA_4,        # Gemma 4 MoE (Primary)
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "plants": [
        GEMMA_4,        # Gemma 4 MoE (Primary)
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "finance_basic": [
        GEMMA_4,        # Gemma 4 MoE (Primary)
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "law_research": [
        GEMINI_31_PRO,    # Gemini 3.1 Pro Preview (Primary)
        KIMI_26,             # Kimi K2.6 fallback
        GEMMA_4,        # Gemma 4 MoE fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "mechanic": [
        GEMMA_4,        # Gemma 4 MoE (Primary)
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "geo": [
        GEMINI_31_PRO,    # Gemini 3.1 Pro Preview (Primary)
        GEMMA_4,        # Gemma 4 MoE fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "history": [
        KIMI_26,              # Kimi K2.6 (Primary)
        GEMMA_4,        # Gemma 4 MoE fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "chemie": [
        "essentialai/rnj-1-instruct",       # RNJ-1 (Primary, top bei Chemie)
        GEMMA_4,       # Gemma 4 MoE Fallback
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "gaming": [
        GEMMA_4,       # Gemma 4 MoE
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "anime": [
        GEMMA_4,       # Gemma 4 MoE (Primary)
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
    ],
    "fox_philosophy": [
        GEMMA_4,       # Gemma 4 MoE (Primary)
        OPENROUTER_AUTO,                  # OpenRouter Auto-Route
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
    Determines the thinking mode type for a model.
    
    Returns:
        "native", "explicit", "qwen", "openrouter", oder "none"
    """
    model_lower = model_name.lower()
    
    # Exact match
    if model_lower in THINKING_MODELS:
        return THINKING_MODELS[model_lower]
    
    # Prefix match (e.g. "qwen3.5:2b" matcht "qwen3.5")
    for key, value in THINKING_MODELS.items():
        if model_lower.startswith(key):
            return value
    
    # Special: Check for "think" in model name
    if "think" in model_lower:
        return "native"
    
    # Default: none (safe)
    return "none"


def create_thinking_llm(model: str, base_url: str, temperature: float = 0.7, keep_alive: str = "5m"):
    """
    Creates a ChatOllama LLM for local models.
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
    Creates an OpenAI-compatible client for OpenRouter.
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
        log("CONFIG", "⚠️ openai package not installed! pip install openai", Fore.YELLOW)
        return None


def _build_openrouter_kwargs(
    system_prompt: str,
    user_message: str,
    target_model: str,
    models: Optional[list],
    temperature: float,
    max_tokens: int,
    extra_params: Optional[dict],
) -> tuple[dict, str]:
    """Helper to construct parameters and label for OpenRouter chat creation."""
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

    return request_kwargs, log_label


def _handle_openrouter_exception(e: Exception, log_label: str) -> None:
    """Helper to classify and raise correct YourAI exceptions for OpenRouter errors."""
    err_str = str(e).lower()
    # Rate Limit (429)
    if "429" in str(e) or "rate limit" in err_str or "too many requests" in err_str:
        raise YourAIRateLimitError(log_label, cause=e)
    # Model Not Found (404)
    if "404" in str(e) or "not found" in err_str or "no endpoints" in err_str:
        raise YourAIModelNotFoundError(log_label, host=OPENROUTER_HOST, cause=e)
    raise YourAILLMConnectionError(log_label, host=OPENROUTER_HOST, cause=e)


def call_openrouter(
    system_prompt: str,
    user_message: str,
    model: Optional[str] = None,
    models: Optional[list] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    extra_params: Optional[dict] = None,
    return_usage: bool = False,  # noqa: ARG001 — kept for caller compatibility; usage is always returned
) -> tuple:
    """
    Ruft ein Model über OpenRouter auf und wirft passende YourAI-Exceptions bei Fehlern.

    Args:
        model: Single model ID (standard mode)
        models: List of model IDs for auto-fallback (OpenRouter tries in order)
                If provided, takes priority over model parameter.

    Returns:
        Tuple of (content: str, used_model: str|None, usage: dict)
    """
    target_model = model or OPENROUTER_MODEL
    client = create_openrouter_client()

    if not client:
        raise YourAIConfigError("OpenRouter nicht verfügbar (missing API key or openai package)", key="OPENROUTER_API_KEY")

    request_kwargs, log_label = _build_openrouter_kwargs(
        system_prompt=system_prompt,
        user_message=user_message,
        target_model=target_model,
        models=models,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_params=extra_params
    )

    try:
        completion = client.chat.completions.create(**request_kwargs)
    except Exception as e:
        _handle_openrouter_exception(e, log_label)

    msg = completion.choices[0].message
    content = msg.content

    # Track which model OpenRouter actually used
    used_model = getattr(completion, "model", None)

    # Token usage (Phase 1 Refactor)
    usage = {
        "prompt_tokens": getattr(completion.usage, "prompt_tokens", 0),
        "completion_tokens": getattr(completion.usage, "completion_tokens", 0),
        "total_tokens": getattr(completion.usage, "total_tokens", 0),
    }

    # Reasoning-Modelle (qwen3.5, etc.) packen Output manchmal ins reasoning-Feld
    if content is None:
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
        if reasoning:
            content = reasoning

    if content is None:
        raise YourAILLMParseError(log_label, expected="Text Response", raw_preview="None")
    if not content.strip():
        raise YourAIEmptyResponseError(log_label, node="call_openrouter")

    return content, used_model, usage


def call_openrouter_stream(
    system_prompt: str,
    user_message: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    usage_callback=None,
):
    """
    Streamt ein Model über OpenRouter und liefert Text-Chunks als Generator.
    Use only when USE_STREAMING=True.
    Raises the same YourAI exceptions as call_openrouter.
    """
    target_model = model or OPENROUTER_MODEL
    client = create_openrouter_client()

    if not client:
        raise YourAIConfigError(
            "OpenRouter nicht verfügbar (missing API key or openai package)",
            key="OPENROUTER_API_KEY"
        )

    try:
        stream = client.chat.completions.create(
            extra_headers=OPENROUTER_HEADERS,
            model=target_model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage and usage_callback:
                usage_callback({
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(usage, "completion_tokens", 0),
                    "total_tokens": getattr(usage, "total_tokens", 0),
                })
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
            raise YourAIModelNotFoundError(target_model, host=OPENROUTER_HOST, cause=e)
        raise YourAILLMConnectionError(target_model, host=OPENROUTER_HOST, cause=e)


def maybe_add_think_prompt(message: str, model: str) -> str:
    """
    Adds /think to prompts for models that require it.
    """
    if not USE_THINKING:
        return message
    
    thinking_type = get_thinking_type(model)
    
    if thinking_type in ["qwen", "explicit"] and "/think" not in message.lower():
        return message + "\n\n/think"
    
    return message


def get_expert_model(domain: str) -> str:
    """Returns the local model configured for a domain, falling back to the fallback model."""
    return EXPERT_MODELS.get(domain, EXPERT_MODELS["fallback"])


def get_expert_openrouter_model(domain: str) -> Optional[str]:
    """
    Checks whether a domain has an OpenRouter override.
    """
    if not USE_OPENROUTER:
        return None
    try:
        from tools.expert_pool import get_primary_model
        pooled = get_primary_model(domain)
        if pooled and pooled != OPENROUTER_AUTO:
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
    return [m for m in chain if m not in exclude_models or m == OPENROUTER_AUTO]

