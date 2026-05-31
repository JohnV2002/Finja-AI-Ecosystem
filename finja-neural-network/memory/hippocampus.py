"""
YourAI Memory: Hippocampus
=========================
Semantic long-term memory: stores and retrieves user-specific facts via an
external memory server, OpenRouter embeddings, and LLM re-ranking.

Main Responsibilities:
- Retrieve relevant memories for a query (vector pre-filter + LLM re-ranking).
- Extract persistent facts from user messages and store new, non-duplicate ones.
- Deduplicate facts via exact, cosine-similarity, and fuzzy-text matching.
- Expose live memory statistics for the dashboard/UI.

Side Effects:
- Performs HTTP calls to the memory server (read/write) and OpenRouter.
- Spawns a background daemon thread for fact extraction.
- Logs to the YourAI logging/dashboard subsystem.
"""

import json
import time
import os
import threading
import asyncio
import aiohttp
import requests
import numpy as np
import sys
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import (
    YourAIError,
    YourAIMemoryServerError,
    YourAIEmbedError,
    YourAILLMError,
    YourAILLMParseError,
    YourAIUnexpectedError,
)

from config import (
    MEMORY_API_BASE,
    MEMORY_API_KEY,
    HIPPOCAMPUS_EMBEDDING_OPENROUTER,
    HIPPOCAMPUS_ENABLE_PREFILTERING,
    HIPPOCAMPUS_RELEVANCE_THRESHOLD,
    HIPPOCAMPUS_PREFILTER_CAP,
    HIPPOCAMPUS_MAX_FETCH,
    HIPPOCAMPUS_DUP_COSINE,
    HIPPOCAMPUS_DUP_LEVENSHTEIN,
    HIPPOCAMPUS_STATS_TIMEOUT,
    HIPPOCAMPUS_EMBED_MAX_LENGTH,
    HIPPOCAMPUS_MIN_TEXT_LENGTH,
    create_openrouter_client,
    call_openrouter
)
import config
from memory.debug_client import get_dashboard_debug

# --- INITIALIZE RAPIDFUZZ ---
fuzz = None
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    log("MEMORY", "⚠️ RapidFuzz not found. (pip install rapidfuzz)", Fore.YELLOW)


# ==========================================
# PROMPTS
# ==========================================
# NOTE: Prompt bodies are functional model input (multilingual few-shot
# examples on purpose) and are intentionally not translated.

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


def _extract_strings_recursively(obj) -> List[str]:
    """
    Recursively collect meaningful strings from arbitrary parsed JSON.

    Walks dicts/lists and harvests fact-like strings. For dict items it keeps
    long key/value text pairs, treats truthy boolean-like values as facts
    (keyed by their name), and recurses into everything else.

    Args:
        obj: A parsed JSON value (dict, list, str, or scalar).

    Returns:
        List[str]: A flat list of extracted strings.
    """
    found_strings: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and len(k) > 15 and len(v) > 15:
                found_strings.append(k)
                found_strings.append(v)
            elif str(v).lower() in ["true", "yes"]:
                found_strings.append(k)
            else:
                found_strings.extend(_extract_strings_recursively(v))
    elif isinstance(obj, list):
        for item in obj:
            found_strings.extend(_extract_strings_recursively(item))
    elif isinstance(obj, str):
        if len(obj) > 3:
            found_strings.append(obj)
    return found_strings


# ==========================================
# 🧠 THE HIPPOCAMPUS CLASS
# ==========================================

class Hippocampus:
    """Semantic long-term memory backed by an external memory server."""

    def __init__(self):
        """Log the online/offline state depending on whether the API key is set."""
        if not MEMORY_API_KEY:
            log("MEMORY", "⚠️ MEMORY_API_KEY not set in .env! Hippocampus cannot store memories.", Fore.RED)
        else:
            log("MEMORY", "🧠 Hippocampus: Online (multi-user)", Fore.GREEN)

    # --- MANUAL MATH HELPER ---
    def _manual_cosine_similarity(self, v1, v2):
        """
        Compute cosine similarity between two vectors without external deps.

        Args:
            v1: First vector (numpy array) or None.
            v2: Second vector (numpy array) or None.

        Returns:
            float: Cosine similarity, or 0.0 for None/empty/mismatched inputs.
        """
        if v1 is None or v2 is None:
            return 0.0
        v1 = v1.flatten()
        v2 = v2.flatten()
        if v1.shape != v2.shape:
            return 0.0  # Dimension mismatch (e.g. old 4096-dim vs new 1024-dim vectors)
        dot = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    # --- STATS FUNCTION FOR THE UI ---
    def get_stats(self, user_id: str = "admin"):
        """
        Fetch live statistics from the memory server.

        Args:
            user_id (str): The user whose statistics should be fetched.

        Returns:
            Optional[dict]: The server stats payload, or None on error.
        """
        try:
            url = f"{MEMORY_API_BASE}/memory_stats"
            resp = requests.get(
                url,
                params={"user_id": user_id},
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

    # --- EMBEDDING (OpenRouter only) ---
    _openrouter_client = None

    def _get_or_create_openrouter_client(self):
        """
        Lazily create and cache the shared OpenRouter client.

        Returns:
            The cached OpenRouter client instance (or None if creation failed).
        """
        if Hippocampus._openrouter_client is None:
            Hippocampus._openrouter_client = create_openrouter_client()
        return Hippocampus._openrouter_client

    async def _get_embedding(self, text: str, silent: bool = False) -> Optional[np.ndarray]:
        """
        Compute an embedding vector for a text via OpenRouter.

        Args:
            text (str): The text to embed.
            silent (bool): When True, suppress per-call error logging (used for
                batch embedding where a summary is logged instead).

        Returns:
            Optional[np.ndarray]: The embedding vector, or None on failure.
        """
        if not text:
            return None
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
            # Embedding failures are non-fatal: callers fall back to a batch
            # error summary and vector/LLM fallbacks, so we swallow and return None.
            if not silent:
                err = YourAIEmbedError(model=HIPPOCAMPUS_EMBEDDING_OPENROUTER, cause=e)
                log_exception("MEMORY", err)
            return None

    async def _llm_json(self, messages: List[dict]) -> str:
        """
        Call OpenRouter for a JSON-only completion, trying a fallback model.

        Args:
            messages (List[dict]): Chat messages; index 0 is the system prompt,
                index 1 (if present) the user message.

        Returns:
            str: The cleaned model response (code fences stripped).

        Raises:
            YourAILLMError: When every OpenRouter model attempt fails.
        """
        _dbg = get_dashboard_debug("MEMORY", module="hippocampus_dashboard_debug")

        system_prompt = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        user_msg = messages[1]["content"] if len(messages) > 1 else ""

        or_primary = getattr(config, "OPENROUTER_MODEL_MEMORY", config.OPENROUTER_MODEL_COHERENCE)
        or_models = [or_primary, "openrouter/auto"]

        last_error = None
        for or_model in or_models:
            try:
                log("MEMORY", f"   ☁️ OpenRouter LLM {or_model}...", Fore.LIGHTBLACK_EX)
                if _dbg:
                    _dbg.llm_call("memory", f"☁️ {or_model}", user_msg[:300])

                content, _, _ = await asyncio.to_thread(
                    call_openrouter,
                    system_prompt=system_prompt,
                    user_message=user_msg,
                    model=or_model,
                    temperature=0.0
                )

                content = content.replace("```json", "").replace("```", "").strip()
                return content
            except Exception as e:
                last_error = e
                log("MEMORY", f"⚠️ OpenRouter [{or_model}] failed: {e}", Fore.YELLOW)
                if _dbg:
                    _dbg.error("memory", f"☁️ {or_model} failed: {e}")

        err = YourAILLMError(f"All OpenRouter models failed: {last_error}", model=or_primary, module="hippocampus")
        log_exception("MEMORY", err)
        raise err

    # ==========================================
    # 1. RETRIEVAL LOGIC ("Inlet")
    # ==========================================

    def get_relevant_memories(self, query_text: str, user_id: str = "admin"):
        """
        Synchronous entry point for memory retrieval (runs the async inlet).

        Args:
            query_text (str): The current user message.
            user_id (str): The user whose memories to search.

        Returns:
            List[str]: A list of relevant memory strings.
        """
        return asyncio.run(self._inlet_logic(query_text, user_id))

    async def _fetch_candidates(self, session: aiohttp.ClientSession, user_id: str) -> List[str]:
        """
        Fetch all stored memory texts for a user from the memory server.

        Args:
            session (aiohttp.ClientSession): An open client session.
            user_id (str): The user whose memories should be fetched.

        Returns:
            List[str]: Memory strings (empty on any server/transport error).
        """
        headers = {"X-API-Key": MEMORY_API_KEY}
        params = {"user_id": user_id, "limit": HIPPOCAMPUS_MAX_FETCH}
        url = f"{MEMORY_API_BASE}/get_memories"
        try:
            async with session.get(url, headers=headers, params=params) as r:
                if r.status != 200:
                    err = YourAIMemoryServerError(url=url, status=r.status)
                    log_exception("MEMORY", err)
                    return []
                data = await r.json()
                candidates = [m.get("text", "") for m in data if m.get("text")]
                log("MEMORY", f"   📚 Server returned {len(candidates)} memories.", Fore.WHITE)
                return candidates
        except Exception as e:
            err = YourAIMemoryServerError(url=url, cause=e)
            log_exception("MEMORY", err)
            return []

    async def _prefilter_candidates(self, query_text: str, all_candidates: List[str]) -> List[str]:
        """
        Rank candidates by cosine similarity to the query and keep the top-N.

        Args:
            query_text (str): The current user message.
            all_candidates (List[str]): All candidate memory strings.

        Returns:
            List[str]: The pre-filtered candidates (or the full list if
            pre-filtering is disabled or the query embedding failed).
        """
        if not HIPPOCAMPUS_ENABLE_PREFILTERING:
            return all_candidates

        log("MEMORY", "   ⚡ Starting vector filtering (pre-filter)...", Fore.LIGHTBLACK_EX)
        query_vec = await self._get_embedding(query_text)
        if query_vec is None:
            log("MEMORY", "   ⚠️ Query embedding failed. Skipping filter.", Fore.YELLOW)
            return all_candidates

        tasks = [self._get_embedding(t, silent=True) for t in all_candidates]
        cand_vecs = await asyncio.gather(*tasks)

        # Batch error summary (instead of 20+ individual logs)
        failed = sum(1 for v in cand_vecs if v is None)
        if failed > 0:
            log("MEMORY", f"⚠️ Embedding: {failed}/{len(cand_vecs)} failed (timeout/blocked?)", Fore.YELLOW)

        scored = []
        for i, vec in enumerate(cand_vecs):
            if vec is not None:
                sim = self._manual_cosine_similarity(query_vec, vec)
                scored.append((sim, all_candidates[i]))

        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            log("MEMORY", f"      🔹 Best vector match: {scored[0][0]:.2f} -> '{scored[0][1]}'", Fore.LIGHTBLACK_EX)

        return [text for _, text in scored[:HIPPOCAMPUS_PREFILTER_CAP]]

    def _parse_reranked_json(self, raw_json: str) -> List[str]:
        """
        Parse the LLM re-ranking JSON and return memories above the threshold.

        Args:
            raw_json (str): Raw JSON returned by the re-ranking LLM call.

        Returns:
            List[str]: Memory texts whose score meets the relevance threshold.
        """
        final_memories: List[str] = []
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as e:
            or_model = getattr(config, "OPENROUTER_MODEL_MEMORY", config.OPENROUTER_MODEL_COHERENCE)
            err = YourAILLMParseError(model=or_model, expected="JSON array", raw_preview=raw_json, cause=e)
            log_exception("MEMORY", err)
            return final_memories

        if isinstance(parsed, dict):
            parsed = [parsed]

        for item in parsed:
            if not isinstance(item, dict):
                continue
            score = float(item.get("score", 0))
            text = item.get("memory", "")
            if score >= HIPPOCAMPUS_RELEVANCE_THRESHOLD:
                final_memories.append(text)
                log("MEMORY", f"   ✅ [HIT] Score {score:.2f}: {text}", Fore.GREEN)
        return final_memories

    async def _rerank_memories(self, query_text: str, filtered_candidates: List[str]) -> Tuple[List[str], Optional[Exception]]:
        """
        Re-rank candidates with the LLM, falling back to top vector matches.

        Args:
            query_text (str): The current user message.
            filtered_candidates (List[str]): Pre-filtered candidate strings.

        Returns:
            Tuple[List[str], Optional[Exception]]: (selected_memories, llm_error).
            llm_error is the caught exception when re-ranking failed (and
            selected_memories then holds the vector fallback), otherwise None.
        """
        sys_msg = {"role": "system", "content": PROMPT_MEMORY_RELEVANCE}
        user_payload = json.dumps({"current_message": query_text, "candidates": filtered_candidates}, ensure_ascii=False)
        user_msg = {"role": "user", "content": user_payload}

        # LLM re-ranking can time out / error -> vector fallback below.
        raw_json = None
        llm_error = None
        try:
            raw_json = await self._llm_json([sys_msg, user_msg])
        except Exception as e:
            llm_error = e
            log("MEMORY", f"⚠️ LLM re-ranking failed: {e} → vector fallback", Fore.YELLOW)

        final_memories = self._parse_reranked_json(raw_json) if raw_json else []

        # Fallback: if LLM re-ranking failed or returned nothing, use the best
        # vector matches directly.
        if not final_memories and filtered_candidates:
            log("MEMORY", "   ⚠️ LLM re-ranking empty/failed → using top vector matches as fallback", Fore.YELLOW)
            final_memories = filtered_candidates[:5]

        return final_memories, llm_error

    async def _inlet_logic(self, query_text: str, user_id: str = "admin"):
        """
        Retrieve the most relevant memories for a query (async core).

        Pipeline: fetch all candidates → vector pre-filter → LLM re-ranking
        with a vector fallback. On LLM failure the fallback memories are stored
        on ``_last_fallback_memories`` and the error is re-raised so the
        pipeline can surface it.

        Args:
            query_text (str): The current user message.
            user_id (str): The user whose memories to search.

        Returns:
            List[str]: A list of relevant memory strings.

        Raises:
            Exception: The original LLM error when re-ranking failed (after a
                vector fallback has been computed and stored).
        """
        log("MEMORY", f"🔍 [RETRIEVAL START] user={user_id} | '{query_text}'", Fore.CYAN)
        _dbg = get_dashboard_debug("MEMORY", module="hippocampus_dashboard_debug")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            all_candidates = await self._fetch_candidates(session, user_id)
            if not all_candidates:
                return []

            filtered_candidates = await self._prefilter_candidates(query_text, all_candidates)
            final_memories, llm_error = await self._rerank_memories(query_text, filtered_candidates)

            # Dashboard: log memory results
            if _dbg:
                used_model = getattr(config, "OPENROUTER_MODEL_MEMORY", config.OPENROUTER_MODEL_COHERENCE)
                _dbg.memory_search(query_text, final_memories, model=used_model)

            # Propagate the error upward (for dashboard + prompt error_context)
            # but still expose the vector-fallback memories via an attribute first.
            if llm_error:
                self._last_fallback_memories = final_memories
                raise llm_error

            return final_memories

    # ==========================================
    # 2. EXTRACTION LOGIC ("Outlet")
    # ==========================================

    def extract_and_save(self, user_text: str, user_id: str = "admin"):
        """
        Fire-and-forget fact extraction on a background daemon thread.

        Args:
            user_text (str): The user message to mine for facts.
            user_id (str): The user the facts belong to.
        """
        t = threading.Thread(target=self._run_async_extraction, args=(user_text, user_id), daemon=True)
        t.start()

    def _run_async_extraction(self, text: str, user_id: str):
        """
        Thread target that runs the async extraction logic to completion.

        Args:
            text (str): The user message to mine for facts.
            user_id (str): The user the facts belong to.
        """
        asyncio.run(self._extraction_logic(text, user_id))

    def _parse_facts(self, raw_json: str) -> List[str]:
        """
        Parse the extraction LLM output into a flat list of fact strings.

        Args:
            raw_json (str): Raw JSON returned by the extraction LLM call.

        Returns:
            List[str]: Extracted fact strings (empty on parse failure).
        """
        try:
            data = json.loads(raw_json)
        except Exception as e:
            or_model = getattr(config, "OPENROUTER_MODEL_MEMORY", config.OPENROUTER_MODEL_COHERENCE)
            err = YourAILLMParseError(model=or_model, expected="JSON", raw_preview=raw_json, cause=e)
            log_exception("MEMORY", err)
            return []
        return _extract_strings_recursively(data)

    async def _extraction_logic(self, text: str, user_id: str = "admin"):
        """
        Extract persistent user facts from a message and store new ones (async core).

        Skips messages that are too short or plain greetings, asks the LLM to
        identify facts, then deduplicates and uploads anything new.

        Args:
            text (str): The user message to mine for facts.
            user_id (str): The user the facts belong to.
        """
        log("MEMORY", f"💾 [EXTRACTION START] user={user_id} | '{text[:30]}...'", Fore.MAGENTA)
        _dbg = get_dashboard_debug("MEMORY", module="hippocampus_dashboard_debug")

        # 1. Filter: too short?
        if len(text) < HIPPOCAMPUS_MIN_TEXT_LENGTH:
            log("MEMORY", "   ⚠️ Text too short for memory.", Fore.LIGHTBLACK_EX)
            return

        # 2. Filter: greeting only? (German greeting tokens on purpose: they match German user input)
        if text.lower().strip() in ["hallo", "hi", "hey", "moin", "hallo yourai"]:
            log("MEMORY", "   ⚠️ Greeting only - no memory.", Fore.LIGHTBLACK_EX)
            return

        # 3. LLM extraction
        sys_msg = {"role": "system", "content": PROMPT_MEMORY_IDENTIFICATION}
        user_msg = {"role": "user", "content": text}

        try:
            raw_json = await self._llm_json([sys_msg, user_msg])
        except Exception as extraction_err:
            err = extraction_err if isinstance(extraction_err, YourAIError) else YourAIUnexpectedError(
                cause=extraction_err, module="hippocampus_extraction"
            )
            log_exception("MEMORY", err)
            if _dbg:
                _dbg.error("memory", f"❌ Extraction failed: {extraction_err}")
            return
        log("MEMORY", f"   🤖 [LLM RAW OUTPUT]: {raw_json}", Fore.LIGHTBLACK_EX)

        new_facts = self._parse_facts(raw_json)
        if not new_facts:
            log("MEMORY", "   ℹ️ No new facts found in text.", Fore.LIGHTBLACK_EX)
            return

        log("MEMORY", f"💾 [NEW FACTS FOUND]: {new_facts}", Fore.GREEN)
        if _dbg:
            _dbg.memory_save(new_facts)

        # 4. Deduplication + upload
        await self._deduplicate_and_upload(new_facts, user_id)

    async def _fetch_existing_memories(self, session: aiohttp.ClientSession, user_id: str) -> List[str]:
        """
        Fetch existing memory texts used for deduplication.

        Args:
            session (aiohttp.ClientSession): An open client session.
            user_id (str): The user whose memories to fetch.

        Returns:
            List[str]: Existing memory strings (empty on error).
        """
        headers = {"X-API-Key": MEMORY_API_KEY}
        url = f"{MEMORY_API_BASE}/get_memories"
        try:
            async with session.get(url, headers=headers, params={"user_id": user_id, "limit": 1000}) as r:
                if r.status == 200:
                    data = await r.json()
                    return [m['text'] for m in data]
        except Exception as e:
            err = YourAIMemoryServerError(url=f"{url} (dedup)", cause=e)
            log_exception("MEMORY", err)
        return []

    async def _embed_existing(self, existing_texts: List[str]) -> List[np.ndarray]:
        """
        Embed existing memory texts for vector-based deduplication.

        Args:
            existing_texts (List[str]): The currently stored memory strings.

        Returns:
            List[np.ndarray]: Embedding vectors (failed embeddings are dropped).
        """
        if not existing_texts:
            return []
        tasks = [self._get_embedding(t, silent=True) for t in existing_texts]
        raw_vecs = await asyncio.gather(*tasks)
        failed = sum(1 for v in raw_vecs if v is None)
        if failed > 0:
            log("MEMORY", f"⚠️ Dedup embedding: {failed}/{len(existing_texts)} failed", Fore.YELLOW)
        return [v for v in raw_vecs if v is not None]

    def _is_semantic_duplicate(self, fact: str, fact_vec: Optional[np.ndarray],
                               existing_texts: List[str], existing_vecs: List[np.ndarray]) -> bool:
        """
        Check whether a fact duplicates an existing memory (vector + fuzzy).

        Exact-match dedup is handled by the caller; this covers cosine-similarity
        and (when available) RapidFuzz Levenshtein-ratio matching.

        Args:
            fact (str): The candidate fact string.
            fact_vec (Optional[np.ndarray]): The fact's embedding vector.
            existing_texts (List[str]): Currently stored memory strings.
            existing_vecs (List[np.ndarray]): Embeddings of the existing memories.

        Returns:
            bool: True if the fact should be treated as a duplicate.
        """
        if fact_vec is not None and existing_vecs:
            for old_vec in existing_vecs:
                sim = self._manual_cosine_similarity(fact_vec, old_vec)
                if sim >= HIPPOCAMPUS_DUP_COSINE:
                    log("MEMORY", f"   ♻️ Vector duplicate ({sim:.2f}): {fact}", Fore.LIGHTBLACK_EX)
                    return True

        if RAPIDFUZZ_AVAILABLE and fuzz:
            for old in existing_texts:
                ratio = fuzz.ratio(fact.lower(), old.lower())
                if ratio >= HIPPOCAMPUS_DUP_LEVENSHTEIN:
                    log("MEMORY", f"   ♻️ Text duplicate ({ratio}): {fact}", Fore.LIGHTBLACK_EX)
                    return True

        return False

    async def _upload_facts(self, session: aiohttp.ClientSession, final_batch: List[dict]):
        """
        Upload a batch of new facts to the memory server.

        Args:
            session (aiohttp.ClientSession): An open client session.
            final_batch (List[dict]): Memory payload dicts to store.
        """
        headers = {"X-API-Key": MEMORY_API_KEY}
        url = f"{MEMORY_API_BASE}/add_memories"
        try:
            async with session.post(url, headers=headers, json=final_batch) as r:
                if r.status == 200:
                    log("MEMORY", f"   ✅ [UPLOAD SUCCESS] {len(final_batch)} facts stored!", Fore.GREEN)
                else:
                    err = YourAIMemoryServerError(url=url, status=r.status)
                    log_exception("MEMORY", err)
        except Exception as e:
            err = YourAIMemoryServerError(url=url, cause=e)
            log_exception("MEMORY", err)

    async def _deduplicate_and_upload(self, new_facts: List[str], user_id: str = "admin"):
        """
        Deduplicate new facts against stored memories and upload the rest.

        Uses three dedup layers: exact string match, cosine similarity of
        embeddings, and RapidFuzz text ratio (when available).

        Args:
            new_facts (List[str]): Candidate fact strings to store.
            user_id (str): The user the facts belong to.
        """
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            existing_texts = await self._fetch_existing_memories(session, user_id)
            existing_vecs = await self._embed_existing(existing_texts)

            final_batch = []
            for fact in new_facts:
                if fact in existing_texts:
                    log("MEMORY", f"   ♻️ Exact duplicate: {fact}", Fore.LIGHTBLACK_EX)
                    continue

                fact_vec = await self._get_embedding(fact)
                if self._is_semantic_duplicate(fact, fact_vec, existing_texts, existing_vecs):
                    continue

                final_batch.append({"user_id": user_id, "text": fact, "timestamp": time.time()})

            if final_batch:
                await self._upload_facts(session, final_batch)


memory = Hippocampus()
