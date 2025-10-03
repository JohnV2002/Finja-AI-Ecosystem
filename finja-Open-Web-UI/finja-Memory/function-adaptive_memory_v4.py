
"""
======================================================================
            Adaptive Memory – External Server Edition
======================================================================

  Project: Adaptive Memory (OpenWebUI Plugin)
  Version: 4.3.2
  Author:  John (J. Apps / Sodakiller1)
  License: Apache License 2.0 (c) 2025 J. Apps
  Original Inspiration & Credits: gramanoid (aka diligent_chooser)
  Original Plugin: https://openwebui.com/f/alexgrama7/adaptive_memory_v2
  Author Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
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

  + **Duales Fallback-System & "Local Only"-Modus:** Das Plugin funktioniert
    dank lokaler Embedding-Modelle auch bei einem OpenAI-Ausfall oder
    komplett ohne OpenAI-Anbindung.

  + **Verbessertes User-Feedback:** Das Plugin gibt dem User jetzt klare und
    freundliche Statusmeldungen für alle Aktionen im Chat aus.

  + **Robuste Logik & Refactoring:** Die zentrale `inlet`-Methode wurde 
    grundlegend überarbeitet, um alle Modi sauber und fehlerresistent zu steuern.
----------------------------------------------------------------------

----------------------------------------------------------------------
 Roadmap:
 ---------------------------------------------------------------------
  • Erweiterbare Memory-Services (z. B. ChromaDB-Backend optional)
  • Mehr Visualisierung und Admin-Tools

----------------------------------------------------------------------
 License Notice:
 ---------------------------------------------------------------------
  Dieses Projekt basiert auf der Arbeit von gramanoid (diligent_chooser)
  und wurde unter Beibehaltung der Apache License 2.0 veröffentlicht.
  Alle Rechte an den Änderungen © 2025 J. Apps

======================================================================
"""

import json
import logging
from typing import Any, Dict, List, Optional, Literal
import aiohttp
from pydantic import BaseModel, Field
from datetime import datetime
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz
import time

logger = logging.getLogger("openwebui.plugins.adaptive_memory_v4")
handler = logging.StreamHandler()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def _log(msg: str, extra: Optional[dict] = None):
    try:
        logger.info(f"[v4] {msg} - {json.dumps(extra, ensure_ascii=False) if extra else '{}'}")
    except Exception:
        logger.info(f"[v4] {msg}")

class Filter:
    """
    Adaptive Memory v4 – PLAYGROUND
    1) user_id aus OpenWebUI
    2) GET /get_memories -> Relevanz-Check via OpenAI (>= threshold)
       -> RELEVANTE Fakten als System-Kontext injizieren (Modell antwortet selbst)
    3) Wenn nix relevant: OpenAI Memory-Extract (JSON), guard + dedupe -> /add_memories
    4) KEINE eigene Antwort-Generierung im Plugin (kein Bypass/Skip), nur Kontext.
    """

    _embedding_model: Optional[SentenceTransformer] = None

    class Valves(BaseModel):
        # --- LLM / OpenAI ---
        llm_api_endpoint_url: str = Field(default="https://api.openai.com/v1/chat/completions")
        llm_model_name: str = Field(default="gpt-4o-mini")
        llm_api_key: str = Field(default="changeme-openai-key")

        # --- Memory Server ---
        memory_api_base: str = Field(
            default="http://localhost:8000",
            description="Base URL deines Memory-Servers (ohne Pfad, http!)"
        )
        memory_api_key: str = Field(default="changeme-supersecretkey")

        processing_mode: Literal["openai", "local_only"] = Field(
            default="openai",
            description="Modus: 'openai' (Standard) oder 'local_only' für reines lokales Embedding."
        )

        # --- Thresholds/Behavior ---
        relevance_threshold: float = Field(default=0.70, description="Relevanz-Schwelle (0..1)")
        max_memories_fetch: int = Field(default=100, description="Wieviele Memories max. holen")
        relevance_prefilter_cap: int = Field(default=15, description="Anzahl der Top-Erinnerungen aus der lokalen Vorauswahl, die an OpenAI gesendet werden.")
        min_memory_chars: int = Field(default=10, description="Minimale Zeichenlänge für eine neue Erinnerung.")
        min_memory_tokens: int = Field(default=3, description="Minimale Anzahl von Wörtern für eine neue Erinnerung.")
        topical_cache_threshold: float = Field(default=0.92, description="Ähnlichkeits-Schwelle (0..1), um den Themen-Cache zu nutzen.")
        spam_filter_patterns: List[str] = Field(
            default=[
                r"^\s*https?://[^\s]+\s*$",  # Blockiert reine URLs
                r"^\s*[\U0001F600-\U0001F64F\s]+\s*$", # Blockiert reine Emojis
            ],
            description="Regex-Muster, um Spam oder unerwünschte Inhalte zu blockieren."
        )
        

        # --- EINSTELLUNGEN FÜR DUPLICATE-KILLER 2.0 ---
        dup_cosine_threshold: float = Field(default=0.92, description="Mindest-Ähnlichkeit (Cosine), um als Duplikat zu gelten.")
        dup_levenshtein_threshold: float = Field(default=0.90, description="Mindest-Textähnlichkeit (Levenshtein), um als Duplikat zu gelten.")
        
        # --- EINSTELLUNGEN FÜR OPENAI EMBEDDINGS ---
        openai_embedding_model: str = Field(default="text-embedding-3-small", description="OpenAI-Modell für Embedding-Vektoren.")
        llm_embedding_endpoint_url: str = Field(default="https://api.openai.com/v1/embeddings", description="API-Endpunkt für OpenAI Embeddings.")

        # --- NEUE FELDER FÜR FALLBACK ---
        use_local_embedding_fallback: bool = Field(default=True, description="Aktiviert den lokalen Embedding-Fallback bei OpenAI-Fehlern.")
        local_embedding_model: str = Field(default="all-MiniLM-L6-v2", description="Modell für lokale Embeddings.")
        min_similarity_for_upload: float = Field(default=0.95, description="Minimale Ähnlichkeit, um ein Duplikat beim Fallback zu erkennen.")


        # --- System Prompts ---
        # WICHTIG: Für Memory-Identifikation, nicht für Chat
        memory_identification_prompt: str = Field(
            default=(
                "You are an automated JSON data extraction system. Your SOLE function is to identify "
                "user-specific, persistent facts from user messages and output them STRICTLY as a JSON array.\n\n"
                "ABSOLUTE RULES:\n"
                "1. OUTPUT MUST BE A VALID JSON ARRAY. It must start with `[` and end with `]`. NO OTHER TEXT.\n"
                "2. A SINGLE FACT MUST BE WRAPPED IN AN ARRAY. e.g., `[{\"operation\": ...}]`.\n"
                "3. IF NO FACTS ARE FOUND, an empty array `[]` is the ONLY valid output.\n"
                "4. EXTRACT ALL DISTINCT FACTS. If a message contains multiple facts (e.g., a name AND a preference), create a separate JSON object for EACH fact inside the array.\n"
                "5. GENERALIZE FROM SINGLE EVENTS. If a user says 'I ate pizza yesterday', extract the persistent preference 'User likes pizza', not the one-time event.\n\n"
                "ALLOWED TAGS: [\"identity\",\"behavior\",\"preference\",\"goal\",\"relationship\",\"possession\"]\n"
                "MEMORY BANKS: \"General\", \"Personal\", \"Work\"\n\n"
                "--- EXAMPLES ---\n"
                "USER MESSAGE 1: \"Mein Name ist Peter und ich mag das Spiel Satisfactory.\"\n"
                "CORRECT OUTPUT 1:\n"
                "[\n"
                "  {\"operation\": \"NEW\", \"content\": \"User's name is Peter\", \"tags\": [\"identity\"], \"memory_bank\": \"Personal\"},\n"
                "  {\"operation\": \"NEW\", \"content\": \"User likes the game Satisfactory\", \"tags\": [\"preference\", \"behavior\"], \"memory_bank\": \"Personal\"}\n"
                "]\n\n"
                "USER MESSAGE 2: \"Ich komme aus Deutschland.\"\n"
                "CORRECT OUTPUT 2:\n"
                "[\n"
                "  {\"operation\": \"NEW\", \"content\": \"User is from Germany\", \"tags\": [\"identity\"], \"memory_bank\": \"Personal\"}\n"
                "]\n\n"
                "Now, analyze the following user message(s) and provide ONLY the JSON array output."
            )
        )
        # WICHTIG: Für Relevanz-Check, nicht für Chat
        # Hier wird geprüft, ob die vorhandenen Memories relevant sind für die aktuelle User-Nachricht.
        # Die Antwort ist eine Liste von Objekten mit "memory" und "score".
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

        delete_trigger_phrases: List[str] = Field(
            default=[
                "lösch meine erinnerungen",
                "lösche meine memorys",
                "vergiss alles über mich",
                "setze dein gedächtnis zurück"
            ],
            description="Liste von Sätzen (in Kleinbuchstaben), die den Löschvorgang einleiten."
        )
        delete_confirmation_phrase: str = Field(
            default="Ja, ich möchte all meine Erinnerungen unwiderruflich gelöscht haben",
            description="Der exakte Satz, den der User zur Bestätigung eingeben muss."
        )
        
    def __init__(self):
        # Initialize valves with default values
        self.valves = self.Valves()
        self._session: Optional[aiohttp.ClientSession] = None
        self._context_cache: Optional[Dict[str, Any]] = None
        self._pending_deletions: Dict[str, float] = {}

        # simple regexes to block saving question-only/ephemeral statements
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

    @property
    def embedding_model(self) -> SentenceTransformer:
        """Lädt das lokale Embedding-Modell oder gibt das gecachte Modell zurück."""
        if Filter._embedding_model is None:
            model_name = self.valves.local_embedding_model
            _log(f"embedding: loading model '{model_name}' for the first time.")
            try:
                # Der Import hier drin ist ein cleverer Trick, falls es doch mal fehlt
                from sentence_transformers import SentenceTransformer
                Filter._embedding_model = SentenceTransformer(model_name)
            except Exception as e:
                _log(f"embedding: FAILED to load model '{model_name}'. Fallback will not work. Error: {e}")
                raise e # Wichtig, um den Fehler klar zu machen
        return Filter._embedding_model
    
    async def _calculate_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """Konvertiert eine Liste von Texten in Embedding-Vektoren."""
        if not texts:
            return None
        try:
            model = self.embedding_model # Ruft die @property-Methode auf
            embeddings = model.encode(texts, convert_to_numpy=True)
            return embeddings
        except Exception as e:
            _log(f"embedding: could not calculate embeddings. Error: {e}")
            return None

    # --------------------------
    # Utils
    # --------------------------
    async def _session_get(self) -> aiohttp.ClientSession: 
        if self._session is None or self._session.closed: 
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        return self._session
    
    def _get_user_id(self, __user__: Optional[dict]) -> str:
        if not __user__:
            return "default"
        # prefer username, dann id
        return (__user__.get("username") if isinstance(__user__, dict) else None) or \
               (__user__.get("id") if isinstance(__user__, dict) else None) or "default"

    def _mem_url(self, path: str) -> str:
        return f"{self.valves.memory_api_base.rstrip('/')}/{path.lstrip('/')}"
    
    async def _emit_status(self, emitter: Optional[Any], message: str):
        """Sendet eine sichtbare Status-Nachricht an den User im Chat."""
        if emitter:
            try:
                # Wir schicken ein Dictionary im Format, das OpenWebUI versteht
                await emitter({
                    "type": "status",
                    "data": { "description": message, "done": True }
                })
            except Exception as e:
                _log(f"emitter: failed to send status. Error: {e}")

    def _is_spam_or_too_short(self, text: str) -> bool:
        """Prüft, ob ein Text zu kurz ist oder Spam-Muster enthält."""
        # 1. Check auf Mindest-Zeichenlänge
        if len(text) < self.valves.min_memory_chars:
            _log("filter: blocked, too short (chars)", {"text": text})
            return True

        # 2. Check auf Mindest-Wörter (Tokens)
        if len(text.split()) < self.valves.min_memory_tokens:
            _log("filter: blocked, too short (tokens)", {"text": text})
            return True

        # 3. Check auf Spam-Muster (URLs, Emojis etc.)
        for pattern in self.valves.spam_filter_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                _log("filter: blocked, spam pattern matched", {"text": text, "pattern": pattern})
                return True

        return False # Wenn alle Checks bestanden, ist es kein Spam.
    
    def _normalize_text(self, text: str) -> str:
        """Bereinigt einen Text für Vergleiche (Kleinschreibung, Satzzeichen etc.)."""
        # Alles klein schreiben
        text = text.lower()
        # Alle Zeichen, die keine Buchstaben, Zahlen oder Leerzeichen sind, entfernen
        text = re.sub(r'[^\w\s]', '', text)
        # Mehrfache Leerzeichen durch ein einziges ersetzen
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    # --------------------------
    # Memory Server
    # --------------------------
    async def _mem_get_existing(self, user_id: str) -> List[dict]:
        try:
            s = await self._session_get()
            url = self._mem_url("get_memories")
            headers = {"X-API-Key": self.valves.memory_api_key}
            params = {"user_id": user_id, "limit": self.valves.max_memories_fetch}
            async with s.get(url, headers=headers, params=params) as r:
                if r.status == 200:
                    return await r.json()
                _log("mem:get failed", {"status": r.status, "text": (await r.text())[:200]})
        except Exception as e:
            _log("mem:get exception", {"err": str(e)})
        return []

    async def _mem_add_batch(self, items: List[dict]) -> bool:
        if not items:
            return True
        try:
            s = await self._session_get()
            url = self._mem_url("add_memories")
            headers = {"X-API-Key": self.valves.memory_api_key, "Content-Type": "application/json"}
            async with s.post(url, headers=headers, json=items) as r:
                txt = await r.text()
                _log("mem:add", {"status": r.status, "resp": txt[:200], "items": len(items)})
                return r.status == 200
        except Exception as e:
            _log("mem:add exception", {"err": str(e)})
            return False

    # --------------------------
    # OpenAI helpers
    # --------------------------
    async def _openai_json(self, messages: List[dict]) -> str:
        """Call OpenAI with response_format=json_object. Returns content string (should be JSON)."""
        s = await self._session_get()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.valves.llm_api_key}"}
        payload = {
            "model": self.valves.llm_model_name,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        async with s.post(self.valves.llm_api_endpoint_url, headers=headers, json=payload) as r:
            txt = await r.text()
            if r.status != 200:
                _log("openai:json error", {"status": r.status, "resp": txt[:200]})
                return "[]"
            try:
                data = json.loads(txt)
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "[]")
                _log("openai:json raw", {"first120": content[:120]})
                return content
            except Exception:
                return "[]"
            
    # In der 'Filter'-Klasse, nach _openai_json

    async def _get_openai_embedding(self, text: str) -> Optional[List[float]]:
        """Holt einen Embedding-Vektor für einen Text von der OpenAI API."""
        # Gib nichts zurück, wenn der Text leer ist.
        if not text:
            return None

        # Bereite die Anfrage-Daten vor.
        s = await self._session_get()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.valves.llm_api_key}"}
        payload = {
            "model": self.valves.openai_embedding_model,
            "input": text
        }
        
        try:
            # Sende die Anfrage an den Embedding-Endpunkt.
            async with s.post(self.valves.llm_embedding_endpoint_url, headers=headers, json=payload) as r:
                if r.status != 200:
                    _log("openai:embedding error", {"status": r.status, "resp": (await r.text())[:200]})
                    return None
                
                # Verarbeite die Antwort.
                data = await r.json()
                # Der Vektor befindet sich im ersten Element der 'data'-Liste.
                embedding = (data.get("data") or [{}])[0].get("embedding")

                if isinstance(embedding, list):
                    return embedding
                else:
                    _log("openai:embedding response format unexpected", {"data": data})
                    return None
        except Exception as e:
            _log("openai:embedding exception", {"err": str(e)})
            # Wir geben hier bewusst eine Exception weiter, damit unser Fallback-System sie fangen kann.
            raise e

    # --------------------------
    # Relevance check using OpenAI
    # --------------------------
    async def _rank_relevance(self, user_msg: str, candidate_texts: List[str]) -> List[dict]:
        """Return list of {"memory": str, "score": float}."""
        if not candidate_texts:
            return []
        sys = {"role": "system", "content": self.valves.memory_relevance_prompt}
        usr = {
            "role": "user",
            "content": json.dumps({
                "current_message": user_msg,
                "candidates": candidate_texts
            }, ensure_ascii=False)
        }
        raw = await self._openai_json([sys, usr])

        # robust parser: accept dict OR list
        try:
            parsed = json.loads(raw)
        except Exception:
            return []

        if isinstance(parsed, dict):
            parsed = [parsed]
        out: List[dict] = []
        if isinstance(parsed, list):
            for e in parsed:
                if not isinstance(e, dict):
                    continue
                mem = e.get("memory")
                try:
                    score = float(e.get("score", 0.0))
                except Exception:
                    score = 0.0
                if isinstance(mem, str):
                    out.append({"memory": mem, "score": max(0.0, min(1.0, score))})
        return out

    # --------------------------
    # Memory extraction & upload
    # --------------------------
    def _is_blocked_for_extract(self, text: str) -> bool:
        t = text.strip().lower()
        for pat in self._block_extract_patterns:
            if re.match(pat, t):
                return True
        return False

    async def _extract_new_memories(self, last_user_text: str) -> List[dict]:
        # guard: block trivial/ephemeral prompts from being saved
        if self._is_blocked_for_extract(last_user_text):
            _log("extract: blocked by guard", {"text": last_user_text[:60]})
            return []

        sys = {"role": "system", "content": self.valves.memory_identification_prompt}
        usr = {"role": "user", "content": last_user_text}
        raw = await self._openai_json([sys, usr])

        # parse flexible: dict OR list; then filter
        try:
            arr = json.loads(raw)
        except Exception:
            arr = []

        if isinstance(arr, dict):
            arr = [arr]
        if not isinstance(arr, list):
            arr = []

        out = []
        for m in arr:
            if not isinstance(m, dict):
                continue
            if m.get("operation") != "NEW":
                continue
            
            content = (m.get("content") or "").strip()
            
            # --- HIER WIRD DER NEUE FILTER ANGERUFEN ---
            if not content or self._is_spam_or_too_short(content):
                continue
            # -------------------------------------------
            
            # sanity filter gegen Grüße (bleibt als extra Sicherheit)
            lc = content.lower()
            if lc in {"hi", "hii", "hiii", "hallo", "hey", "wie gehts", "wie geht's"}:
                continue
            if re.search(r"\b(asking for (their|his|her) name|frägt?|fragt? nach seinem namen)\b", lc):
                continue
                
            out.append(m)

        _log("extract: parsed and filtered", {"in": len(arr), "out": len(out)})
        return out

    async def _upload_new_dedup(self, user_id: str, candidates: List[dict]) -> int:
        """
        Lädt neue Erinnerungen hoch und führt dabei eine erweiterte Duplikats-Prüfung 
        (Cosine & Levenshtein) durch. Gibt die Anzahl der tatsächlich hochgeladenen 
        Erinnerungen zurück.
        """
        if not candidates:
            return 0

        # 1. Lade existierende Erinnerungen zum Vergleichen
        existing_memories = await self._mem_get_existing(user_id)
        if not existing_memories:
            _log("dedup: No existing memories, uploading all candidates.")
            return await self._mem_add_batch_from_candidates(user_id, candidates)

        # Bereite die Texte für den Vergleich vor
        existing_texts = [m.get("text", "") for m in existing_memories]
        normalized_existing_texts = [self._normalize_text(t) for t in existing_texts]

        # --- OPTIMIERUNG: Lade alle benötigten Embeddings EINMAL im Voraus ---
        existing_embeddings_openai = []
        if self.valves.processing_mode == 'openai':
            _log("dedup: Pre-fetching OpenAI embeddings for existing memories...")
            existing_embeddings_openai = [await self._get_openai_embedding(t) for t in normalized_existing_texts]
        # --------------------------------------------------------------------

        # 2. Filtere Duplikate aus den neuen Kandidaten heraus
        non_duplicates = []
        for mem_candidate in candidates:
            content = mem_candidate.get("content", "").strip()
            if not content:
                continue
            
            normalized_content = self._normalize_text(content)
            is_duplicate = False

            # --- PRÜFUNG 1: COSINE SIMILARITY (OpenAI oder Lokal) ---
            try:
                new_embedding = None
                if self.valves.processing_mode == 'openai':
                    new_embedding = await self._get_openai_embedding(normalized_content)

                if new_embedding is None:
                    _log("dedup: Using local embeddings for cosine check.")
                    new_vec_np = await self._calculate_embeddings([normalized_content])
                    existing_vecs_np = await self._calculate_embeddings(normalized_existing_texts)
                    if new_vec_np is not None and existing_vecs_np is not None:
                        similarities = cosine_similarity(new_vec_np, existing_vecs_np)[0]
                        max_sim = np.max(similarities)
                        if max_sim >= self.valves.dup_cosine_threshold:
                            _log(f"dedup: Blocked by local cosine similarity (Score: {max_sim:.2f})", {"text": content})
                            is_duplicate = True
                else:
                    _log("dedup: Using pre-fetched OpenAI embeddings for cosine check.")
                    # Vergleiche mit den VORHER geladenen Embeddings
                    for old_embedding in existing_embeddings_openai:
                        if old_embedding:
                            sim = np.dot(new_embedding, old_embedding) / (np.linalg.norm(new_embedding) * np.linalg.norm(old_embedding))
                            if sim >= self.valves.dup_cosine_threshold:
                                _log(f"dedup: Blocked by OpenAI cosine similarity (Score: {sim:.2f})", {"text": content})
                                is_duplicate = True
                                break
                
                if is_duplicate:
                    continue

            except Exception as e:
                _log(f"dedup: Cosine similarity check failed unexpectedly: {e}. Skipping to Levenshtein.")

            # --- PRÜFUNG 2: LEVENSHTEIN-DISTANZ (als Backup) ---
            for old_text in normalized_existing_texts:
                ratio = fuzz.ratio(normalized_content, old_text) / 100.0
                if ratio >= self.valves.dup_levenshtein_threshold:
                    _log(f"dedup: Blocked by Levenshtein distance (Score: {ratio:.2f})", {"text": content})
                    is_duplicate = True
                    break
            
            if is_duplicate:
                continue

            non_duplicates.append(mem_candidate)

        # 3. Lade die gefilterte Liste hoch
        if not non_duplicates:
            _log("dedup: All candidates were identified as duplicates.")
            return 0
        
        _log(f"dedup: Found {len(non_duplicates)} non-duplicate memories to upload.")
        return await self._mem_add_batch_from_candidates(user_id, non_duplicates)


    async def _mem_add_batch_from_candidates(self, user_id: str, candidates: List[dict]) -> int:
        """Hilfsfunktion, um eine Liste von Kandidaten-Dicts in Batch-Items umzuwandeln und hochzuladen."""
        batch = []
        for m in candidates:
            content = (m.get("content") or "").strip()
            if content:
                batch.append({
                    "user_id": user_id,
                    "text": content
                    # id und timestamp werden vom Server gesetzt
                })
        
        if not batch:
            return 0
            
        ok = await self._mem_add_batch(batch)
        return len(batch) if ok else 0

    # --------------------------
    # Main hooks
    # --------------------------
    async def inlet(
        self,
        body: Dict[str, Any],
        __event_emitter__: Optional[Any] = None,
        __user__: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
         # --- 1. SETUP: Grundlegende Daten vorbereiten ---
        _log("inlet: received batch")

        try:
            # Wir nutzen einen leichten Endpunkt wie /memory_stats für den Check.
            # Wichtig: Wir brauchen hier ein eigenes Timeout, um nicht ewig zu warten.
            s = await self._session_get()
            headers = {"X-API-Key": self.valves.memory_api_key}
            async with s.get(self._mem_url("memory_stats"), headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200:
                    raise ConnectionError(f"Server responded with status {r.status}")
        except Exception as e:
            error_message = (
                "🚨 **Memory-Server nicht erreichbar!**\n\n"
                "Bitte stelle sicher, dass der externe Server korrekt gestartet wurde. "
                "Die Anleitung findest du hier: [GitHub-Anleitung](https://github.com/JohnV2002/Finja-AI-Ecosystem/tree/main/finja-Open-Web-UI/finja-Memory)"
            )
            await self._emit_status(__event_emitter__, error_message)
            _log(f"inlet: connection to memory server failed. Aborting. Error: {e}")
            return body # Wichtig: Wir brechen hier ab, ohne das System abstürzen zu lassen.


        # 1) user_id # !snyk FALSE Positiv! 

        # snyk:ignore:python/UseOfHardcodedCredentials
        # Reason: User ID is dynamically retrieved from Open-Web-UI at runtime
        #         to identify the correct memory context. No static credentials
        #         are stored or loaded from hardcoded strings.
        user_id = self._get_user_id(__user__)

        # Finde die letzte Nachricht des Benutzers im Chatverlauf
        last_user = ""
        for m in reversed(body.get("messages", [])):
            if m.get("role") == "user" and m.get("content"):
                last_user = m["content"]
                break
        # Wenn keine User-Nachricht da ist, tu nix.
        if not last_user:
            return body


        # =================================================================
        # LÖSCH-ROUTINE (hat Vorrang vor allem anderen)
        # =================================================================
        
        # --- PRÜFUNG 1: Bestätigt der User eine laufende Lösch-Anfrage? ---
        if user_id in self._pending_deletions:
            # Sicherheits-Timeout: Anfrage verfällt nach 2 Minuten (120s)
            if time.time() - self._pending_deletions[user_id] > 120:
                del self._pending_deletions[user_id]
                await self._emit_status(__event_emitter__, "ℹ️ Zeit für die Lösch-Bestätigung ist abgelaufen.")
                return body # Abbrechen und normal weiter

            # Prüfe, ob die Nachricht die exakte Bestätigung ist.
            elif last_user.strip() == self.valves.delete_confirmation_phrase:
                _log("delete: User confirmed deletion.", {"user_id": user_id})
                # Sende den Lösch-Befehl an den Server
                try:
                    s = await self._session_get()
                    url = self._mem_url("delete_user_memories")
                    headers = {"X-API-Key": self.valves.memory_api_key, "Content-Type": "application/json"}
                    async with s.post(url, headers=headers, json={"user_id": user_id}) as r:
                        if r.status == 200:
                            await self._emit_status(__event_emitter__, "✅ Alle deine Erinnerungen wurden unwiderruflich gelöscht.")
                        else:
                            await self._emit_status(__event_emitter__, f"🔥 Server-Fehler: Deine Erinnerungen konnten nicht gelöscht werden (Status: {r.status}).")
                except Exception as e:
                    _log(f"delete: server call failed: {e}")
                    await self._emit_status(__event_emitter__, "🔥 Verbindungs-Fehler: Keine Verbindung zum Memory-Server.")

                # Setze den Status zurück und blockiere die weitere Verarbeitung dieser Nachricht.
                del self._pending_deletions[user_id]
                body["messages"] = [] # Leere die Nachrichten, damit die LLM nicht auf die Bestätigung antwortet.
                return body

            # Wenn der User etwas anderes schreibt, wird die Anfrage abgebrochen.
            else:
                _log("delete: User aborted deletion.", {"user_id": user_id})
                await self._emit_status(__event_emitter__, "ℹ️ Löschvorgang abgebrochen.")
                del self._pending_deletions[user_id]
                body["messages"] = [] # Leere auch hier die Nachrichten.
                return body

        # --- PRÜFUNG 2: Startet der User eine neue Lösch-Anfrage? ---
        # Wir prüfen, ob eine der Trigger-Phrasen in der User-Nachricht enthalten ist.
        if any(phrase in last_user.lower() for phrase in self.valves.delete_trigger_phrases):
            _log("delete: User initiated deletion.", {"user_id": user_id})
            # Merke dir, dass dieser User eine Bestätigung abgeben muss (setzt den Timer).
            self._pending_deletions[user_id] = time.time()
            
            # Wir zwingen die LLM, unsere Bestätigungsfrage zu stellen.
            confirmation_question = (
                f"Bist du dir sicher, dass du alle deine Erinnerungen unwiderruflich löschen möchtest? "
                f"Antworte bitte mit genau dem Satz: '{self.valves.delete_confirmation_phrase}'"
            )
            
            # Erstelle eine "künstliche" Antwort vom Assistenten.
            # Wir überschreiben den Nachrichtenverlauf, sodass die LLM gar nicht erst antworten muss.
            body["messages"].append({"role": "assistant", "content": confirmation_question})
            
            # Wir fügen eine Status-Meldung hinzu, um es "offizieller" zu machen.
            await self._emit_status(__event_emitter__, "🔒 Eine Sicherheitsüberprüfung ist erforderlich.")
            
            return body
    
        # Lade alle bisherigen Erinnerungen des Users vom Server
        existing = await self._mem_get_existing(user_id)
        # Bereite eine reine Text-Liste der Erinnerungen für die Analyse vor.
        candidates = [(m.get("text") or "") for m in existing if isinstance(m, dict) and (m.get("text") or "").strip()]

        # =================================================================
        # PHASE 1: RELEVANZ-CHECK
        # =================================================================
        
        ### KORREKTUR 1: Der Themen-Cache-Check kommt GANZ an den Anfang von Phase 1 ###
        # --- "THEMEN-CACHE"-CHECK ---
        if self._context_cache and 'embedding' in self._context_cache:
            _log("cache: checking topical cache...")
            new_embedding = await self._calculate_embeddings([last_user])
            if new_embedding is not None:
                # Vergleiche die Ähnlichkeit der aktuellen Nachricht mit der letzten.
                similarity = cosine_similarity(new_embedding, self._context_cache['embedding'])[0][0]
                
                # Wenn das Thema sehr ähnlich ist, nutze den gespeicherten Kontext.
                if similarity >= self.valves.topical_cache_threshold:
                    _log(f"cache: HIT! Topic similarity {similarity:.2f} is high. Re-injecting cached context.")
                    body["messages"].insert(0, self._context_cache['context_message'])
                    return body # Wichtig: Wir überspringen den Rest der Funktion.
                else:
                    _log(f"cache: MISS! Topic similarity {similarity:.2f} is low. Performing full check.")

        is_context_injected = False
        if candidates:
            ranked = []
            if self.valves.processing_mode == "openai":
                try:
                    # --- LOKALE VORAUSWAHL (um Token zu sparen) ---
                    # ... (dieser Teil war schon korrekt)
                    prefilter_cap = self.valves.relevance_prefilter_cap
                    new_embedding = await self._calculate_embeddings([last_user])
                    existing_embeddings = await self._calculate_embeddings(candidates)
                    if new_embedding is not None and existing_embeddings is not None:
                        similarities = cosine_similarity(new_embedding, existing_embeddings)[0]
                        sorted_candidates = sorted(zip(candidates, similarities), key=lambda item: item[1], reverse=True)
                        prefiltered_candidates = [text for text, score in sorted_candidates[:prefilter_cap]]
                    else:
                        prefiltered_candidates = candidates[-prefilter_cap:]

                    # --- FINALE PRÜFUNG mit OpenAI (nur noch mit den Top-Kandidaten) ---
                    ranked = await self._rank_relevance(last_user, prefiltered_candidates)

                except Exception as e:
                    _log(f"relevance: OpenAI path failed ({e}), using fallback...")
                    await self._emit_status(__event_emitter__, "⚠️ OpenAI nicht erreichbar. Wechsle auf lokale Analyse...")
                    if not self.valves.use_local_embedding_fallback:
                        raise e
            
            if not ranked and self.valves.use_local_embedding_fallback:
                # ... (Lokaler Pfad, dieser Teil war schon korrekt)
                _log("relevance: using local embeddings for full ranking...")
                new_embedding = await self._calculate_embeddings([last_user])
                existing_embeddings = await self._calculate_embeddings(candidates)
                if new_embedding is not None and existing_embeddings is not None:
                    similarities = cosine_similarity(new_embedding, existing_embeddings)[0]
                    ranked = [{"memory": text, "score": float(score)} for text, score in zip(candidates, similarities)]

            # --- Auswertung: Dieser Teil war schon korrekt ---
            threshold = self.valves.relevance_threshold
            relevant = [r for r in ranked if r.get("score", 0.0) >= threshold]
            if relevant:
                relevant.sort(key=lambda x: x.get("score", 0.0), reverse=True)
                top = [r["memory"] for r in relevant[:3] if isinstance(r.get("memory"), str)]
                if top:
                    context = "MEMORY_CONTEXT:\n" + "\n".join(f"- {t}" for t in top)
                    
                    ### KORREKTUR 2: Variable 'context_message' hier erstellen ###
                    context_message = {"role": "system", "content": context}
                    body["messages"].insert(0, context_message)
                    
                    _log("context: injected", {"items": len(top), "first": top[0][:60]})
                    is_context_injected = True
                    
                    # Speichere den Erfolg im Cache für die nächste Runde
                    current_embedding = await self._calculate_embeddings([last_user])
                    if current_embedding is not None:
                        self._context_cache = {
                            "embedding": current_embedding,
                            "context_message": context_message # Jetzt existiert diese Variable
                        }

        if is_context_injected:
            return body

        # =================================================================
        # PHASE 2: NEUE ERINNERUNGEN EXTRAHIEREN (Dieser Teil war schon korrekt)
        # =================================================================
        # ... (der Rest der Funktion bleibt unverändert) ...
        if self.valves.processing_mode == "openai":
            try:
                _log("extract: trying OpenAI...")
                await self._emit_status(__event_emitter__, "🧠 Analysiere Nachricht auf neue Fakten...")
                new_mems = await self._extract_new_memories(last_user)
                if new_mems:
                    added_count = await self._upload_new_dedup(user_id, new_mems)
                    plural = "Fakt" if added_count == 1 else "Fakten"
                    await self._emit_status(__event_emitter__, f"✅ {added_count} neue {plural} gelernt und gespeichert.")
                else:
                    await self._emit_status(__event_emitter__, "ℹ️ Nichts Neues zum Merken gefunden.")
                return body
            except Exception as e:
                _log(f"extract: OpenAI failed ({e}), using fallback...")
                await self._emit_status(__event_emitter__, "⚠️ OpenAI nicht erreichbar. Wechsle auf lokale Analyse...")
                if not self.valves.use_local_embedding_fallback:
                    raise e
        
        _log("extract: using local embeddings for deduplication check...")
        await self._emit_status(__event_emitter__, "⚙️ Führe lokale Analyse durch...")
        if not candidates:
            await self._upload_new_dedup(user_id, [{"content": last_user}])
            await self._emit_status(__event_emitter__, "✅ Erster Fakt gelernt und lokal gespeichert.")
        else:
            new_embedding = await self._calculate_embeddings([last_user])
            existing_embeddings = await self._calculate_embeddings(candidates)
            if new_embedding is not None and existing_embeddings is not None:
                similarities = cosine_similarity(new_embedding, existing_embeddings)
                max_similarity = np.max(similarities)
                if max_similarity < self.valves.min_similarity_for_upload:
                    await self._upload_new_dedup(user_id, [{"content": last_user}])
                    await self._emit_status(__event_emitter__, f"✅ Neuer Fakt gelernt (Ähnlichkeit: {max_similarity:.0%}).")
                else:
                    await self._emit_status(__event_emitter__, f"❌ Fakt zu ähnlich, nicht erneut gespeichert (Ähnlichkeit: {max_similarity:.0%}).")
            else:
                await self._emit_status(__event_emitter__, "❌ Lokale Analyse fehlgeschlagen.")

        return body

    async def outlet(
        self,
        body: Dict[str, Any],
        __event_emitter__: Optional[Any] = None,
        __user__: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # passthrough
        return body

    async def cleanup(self):
        if self._session and not self._session.closed:
            await self._session.close()
