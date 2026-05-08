import json
import time
import os
import threading
import asyncio
import aiohttp
import requests
import re
import numpy as np
import sys
from typing import List, Optional, Dict, Any, Literal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore, Style
from exceptions import (
    YourAIMemoryServerError,
    YourAIEmbedError,
    YourAIEmbedDisconnectError,
    YourAILLMTimeoutError,
    YourAILLMError,
    YourAIUnexpectedError
)

from config import (
    LLM_HOST_MAIN,
    LLM_HOST_STD,
    MEMORY_API_BASE,
    MEMORY_API_KEY,
    HIPPOCAMPUS_USER_ID,
    HIPPOCAMPUS_EXTRACTION_MODEL,
    HIPPOCAMPUS_EMBEDDING_MODEL,
    HIPPOCAMPUS_EMBEDDING_OPENROUTER,
    HIPPOCAMPUS_RELEVANCE_MODEL,
    HIPPOCAMPUS_ENABLE_PREFILTERING,
    HIPPOCAMPUS_RELEVANCE_THRESHOLD,
    HIPPOCAMPUS_PREFILTER_CAP,
    HIPPOCAMPUS_MAX_FETCH,
    HIPPOCAMPUS_DUP_COSINE,
    HIPPOCAMPUS_DUP_LEVENSHTEIN,
    HIPPOCAMPUS_STATS_TIMEOUT,
    HIPPOCAMPUS_EMBED_MAX_LENGTH,
    HIPPOCAMPUS_KEEP_ALIVE,
    HIPPOCAMPUS_LLM_TIMEOUT,
    HIPPOCAMPUS_MIN_TEXT_LENGTH,
    EMBED_TIMEOUT,
    EMBED_MAX_RETRIES,
    create_openrouter_client,
    call_openrouter
)
import config

# --- RAPIDFUZZ INITIALISIEREN ---
fuzz = None
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    log("MEMORY", "⚠️ RapidFuzz nicht gefunden. (pip install rapidfuzz)", Fore.YELLOW)


# ==========================================
# PROMPTS
# ==========================================

PROMPT_MEMORY_IDENTIFICATION = """You are an automated JSON data extraction system. Your SOLE function is to identify user-specific, persistent facts (relationships, hobbies, names, projects, GOALS, INTERESTS, TOPICS) from user messages.

EXAMPLE INPUT: "My best friend Bendy draws cool stuff."
EXAMPLE OUTPUT: ["User has a best friend named Bendy", "Bendy draws art"]

EXAMPLE INPUT: "Can you help me fix this Python code?"
EXAMPLE OUTPUT: ["User is coding in Python", "User is interested in programming"]

EXAMPLE INPUT: "Wie ist die chemische Zusammensetzung von Schnee?"
EXAMPLE OUTPUT: ["User interessiert sich für Chemie", "User fragt nach Schnee/Wissenschaft"]

EXAMPLE INPUT: "Look at my screen please."
EXAMPLE OUTPUT: []

RULES:
1. OUTPUT STRICTLY A JSON ARRAY OF STRINGS: ["Fact 1", "Fact 2"].
2. Extract facts about FRIENDS, FAMILY, NAMES, PREFERENCES, IMMEDIATE GOALS, and TOPICS OF INTEREST (e.g. Science, Coding, Gaming).
3. If the user asks technical questions, note their interest in that field.
4. If no facts are found, return [].
"""

PROMPT_MEMORY_RELEVANCE = """You are a memory retrieval assistant. Given:
1) CURRENT USER MESSAGE
2) CANDIDATE MEMORIES (list of strings)

Return a JSON array like: [{"memory":"...","score":0.0}] with score in [0,1].
Score high only if the memory is directly useful to respond to the current message.
Avoid trivia/irrelevant info. JSON only, no extra text."""


# ==========================================
# 🧠 THE HIPPOCAMPUS CLASS
# ==========================================

class Hippocampus:
    def __init__(self):
        self._user_id = HIPPOCAMPUS_USER_ID
        if not MEMORY_API_KEY:
            log("MEMORY", "⚠️ MEMORY_API_KEY nicht in .env gesetzt! Hippocampus kann nicht speichern.", Fore.RED)
        else:
            log("MEMORY", f"🧠 Hippocampus: Online für User '{self._user_id}'", Fore.GREEN)

    @property
    def user_id(self) -> str:
        return self._user_id

    @user_id.setter
    def user_id(self, value: str):
        self._user_id = value
        log("MEMORY", f"🧠 Hippocampus user_id → '{value}'", Fore.CYAN)

    # --- EIGENE MATHE FUNKTION ---
    def _manual_cosine_similarity(self, v1, v2):
        if v1 is None or v2 is None: return 0.0
        v1 = v1.flatten()
        v2 = v2.flatten()
        if v1.shape != v2.shape: return 0.0  # Dimension mismatch (e.g. old 4096-dim vs new 1024-dim vectors)
        dot = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0: return 0.0
        return dot / (norm1 * norm2)

    # --- STATS FUNKTION FÜR DAS UI ---
    def get_stats(self):
        """Holt live Statistiken vom Memory-Server."""
        try:
            url = f"{MEMORY_API_BASE}/memory_stats"
            # Kurzer Timeout (0.5s), damit das UI flüssig bleibt
            resp = requests.get(
                url, 
                params={"user_id": self._user_id},
                headers={"X-API-Key": MEMORY_API_KEY}, 
                timeout=HIPPOCAMPUS_STATS_TIMEOUT
            )
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException as e:
            err = YourAIMemoryServerError(url=f"{MEMORY_API_BASE}/memory_stats", cause=e)
            log_exception("MEMORY", err)
            return None
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="hippocampus_stats")
            log_exception("MEMORY", err)
            return None
        return None

    # --- HELPER: EMBEDDING (OpenRouter primary, Ollama fallback) ---
    _openrouter_client = None  # lazy-init, shared across calls

    def _get_or_create_openrouter_client(self):
        if Hippocampus._openrouter_client is None:
            Hippocampus._openrouter_client = create_openrouter_client()
        return Hippocampus._openrouter_client

    async def _get_embedding_openrouter(self, text: str, silent: bool = False) -> Optional[np.ndarray]:
        """OpenRouter embedding via openai SDK (sync → run in thread)."""
        client = self._get_or_create_openrouter_client()
        if not client:
            return None
        try:
            resp = await asyncio.to_thread(
                client.embeddings.create,
                model=HIPPOCAMPUS_EMBEDDING_OPENROUTER,
                input=text[:HIPPOCAMPUS_EMBED_MAX_LENGTH],
            )
            if resp.data and len(resp.data) > 0:
                return np.array(resp.data[0].embedding)
            return None
        except Exception as e:
            if not silent:
                log("MEMORY", f"⚠️ OpenRouter embed failed: {e}", Fore.YELLOW)
            return None

    async def _get_embedding_ollama(self, text: str, session: aiohttp.ClientSession, silent: bool = False) -> Optional[np.ndarray]:
        """Ollama local embedding (fallback)."""
        url = f"{LLM_HOST_STD.rstrip('/')}/api/embed"
        max_retries = EMBED_MAX_RETRIES

        for attempt in range(max_retries + 1):
            try:
                payload = {"model": HIPPOCAMPUS_EMBEDDING_MODEL, "input": text[:HIPPOCAMPUS_EMBED_MAX_LENGTH], "keep_alive": HIPPOCAMPUS_KEEP_ALIVE}

                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=EMBED_TIMEOUT)) as r:
                    if r.status == 200:
                        data = await r.json()
                        embeddings = data.get("embeddings") or data.get("embedding")
                        if isinstance(embeddings, list) and len(embeddings) > 0:
                            if isinstance(embeddings[0], list):
                                return np.array(embeddings[0])
                            return np.array(embeddings)
                        return None
                    else:
                        error_body = await r.text()
                        if not silent:
                            err = YourAIEmbedError(f"HTTP {r.status}: {error_body[:100]}", model=HIPPOCAMPUS_EMBEDDING_MODEL, attempt=attempt+1)
                            log_exception("MEMORY", err)
            except aiohttp.ServerDisconnectedError as e:
                if attempt < max_retries:
                    wait = 1.0 * (attempt + 1)
                    if not silent:
                        log("MEMORY", f"⚠️ Embed disconnect (attempt {attempt+1}/{max_retries+1}) → retry in {wait}s...", Fore.YELLOW)
                    await asyncio.sleep(wait)
                else:
                    if not silent:
                        err = YourAIEmbedDisconnectError(server_url=url, reconnect_attempts=max_retries, cause=e)
                        log_exception("MEMORY", err)
            except asyncio.TimeoutError as e:
                if attempt >= max_retries and not silent:
                    err = YourAIEmbedError("Timeout beim Embedding-Abruf", model=HIPPOCAMPUS_EMBEDDING_MODEL, attempt=attempt+1, cause=e)
                    log_exception("MEMORY", err)
            except Exception as e:
                if attempt >= max_retries and not silent:
                    err = YourAIUnexpectedError(cause=e, module="hippocampus_embedding")
                    log_exception("MEMORY", err)
        return None

    async def _get_embedding(self, text: str, session: aiohttp.ClientSession, silent: bool = False) -> Optional[np.ndarray]:
        """Holt Embedding-Vektor: OpenRouter primary, Ollama fallback.

        Args:
            silent: Wenn True, werden Fehler nicht geloggt (für Batch-Calls → Caller loggt Summary).
        """
        if not text:
            return None

        # Primary: OpenRouter only — kein Ollama-Fallback!
        # Grund: qwen3-embedding-8b (OpenRouter) = 4096-dim, qwen3-embedding:0.6b (Ollama) = 1024-dim
        # Dimension-Mismatch innerhalb eines Batches → cosine = 0.0 → Memories nie gefunden
        return await self._get_embedding_openrouter(text, silent=silent)

    async def _llm_json(self, model: str, messages: List[dict], session: aiohttp.ClientSession) -> str:
        try:
            from clients.dashboard_client import debug as _dbg
        except Exception:
            _dbg = None

        # 1. Mache ein OpenRouter Fallback!
        if config.USE_OPENROUTER:
            system_prompt = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
            user_msg = messages[1]["content"] if len(messages) > 1 else ""

            # Fallback-Kette: primäres Model → openrouter/auto → Ollama lokal
            or_primary = getattr(config, "OPENROUTER_MODEL_MEMORY", config.OPENROUTER_MODEL_COHERENCE)
            or_models_to_try = [or_primary, "openrouter/auto"]

            for or_model in or_models_to_try:
                try:
                    log("MEMORY", f"   ☁️ Starte OpenRouter LLM {or_model}...", Fore.LIGHTBLACK_EX)
                    if _dbg:
                        _dbg.llm_call("memory", f"☁️ {or_model}", user_msg[:300])

                    content, _ = await asyncio.to_thread(
                        call_openrouter,
                        system_prompt=system_prompt,
                        user_message=user_msg,
                        model=or_model,
                        temperature=0.0
                    )

                    content = content.replace("```json", "").replace("```", "").strip()
                    return content
                except Exception as e:
                    log("MEMORY", f"⚠️ OpenRouter [{or_model}] failed: {e} → nächster Fallback...", Fore.YELLOW)
                    if _dbg:
                        _dbg.error("memory", f"☁️ {or_model} fehlgeschlagen: {e}")

            log("MEMORY", "⚠️ Alle OpenRouter Models fehlgeschlagen → Ollama lokal", Fore.YELLOW)

        # 2. Local Fallback via Ollama
        log("MEMORY", f"   🖥️ Starte lokales Ollama {model}...", Fore.LIGHTBLACK_EX)
        if _dbg:
            _dbg.llm_call("memory", f"🏠 {model}", "")
        url = f"{LLM_HOST_STD.rstrip('/')}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "temperature": 0.0,
            "keep_alive": HIPPOCAMPUS_KEEP_ALIVE
        }

        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=HIPPOCAMPUS_LLM_TIMEOUT)) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("message", {}).get("content", "[]")
                else:
                    error_body = await r.text()
                    err = YourAILLMError(f"LLM Error {r.status}: {error_body[:150]}", model=model, module="hippocampus")
                    log_exception("MEMORY", err)
                    return "[]"
        except aiohttp.ServerDisconnectedError as e:
            err = YourAILLMError("ServerDisconnected (Ollama überlastet?)", model=model, module="hippocampus", cause=e)
            log_exception("MEMORY", err)
            raise err
        except asyncio.TimeoutError as e:
            err = YourAILLMTimeoutError(model=model, timeout_seconds=HIPPOCAMPUS_LLM_TIMEOUT, cause=e)
            log_exception("MEMORY", err)
            raise err
        except Exception as e:
            err = YourAIUnexpectedError(cause=e, module="hippocampus_llm_json")
            log_exception("MEMORY", err)
            raise err

    # ==========================================
    # 1. RETRIEVAL LOGIC ("Inlet")
    # ==========================================
    
    def get_relevant_memories(self, query_text: str):
        return asyncio.run(self._inlet_logic(query_text))

    async def _inlet_logic(self, query_text: str):
        log("MEMORY", f"🔍 [RETRIEVAL START] Frage: '{query_text}'", Fore.CYAN)
        try:
            from clients.dashboard_client import debug as _dbg
        except Exception:
            _dbg = None

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HIPPOCAMPUS_LLM_TIMEOUT)) as session:
            # A) Alle Memories holen
            headers = {"X-API-Key": MEMORY_API_KEY}
            params = {"user_id": self._user_id, "limit": HIPPOCAMPUS_MAX_FETCH}
            
            all_candidates = []
            try:
                async with session.get(f"{MEMORY_API_BASE}/get_memories", headers=headers, params=params) as r:
                    if r.status != 200: 
                        err = YourAIMemoryServerError(url=f"{MEMORY_API_BASE}/get_memories", status=r.status)
                        log_exception("MEMORY", err)
                        return []
                    data = await r.json()
                    all_candidates = [m.get("text", "") for m in data if m.get("text")]
                    log("MEMORY", f"   📚 Server lieferte {len(all_candidates)} Erinnerungen.", Fore.WHITE)
            except Exception as e: 
                err = YourAIMemoryServerError(url=f"{MEMORY_API_BASE}/get_memories", cause=e)
                log_exception("MEMORY", err)
                return []

            if not all_candidates: 
                return []

            # B) Pre-Filtering
            filtered_candidates = all_candidates
            if HIPPOCAMPUS_ENABLE_PREFILTERING:
                log("MEMORY", "   ⚡ Starte Vektor-Filterung (Pre-Filter)...", Fore.LIGHTBLACK_EX)
                query_vec = await self._get_embedding(query_text, session)
                
                if query_vec is not None:
                    tasks = [self._get_embedding(t, session, silent=True) for t in all_candidates]
                    cand_vecs = await asyncio.gather(*tasks)

                    # Batch-Error Summary (statt 20+ einzelne Logs)
                    _failed = sum(1 for v in cand_vecs if v is None)
                    if _failed > 0:
                        log("MEMORY", f"⚠️ Embedding: {_failed}/{len(cand_vecs)} fehlgeschlagen (Timeout/Blocked?)", Fore.YELLOW)

                    scored = []
                    for i, vec in enumerate(cand_vecs):
                        if vec is not None:
                            sim = self._manual_cosine_similarity(query_vec, vec)
                            scored.append((sim, all_candidates[i]))
                    
                    scored.sort(key=lambda x: x[0], reverse=True)
                    if scored: 
                        log("MEMORY", f"      🔹 Bester Vektor Match: {scored[0][0]:.2f} -> '{scored[0][1]}'", Fore.LIGHTBLACK_EX)
                    
                    filtered_candidates = [x[1] for x in scored[:HIPPOCAMPUS_PREFILTER_CAP]]
                else:
                    log("MEMORY", "   ⚠️ Query-Embedding fehlgeschlagen. Überspringe Filter.", Fore.YELLOW)

            # C) LLM Re-Ranking
            sys_msg = {"role": "system", "content": PROMPT_MEMORY_RELEVANCE}
            user_payload = json.dumps({"current_message": query_text, "candidates": filtered_candidates}, ensure_ascii=False)
            user_msg = {"role": "user", "content": user_payload}
            
            # LLM Re-Ranking (kann timeout/error werfen → Vektor-Fallback)
            raw_json = None
            llm_error = None
            try:
                raw_json = await self._llm_json(HIPPOCAMPUS_RELEVANCE_MODEL, [sys_msg, user_msg], session)
            except Exception as e:
                llm_error = e
                log("MEMORY", f"⚠️ LLM Re-Ranking failed: {e} → Vektor-Fallback", Fore.YELLOW)

            final_memories = []
            if raw_json:
                try:
                    parsed = json.loads(raw_json)
                    if isinstance(parsed, dict):
                        parsed = [parsed]

                    for item in parsed:
                        if isinstance(item, dict):
                            score = float(item.get("score", 0))
                            text = item.get("memory", "")

                            if score >= HIPPOCAMPUS_RELEVANCE_THRESHOLD:
                                final_memories.append(text)
                                log("MEMORY", f"   ✅ [TREFFER] Score {score:.2f}: {text}", Fore.GREEN)
                except json.JSONDecodeError as e:
                    from exceptions import YourAILLMParseError
                    err = YourAILLMParseError(model=HIPPOCAMPUS_RELEVANCE_MODEL, expected="JSON array", raw_preview=raw_json, cause=e)
                    log_exception("MEMORY", err)

            # FALLBACK: Wenn LLM Re-Ranking fehlschlägt oder nichts liefert,
            # nimm die besten Vektor-Matches direkt
            if not final_memories and filtered_candidates:
                log("MEMORY", "   ⚠️ LLM Re-Ranking leer/fehlgeschlagen → Nutze Top Vektor-Matches als Fallback", Fore.YELLOW)
                final_memories = filtered_candidates[:5]

            # Dashboard: Memory-Ergebnisse loggen
            if _dbg:
                used_model = getattr(config, "OPENROUTER_MODEL_MEMORY", config.OPENROUTER_MODEL_COHERENCE) if config.USE_OPENROUTER else HIPPOCAMPUS_RELEVANCE_MODEL
                _dbg.memory_search(query_text, final_memories, model=used_model)

            # Error nach oben propagieren (für Dashboard + Prompt error_context)
            # ABER trotzdem Memories zurückgeben (Vektor-Fallback)
            if llm_error:
                # Speichere Fallback-Memories als Attribut bevor wir raisen
                self._last_fallback_memories = final_memories
                raise llm_error

            return final_memories

    # ==========================================
    # 2. EXTRACTION LOGIC ("Outlet")
    # ==========================================

    def extract_and_save(self, user_text: str):
        t = threading.Thread(target=self._run_async_extraction, args=(user_text,))
        t.start()

    def _run_async_extraction(self, text: str):
        asyncio.run(self._extraction_logic(text))

    async def _extraction_logic(self, text: str):
        log("MEMORY", f"💾 [EXTRACTION START] Analysiere: '{text[:30]}...'", Fore.MAGENTA)
        try:
            from clients.dashboard_client import debug as _dbg
        except Exception:
            _dbg = None
        
        # 1. Filter: Zu kurz?
        if len(text) < HIPPOCAMPUS_MIN_TEXT_LENGTH:
            log("MEMORY", "   ⚠️ Text zu kurz für Memory.", Fore.LIGHTBLACK_EX)
            return
        
        # 2. Filter: Nur Hallo?
        if text.lower().strip() in ["hallo", "hi", "hey", "moin", "hallo yourai"]:
            log("MEMORY", "   ⚠️ Nur Begrüßung - kein Memory.", Fore.LIGHTBLACK_EX)
            return

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HIPPOCAMPUS_LLM_TIMEOUT)) as session:
            # 1. LLM Extraction
            sys_msg = {"role": "system", "content": PROMPT_MEMORY_IDENTIFICATION}
            user_msg = {"role": "user", "content": text}

            try:
                raw_json = await self._llm_json(HIPPOCAMPUS_EXTRACTION_MODEL, [sys_msg, user_msg], session)
            except Exception as extraction_err:
                log("MEMORY", f"❌ Extraction LLM failed: {extraction_err}", Fore.RED)
                if _dbg:
                    _dbg.error("memory", f"❌ Extraction failed: {extraction_err}")
                return
            log("MEMORY", f"   🤖 [LLM RAW OUTPUT]: {raw_json}", Fore.LIGHTBLACK_EX)
            
            new_facts = []
            try:
                data = json.loads(raw_json)
                
                # --- HELPER: REKURSIVER "STAUBSAUGER" ---
                def extract_strings_recursively(obj):
                    found_strings = []
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if isinstance(v, str) and len(k) > 15 and len(v) > 15:
                                found_strings.append(k)
                                found_strings.append(v)
                            elif str(v).lower() in ["true", "yes"]:
                                found_strings.append(k)
                            else:
                                found_strings.extend(extract_strings_recursively(v))
                    elif isinstance(obj, list):
                        for item in obj:
                            found_strings.extend(extract_strings_recursively(item))
                    elif isinstance(obj, str):
                        if len(obj) > 3: 
                            found_strings.append(obj)
                    return found_strings

                new_facts = extract_strings_recursively(data)
                         
            except Exception as e:
                from exceptions import YourAILLMParseError
                err = YourAILLMParseError(model=HIPPOCAMPUS_EXTRACTION_MODEL, expected="JSON", raw_preview=raw_json, cause=e)
                log_exception("MEMORY", err)
                return

            if not new_facts: 
                log("MEMORY", "   ℹ️ Keine neuen Fakten im Text gefunden.", Fore.LIGHTBLACK_EX)
                return
            
            log("MEMORY", f"💾 [NEUE FAKTEN GEFUNDEN]: {new_facts}", Fore.GREEN)
            if _dbg:
                _dbg.memory_save(new_facts)

            # 2. Deduplizierung
            await self._deduplicate_and_upload(new_facts, session)

    async def _deduplicate_and_upload(self, new_facts: List[str], session: aiohttp.ClientSession):
        headers = {"X-API-Key": MEMORY_API_KEY}
        existing_texts = []
        try:
            async with session.get(f"{MEMORY_API_BASE}/get_memories", headers=headers, params={"user_id": self._user_id, "limit": 1000}) as r:
                if r.status == 200:
                    data = await r.json()
                    existing_texts = [m['text'] for m in data]
        except Exception as e:
            err = YourAIMemoryServerError(url=f"{MEMORY_API_BASE}/get_memories (dedup)", cause=e)
            log_exception("MEMORY", err)

        final_batch = []
        
        # Vektoren laden (nur wenn wir Vergleiche machen müssen)
        existing_vecs = []
        if existing_texts:
            tasks = [self._get_embedding(t, session, silent=True) for t in existing_texts]
            existing_vecs_raw = await asyncio.gather(*tasks)
            _failed = sum(1 for v in existing_vecs_raw if v is None)
            if _failed > 0:
                log("MEMORY", f"⚠️ Dedup-Embedding: {_failed}/{len(existing_texts)} fehlgeschlagen", Fore.YELLOW)
            existing_vecs = [v for v in existing_vecs_raw if v is not None]

        for fact in new_facts:
            is_dupe = False
            
            # 1. String Match
            if fact in existing_texts: 
                log("MEMORY", f"   ♻️ Exaktes Duplikat: {fact}", Fore.LIGHTBLACK_EX)
                continue
            
            # 2. Vektor Cosine
            fact_vec = await self._get_embedding(fact, session)
            if fact_vec is not None and existing_vecs:
                for old_vec in existing_vecs:
                    sim = self._manual_cosine_similarity(fact_vec, old_vec)
                    if sim >= HIPPOCAMPUS_DUP_COSINE:
                        log("MEMORY", f"   ♻️ Vektor-Duplikat ({sim:.2f}): {fact}", Fore.LIGHTBLACK_EX)
                        is_dupe = True; break
            
            if is_dupe: continue

            # 3. Levenshtein
            if RAPIDFUZZ_AVAILABLE and fuzz: 
                for old in existing_texts:
                    ratio = fuzz.ratio(fact.lower(), old.lower())
                    if ratio >= HIPPOCAMPUS_DUP_LEVENSHTEIN:
                        log("MEMORY", f"   ♻️ Text-Duplikat ({ratio}): {fact}", Fore.LIGHTBLACK_EX)
                        is_dupe = True; break
            
            if not is_dupe:
                final_batch.append({"user_id": self._user_id, "text": fact, "timestamp": time.time()})

        # D) Upload
        if final_batch:
            try:
                async with session.post(f"{MEMORY_API_BASE}/add_memories", headers=headers, json=final_batch) as r:
                    if r.status == 200: 
                        log("MEMORY", f"   ✅ [UPLOAD SUCCESS] {len(final_batch)} Fakten gespeichert!", Fore.GREEN)
                    else:
                        err = YourAIMemoryServerError(url=f"{MEMORY_API_BASE}/add_memories", status=r.status)
                        log_exception("MEMORY", err)
            except Exception as e:
                err = YourAIMemoryServerError(url=f"{MEMORY_API_BASE}/add_memories", cause=e)
                log_exception("MEMORY", err)

memory = Hippocampus()