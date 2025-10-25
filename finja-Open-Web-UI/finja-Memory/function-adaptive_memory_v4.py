"""
======================================================================
            Adaptive Memory – External Server Edition
======================================================================

  Project: Adaptive Memory (OpenWebUI Plugin)
  Version: 4.3.11 (Fix Status Message)
  Author:  John (J. Apps / Sodakiller1)
  License: Apache License 2.0 (c) 2025 J. Apps
  Original Inspiration & Credits: gramanoid (aka diligent_chooser)
  Original Plugin: https://openwebui.com/f/alexgrama7/adaptive_memory_v2
  Author Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Updates 4.3.11:
 ---------------------------------------------------------------------
  + **Fix Persistente Statusmeldung:** Eine abschließende Statusmeldung ("✅ Relevante Erinnerungen zum Kontext hinzugefügt.")
    hinzugefügt, die vor dem Verlassen von `inlet` gesendet wird, wenn Kontext injiziert wurde.
    Dies stellt sicher, dass vorherige "Prüfe Relevanz..."-Meldungen abgeschlossen werden.
  + **Fix `NoneType` Callable Fehler:** Die Logik in der `embedding_model`-Property korrigiert,
    um sicherzustellen, dass `SentenceTransformer()` nur aufgerufen wird, wenn der Import erfolgreich war
    (`_SENTENCE_TRANSFORMER_AVAILABLE` ist True).

 Updates 4.3.10:
 ---------------------------------------------------------------------
  + **Fix Unbound `SentenceTransformer`:** Die `embedding_model`-Property modifiziert,
    um potenzielle `ImportError` korrekt zu behandeln und sicherzustellen, dass der Check
    `SentenceTransformer is None` zuverlässig funktioniert. (Logik in 4.3.11 verfeinert)
  + **Fix Potenziell Unbound `extraction_provider`:** Sichergestellt, dass die
    `extraction_provider_name`-Variable vor dem `try`-Block in `inlet` Phase 2 zugewiesen wird,
    um Fehler im `except`-Block zu verhindern.

 Updates 4.3.9:
 ---------------------------------------------------------------------
  + **Fehlerkorrekturversuch:** Code überprüft und potenzielle Probleme behoben,
    wie fehlende Importe, Variableninitialisierung und Logikfehler, die in früheren
    Interaktionen identifiziert wurden. Konsistenz bei Funktionsaufrufen und Provider-Logik sichergestellt.

 Updates 4.3.8:
 ---------------------------------------------------------------------
  + **Modulare lokale Embeddings:** Unterstützung für die Verwendung von Ollamas
    `/api/embeddings`-Endpunkt als Alternative zur eingebauten `sentence-transformers`-Bibliothek
    für lokale Embedding-Berechnungen hinzugefügt.
    - Neue Valves: `local_embedding_provider` ('sentence_transformer' oder 'ollama'),
      `ollama_embedding_api_endpoint_url`, `ollama_embedding_model_name`.
    - Neue Funktion: `_get_ollama_embeddings` behandelt die Kommunikation mit der Ollama-API.
    - Aktualisierte Funktion: `_calculate_embeddings` prüft jetzt das Provider-Valve
      und ruft die entsprechende Funktion auf (SentenceTransformer oder Ollama).

 Updates 4.3.7:
 ---------------------------------------------------------------------
  + **Fix `traceback` Import:** `import traceback` für Fehlerprotokollierung
    in `_local_llm_json` hinzugefügt.
  + **Fix `UnboundLocalError`:** `existing_vecs_local` auf `None`
    in `_upload_new_dedup` initialisiert, um potenzielle Fehler zu verhindern, wenn die erste
    Embedding-Berechnung fehlschlägt.

 Updates 4.3.6:
 ---------------------------------------------------------------------
  + **Fix Deduplizierungslogik:** Die Funktion `_upload_new_dedup` versucht nun
    nur noch, OpenAI-Embeddings für die Duplikatsprüfung zu verwenden, wenn
    OpenAI auch tatsächlich als `extraction_provider` oder `relevance_provider`
    ausgewählt ist. Ansonsten wird direkt der lokale Embedding-Fallback genutzt.

 Updates 4.3.5:
 ---------------------------------------------------------------------
  + **LLM Provider-Auswahl:** Benutzer können nun zwischen 'openai' und 'local' (Ollama)
    sowohl für die Extraktion von Erinnerungen (`extraction_provider`) als auch für die Relevanzprüfung
    (`relevance_provider`) wählen.
  + **Dedizierte Ollama-Funktion:** `_local_llm_json` für robuste Kommunikation
    mit lokalen LLM-APIs wie Ollama hinzugefügt.
  + **Überarbeitete Relevanz & Extraktion:** `_extract_new_memories` und
    `_rank_relevance` aktualisiert, um den ausgewählten Provider zu verwenden.
  + **Vereinfachter `processing_mode`:** `processing_mode` entfernt, da Provider-Auswahl
    und `use_local_embedding_fallback` nun den Ablauf steuern.

 Updates 4.3.3:
 ---------------------------------------------------------------------
  + **Stabilitäts-Verbesserungen:**
      - Das Timeout für externe Anfragen ist nun konfigurierbar.
      - Der Parser für OpenAI-Antworten wurde gehärtet und kann nun auch
        fehlerhafte Formate (einzelnes Objekt statt Liste) selbst korrigieren.

 Updates 4.3:
 ---------------------------------------------------------------------
  + **Datenschutz & Benutzerkontrolle (Memory-Löschung):**
      - User können jetzt per Chat-Befehl die Löschung all ihrer
        persönlichen Erinnerungen anfordern.
      - Ein Zwei-Stufen-Bestätigungsprozess mit exakter Phrasen-Eingabe
        sorgt für maximale Sicherheit und verhindert versehentliches Löschen.
      - Der Server löscht daraufhin alle zugehörigen Daten des Users,
        inklusive der Memory-JSON und aller Audio-Dateien.

 Updates 4.2:
 ---------------------------------------------------------------------
  + **Server-Verbindungs-Check:** Das Plugin prüft beim Start, ob der
    Memory-Server erreichbar ist und gibt eine klare Fehlermeldung aus.

  + **Prompt-Feintuning:** Der Extraktions-Prompt wurde gehärtet, um
    qualitativ hochwertigere, dauerhafte Fakten zu generieren.

  + **Duales Fallback-System:** Das Plugin funktioniert dank lokaler
    Embedding-Modelle auch bei einem Ausfall des primären LLM-Providers.

  + **Verbessertes User-Feedback:** Das Plugin gibt dem User jetzt klare und
    freundliche Statusmeldungen für alle Aktionen im Chat aus.

  + **Robuste Logik & Refactoring:** Die zentrale `inlet`-Methode wurde
    überarbeitet, um alle Modi sauber und fehlerresistent zu steuern.

  + **Performance & Kosten-Optimierung:**
      - Ein "Themen-Cache" vermeidet unnötige API-Anfragen komplett.
      - Eine lokale Vor-Filterung reduziert die Anzahl der an LLMs
        gesendeten Erinnerungen drastisch.

  + **Duplicate-Killer 2.0:** Nutzt Cosine-Similarity und Levenshtein-Distanz.

  + **Erweiterter Content-Filter:** Blockiert zu kurze oder Spam-Erinnerungen.
----------------------------------------------------------------------
"""

import json
import logging
from typing import Any, Dict, List, Optional, Literal
import aiohttp
from pydantic import BaseModel, Field
from datetime import datetime
import re
import numpy as np
# Conditional import for sentence-transformers
_SENTENCE_TRANSFORMER_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer
    _SENTENCE_TRANSFORMER_AVAILABLE = True
except ImportError:
    SentenceTransformer = None # type: ignore # Define fallback for type checking
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz
import time
import asyncio # Für sleep in retry logic
import traceback # Hinzugefügt für Fehler-Logging

logger = logging.getLogger("openwebui.plugins.adaptive_memory_v4")
handler = logging.StreamHandler()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --- Constants ---
# Placeholder API key to check against
PLACEHOLDER_OPENAI_KEY = "changeme-openai-key"

def _log(msg: str, extra: Optional[dict] = None):
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
        # --- LLM Provider Settings ---
        extraction_provider: Literal["openai", "local"] = Field(
            default="openai",
            description="LLM provider for extracting new facts ('openai' or 'local')."
        )
        relevance_provider: Literal["openai", "local", "embedding"] = Field(
            default="openai",
            description="Method for relevance checking ('openai', 'local' LLM, or 'embedding' for local vector similarity)."
        )

        # --- OpenAI Settings (if used) ---
        openai_api_endpoint_url: str = Field(
            default="https://api.openai.com/v1/chat/completions",
            description="API endpoint for OpenAI or compatible services."
        )
        openai_model_name: str = Field(
            default="gpt-4o-mini",
            description="Model name for OpenAI or compatible services."
        )
        openai_api_key: str = Field(
            default=PLACEHOLDER_OPENAI_KEY,
            description="API Key for OpenAI or compatible services."
        )
        openai_embedding_model: str = Field(
            default="text-embedding-3-small",
            description="OpenAI model for embedding vectors (used if extraction_provider='openai' or relevance_provider='openai' for cosine sim in dedupe/prefilter)."
        )
        openai_embedding_endpoint_url: str = Field(
            default="https://api.openai.com/v1/embeddings",
            description="API endpoint for OpenAI Embeddings."
        )

        # --- Local LLM (Ollama) Settings (if used for extraction or relevance) ---
        local_llm_api_endpoint_url: str = Field(
            default="http://host.docker.internal:11434/api/chat",
            description="API endpoint for local LLM (Ollama v1 Chat Endpoint recommended)."
        )
        local_llm_model_name: str = Field(
            default="qwen3:8b",
            description="Model name for local LLM (e.g., 'qwen3:8b', 'llama3:latest', 'gemma3:4b')."
        )
        local_llm_api_key: Optional[str] = Field(
            default=None,
            description="API Key for local LLM (if required)."
        )

        # --- Local Embedding Settings ---
        local_embedding_provider: Literal["sentence_transformer", "ollama"] = Field(
            default="sentence_transformer",
            description="Source for local embeddings ('sentence_transformer' for built-in library, 'ollama' for Ollama API)."
        )
        # Sentence Transformer specific (if local_embedding_provider is 'sentence_transformer')
        sentence_transformer_model: str = Field(
            default="all-MiniLM-L6-v2",
            description="Model name for sentence-transformers library (e.g., 'all-MiniLM-L6-v2', 'qwen3-embedding', 'embeddinggemma'). Ensure it's installed or downloadable."
        )
        # Ollama Embedding specific (if local_embedding_provider is 'ollama')
        ollama_embedding_api_endpoint_url: str = Field(
             default="http://host.docker.internal:11434/api/embeddings", # Default Ollama embedding endpoint
             description="API endpoint for Ollama embeddings."
        )
        ollama_embedding_model_name: str = Field(
            default="qwen2:7b-embed", # Example embedding model, adjust as needed
            description="Model name for Ollama embeddings (e.g., 'nomic-embed-text', 'qwen3-embedding', 'embeddinggemma')."
        )

        # --- Memory Server ---
        memory_api_base: str = Field(
            default="http://localhost:8000",
            description="Base URL of your Memory Server (without path, http or https!)"
        )
        memory_api_key: str = Field(default="changeme-supersecretkey")

        # --- Thresholds/Behavior ---
        relevance_threshold: float = Field(default=0.70, description="Relevance threshold (0..1) for context injection.")
        max_memories_fetch: int = Field(default=100, description="Max memories to fetch from server.")
        relevance_prefilter_cap: int = Field(default=15, description="Number of top memories from local pre-selection sent to LLM for relevance check (if provider is 'openai' or 'local').")
        min_memory_chars: int = Field(default=10, description="Minimum character length for a new memory.")
        min_memory_tokens: int = Field(default=3, description="Minimum number of words for a new memory.")
        topical_cache_threshold: float = Field(default=0.92, description="Similarity threshold (0..1) to use the topical context cache.")
        spam_filter_patterns: List[str] = Field(
            default=[
                r"^\s*https?://[^\s]+\s*$",
                r"^\s*[\U0001F600-\U0001F64F\s]+\s*$",
            ],
            description="Regex patterns to block spam or unwanted content."
        )

        # --- Duplicate Killer 2.0 Settings ---
        dup_cosine_threshold: float = Field(default=0.92, description="Minimum cosine similarity to be considered a duplicate.")
        dup_levenshtein_threshold: float = Field(default=0.90, description="Minimum text similarity (Levenshtein) to be considered a duplicate.")

        # --- Embedding Fallback Settings ---
        use_local_embedding_fallback: bool = Field(default=True, description="Enable local embedding fallback for relevance/deduplication if the selected LLM provider fails.")
        min_similarity_for_upload: float = Field(default=0.95, description="Minimum similarity to detect a duplicate during embedding fallback save raw.")

        # --- General Settings ---
        http_client_timeout: int = Field(default=180, description="Timeout in seconds for all external requests.")

        # --- System Prompts ---
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

        # --- Memory Deletion Settings ---
        delete_trigger_phrases: List[str] = Field(
            default=[
                "lösch meine erinnerungen",
                "lösche meine memorys",
                "vergiss alles über mich",
                "setze dein gedächtnis zurück"
            ],
            description="List of phrases (lowercase) that initiate the deletion process."
        )
        delete_confirmation_phrase: str = Field(
            default="Ja, ich möchte all meine Erinnerungen unwiderruflich gelöscht haben",
            description="The exact phrase the user must enter for confirmation."
        )


    def __init__(self):
        self.valves = self.Valves()
        self._session: Optional[aiohttp.ClientSession] = None
        self._context_cache: Optional[Dict[str, Any]] = None
        self._pending_deletions: Dict[str, float] = {}
        self._block_extract_patterns = [
            r"^\s*(was\s+ist\s+mein\s+name\??)\s*$",
            r"^\s*(wie\s+heiße\s+ich\??)\s*$",
            r"^\s*what'?s\s+my\s+name\??\s*$",
            r"^\s*h+i+(\s+there)?\s*!?\s*$",
            r"^\s*(wie\s+geht'?s|how\s+are\s+you)\b.*$",
            r"^\s*ok(ay)?\s*$",
            r"^\s*ja\s*$",
            r"^\s*yes\s*$",
            r"^\s*aha\s*$",
            r"^\s*hm(m)?\s*$"
        ]
        # Log if SentenceTransformer library is available
        if not _SENTENCE_TRANSFORMER_AVAILABLE:
             _log("WARNING: sentence-transformers library not found. Local embedding provider 'sentence_transformer' will not work.")


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
    async def _get_ollama_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """Gets embeddings for a list of texts from the Ollama API."""
        if not texts: return None

        s = await self._session_get()
        api_url = self.valves.ollama_embedding_api_endpoint_url
        model = self.valves.ollama_embedding_model_name

        if not api_url or not model:
            _log("ollama_embedding: API URL or model name not configured.")
            return None

        embeddings_list = []
        max_retries = 1 # Less aggressive retries for embeddings
        retry_delay = 0.5
        try:
            for text in texts:
                 payload = {"model": model, "prompt": text}
                 embedding = None # Reset for each text
                 for attempt in range(max_retries + 1):
                      try:
                          async with s.post(api_url, json=payload, timeout=aiohttp.ClientTimeout(total=self.valves.http_client_timeout / 2)) as r: # Shorter timeout for embeddings
                              if r.status == 200:
                                  data = await r.json()
                                  if "embedding" in data and isinstance(data["embedding"], list):
                                      embedding = data["embedding"]
                                      break # Success for this text
                                  else:
                                      _log(f"ollama_embedding: Unexpected response format for text '{text[:50]}...'", {"response": data})
                                      break # Don't retry format errors
                              else:
                                  _log(f"ollama_embedding: API error for text '{text[:50]}...' (attempt {attempt+1})", {"status": r.status, "resp": (await r.text())[:200]})
                                  if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt))
                                  else: break # Max retries reached
                      except (aiohttp.ClientError, asyncio.TimeoutError) as e_inner:
                           _log(f"ollama_embedding: Network/timeout error for text '{text[:50]}...' (attempt {attempt+1}): {e_inner}")
                           if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt))
                           else: break # Max retries reached
                 embeddings_list.append(embedding) # Append result (or None if all retries failed)

            # Check overall success
            successful_embeddings = [e for e in embeddings_list if e is not None]
            if not successful_embeddings:
                _log("ollama_embedding: Failed to get embeddings for all texts after retries.")
                return None
            if len(successful_embeddings) < len(texts):
                 _log(f"ollama_embedding: Partially failed, got {len(successful_embeddings)}/{len(texts)} embeddings.")

            # Ensure all embeddings have the same dimension before creating numpy array
            if len(set(len(e) for e in successful_embeddings)) > 1:
                _log("ollama_embedding: Embeddings have inconsistent dimensions.")
                return None

            return np.array(successful_embeddings)

        except Exception as e:
            _log(f"ollama_embedding: Unexpected error during batch processing: {e}", {"traceback": traceback.format_exc()})
            return None


    async def _calculate_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        Calculates embeddings using the configured local provider ('sentence_transformer' or 'ollama').
        Returns None if calculation fails for any reason.
        """
        if not texts: return None

        provider = self.valves.local_embedding_provider
        _log(f"embedding: Calculating embeddings for {len(texts)} texts using provider: {provider}")

        try:
            if provider == "sentence_transformer":
                model = self.embedding_model # Calls the @property
                if model:
                    loop = asyncio.get_running_loop()
                    # Execute sentence-transformer encoding in a thread pool
                    # Wrap the lambda and its execution in a try-except block
                    try:
                        embeddings = await loop.run_in_executor(
                            None,
                            lambda blocking_texts: model.encode(blocking_texts, convert_to_numpy=True),
                            texts # Pass texts to the lambda
                        )
                    except Exception as encode_error:
                         _log(f"embedding: SentenceTransformer encode failed: {encode_error}", {"traceback": traceback.format_exc()})
                         return None

                    # Check if encoding returned a valid numpy array
                    if isinstance(embeddings, np.ndarray):
                        return embeddings
                    else:
                        _log("embedding: SentenceTransformer encode did not return a numpy array.")
                        return None
                else:
                    _log("embedding: SentenceTransformer model instance is None or library unavailable.")
                    return None
            elif provider == "ollama":
                # Call the async Ollama embedding function
                embeddings = await self._get_ollama_embeddings(texts)
                # _get_ollama_embeddings already returns np.ndarray or None
                return embeddings
            else:
                _log(f"embedding: Unknown local_embedding_provider: {provider}")
                return None
        except Exception as e:
            # Catch any unexpected error during the process
            _log(f"embedding: Error during _calculate_embeddings with provider {provider}: {e}", {"traceback": traceback.format_exc()})
            return None

    # --------------------------
    # Utils
    # --------------------------
    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout_seconds = self.valves.http_client_timeout
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_seconds))
        return self._session

    def _get_user_id(self, __user__: Optional[dict]) -> str:
        if not __user__: return "default"
        return (__user__.get("username") if isinstance(__user__, dict) else None) or \
               (__user__.get("id") if isinstance(__user__, dict) else None) or "default"

    def _mem_url(self, path: str) -> str:
        return f"{self.valves.memory_api_base.rstrip('/')}/{path.lstrip('/')}"

    async def _emit_status(self, emitter: Optional[Any], message: str, done: bool = True):
        """Sends a visible status message, allowing control over the 'done' state."""
        if emitter:
            try:
                await emitter({"type": "status", "data": {"description": message, "done": done}})
            except Exception as e:
                _log(f"emitter: failed to send status. Error: {e}")


    def _is_spam_or_too_short(self, text: str) -> bool:
        if len(text) < self.valves.min_memory_chars:
            _log("filter: blocked, too short (chars)", {"text": text}); return True
        if len(text.split()) < self.valves.min_memory_tokens:
            _log("filter: blocked, too short (tokens)", {"text": text}); return True
        for pattern in self.valves.spam_filter_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                _log("filter: blocked, spam pattern matched", {"text": text, "pattern": pattern}); return True
        return False

    def _normalize_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    # --------------------------
    # Memory Server Interaction
    # --------------------------
    async def _mem_get_existing(self, user_id: str) -> List[dict]:
        try:
            s = await self._session_get()
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
        if not items: return True
        try:
            s = await self._session_get()
            url = self._mem_url("add_memories")
            headers = {"X-API-Key": self.valves.memory_api_key, "Content-Type": "application/json"}
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
    async def _openai_json(self, messages: List[dict]) -> str:
        s = await self._session_get()
        headers = {"Content-Type": "application/json"}
        api_key = self.valves.openai_api_key
        if api_key and api_key != PLACEHOLDER_OPENAI_KEY:
             headers["Authorization"] = f"Bearer {api_key}"
        else:
             _log("openai:json API key missing or placeholder.")
             return "[]" # Return empty if no valid key

        payload = {
            "model": self.valves.openai_model_name,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        api_url = self.valves.openai_api_endpoint_url
        max_retries = 2; retry_delay = 1.0

        for attempt in range(max_retries + 1):
             try:
                 async with s.post(api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=self.valves.http_client_timeout)) as r:
                     txt = await r.text()
                     if r.status == 200:
                         try:
                             data = json.loads(txt)
                             content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "[]")
                             _log("openai:json raw", {"first120": content[:120]})
                             return content # Return raw JSON string
                         except (json.JSONDecodeError, IndexError, KeyError) as e:
                             _log("openai:json parse error", {"error": str(e), "raw": txt[:200]}); return "[]"
                     else:
                         _log("openai:json API error", {"status": r.status, "resp": txt[:200]})
                         if r.status == 401: return "[]" # No retry on auth error
                         if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                         return "[]"
             except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                  _log(f"openai:json network/timeout error attempt {attempt+1}: {e}")
                  if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                  return "[]"
             except Exception as e:
                 _log(f"openai:json unexpected error attempt {attempt+1}: {e}", {"traceback": traceback.format_exc()})
                 if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                 return "[]"
        return "[]"

    async def _local_llm_json(self, messages: List[dict]) -> str:
        s = await self._session_get()
        headers = {"Content-Type": "application/json"}
        api_url = self.valves.local_llm_api_endpoint_url
        model = self.valves.local_llm_model_name
        api_key = self.valves.local_llm_api_key

        if not api_url or not model: _log("local_llm: API URL or model not configured."); return "[]"
        if api_key: headers["Authorization"] = f"Bearer {api_key}"

        payload = {"model": model, "messages": messages, "temperature": 0.0, "format": "json", "stream": False}
        max_retries = 2; retry_delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                async with s.post(api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=self.valves.http_client_timeout)) as r:
                    txt = await r.text()
                    if r.status == 200:
                        try:
                            data = json.loads(txt)
                            content = "[]"
                            # Handle different response structures gracefully
                            if "choices" in data and data["choices"] and isinstance(data["choices"][0].get("message"), dict):
                                content = data["choices"][0]["message"].get("content", "[]")
                            elif "message" in data and isinstance(data["message"], dict):
                                content = data["message"].get("content", "[]")
                            elif "response" in data: # Fallback for /api/generate
                                content = data.get("response", "[]")

                            _log("local_llm: Raw content received", {"first120": content[:120]})

                            # Validate if content looks like JSON and return as string
                            if isinstance(content, str) and content.strip().startswith(('[', '{')) and content.strip().endswith((']', '}')):
                                try: json.loads(content); return content
                                except json.JSONDecodeError: pass # Fall through
                            elif isinstance(content, (dict, list)):
                                return json.dumps(content) # Convert back to string if already parsed

                            _log("local_llm: Response content not valid JSON", {"raw_content": content[:200]})
                            return "[]"

                        except json.JSONDecodeError: _log("local_llm: Failed to decode outer JSON", {"raw": txt[:200]}); return "[]"
                    else:
                        _log("local_llm: API error", {"status": r.status, "resp": txt[:200]})
                        if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                        return "[]"
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                 _log(f"local_llm: Network/timeout error attempt {attempt+1}: {e}")
                 if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                 return "[]"
            except Exception as e:
                _log(f"local_llm: Unexpected error attempt {attempt+1}: {e}", {"traceback": traceback.format_exc()})
                if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                return "[]"
        return "[]"


    async def _get_openai_embedding(self, text: str) -> Optional[List[float]]:
        if not text: return None
        api_key = self.valves.openai_api_key
        if not api_key or api_key == PLACEHOLDER_OPENAI_KEY:
             _log("openai:embedding API key missing or placeholder."); return None

        s = await self._session_get()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {"model": self.valves.openai_embedding_model, "input": text}
        api_url = self.valves.openai_embedding_endpoint_url
        max_retries = 1; retry_delay = 0.5 # Less aggressive for embeddings

        for attempt in range(max_retries + 1):
             try:
                 async with s.post(api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=self.valves.http_client_timeout / 3)) as r:
                     if r.status != 200:
                         _log("openai:embedding error", {"status": r.status, "resp": (await r.text())[:200]})
                         if r.status == 401: return None # No retry on auth error
                         if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                         return None
                     data = await r.json()
                     embedding = (data.get("data") or [{}])[0].get("embedding")
                     return embedding if isinstance(embedding, list) else None
             except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                  _log(f"openai:embedding network/timeout error attempt {attempt+1}: {e}")
                  if attempt < max_retries: await asyncio.sleep(retry_delay * (2 ** attempt)); continue
                  return None
             except Exception as e:
                 _log(f"openai:embedding unexpected error attempt {attempt+1}: {e}", {"traceback": traceback.format_exc()}); return None
        return None

    # --------------------------
    # Relevance check
    # --------------------------
    async def _rank_relevance(self, user_msg: str, candidate_texts: List[str]) -> List[dict]:
        if not candidate_texts: return []
        provider = self.valves.relevance_provider
        if provider not in ["openai", "local"]:
            _log("relevance: _rank_relevance called but provider is not LLM-based.", {"provider": provider}); return []

        sys = {"role": "system", "content": self.valves.memory_relevance_prompt}
        usr = {"role": "user", "content": json.dumps({"current_message": user_msg, "candidates": candidate_texts}, ensure_ascii=False)}
        raw = "[]"
        try:
            if provider == "openai": raw = await self._openai_json([sys, usr])
            elif provider == "local": raw = await self._local_llm_json([sys, usr])
        except Exception as e: _log(f"relevance: Error calling LLM provider '{provider}': {e}"); return []

        parsed = []; out: List[dict] = []
        try:
            parsed_json = json.loads(raw)
            if isinstance(parsed_json, dict): # Handle potential dict wrapping
                 for key in ["results", "relevance_scores", "memories", "candidates"]:
                     if key in parsed_json and isinstance(parsed_json[key], list): parsed = parsed_json[key]; break
                 else:
                     if 'memory' in parsed_json and 'score' in parsed_json: parsed = [parsed_json]
                     else: _log("relevance: LLM returned unexpected dict structure."); parsed = []
            elif isinstance(parsed_json, list): parsed = parsed_json
            else: _log("relevance: Unexpected JSON type.", {"type": type(parsed_json)}); parsed = []

            for e in parsed:
                if isinstance(e, dict) and isinstance(e.get("memory"), str):
                    try: score = float(e.get("score", 0.0))
                    except (ValueError, TypeError): score = 0.0
                    out.append({"memory": e["memory"], "score": max(0.0, min(1.0, score))})
                else: _log("relevance: Invalid item format in list.", {"item": e})
        except json.JSONDecodeError: _log("relevance: Failed to decode JSON.", {"raw": raw[:200]})
        return out

    # --------------------------
    # Memory extraction & upload
    # --------------------------
    def _is_blocked_for_extract(self, text: str) -> bool:
        t = text.strip().lower();
        for pat in self._block_extract_patterns:
            if re.match(pat, t): return True
        return False

    async def _extract_new_memories(self, last_user_text: str) -> List[dict]:
        if self._is_blocked_for_extract(last_user_text):
            _log("extract: blocked by guard", {"text": last_user_text[:60]}); return []

        provider = self.valves.extraction_provider
        sys = {"role": "system", "content": self.valves.memory_identification_prompt}
        usr = {"role": "user", "content": last_user_text}
        raw = "[]"
        try:
            if provider == "openai": raw = await self._openai_json([sys, usr])
            elif provider == "local": raw = await self._local_llm_json([sys, usr])
            else: _log(f"extract: Unknown provider: {provider}"); return []
        except Exception as e: _log(f"extract: Error calling provider '{provider}': {e}"); return []

        arr = []
        try:
            parsed_json = json.loads(raw)
            if isinstance(parsed_json, list): arr = parsed_json
            elif isinstance(parsed_json, dict) and 'operation' in parsed_json and 'content' in parsed_json: arr = [parsed_json] # Handle single object
            else: _log("parser: Unexpected JSON structure.", {"raw": raw[:200]})
        except json.JSONDecodeError: _log("parser: Failed to decode JSON.", {"raw": raw[:200]})

        out = []
        for m in arr:
            if not isinstance(m, dict): continue
            if m.get("operation", "NEW").upper() != "NEW": continue # Default to NEW if missing
            content = (m.get("content") or "").strip()
            if not content or self._is_spam_or_too_short(content): continue
            lc = content.lower()
            if lc in {"hi", "hii", "hiii", "hallo", "hey", "wie gehts", "wie geht's"}: continue
            if re.search(r"\b(asking for (their|his|her) name|frägt?|fragt? nach seinem namen)\b", lc): continue
            out.append(m)

        _log("extract: parsed and filtered", {"in": len(arr), "out": len(out)})
        return out

    async def _upload_new_dedup(self, user_id: str, candidates: List[dict]) -> int:
        if not candidates: return 0
        existing_memories = await self._mem_get_existing(user_id)
        if not existing_memories:
            _log("dedup: No existing memories, uploading all."); return await self._mem_add_batch_from_candidates(user_id, candidates)

        existing_texts = [m.get("text", "") for m in existing_memories]
        normalized_existing_texts = [self._normalize_text(t) for t in existing_texts]

        use_openai_for_dedupe = (
            (self.valves.extraction_provider == "openai" or self.valves.relevance_provider == "openai") and
            self.valves.openai_api_key and self.valves.openai_api_key != PLACEHOLDER_OPENAI_KEY
        )

        existing_embeddings_openai = []
        if use_openai_for_dedupe:
            _log("dedup: Pre-fetching OpenAI embeddings...")
            tasks = [self._get_openai_embedding(t) for t in normalized_existing_texts]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            existing_embeddings_openai = [res for res in results if isinstance(res, list)]
            if len(existing_embeddings_openai) < len(normalized_existing_texts) * 0.5:
                 _log("dedup: High failure rate fetching OpenAI embeddings, disabling for this run.")
                 use_openai_for_dedupe = False

        existing_vecs_local: Optional[np.ndarray] = None

        non_duplicates = []
        for mem_candidate in candidates:
            content = mem_candidate.get("content", "").strip();
            if not content: continue
            normalized_content = self._normalize_text(content)
            is_duplicate = False
            cosine_check_method = "none"

            # --- CHECK 1: COSINE ---
            if use_openai_for_dedupe:
                new_embedding_openai = await self._get_openai_embedding(normalized_content)
                if new_embedding_openai and existing_embeddings_openai:
                    cosine_check_method = "openai"
                    _log("dedup: Using OpenAI embeddings...")
                    for old_embedding in existing_embeddings_openai:
                        if old_embedding:
                            try:
                                vec1, vec2 = np.array(new_embedding_openai), np.array(old_embedding)
                                norm1, norm2 = np.linalg.norm(vec1), np.linalg.norm(vec2)
                                if norm1 > 0 and norm2 > 0:
                                     sim = np.dot(vec1, vec2) / (norm1 * norm2)
                                     if sim >= self.valves.dup_cosine_threshold:
                                         _log(f"dedup: Blocked by OpenAI cosine (Score: {sim:.2f})", {"text": content}); is_duplicate = True; break
                            except Exception as e: _log(f"dedup: Error calc OpenAI cosine: {e}")
                    if is_duplicate: continue

            if not is_duplicate and self.valves.use_local_embedding_fallback:
                cosine_check_method = f"local_{self.valves.local_embedding_provider}"
                _log(f"dedup: Using local embeddings ({self.valves.local_embedding_provider})...")
                try:
                    new_vec_local_list = await self._calculate_embeddings([normalized_content])
                    if new_vec_local_list is not None and len(new_vec_local_list) > 0:
                         new_vec_local = new_vec_local_list[0]
                         if existing_vecs_local is None: existing_vecs_local = await self._calculate_embeddings(normalized_existing_texts)

                         if existing_vecs_local is not None:
                             if new_vec_local.ndim == 1: new_vec_local = new_vec_local.reshape(1,-1) # Ensure 2D
                             if existing_vecs_local.ndim == 1: existing_vecs_local = existing_vecs_local.reshape(1,-1) # Should be 2D, but safeguard

                             if new_vec_local.shape[1] == existing_vecs_local.shape[1]: # Check matching dimensions
                                 similarities = cosine_similarity(new_vec_local, existing_vecs_local)[0]
                                 max_sim = np.max(similarities) if similarities.size > 0 else 0.0
                                 if max_sim >= self.valves.dup_cosine_threshold:
                                     _log(f"dedup: Blocked by local cosine (Score: {max_sim:.2f})", {"text": content}); is_duplicate = True
                             else:
                                 _log("dedup: Local embedding dimension mismatch.", {"new_shape": new_vec_local.shape, "existing_shape": existing_vecs_local.shape})
                                 cosine_check_method += "_dim_mismatch"
                         else: cosine_check_method += "_failed_existing"
                    else: cosine_check_method += "_failed_new"
                except Exception as e: _log(f"dedup: Local cosine check failed: {e}"); cosine_check_method += "_exception"


            if is_duplicate: continue

            # --- CHECK 2: LEVENSHTEIN (Fallback) ---
            if not is_duplicate:
                 _log(f"dedup: Cosine ({cosine_check_method}) no duplicate. Using Levenshtein.")
                 for old_text in normalized_existing_texts:
                     ratio = fuzz.ratio(normalized_content, old_text) / 100.0
                     if ratio >= self.valves.dup_levenshtein_threshold:
                         _log(f"dedup: Blocked by Levenshtein (Score: {ratio:.2f})", {"text": content}); is_duplicate = True; break

            if not is_duplicate: non_duplicates.append(mem_candidate)

        if not non_duplicates: _log("dedup: All candidates were duplicates."); return 0
        _log(f"dedup: Uploading {len(non_duplicates)} non-duplicates."); return await self._mem_add_batch_from_candidates(user_id, non_duplicates)

    async def _mem_add_batch_from_candidates(self, user_id: str, candidates: List[dict]) -> int:
        batch = [{"user_id": user_id, "text": c.get("content","").strip()} for c in candidates if c.get("content","").strip()]
        if not batch: return 0
        ok = await self._mem_add_batch(batch)
        return len(batch) if ok else 0

    # --------------------------
    # Main hooks
    # --------------------------
    async def inlet(
        self, body: Dict[str, Any], __event_emitter__: Optional[Any] = None, __user__: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        _log("inlet: received batch")
        # --- 1. SETUP & SERVER CHECK ---
        try:
             s = await self._session_get(); headers = {"X-API-Key": self.valves.memory_api_key}
             async with s.get(self._mem_url("memory_stats"), headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
                 if r.status != 200: raise ConnectionError(f"Server status {r.status}")
        except Exception as e:
            await self._emit_status(__event_emitter__, "🚨 **Memory-Server nicht erreichbar!**..."); _log(f"inlet: server connection failed: {e}"); return body

        user_id = self._get_user_id(__user__); last_user = ""
        for m in reversed(body.get("messages", [])):
            if m.get("role") == "user" and m.get("content"): last_user = m["content"]; break
        if not last_user: return body

        # --- 2. DELETION ROUTINE ---
        # ... (unchanged, includes early returns) ...
        if user_id in self._pending_deletions: # Check pending
            if time.time() - self._pending_deletions[user_id] > 120:
                del self._pending_deletions[user_id]; await self._emit_status(__event_emitter__, "ℹ️ Zeit für Lösch-Bestätigung abgelaufen.")
            elif last_user.strip().lower() == self.valves.delete_confirmation_phrase.lower():
                _log("delete: Confirmed.", {"user_id": user_id})
                try:
                    s = await self._session_get(); url = self._mem_url("delete_user_memories")
                    headers = {"X-API-Key": self.valves.memory_api_key, "Content-Type": "application/json"}
                    async with s.post(url, headers=headers, json={"user_id": user_id}) as r:
                        if r.status == 200:
                            await self._emit_status(__event_emitter__, "✅ Alle Erinnerungen gelöscht."); body["messages"] = [{"role": "system", "content": "System Instruction: User confirmed deletion. Respond briefly like 'Done. Let's start fresh.'"}, {"role": "user", "content": last_user}]
                        else: await self._emit_status(__event_emitter__, f"🔥 Server-Fehler ({r.status})."); body["messages"] = []
                except Exception as e: _log(f"delete: server call failed: {e}"); await self._emit_status(__event_emitter__, "🔥 Verbindungs-Fehler."); body["messages"] = []
                del self._pending_deletions[user_id]; return body
            else: _log("delete: Aborted.", {"user_id": user_id}); await self._emit_status(__event_emitter__, "ℹ️ Löschvorgang abgebrochen."); del self._pending_deletions[user_id]
        elif any(phrase in last_user.lower() for phrase in self.valves.delete_trigger_phrases): # Initiate deletion
            _log("delete: Initiated.", {"user_id": user_id}); self._pending_deletions[user_id] = time.time()
            sys_prompt = f"IMPORTANT: Ask user for confirmation using ONLY this EXACT text: Bist du dir sicher, dass du alle deine Erinnerungen unwiderruflich löschen möchtest? Antworte bitte mit genau dem Satz: '{self.valves.delete_confirmation_phrase}'"
            body["messages"] = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "Proceed."}]; await self._emit_status(__event_emitter__, "🔒 Sicherheitsüberprüfung erforderlich.")
            return body # Important return

        # --- 3. RELEVANCE CHECK (PHASE 1) ---
        existing = await self._mem_get_existing(user_id)
        candidates = [m.get("text", "") for m in existing if isinstance(m, dict) and m.get("text", "").strip()]

        # --- Topical Cache Check ---
        if self._context_cache and 'embedding' in self._context_cache:
            _log("cache: checking topical cache...")
            new_embedding = await self._calculate_embeddings([last_user])
            if new_embedding is not None and self._context_cache['embedding'] is not None:
                try:
                    if new_embedding.shape == self._context_cache['embedding'].shape:
                        similarity = cosine_similarity(new_embedding, self._context_cache['embedding'])[0][0]
                        if similarity >= self.valves.topical_cache_threshold:
                            _log(f"cache: HIT! Sim {similarity:.2f}. Re-injecting.")
                            body["messages"].insert(0, self._context_cache['context_message'])
                            return body
                        else: _log(f"cache: MISS! Sim {similarity:.2f}.")
                    else: _log("cache: Embedding dimension mismatch.")
                except Exception as cache_sim_error: _log(f"cache: Error calc sim: {cache_sim_error}")
            else: _log("cache: Failed to calculate embeddings for cache check.")


        is_context_injected = False; ranked = []; llm_failed = False
        if candidates:
            relevance_provider = self.valves.relevance_provider
            # --- A) Embedding Directly ---
            if relevance_provider == "embedding":
                _log("relevance: using local embeddings directly..."); await self._emit_status(__event_emitter__, "⚙️ Lokale Relevanz-Analyse...", done=False) # Keep status until injection
                try:
                    new_emb = await self._calculate_embeddings([last_user]); existing_emb = await self._calculate_embeddings(candidates)
                    if new_emb is not None and existing_emb is not None:
                         if new_emb.ndim == 1: new_emb = new_emb.reshape(1, -1)
                         if existing_emb.ndim == 1: existing_emb = existing_emb.reshape(1, -1)
                         if new_emb.shape[1] == existing_emb.shape[1]:
                              similarities = cosine_similarity(new_emb, existing_emb)[0]
                              ranked = [{"memory": text, "score": float(score)} for text, score in zip(candidates, similarities)]
                         else: _log("relevance: embedding dimension mismatch.")
                    else: _log("relevance: embedding calc failed.")
                except Exception as e: _log(f"relevance: embedding calc failed: {e}")
            # --- B) LLM (OpenAI or Local) ---
            elif relevance_provider in ["openai", "local"]:
                provider_name = relevance_provider.upper()
                try:
                    _log("relevance: performing local pre-filtering..."); prefiltered_candidates = candidates
                    try: # Prefiltering logic using _calculate_embeddings
                         new_emb_pre = await self._calculate_embeddings([last_user]); existing_emb_pre = await self._calculate_embeddings(candidates)
                         if new_emb_pre is not None and existing_emb_pre is not None:
                              if new_emb_pre.ndim == 1: new_emb_pre = new_emb_pre.reshape(1, -1)
                              if existing_emb_pre.ndim == 1: existing_emb_pre = existing_emb_pre.reshape(1, -1)
                              if new_emb_pre.shape[1] == existing_emb_pre.shape[1]:
                                   similarities_pre = cosine_similarity(new_emb_pre, existing_emb_pre)[0]
                                   scored = sorted(zip(candidates, similarities_pre), key=lambda i: i[1], reverse=True)
                                   prefiltered_candidates = [txt for txt, scr in scored[:self.valves.relevance_prefilter_cap]]
                                   _log(f"relevance: pre-filtered to {len(prefiltered_candidates)}.")
                              else: _log("relevance: pre-filtering dim mismatch.")
                         else: _log("relevance: embedding failed pre-filtering.")
                    except Exception as pre_e: _log(f"relevance: pre-filtering failed: {pre_e}")

                    if prefiltered_candidates:
                         _log(f"relevance: using {provider_name} LLM for ranking."); await self._emit_status(__event_emitter__, f"🔍 Prüfe Relevanz ({provider_name})...", done=False) # Keep status until injection
                         ranked = await self._rank_relevance(last_user, prefiltered_candidates)
                         if not ranked: llm_failed = True; _log(f"relevance: {provider_name} LLM call failed or returned empty.")
                    else: _log("relevance: no candidates after pre-filtering.")
                except Exception as e: _log(f"relevance: {provider_name} LLM path failed: {e}"); llm_failed = True; await self._emit_status(__event_emitter__, f"⚠️ {provider_name} nicht erreichbar...")
            # --- C) Embedding Fallback ---
            if llm_failed and self.valves.use_local_embedding_fallback:
                _log("relevance: using local embeddings fallback..."); await self._emit_status(__event_emitter__, "⚙️ Lokale Fallback-Analyse...", done=False) # Keep status until injection
                try: # Fallback logic using _calculate_embeddings
                     new_emb_fb = await self._calculate_embeddings([last_user]); existing_emb_fb = await self._calculate_embeddings(candidates)
                     if new_emb_fb is not None and existing_emb_fb is not None:
                         if new_emb_fb.ndim == 1: new_emb_fb = new_emb_fb.reshape(1, -1)
                         if existing_emb_fb.ndim == 1: existing_emb_fb = existing_emb_fb.reshape(1, -1)
                         if new_emb_fb.shape[1] == existing_emb_fb.shape[1]:
                             similarities_fb = cosine_similarity(new_emb_fb, existing_emb_fb)[0]
                             ranked = [{"memory": text, "score": float(score)} for text, score in zip(candidates, similarities_fb)]
                         else: _log("relevance: fallback dim mismatch.")
                     else: _log("relevance: embedding failed fallback.")
                except Exception as fb_e: _log(f"relevance: fallback failed: {fb_e}")

            # --- Evaluation & Injection ---
            threshold = self.valves.relevance_threshold
            relevant = [r for r in ranked if r.get("score", 0.0) >= threshold]
            if relevant:
                relevant.sort(key=lambda x: x.get("score", 0.0), reverse=True)
                top = [r["memory"] for r in relevant[:3]] # Example: top 3
                if top:
                    context = "MEMORY_CONTEXT:\n" + "\n".join(f"- {t}" for t in top)
                    context_message = {"role": "system", "content": context}
                    body["messages"].insert(0, context_message)
                    _log("context: injected", {"items": len(top)})
                    is_context_injected = True
                    # Update cache... (try/except block)
                    try:
                        cur_emb = await self._calculate_embeddings([last_user])
                        if cur_emb is not None: self._context_cache = {"embedding": cur_emb, "context_message": context_message}
                    except Exception as cache_e: _log(f"cache: update failed: {cache_e}")

        # --- FIX: Add final status message if context was injected ---
        if is_context_injected:
            await self._emit_status(__event_emitter__, "✅ Relevante Erinnerungen Gefunden", done=True)
            return body

        # =================================================================
        # PHASE 2: EXTRACT NEW MEMORIES
        # =================================================================
        extraction_done = False; llm_found_memories = False
        new_mems_candidates: List[Dict] = []; should_save_raw = False
        extraction_provider_name = self.valves.extraction_provider.upper() # Assign before try

        try:
            _log(f"extract: trying configured LLM ({extraction_provider_name})...")
            # Set status to 'processing' (done=False)
            await self._emit_status(__event_emitter__, f"🧠 Analysiere Nachricht ({extraction_provider_name})...", done=False)
            new_mems_candidates = await self._extract_new_memories(last_user)
            extraction_done = True; llm_found_memories = bool(new_mems_candidates)
        except Exception as e:
            # Set status to 'failed' (done=True)
            _log(f"extract: Configured LLM ({extraction_provider_name}) failed ({e}), checking fallback...", {"traceback": traceback.format_exc()})
            await self._emit_status(__event_emitter__, f"⚠️ {extraction_provider_name} nicht erreichbar...", done=True)
            extraction_done = False


        # --- Embedding Fallback (Simple Dedupe & Save Raw) ---
        if not extraction_done and self.valves.use_local_embedding_fallback:
            _log("extract: using local embeddings fallback...");
            # Set status to 'processing fallback' (done=False)
            await self._emit_status(__event_emitter__, "⚙️ Lokale Fallback-Prüfung...", done=False)
            if self._is_blocked_for_extract(last_user) or self._is_spam_or_too_short(last_user): _log("extract: blocked raw message.")
            elif not candidates: should_save_raw = True; _log("extract: saving first raw message.")
            else:
                 try: # Fallback similarity check using _calculate_embeddings
                      new_emb = await self._calculate_embeddings([last_user]); existing_emb = await self._calculate_embeddings(candidates)
                      if new_emb is not None and existing_emb is not None:
                           if new_emb.ndim == 1: new_emb = new_emb.reshape(1, -1)
                           if existing_emb.ndim == 1: existing_emb = existing_emb.reshape(1, -1)
                           if new_emb.shape[1] == existing_emb.shape[1]:
                               sims = cosine_similarity(new_emb, existing_emb); max_sim = np.max(sims) if sims.size > 0 else 0.0
                               if max_sim < self.valves.min_similarity_for_upload:
                                    should_save_raw = True
                                    # Status update within the condition (done=True)
                                    await self._emit_status(__event_emitter__, f"✅ Neuer Fakt (Fallback, Ähnlichkeit: {max_sim:.0%}).", done=True)
                               else:
                                    # Status update within the condition (done=True)
                                    await self._emit_status(__event_emitter__, f"❌ Fakt zu ähnlich (Fallback, Ähnlichkeit: {max_sim:.0%}).", done=True)
                           else:
                                _log("extract: fallback dim mismatch."); await self._emit_status(__event_emitter__, "❌ Fallback-Fehler (Dim).", done=True)
                      else:
                           # Status update (done=True)
                           await self._emit_status(__event_emitter__, "❌ Lokale Fallback-Analyse fehlgeschlagen (Embeddings).", done=True)
                 except Exception as fb_e:
                     _log(f"extract: fallback check failed: {fb_e}"); await self._emit_status(__event_emitter__, "❌ Fehler bei Fallback-Analyse.", done=True)
            if should_save_raw: await self._mem_add_batch_from_candidates(user_id, [{"content": last_user}])
            # No need to set extraction_done=True here, the status messages handle completion.

        # --- Upload / Final Status (only if LLM extraction was attempted) ---
        elif extraction_done: # Only handle status if LLM extraction was the primary path
            if llm_found_memories:
                added_count = await self._upload_new_dedup(user_id, new_mems_candidates)
                if added_count > 0: await self._emit_status(__event_emitter__, f"✅ {added_count} neue {'Fakt' if added_count == 1 else 'Fakten'} gespeichert.", done=True)
                else: await self._emit_status(__event_emitter__, "ℹ️ Fakten gefunden, aber Duplikate oder gefiltert.", done=True)
            else: # LLM ran, found nothing
                await self._emit_status(__event_emitter__, "ℹ️ Nichts Neues zum Merken gefunden.", done=True)
        # --- Handle case where LLM failed and fallback is disabled ---
        elif not extraction_done and not self.valves.use_local_embedding_fallback:
             # The failure status was already emitted in the except block
             pass # No additional status needed here

        return body

    async def outlet(self, body: Dict[str, Any], __event_emitter__: Optional[Any] = None, __user__: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return body # Passthrough

    async def cleanup(self):
        if self._session and not self._session.closed: await self._session.close()

