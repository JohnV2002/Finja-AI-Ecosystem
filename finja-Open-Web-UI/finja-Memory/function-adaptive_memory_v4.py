"""
======================================================================
         Adaptive Memory - External Server Edition
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module: adaptive-memory (OpenWebUI Plugin)
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 4.4.2 (Ollama Payload Switch)

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the Apache License 2.0

  Original Inspiration & Credits: gramanoid (aka diligent_chooser)
  Original Plugin: https://openwebui.com/f/alexgrama7/adaptive_memory_v2

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------

  ✨ New in 4.4.2:
    • SonarQube Refactoring: Massively reduced Cognitive Complexity
      across the entire plugin by breaking down monolithic functions
      into smaller, single-purpose helper methods (e.g., `inlet`,
      `_upload_new_dedup`, `_run_extraction_phase`, `_rank_candidates_all`).
    • Improved modularization for code maintainability.

  ✨ New in 4.4.1:
    • New valve: Pre-Filtering (`enable_relevance_prefiltering`).
      Allows disabling local pre-selection (Phase 1). Essential for
      users who exclusively use external APIs (OpenAI/Ollama) or
      whose local embedding environment is broken.
    • Stability fix (Phase 1): prevents crashes during cache check
      and pre-filtering when local embeddings are unavailable, even
      if the fallback (Phase 2) was already disabled.
    • Fix `sentence-transformers` compatibility: corrects a
      `ValueError: Prompt name 'True'` with newer library versions
      by using clean argument passing in `_calculate_embeddings`.
    • UI cleanup: valves (settings) reorganized into logical groups
      (Server, Provider, Embedding, Thresholds) for better clarity.

  ✨ New in 4.4.0 (Vision Update):
    • New valve `extraction_mode`:
      - "inlet" (default): analyzes user message before AI replies.
        Ideal for text models and OCR.
      - "outlet": analyzes user message + AI reply after the AI has
        responded. Ideal for vision models (e.g. LLaVA).
    • New valve `block_image_generation_prompts` to control whether
      "create an image..." prompts are stored as memories.
    • Refactoring: extraction logic (Phase 2) moved into
      `_run_extraction_phase`, callable from inlet or outlet.

  ✨ New in 4.3.13:
    • Multimodal stability fix: plugin no longer crashes when a
      vision model sends a message with image data (list payload).
    • New helper `_extract_text_from_content` for robust text
      extraction from `str` or `list` payloads.
    • Regex filter now prevents storing image generation prompts.

  ✨ New in 4.3.12:
    • Ollama payload format switch via `local_llm_payload_format`:
      - "v4_standard": `format: "json"` at top level (modern).
      - "v3_options": format/temperature inside "options" block.
    • Fix: `_local_llm_json` builds payload correctly per valve.

  ✨ New in 4.3.11:
    • Fix: final status message sent before leaving `inlet` when
      context was injected.
    • Fix: `embedding_model` property ensures `SentenceTransformer()`
      is only called when import succeeded.

  ✨ New in 4.3.10:
    • Fix unbound `SentenceTransformer` (refined in 4.3.11).
    • Fix potentially unbound `extraction_provider` variable.

  ✨ New in 4.3.9:
    • Bug fix pass: missing imports, variable init, logic errors.

  ✨ New in 4.3.8:
    • Modular local embeddings via Ollama `/api/embeddings`.

  ✨ New in 4.3.7:
    • Fix: added `import traceback` for error logging.
    • Fix: initialized `existing_vecs_local` to `None`.

  ✨ New in 4.3.6:
    • Fix: deduplication only uses OpenAI when actively selected.

  ✨ New in 4.3.5:
    • LLM provider selection: `extraction_provider` / `relevance_provider`.
    • Dedicated Ollama function: `_local_llm_json`.
    • Revised relevance & extraction for provider selection.

======================================================================
"""

import json
import logging
from typing import Any, Dict, List, Optional, Literal

import aiohttp
from pydantic import BaseModel, Field
from datetime import datetime

# deepcode ignore HardcodedCredentials: This is just a fallback identifier, not a real credential
DEFAULT_USER_ID = "default"
import re
import numpy as np

# Conditional import for sentence-transformers
_SENTENCE_TRANSFORMER_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer
    _SENTENCE_TRANSFORMER_AVAILABLE = True
except ImportError:
    SentenceTransformer = None  # type: ignore  # Fallback for type checking

from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz
import time
import asyncio  # For sleep in retry logic
import traceback  # For error logging

logger = logging.getLogger("openwebui.plugins.adaptive_memory_v4")
handler = logging.StreamHandler()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --- Constants ---
# Placeholder API key to check against
PLACEHOLDER_OPENAI_KEY = "changeme-openai-key"
APPLICATION_JSON = "application/json"

def _log(msg: str, extra: Optional[dict] = None):
    """Log a plugin message with optional JSON extra data."""
    try:
        # Ensure extra is always a dict for dumps
        log_extra = extra if extra is not None else {}
        logger.info(f"[v4] {msg} - {json.dumps(log_extra, ensure_ascii=False)}")
    except Exception:
        # Fallback if JSON serialization fails
        logger.info(f"[v4] {msg}")

class Filter:
    """
    Adaptive Memory v4 – Extensible Memory Plugin
    Handles memory extraction, relevance checking, and context injection
    using configurable LLM providers and embedding methods.
    """

    _embedding_model_instance: Optional[Any] = None # Renamed to avoid conflict

    class Valves(BaseModel):
        # =========================================================
        # 1. MEMORY SERVER CONNECTION (Essential)
        # =========================================================
        memory_api_base: str = Field(
            default="http://localhost:8000",
            description="Base URL of your Memory Server (do not include trailing slash)."
        )
        memory_api_key: str = Field(
            default="changeme-supersecretkey",
            description="API Key for the Memory Server authentication."
        )

        # =========================================================
        # 2. MAIN BEHAVIOR & PROVIDERS
        # =========================================================
        extraction_mode: Literal["inlet", "outlet"] = Field(
            default="inlet",
            description="Extraction Mode: 'inlet' (Standard/Text) analyzes user message before AI reply. 'outlet' (Vision) analyzes user message + AI reply (good for image descriptions)."
        )
        extraction_provider: Literal["openai", "local"] = Field(
            default="openai",
            description="LLM provider used to extract new facts/memories."
        )
        relevance_provider: Literal["openai", "local", "embedding"] = Field(
            default="openai",
            description="Method to check if existing memories are relevant to the current conversation."
        )

        # =========================================================
        # 3. OPENAI SETTINGS (if provider is 'openai')
        # =========================================================
        openai_api_endpoint_url: str = Field(
            default="https://api.openai.com/v1/chat/completions",
            description="API endpoint for OpenAI chat completions."
        )
        openai_model_name: str = Field(
            default="gpt-4o-mini",
            description="Chat Model name for OpenAI."
        )
        openai_api_key: str = Field(
            default=PLACEHOLDER_OPENAI_KEY,
            description="API Key for OpenAI."
        )
        openai_embedding_model: str = Field(
            default="text-embedding-3-small",
            description="OpenAI model for embeddings (used for cosine similarity checks)."
        )
        openai_embedding_endpoint_url: str = Field(
            default="https://api.openai.com/v1/embeddings",
            description="API endpoint for OpenAI Embeddings."
        )

        # =========================================================
        # 4. LOCAL LLM / OLLAMA SETTINGS (if provider is 'local')
        # =========================================================
        local_llm_api_endpoint_url: str = Field(
            default="http://host.docker.internal:11434/api/chat",
            description="Full API endpoint for local LLM (e.g. .../api/chat)."
        )
        local_llm_model_name: str = Field(
            default="qwen3:8b",
            description="Model name for local LLM."
        )
        local_llm_api_key: Optional[str] = Field(
            default=None,
            description="API Key for local LLM (optional)."
        )
        local_llm_payload_format: Literal["v4_standard", "v3_options"] = Field(
            default="v4_standard",
            description="Payload format: 'v4_standard' (Ollama default) or 'v3_options' (compatibility mode)."
        )

        # =========================================================
        # 5. LOCAL EMBEDDING SETTINGS
        # =========================================================
        local_embedding_provider: Literal["sentence_transformer", "ollama"] = Field(
            default="sentence_transformer",
            description="Provider for local embeddings."
        )
        # Option A: Sentence Transformers
        sentence_transformer_model: str = Field(
            default="all-MiniLM-L6-v2",
            description="Model name for 'sentence_transformer' provider."
        )
        # Option B: Ollama Embeddings
        ollama_embedding_api_endpoint_url: str = Field(
             default="http://host.docker.internal:11434/api/embeddings", 
             description="Full API endpoint for 'ollama' embedding provider."
        )
        ollama_embedding_model_name: str = Field(
            default="qwen3-embedding:0.6b", 
            description="Model name for 'ollama' embedding provider."
        )
        # Behavior Control
        enable_relevance_prefiltering: bool = Field(
            default=True,
            description="PHASE 1: Enable local pre-filtering? (Disable this if your local embedding setup is broken to force pure API usage)."
        )
        use_local_embedding_fallback: bool = Field(
            default=True, 
            description="PHASE 2: Use local embedding fallback if the LLM extraction fails?"
        )

        # =========================================================
        # 6. THRESHOLDS & FINE-TUNING
        # =========================================================
        relevance_threshold: float = Field(
            default=0.70, 
            description="Minimum score (0.0-1.0) for a memory to be injected into context."
        )
        relevance_prefilter_cap: int = Field(
            default=15, 
            description="How many top memories to send to the LLM for final relevance ranking."
        )
        max_memories_fetch: int = Field(
            default=100, 
            description="Maximum memories to fetch from server for analysis."
        )
        topical_cache_threshold: float = Field(
            default=0.92, 
            description="Similarity threshold (0.0-1.0) to re-use the previous context (Cache)."
        )
        # Duplicate Detection
        dup_cosine_threshold: float = Field(
            default=0.92, 
            description="Cosine similarity threshold to consider a memory a duplicate."
        )
        dup_levenshtein_threshold: float = Field(
            default=0.90, 
            description="Text similarity threshold to consider a memory a duplicate."
        )
        min_similarity_for_upload: float = Field(
            default=0.95, 
            description="Threshold for the fallback mechanism to save raw messages."
        )
        # Input Limits
        min_memory_chars: int = Field(default=10, description="Min chars for a message to be considered.")
        min_memory_tokens: int = Field(default=3, description="Min words for a message to be considered.")
        http_client_timeout: int = Field(default=180, description="Timeout in seconds for requests.")

        # =========================================================
        # 7. PROMPTS & FILTERS
        # =========================================================
        block_image_generation_prompts: bool = Field(
            default=True,
            description="If True, blocks memory extraction from prompts like 'create an image...'."
        )
        spam_filter_patterns: List[str] = Field(
            default=[
                r"^\s*https?://[^\s]+\s*$",
                r"^\s*[\U0001F600-\U0001F64F\s]+\s*$",
            ],
            description="Regex patterns to ignore."
        )
        delete_trigger_phrases: List[str] = Field(
            default=[
                "delete my memories",
                "erase my memories",
                "forget everything about me",
                "reset your memory"
            ],
            description="Phrases that trigger the deletion confirmation."
        )
        delete_confirmation_phrase: str = Field(
            default="Yes, I want all my memories permanently deleted",
            description="The exact phrase required to confirm deletion."
        )
        
        # System Prompts (Keep at bottom as they are long)
        memory_identification_prompt: str = Field(
            default=(
                "You are an automated JSON data extraction system. Your SOLE function is to identify "
                "user-specific, persistent facts from user messages and output them STRICTLY as a JSON array.\n\n"
                "ABSOLUTE RULES:\n"
                "1. YOUR ENTIRE OUTPUT MUST BE A VALID JSON ARRAY, STARTING WITH `[` AND ENDING WITH `]`. THIS IS THE MOST IMPORTANT RULE. A single JSON object without the array brackets `[]` is INVALID.\n"
                "2. EXTRACT ALL DISTINCT FACTS. If a message contains multiple facts (e.g., a name AND a preference), create a separate JSON object for EACH fact inside the array.\n"
                "3. GENERALIZE FROM SINGLE EVENTS. If a user says 'I ate pizza yesterday', extract the persistent preference 'User likes pizza', not the one-time event.\n"
                "4. IF NO FACTS ARE FOUND, an empty array `[]` is the ONLY valid output.\n\n"
                "--- EXAMPLES ---\n"
                "USER MESSAGE 1: \"Mein Name ist Peter und ich mag das Spiel Satisfactory.\"\n"
                "CORRECT OUTPUT 1 (Array with multiple objects):\n"
                "[\n"
                "  {\"operation\": \"NEW\", \"content\": \"User's name is Peter\", \"tags\": [\"identity\"], \"memory_bank\": \"Personal\"},\n"
                "  {\"operation\": \"NEW\", \"content\": \"User likes the game Satisfactory\", \"tags\": [\"preference\", \"behavior\"], \"memory_bank\": \"Personal\"}\n"
                "]\n\n"
                "USER MESSAGE 2: \"Ich komme aus Deutschland.\"\n"
                "CORRECT OUTPUT 2 (Array with a single object):\n"
                "[\n"
                "  {\"operation\": \"NEW\", \"content\": \"User is from Germany\", \"tags\": [\"identity\"], \"memory_bank\": \"Personal\"}\n"
                "]\n\n"
                "Now, analyze the following user message(s) and provide ONLY the JSON array output."
            )
        )
        memory_relevance_prompt: str = Field(
            default=(
                "You are a memory retrieval assistant. Given:\n"
                "1) CURRENT USER MESSAGE\n"
                "2) CANDIDATE MEMORIES (list of strings)\n\n"
                "Return a JSON array like: [{\"memory\":\"...\",\"score\":0.0}] with score in [0,1].\n"
                "Score high only if the memory is directly useful to respond to the current message. "
                "Avoid trivia/irrelevant info. JSON only, no extra text."
            )
        )


    def __init__(self):
        """Initialize filter with default valves, session, and caches."""
        self.valves = self.Valves()
        self._session: Optional[aiohttp.ClientSession] = None
        self._context_cache: Optional[Dict[str, Any]] = None
        self._pending_deletions: Dict[str, float] = {}
        self._general_block_patterns = [
            r"^\s*(was\s+ist\s+mein\s+name\??)\s*$",  # DE: "what is my name"
            r"^\s*(wie\s+heiße\s+ich\??)\s*$",         # DE: "what's my name"
            r"^\s*what'?s\s+my\s+name\??\s*$",         # EN: "what's my name"
            r"^\s*h+i+(\s+there)?\s*!?\s*$",           # "hi", "hiii", etc.
            r"^\s*(wie\s+geht'?s|how\s+are\s+you)\b.*$",  # Greetings DE/EN
            r"^\s*ok(ay)?\s*$",
            r"^\s*ja\s*$",
            r"^\s*yes\s*$",
            r"^\s*aha\s*$",
            r"^\s*hm(m)?\s*$"
        ]
        # Log if SentenceTransformer library is available
        if not _SENTENCE_TRANSFORMER_AVAILABLE:
             _log("WARNING: sentence-transformers library not found. Local embedding provider 'sentence_transformer' will not work.")


        # These are only blocked when the valve is enabled
        self._generation_block_patterns = [
            r"^\s*(erstelle|generiere|generate|zeichne)\s+(mir\s+)?(ein\s+)?(bild|image)\b.*$"
        ]
    @property
    def embedding_model(self) -> Optional[Any]: # Return type depends on library
        """Loads the SentenceTransformer model instance or returns the cached one."""
        if self.valves.local_embedding_provider != "sentence_transformer":
            return None
        # Check the flag set during import
        if not _SENTENCE_TRANSFORMER_AVAILABLE:
            return None

        if Filter._embedding_model_instance is None:
            model_name = self.valves.sentence_transformer_model
            _log(f"embedding: loading SentenceTransformer model '{model_name}' for the first time.")
            try:
                # Check again if SentenceTransformer is not None before calling
                # This ensures SentenceTransformer() is only called if the import succeeded
                if SentenceTransformer is not None:
                    Filter._embedding_model_instance = SentenceTransformer(model_name)
                else:
                     _log("embedding: SentenceTransformer is None despite flag being True. Cannot load model.")
                     Filter._embedding_model_instance = None # Mark as failed
            except Exception as e:
                _log(f"embedding: FAILED to load SentenceTransformer model '{model_name}'. Provider 'sentence_transformer' will not work. Error: {e}")
                Filter._embedding_model_instance = None # Mark as failed
        return Filter._embedding_model_instance

    # --- NEW: Function to get embeddings from Ollama ---
    def _get_ollama_embedding_url(self) -> str:
        base_url = self.valves.ollama_embedding_api_endpoint_url.rstrip('/')
        if not base_url.endswith("/api/embeddings"):
            api_url = f"{base_url}/api/embeddings"
            _log("ollama_embedding: Appending /api/embeddings to base URL.", {"base": base_url, "final": api_url})
            return api_url
        _log("ollama_embedding: Using provided URL as full endpoint.", {"url": base_url})
        return base_url

    async def _fetch_single_ollama_embedding(self, s: aiohttp.ClientSession, api_url: str, model: str, text: str) -> Optional[List[float]]:
        payload = {"model": model, "prompt": text}
        max_retries = 1
        retry_delay = 0.5
        for attempt in range(max_retries + 1):
            try:
                async with s.post(api_url, json=payload, timeout=aiohttp.ClientTimeout(total=self.valves.http_client_timeout / 2)) as r:
                    if r.status == 200:
                        data = await r.json()
                        if "embedding" in data and isinstance(data["embedding"], list):
                            return data["embedding"]
                        _log(f"ollama_embedding: Unexpected format '{text[:50]}...'", {"response": data})
                        return None
                    _log(f"ollama_embedding: API error '{text[:50]}...' (attempt {attempt+1})", {"status": r.status})
            except Exception as e_inner:
                _log(f"ollama_embedding: Net error '{text[:50]}...' (attempt {attempt+1}): {e_inner}")
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * (2 ** attempt))
        return None

    async def _get_ollama_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """Gets embeddings for a list of texts from the Ollama API."""
        if not texts: return None
        s = self._session_get()
        api_url = self._get_ollama_embedding_url()
        model = self.valves.ollama_embedding_model_name

        if not api_url or not model:
            _log("ollama_embedding: API URL or model name not configured.")
            return None

        successful_embeddings = []
        for text in texts:
            emb = await self._fetch_single_ollama_embedding(s, api_url, model, text)
            if emb is not None:
                successful_embeddings.append(emb)

        if not successful_embeddings:
            _log("ollama_embedding: Failed to get embeddings for all texts after retries.")
            return None
            
        if len(successful_embeddings) < len(texts):
             _log(f"ollama_embedding: Partially failed, got {len(successful_embeddings)}/{len(texts)} embeddings.")

        if successful_embeddings and len({len(e) for e in successful_embeddings}) > 1:
            _log("ollama_embedding: Embeddings have inconsistent dimensions.")
            return None

        return np.array(successful_embeddings)


    async def _calculate_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        Calculates embeddings using the configured local provider.
        """
        if not texts: return None

        provider = self.valves.local_embedding_provider
        _log(f"embedding: Calculating embeddings for {len(texts)} texts using provider: {provider}")

        try:
            if provider == "sentence_transformer":
                model = self.embedding_model 
                if model:
                    loop = asyncio.get_running_loop()
                    try:
                        # FIX: Use lambda to pass keyword arguments correctly, avoiding the "Prompt name 'True'" crash
                        # Old buggy call: await loop.run_in_executor(None, model.encode, texts, True)
                        embeddings = await loop.run_in_executor(None, lambda: model.encode(texts, convert_to_numpy=True))
                    except Exception as encode_error:
                         _log(f"embedding: SentenceTransformer encode failed: {encode_error}", {"traceback": traceback.format_exc()})
                         return None

                    if isinstance(embeddings, np.ndarray):
                        return embeddings
                    else:
                        _log("embedding: SentenceTransformer encode did not return a numpy array.")
                        return None
                else:
                    _log("embedding: SentenceTransformer model instance is None or library unavailable.")
                    return None
            elif provider == "ollama":
                embeddings = await self._get_ollama_embeddings(texts)
                return embeddings
            else:
                _log(f"embedding: Unknown local_embedding_provider: {provider}")
                return None
        except Exception as e:
            _log(f"embedding: Error during _calculate_embeddings with provider {provider}: {e}", {"traceback": traceback.format_exc()})
            return None

    # --------------------------
    # Utils
    # --------------------------
    def _session_get(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session with configured timeout."""
        if self._session is None or self._session.closed:
            timeout_seconds = self.valves.http_client_timeout
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_seconds))
        return self._session

    def _get_user_id(self, __user__: Optional[dict]) -> str:
        """Extract user ID from the OpenWebUI user dict."""
        if not __user__: return DEFAULT_USER_ID
        return (__user__.get("username") if isinstance(__user__, dict) else None) or \
               (__user__.get("id") if isinstance(__user__, dict) else None) or DEFAULT_USER_ID

    def _mem_url(self, path: str) -> str:
        """Build a full URL for the memory server endpoint."""
        return f"{self.valves.memory_api_base.rstrip('/')}/{path.lstrip('/')}"

    async def _emit_status(self, emitter: Optional[Any], message: str, done: bool = True):
        """Sends a visible status message, allowing control over the 'done' state."""
        if emitter:
            try:
                await emitter({"type": "status", "data": {"description": message, "done": done}})
            except Exception as e:
                _log(f"emitter: failed to send status. Error: {e}")


    def _is_spam_or_too_short(self, text: str) -> bool:
        """Check if text is too short or matches spam patterns."""
        if len(text) < self.valves.min_memory_chars:
            _log("filter: blocked, too short (chars)", {"text": text}); return True
        if len(text.split()) < self.valves.min_memory_tokens:
            _log("filter: blocked, too short (tokens)", {"text": text}); return True
        for pattern in self.valves.spam_filter_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                _log("filter: blocked, spam pattern matched", {"text": text, "pattern": pattern}); return True
        return False

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison: lowercase, strip punctuation."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _extract_text_from_content(self, content: Any) -> str:
        """Extract and combine all text parts from the 'content' field.

        Handles both plain strings and multimodal list payloads.
        """
        if isinstance(content, str):
            # Simple case: already a plain string
            return content.strip()
        
        if isinstance(content, list):
            # Multimodal case: list of content blocks
            text_parts = []
            for item in content:
                # Only extract parts of type "text"
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            
            # Join all found text parts
            return "\n".join(p for p in text_parts if p).strip()
        
        # Fallback if neither string nor list
        return ""

    # --------------------------
    # Memory Server Interaction
    # --------------------------
    async def _mem_get_existing(self, user_id: str) -> List[dict]:
        """Fetch existing memories from the memory server."""
        try:
            s = self._session_get()
            url = self._mem_url("get_memories")
            headers = {"X-API-Key": self.valves.memory_api_key}
            params = {"user_id": user_id, "limit": self.valves.max_memories_fetch}
            async with s.get(url, headers=headers, params=params) as r:
                if r.status == 200:
                    try: return await r.json()
                    except json.JSONDecodeError: _log("mem:get failed to decode JSON"); return []
                _log("mem:get failed", {"status": r.status, "text": (await r.text())[:200]})
        except (aiohttp.ClientError, asyncio.TimeoutError) as e: _log("mem:get network/timeout error", {"err": str(e)})
        except Exception as e: _log("mem:get unexpected exception", {"err": str(e)})
        return []

    async def _mem_add_batch(self, items: List[dict]) -> bool:
        """Upload a batch of memory items to the server."""
        if not items: return True
        try:
            s = self._session_get()
            url = self._mem_url("add_memories")
            headers = {"X-API-Key": self.valves.memory_api_key, "Content-Type": APPLICATION_JSON}
            async with s.post(url, headers=headers, json=items) as r:
                txt = await r.text()
                _log("mem:add", {"status": r.status, "resp": txt[:200], "items": len(items)})
                return r.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError) as e: _log("mem:add network/timeout error", {"err": str(e)})
        except Exception as e: _log("mem:add unexpected exception", {"err": str(e)})
        return False

    # --------------------------
    # LLM Helpers
    # --------------------------
    def _build_openai_headers_and_payload(self, messages: List[dict]) -> tuple[dict, dict]:
        headers = {"Content-Type": APPLICATION_JSON}
        api_key = self.valves.openai_api_key
        if api_key and api_key != PLACEHOLDER_OPENAI_KEY:
             headers["Authorization"] = f"Bearer {api_key}"
        else:
             _log("openai:json API key missing or placeholder.")
             raise ValueError("OpenAI API Key is missing or invalid.")
        payload = {
            "model": self.valves.openai_model_name,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        return headers, payload

    def _parse_openai_response(self, txt: str) -> str:
        try:
            data = json.loads(txt)
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "[]")
            _log("openai:json raw", {"first120": content[:120]})
            return content
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            _log("openai:json parse error", {"error": str(e), "raw": txt[:200]})
            raise ValueError(f"OpenAI response parsing failed: {e}")

    async def _openai_json(self, messages: List[dict]) -> str:
        """Send messages to OpenAI and return the raw JSON response string."""
        s = self._session_get()
        headers, payload = self._build_openai_headers_and_payload(messages)
        api_url = self.valves.openai_api_endpoint_url
        max_retries = 2; retry_delay = 1.0

        for attempt in range(max_retries + 1):
             try:
                 async with s.post(api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=self.valves.http_client_timeout)) as r:
                     txt = await r.text()
                     if r.status == 200:
                         return self._parse_openai_response(txt)
                     
                     _log("openai:json API error", {"status": r.status, "resp": txt[:200]})
                     if r.status == 401: raise ValueError("OpenAI API Key is invalid.")
                     
                     if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                     raise aiohttp.ClientResponseError(r.request_info, r.history, status=r.status, message=txt[:500])
             except Exception as e:
                  _log(f"openai:json error attempt {attempt+1}: {e}")
                  if attempt < max_retries and not isinstance(e, ValueError):
                      await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                  raise
        raise ConnectionError("OpenAI request failed after all retries.")


    def _build_local_llm_payload_and_url(self, messages: List[dict], model: str) -> tuple[str, dict]:
        base_url = self.valves.local_llm_api_endpoint_url.rstrip('/')
        if not base_url.endswith(("/api/chat", "/v1/chat/completions")):
            api_url = f"{base_url}/api/chat"
            _log("local_llm: Appending /api/chat to base URL.", {"base": base_url, "final": api_url})
        else:
            api_url = base_url
            _log("local_llm: Using provided URL as full endpoint.", {"url": api_url})
            
        payload_format = self.valves.local_llm_payload_format
        if payload_format == "v3_options":
            _log("local_llm: Using v3-style payload.")
            payload = {
                "model": model, "messages": messages, "stream": False,
                "options": {"temperature": 0.0, "format": "json"}
            }
        else:
            _log("local_llm: Using v4-style payload.")
            payload = {"model": model, "messages": messages, "temperature": 0.0, "format": "json", "stream": False}
        return api_url, payload

    def _extract_content_from_llm_data(self, data: dict) -> Any:
        if "choices" in data and data["choices"] and isinstance(data["choices"][0].get("message"), dict):
            return data["choices"][0]["message"].get("content", "[]")
        if "message" in data and isinstance(data["message"], dict):
            return data["message"].get("content", "[]")
        return data.get("response", "[]")

    def _validate_local_llm_content(self, content: Any) -> str:
        _log("local_llm: Raw content received", {"first120": str(content)[:120]})
        if isinstance(content, str):
            c_strip = content.strip()
            if c_strip.startswith(('[', '{')) and c_strip.endswith((']', '}')):
                try: 
                    json.loads(content)
                    return content
                except json.JSONDecodeError: 
                    pass
        elif isinstance(content, (dict, list)):
            return json.dumps(content)

        _log("local_llm: Response not valid JSON", {"raw_content": str(content)[:200]})
        raise ValueError(f"Local LLM response was not valid JSON: {str(content)[:200]}...")

    def _parse_local_llm_response(self, txt: str) -> str:
        try:
            data = json.loads(txt)
            content = self._extract_content_from_llm_data(data)
            return self._validate_local_llm_content(content)
        except json.JSONDecodeError as e:
            _log("local_llm: Failed decode outer JSON", {"raw": txt[:200]})
            raise ValueError(f"Local LLM outer JSON decode failed: {e}")

    def _handle_local_llm_response(self, r, txt: str, model: str, attempt: int, max_retries: int) -> Optional[str]:
        if r.status == 200:
            return self._parse_local_llm_response(txt)
        
        _log("local_llm: API error", {"status": r.status, "resp": txt[:200]})
        txt_lower = txt.lower()
        if r.status == 404 or "model not found" in txt_lower or "model is required" in txt_lower:
             raise ValueError(f"Model '{model}' not found or invalid on Ollama server.")
             
        if attempt < max_retries: 
             return None
        raise aiohttp.ClientResponseError(r.request_info, r.history, status=r.status, message=txt[:500])

    async def _attempt_local_llm_request(self, s, api_url, headers, payload, model, attempt, max_retries) -> Optional[str]:
        try:
            async with s.post(api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=self.valves.http_client_timeout)) as r:
                txt = await r.text()
                return self._handle_local_llm_response(r, txt, model, attempt, max_retries)
        except Exception as e:
            _log(f"local_llm: error attempt {attempt+1}: {e}", {"traceback": traceback.format_exc()})
            if attempt < max_retries and not isinstance(e, ValueError):
                return None
            raise

    async def _local_llm_json(self, messages: List[dict]) -> str:
        s = self._session_get()
        headers = {"Content-Type": APPLICATION_JSON}
        model = self.valves.local_llm_model_name
        api_key = self.valves.local_llm_api_key

        if not self.valves.local_llm_api_endpoint_url or not model:
            _log("local_llm: API URL or model not configured.")
            raise ValueError("Local LLM API URL or model name not configured.")
        if api_key: headers["Authorization"] = f"Bearer {api_key}"

        api_url, payload = self._build_local_llm_payload_and_url(messages, model)
        max_retries = 2; retry_delay = 1.0

        for attempt in range(max_retries + 1):
            res = await self._attempt_local_llm_request(s, api_url, headers, payload, model, attempt, max_retries)
            if res is not None:
                return res
            await asyncio.sleep(retry_delay * (2 ** attempt))
            
        raise ConnectionError("Local LLM request failed after all retries.")


    async def _attempt_openai_embedding(self, s, api_url, headers, payload, attempt) -> Optional[List[float]]:
         try:
             async with s.post(api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=self.valves.http_client_timeout / 3)) as r:
                 if r.status == 200:
                     data = await r.json()
                     embedding = (data.get("data") or [{}])[0].get("embedding")
                     return embedding if isinstance(embedding, list) else None                     
                 _log("openai:embedding error", {"status": r.status, "resp": (await r.text())[:200]})
                 if r.status == 401: return None
         except Exception as e:
              _log(f"openai:embedding error attempt {attempt+1}: {e}")
         return None

    async def _get_openai_embedding(self, text: str) -> Optional[List[float]]:
        """Get an embedding vector for a single text via OpenAI API."""
        if not text: return None
        api_key = self.valves.openai_api_key
        if not api_key or api_key == PLACEHOLDER_OPENAI_KEY:
             _log("openai:embedding API key missing or placeholder."); return None

        s = self._session_get()
        headers = {"Content-Type": APPLICATION_JSON, "Authorization": f"Bearer {api_key}"}
        payload = {"model": self.valves.openai_embedding_model, "input": text}
        api_url = self.valves.openai_embedding_endpoint_url
        max_retries = 1; retry_delay = 0.5

        for attempt in range(max_retries + 1):
             emb = await self._attempt_openai_embedding(s, api_url, headers, payload, attempt)
             if emb is not None: return emb
             
             if attempt < max_retries: 
                 await asyncio.sleep(retry_delay * (2 ** attempt))
        return None

    # --------------------------
    # Relevance check
    # --------------------------
    async def _call_relevance_llm(self, provider: str, messages: List[dict]) -> str:
        try:
            if provider == "openai": return await self._openai_json(messages)
            if provider == "local": return await self._local_llm_json(messages)
            return "[]"
        except Exception as e: 
            _log(f"relevance: Error calling LLM provider '{provider}': {e}")
            return "[]"

    def _extract_relevance_list(self, parsed_json: Any) -> list:
        if isinstance(parsed_json, dict):
            for key in ["results", "relevance_scores", "memories", "candidates"]:
                if key in parsed_json and isinstance(parsed_json[key], list): 
                    return parsed_json[key]
            if 'memory' in parsed_json and 'score' in parsed_json: 
                return [parsed_json]
            _log("relevance: LLM returned unexpected dict structure.")
            return []
        if isinstance(parsed_json, list): 
            return parsed_json
        _log("relevance: Unexpected JSON type.", {"type": type(parsed_json)})
        return []

    def _parse_relevance_response(self, raw: str) -> List[dict]:
        try:
            parsed_json = json.loads(raw)
            parsed = self._extract_relevance_list(parsed_json)
            
            out = []
            for e in parsed:
                if isinstance(e, dict) and isinstance(e.get("memory"), str):
                    try: score = float(e.get("score", 0.0))
                    except (ValueError, TypeError): score = 0.0
                    out.append({"memory": e["memory"], "score": max(0.0, min(1.0, score))})
                else: 
                    _log("relevance: Invalid item format in list.", {"item": e})
            return out
        except json.JSONDecodeError: 
            _log("relevance: Failed to decode JSON.", {"raw": raw[:200]})
            return []

    async def _rank_relevance(self, user_msg: str, candidate_texts: List[str]) -> List[dict]:
        """Rank candidate memories by relevance using the configured LLM provider."""
        if not candidate_texts: return []
        provider = self.valves.relevance_provider
        if provider not in ["openai", "local"]:
            _log("relevance: _rank_relevance called but provider is not LLM-based.", {"provider": provider})
            return []

        sys = {"role": "system", "content": self.valves.memory_relevance_prompt}
        usr = {"role": "user", "content": json.dumps({"current_message": user_msg, "candidates": candidate_texts}, ensure_ascii=False)}
        
        raw = await self._call_relevance_llm(provider, [sys, usr])
        if raw == "[]": return []
        return self._parse_relevance_response(raw)


    # --------------------------
    # Memory extraction & upload
    # --------------------------
    def _is_blocked_for_extract(self, text: str) -> bool:
        """Check if text should be blocked from memory extraction."""
        t = text.strip().lower();

        # 1. Check general block patterns (ALWAYS)
        for pat in self._general_block_patterns:
            if re.match(pat, t):
                return True

        # 2. Check generation block patterns (only when valve is ON)
        if self.valves.block_image_generation_prompts:
            for pat in self._generation_block_patterns:
                if re.match(pat, t):
                    return True

        return False

    async def _call_extraction_llm(self, provider: str, messages: List[dict]) -> str:
        try:
            if provider == "openai": return await self._openai_json(messages)
            if provider == "local": return await self._local_llm_json(messages)
            _log(f"extract: Unknown provider: {provider}"); return "[]"
        except Exception as e:
            _log(f"extract: Error calling provider '{provider}': {e}"); return "[]"

    def _parse_extraction_response(self, raw: str) -> List[dict]:
        try:
            parsed_json = json.loads(raw)
            if isinstance(parsed_json, list): return parsed_json
            if isinstance(parsed_json, dict) and 'operation' in parsed_json and 'content' in parsed_json: return [parsed_json]
            _log("parser: Unexpected JSON structure.", {"raw": raw[:200]})
            return []
        except json.JSONDecodeError: 
            _log("parser: Failed to decode JSON.", {"raw": raw[:200]})
            return []

    def _filter_extracted_memories(self, arr: List[dict]) -> List[dict]:
        out = []
        for m in arr:
            if not isinstance(m, dict): continue
            if m.get("operation", "NEW").upper() != "NEW": continue
            content = (m.get("content") or "").strip()
            if not content or self._is_spam_or_too_short(content): continue
            
            lc = content.lower()
            if lc in {"hi", "hii", "hiii", "hallo", "hey", "wie gehts", "wie geht's"}: continue
            if re.search(r"\b(asking for (their|his|her) name|frägt?|fragt? nach seinem namen)\b", lc): continue
            
            out.append(m)
        return out

    async def _extract_new_memories(self, last_user_text: str) -> List[dict]:
        """Extract new memory candidates from user text via LLM."""
        if self._is_blocked_for_extract(last_user_text):
            _log("extract: blocked by guard", {"text": last_user_text[:60]}); return []

        provider = self.valves.extraction_provider
        sys = {"role": "system", "content": self.valves.memory_identification_prompt}
        usr = {"role": "user", "content": last_user_text}
        
        raw = await self._call_extraction_llm(provider, [sys, usr])
        arr = self._parse_extraction_response(raw)
        out = self._filter_extracted_memories(arr)

        _log("extract: parsed and filtered", {"in": len(arr), "out": len(out)})
        return out


    def _check_cosine_similarity(self, vec1, vec2, threshold: float, content: str) -> bool:
        if vec1.ndim == 1: vec1 = vec1.reshape(1, -1)
        if vec2.ndim == 1: vec2 = vec2.reshape(1, -1)
        if vec1.shape[1] != vec2.shape[1]:
            _log("Similarity check: Dimension mismatch.", {"vec1": vec1.shape, "vec2": vec2.shape})
            return False
        
        # Ensure we use numpy functions inside cosine logic
        sims = cosine_similarity(vec1, vec2)[0]
        max_sim = np.max(sims) if sims.size > 0 else 0.0
        if max_sim >= threshold:
            _log(f"Blocked by cosine (Score: {max_sim:.2f})", {"text": content})
            return True
        return False

    async def _is_openai_duplicate(self, normalized_content: str, existing_embeddings_openai: list, content: str) -> bool:
        new_embedding_openai = await self._get_openai_embedding(normalized_content)
        if not new_embedding_openai or not existing_embeddings_openai:
            return False
        
        _log("dedup: Using OpenAI embeddings...")
        for old_embedding in existing_embeddings_openai:
            if not old_embedding: continue
            try:
                is_dup = self._check_cosine_similarity(np.array(new_embedding_openai), np.array(old_embedding), self.valves.dup_cosine_threshold, content)
                if is_dup: return True
            except Exception as e: 
                _log(f"dedup: Error calc OpenAI cosine: {e}")
        return False

    async def _is_local_embedding_duplicate(self, normalized_content: str, existing_vecs_local: Optional[np.ndarray], normalized_existing_texts: List[str], content: str) -> tuple[bool, Optional[np.ndarray]]:
        _log(f"dedup: Using local embeddings ({self.valves.local_embedding_provider})...")
        try:
            new_vec_local_list = await self._calculate_embeddings([normalized_content])
            if not new_vec_local_list or len(new_vec_local_list) == 0:
                return False, existing_vecs_local

            new_vec_local = new_vec_local_list[0]
            if existing_vecs_local is None: 
                existing_vecs_local = await self._calculate_embeddings(normalized_existing_texts)

            if existing_vecs_local is not None:
                is_dup = self._check_cosine_similarity(new_vec_local, existing_vecs_local, self.valves.dup_cosine_threshold, content)
                return is_dup, existing_vecs_local
        except Exception as e: 
            _log(f"dedup: Local cosine check failed: {e}")
        return False, existing_vecs_local

    def _is_levenshtein_duplicate(self, normalized_content: str, normalized_existing_texts: List[str], content: str) -> bool:
        _log("dedup: Cosine no duplicate. Using Levenshtein.")
        for old_text in normalized_existing_texts:
            ratio = fuzz.ratio(normalized_content, old_text) / 100.0
            if ratio >= self.valves.dup_levenshtein_threshold:
                _log(f"dedup: Blocked by Levenshtein (Score: {ratio:.2f})", {"text": content})
                return True
        return False

    async def _prefetch_openai_embeddings(self, texts: List[str]) -> list:
        _log("dedup: Pre-fetching OpenAI embeddings...")
        tasks = [self._get_openai_embedding(t) for t in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [res for res in results if isinstance(res, list)]

    async def _setup_openai_dedup(self, normalized_existing_texts: List[str]) -> tuple[bool, list]:
        use_openai_for_dedupe = (
            (self.valves.extraction_provider == "openai" or self.valves.relevance_provider == "openai") and
            self.valves.openai_api_key and self.valves.openai_api_key != PLACEHOLDER_OPENAI_KEY
        )
        if not use_openai_for_dedupe:
            return False, []
            
        embeddings = await self._prefetch_openai_embeddings(normalized_existing_texts)
        if len(embeddings) < len(normalized_existing_texts) * 0.5:
             _log("dedup: High failure rate fetching OpenAI embeddings, disabling for this run.")
             return False, embeddings
        return True, embeddings

    async def _is_duplicate_candidate(self, mem: dict, use_openai: bool, openai_embs: list, existing_texts: list, existing_vecs_local: Optional[np.ndarray]) -> tuple[bool, Optional[np.ndarray]]:
        content = mem.get("content", "").strip()
        if not content: return True, existing_vecs_local
        
        norm = self._normalize_text(content)
        if use_openai and await self._is_openai_duplicate(norm, openai_embs, content):
            return True, existing_vecs_local
        
        if self.valves.use_local_embedding_fallback:
            is_dup, existing_vecs_local = await self._is_local_embedding_duplicate(norm, existing_vecs_local, existing_texts, content)
            if is_dup: return True, existing_vecs_local

        if self._is_levenshtein_duplicate(norm, existing_texts, content):
            return True, existing_vecs_local
            
        return False, existing_vecs_local

    async def _upload_new_dedup(self, user_id: str, candidates: List[dict]) -> int:
        """Deduplicate candidates against existing memories, then upload new ones."""
        if not candidates: return 0
        existing_memories = await self._mem_get_existing(user_id)
        if not existing_memories:
            _log("dedup: No existing memories, uploading all.")
            return await self._mem_add_batch_from_candidates(user_id, candidates)

        existing_texts = [m.get("text", "") for m in existing_memories]
        normalized_existing_texts = [self._normalize_text(t) for t in existing_texts]

        use_openai, openai_embs = await self._setup_openai_dedup(normalized_existing_texts)

        existing_vecs_local: Optional[np.ndarray] = None
        non_duplicates = []

        for mem in candidates:
            is_dup, existing_vecs_local = await self._is_duplicate_candidate(mem, use_openai, openai_embs, normalized_existing_texts, existing_vecs_local)
            if not is_dup:
                non_duplicates.append(mem)

        if not non_duplicates: 
            _log("dedup: All candidates were duplicates.")
            return 0
        _log(f"dedup: Uploading {len(non_duplicates)} non-duplicates.")
        return await self._mem_add_batch_from_candidates(user_id, non_duplicates)
    
    async def _try_extract_memories_llm(self, text: str, emitter: Optional[Any]) -> tuple[bool, bool, List[Dict]]:
        extraction_provider_name = self.valves.extraction_provider.upper()
        try:
            _log(f"extract: trying configured LLM ({extraction_provider_name})...")
            await self._emit_status(emitter, f"🧠 Analyzing message ({extraction_provider_name})...", done=False)
            
            new_mems = await self._extract_new_memories(text) 
            return True, bool(new_mems), new_mems
        except (ValueError, ConnectionError, aiohttp.ClientResponseError) as llm_e:
             _log(f"extract: Configured LLM ({extraction_provider_name}) failed ({llm_e}), checking fallback...", {"traceback": traceback.format_exc()})
             await self._emit_status(emitter, f"⚠️ {extraction_provider_name} unreachable...", done=True)
        except Exception as e:
            _log(f"extract: Unexpected error during LLM extraction ({extraction_provider_name}): {e}", {"traceback": traceback.format_exc()})
            await self._emit_status(emitter, f"🔥 Unexpected error during extraction ({extraction_provider_name}).", done=True)
        
        return False, False, []

    async def _check_fallback_similarity(self, text: str, candidates_fb: list, emitter: Optional[Any]) -> bool:
        try: 
            new_emb = await self._calculate_embeddings([text])
            existing_emb = await self._calculate_embeddings(candidates_fb)
            
            if new_emb is not None and existing_emb is not None:
                is_dup = self._check_cosine_similarity(new_emb, existing_emb, self.valves.min_similarity_for_upload, "fallback check")
                if not is_dup:
                    await self._emit_status(emitter, "✅ New fact (fallback).", done=True)
                    return True
                else:
                    await self._emit_status(emitter, "❌ Fact too similar (fallback).", done=True)
            else:
                await self._emit_status(emitter, "❌ Local fallback analysis failed (embeddings).", done=True)
        except Exception as fb_e:
            _log(f"extract: fallback check failed: {fb_e}")
            await self._emit_status(emitter, "❌ Fallback analysis error.", done=True)
        return False

    async def _handle_extraction_fallback(self, user_id: str, text: str, emitter: Optional[Any]):
        _log("extract: using local embeddings fallback...")
        await self._emit_status(emitter, "⚙️ Local fallback check...", done=False)
        
        if self._is_blocked_for_extract(text) or self._is_spam_or_too_short(text):
            _log("extract: blocked raw message.")
            await self._emit_status(emitter, "ℹ️ Message blocked from memorization.", done=True)
            return

        existing_fb = await self._mem_get_existing(user_id)
        candidates_fb = [m.get("text", "") for m in existing_fb if isinstance(m, dict) and m.get("text", "").strip()]
        
        should_save = False
        if not candidates_fb:
            _log("extract: saving first raw message.")
            should_save = True
        else:
            should_save = await self._check_fallback_similarity(text, candidates_fb, emitter)

        if should_save:
            save_ok = await self._mem_add_batch_from_candidates(user_id, [{"content": text}])
            if not save_ok: 
                await self._emit_status(emitter, "🔥 Error saving (fallback).", done=True)

    async def _run_extraction_phase(self, user_id: str, text_to_analyze: str, emitter: Optional[Any]):
        """Run Phase 2 of memory extraction."""
        _log(f"extract: running phase 2, analyzing text (len: {len(text_to_analyze)})...")

        extraction_done, llm_found, new_mems = await self._try_extract_memories_llm(text_to_analyze, emitter)

        if not extraction_done and self.valves.use_local_embedding_fallback:
            await self._handle_extraction_fallback(user_id, text_to_analyze, emitter)
        elif extraction_done:
            if llm_found:
                added_count = await self._upload_new_dedup(user_id, new_mems)
                if added_count > 0: 
                    await self._emit_status(emitter, f"✅ {added_count} new {'fact' if added_count == 1 else 'facts'} saved.", done=True)
                else: 
                    await self._emit_status(emitter, "ℹ️ Facts found, but duplicates or filtered.", done=True)
            else:
                await self._emit_status(emitter, "ℹ️ Nothing new to memorize.", done=True)

    async def _mem_add_batch_from_candidates(self, user_id: str, candidates: List[dict]) -> int:
        """Convert candidate dicts to server format and upload as batch."""
        batch = [{"user_id": user_id, "text": c.get("content","").strip()} for c in candidates if c.get("content","").strip()]
        if not batch: return 0
        ok = await self._mem_add_batch(batch)
        return len(batch) if ok else 0

    # --------------------------
    # Main hooks
    # --------------------------
    # --------------------------
    # Main hooks
    # --------------------------
    async def _execute_deletion(self, user_id: str, last_user: str, body: dict, emitter: Optional[Any]):
        _log("delete: Confirmed.", {"user_id": user_id})
        try:
            s = self._session_get()
            url = self._mem_url("delete_user_memories")
            headers = {"X-API-Key": self.valves.memory_api_key, "Content-Type": APPLICATION_JSON}
            async with s.post(url, headers=headers, json={"user_id": user_id}) as r:
                if r.status == 200:
                    await self._emit_status(emitter, "✅ All memories deleted.")
                    body["messages"] = [{"role": "system", "content": "System Instruction: User confirmed deletion. Respond briefly like 'Done. Let's start fresh.'"}, {"role": "user", "content": last_user}]
                else: 
                    await self._emit_status(emitter, f"🔥 Server error ({r.status}).")
                    body["messages"] = []
        except Exception as e: 
            _log(f"delete: server call failed: {e}")
            await self._emit_status(emitter, "🔥 Connection error.")
            body["messages"] = []
            
    async def _process_pending_deletion(self, user_id: str, last_user: str, body: dict, emitter: Optional[Any]) -> tuple[bool, dict]:
        if time.time() - self._pending_deletions[user_id] > 120:
            del self._pending_deletions[user_id]
            await self._emit_status(emitter, "ℹ️ Deletion confirmation timed out.")
            return False, body
        if last_user.strip().lower() == self.valves.delete_confirmation_phrase.lower():
            await self._execute_deletion(user_id, last_user, body, emitter)
            if user_id in self._pending_deletions:
                del self._pending_deletions[user_id]
            return True, body
        
        _log("delete: Aborted.", {"user_id": user_id})
        await self._emit_status(emitter, "ℹ️ Deletion cancelled.")
        del self._pending_deletions[user_id]
        return False, body

    async def _handle_deletion_routine(self, user_id: str, last_user: str, body: dict, emitter: Optional[Any]) -> tuple[bool, dict]:
        if user_id in self._pending_deletions: 
            return await self._process_pending_deletion(user_id, last_user, body, emitter)

        if any(phrase in last_user.lower() for phrase in self.valves.delete_trigger_phrases): 
            _log("delete: Initiated.", {"user_id": user_id})
            self._pending_deletions[user_id] = time.time()
            sys_prompt = f"IMPORTANT: Ask user for confirmation using ONLY this EXACT text: Are you sure you want to permanently delete all your memories? Please reply with exactly this sentence: '{self.valves.delete_confirmation_phrase}'"
            body["messages"] = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "Proceed."}]
            await self._emit_status(emitter, "🔒 Security verification required.")
            return True, body

        return False, body

    async def _check_memory_server(self, emitter: Optional[Any]) -> bool:
        try:
            s = self._session_get()
            headers = {"X-API-Key": self.valves.memory_api_key}
            async with s.get(self._mem_url("memory_stats"), headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200: raise ConnectionError(f"Server status {r.status}")
            return True
        except Exception as e:
            await self._emit_status(emitter, "🚨 **Memory server unreachable!**...")
            _log(f"inlet: server connection failed: {e}")
            return False

    async def _rank_with_local_embeddings(self, last_user: str, candidates: list, emitter: Optional[Any], fallback=False) -> list:
        msg = "⚙️ Local fallback analysis..." if fallback else "⚙️ Local relevance analysis..."
        await self._emit_status(emitter, msg, done=False)
        try:
            new_emb = await self._calculate_embeddings([last_user])
            existing_emb = await self._calculate_embeddings(candidates)
            if new_emb is not None and existing_emb is not None:
                if new_emb.shape[1] == existing_emb.shape[1]:
                    sims = cosine_similarity(new_emb.reshape(1, -1) if new_emb.ndim == 1 else new_emb, existing_emb.reshape(1, -1) if existing_emb.ndim == 1 else existing_emb)[0]
                    return [{"memory": text, "score": float(score)} for text, score in zip(candidates, sims)]
        except Exception as e: _log(f"relevance: embedding calc failed: {e}")
        return []

    async def _prefilter_candidates(self, last_user: str, candidates: list) -> list:
        if not self.valves.enable_relevance_prefiltering:
            return candidates
        try:
            new_emb_pre = await self._calculate_embeddings([last_user])
            existing_emb_pre = await self._calculate_embeddings(candidates)
            if new_emb_pre is not None and existing_emb_pre is not None:
                if new_emb_pre.shape[1] == existing_emb_pre.shape[1]:
                    sims = cosine_similarity(new_emb_pre.reshape(1, -1) if new_emb_pre.ndim == 1 else new_emb_pre, existing_emb_pre.reshape(1, -1) if existing_emb_pre.ndim == 1 else existing_emb_pre)[0]
                    scored = sorted(zip(candidates, sims), key=lambda i: i[1], reverse=True)
                    return [txt for txt, scr in scored[:self.valves.relevance_prefilter_cap]]
        except Exception as pre_e: _log(f"relevance: PRE_FAIL: {pre_e}")
        return candidates

    async def _rank_with_llm(self, last_user: str, candidates: list, relevance_provider: str, emitter: Optional[Any]) -> tuple[list, bool]:
        provider_name = relevance_provider.upper()
        await self._emit_status(emitter, f"🔍 Checking relevance ({provider_name})...", done=False)
        try:
            prefiltered = await self._prefilter_candidates(last_user, candidates)
            if prefiltered:
                ranked = await self._rank_relevance(last_user, prefiltered)
                if not ranked: return [], True
                return ranked, False
        except Exception as _e: 
            await self._emit_status(emitter, f"⚠️ {provider_name} unreachable...", done=True)
        return [], True

    async def _rank_candidates_all(self, last_user: str, candidates: list, emitter: Optional[Any]) -> list:
        relevance_provider = self.valves.relevance_provider
        ranked = []
        llm_failed = False
        
        if relevance_provider == "embedding":
            ranked = await self._rank_with_local_embeddings(last_user, candidates, emitter)
        elif relevance_provider in ["openai", "local"]:
            ranked, llm_failed = await self._rank_with_llm(last_user, candidates, relevance_provider, emitter)
                
        if llm_failed and self.valves.use_local_embedding_fallback:
            ranked_fb = await self._rank_with_local_embeddings(last_user, candidates, emitter, fallback=True)
            if ranked_fb: ranked = ranked_fb

        return ranked

    async def _check_and_use_topical_cache(self, last_user: str, body: dict) -> bool:
        if not self.valves.enable_relevance_prefiltering or not self._context_cache or 'embedding' not in self._context_cache:
            return False
            
        _log("cache: checking topical cache...")
        new_embedding = await self._calculate_embeddings([last_user])
        if new_embedding is None or self._context_cache['embedding'] is None:
            _log("cache: Failed to calculate embeddings for cache check.")
            return False

        try:
            is_cache_hit = self._check_cosine_similarity(new_embedding, self._context_cache['embedding'], self.valves.topical_cache_threshold, "Cache checking")
            if is_cache_hit:
                _log("cache: HIT! Re-injecting.")
                body["messages"].insert(0, self._context_cache['context_message'])
                return True
            else:
                _log("cache: MISS!")
        except Exception as cache_sim_error:
            _log(f"cache: Error calculating similarity: {cache_sim_error}")
        return False

    def _format_and_inject_context(self, top_memories: list, body: dict) -> dict:
        context = "MEMORY_CONTEXT:\n" + "\n".join(f"- {t}" for t in top_memories)
        context_message = {"role": "system", "content": context}
        body["messages"].insert(0, context_message)
        _log("context: injected", {"items": len(top_memories)})
        return context_message

    async def _update_context_cache(self, last_user: str, context_message: dict):
        if not self.valves.enable_relevance_prefiltering: return
        try:
            cur_emb = await self._calculate_embeddings([last_user])
            if cur_emb is not None: 
                self._context_cache = {"embedding": cur_emb, "context_message": context_message}
        except Exception as cache_e: 
            _log(f"cache: update failed: {cache_e}")

    async def _inject_relevance_context(self, user_id: str, last_user: str, body: dict, emitter: Optional[Any]) -> dict:
        existing = await self._mem_get_existing(user_id)
        candidates = [m.get("text", "") for m in existing if isinstance(m, dict) and m.get("text", "").strip()]

        if await self._check_and_use_topical_cache(last_user, body):
            return body

        ranked = []
        if candidates:
            ranked = await self._rank_candidates_all(last_user, candidates, emitter)

        threshold = self.valves.relevance_threshold
        relevant = [r for r in ranked if r.get("score", 0.0) >= threshold]
        
        if not relevant:
            await self._emit_status(emitter, "No relevant memories found.", done=True)
            return body
            
        relevant.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        top = [r["memory"] for r in relevant[:3]] 
        if top:
            context_message = self._format_and_inject_context(top, body)
            await self._update_context_cache(last_user, context_message)
            await self._emit_status(emitter, "✅ Relevant memories added to context.", done=True)

        return body

    async def inlet(
        self, body: Dict[str, Any], __event_emitter__: Optional[Any] = None, __user__: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Main inlet hook: relevance check, context injection, and memory extraction."""
        _log("inlet: received batch")
        
        is_up = await self._check_memory_server(__event_emitter__)
        if not is_up: return body

        user_id = self._get_user_id(__user__)
        last_user = ""
        for m in reversed(body.get("messages", [])):
            if m.get("role") == "user" and m.get("content") is not None:
                last_user = self._extract_text_from_content(m["content"])
                if last_user: break
        
        if not last_user: return body

        handled, body = await self._handle_deletion_routine(user_id, last_user, body, __event_emitter__)
        if handled: return body

        body = await self._inject_relevance_context(user_id, last_user, body, __event_emitter__)

        if self.valves.extraction_mode == "inlet":
            _log("extract: running in INLET mode...")
            await self._run_extraction_phase(user_id, last_user, __event_emitter__)
        else:
             _log("extract: running in OUTLET mode, skipping extraction in inlet.")
             self._last_user_message_for_outlet = last_user 

        return body


    # ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    # +++ ADAPTED OUTLET FUNCTION +++
    # ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    async def outlet(self, body: Dict[str, Any], __event_emitter__: Optional[Any] = None, __user__: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Outlet hook: extract memories from AI response when in outlet mode."""
        if self.valves.extraction_mode == "outlet":
            _log("extract: running in OUTLET mode...")
            
            try:
                # 1. Get the LLM response (this is the 'body' in outlet)
                assistant_response = self._extract_text_from_content(body.get("content"))
                
                # 2. Get the user question we stored in inlet
                user_message = getattr(self, "_last_user_message_for_outlet", "")
                
                if user_message and assistant_response:
                    # 3. Combine both for analysis
                    text_to_analyze = f"USER: {user_message}\nASSISTANT: {assistant_response}"
                    
                    user_id = self._get_user_id(__user__)
                    
                    # 4. Call the SAME extracted function
                    await self._run_extraction_phase(user_id, text_to_analyze, __event_emitter__)
                
                # 5. Reset the buffer regardless of outcome
                self._last_user_message_for_outlet = ""

            except Exception as e:
                _log(f"extract: outlet mode failed: {e}")
                self._last_user_message_for_outlet = ""  # Reset on error too
        
        return body  # Passthrough

    async def cleanup(self):
        """Close the aiohttp session on plugin shutdown."""
        if self._session and not self._session.closed: await self._session.close()