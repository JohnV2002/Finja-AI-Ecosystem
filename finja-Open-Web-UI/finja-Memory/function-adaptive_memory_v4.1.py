
"""
======================================================================
            Adaptive Memory – External Server Edition
======================================================================

  Project: Adaptive Memory (OpenWebUI Plugin)
  Version: 4.1
  Author:  John (J. Apps / Sodakiller1)
  License: Apache License 2.0 (c) 2025 J. Apps
  Original Inspiration & Credits: gramanoid (aka diligent_chooser)
  Original Plugin: https://openwebui.com/f/alexgrama7/adaptive_memory_v2
  Author Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Vollständig überarbeitete Version von Adaptive Memory v3 (gramanoid)
  • Speichert Memories nicht mehr lokal, sondern auf einem externen Server
  • Nutzerbasierte Speicherung: jede User-ID erhält eigene Memory-JSONs (serverseitig)
  • OpenAI-gestützte Validierung und Extraktion nützlicher Fakten
  • Relevanzprüfung von Memories pro User-Eingabe
  • Automatisches Dedupe (lokal und serverseitig)
  • Mehrstufige Sicherheitsprüfungen (funktion- und serverseitig)
  • Kompatibel mit externem Browser + OpenWebUI User-ID

----------------------------------------------------------------------
 Updates:
 ---------------------------------------------------------------------

----------------------------------------------------------------------
 Roadmap:
 ---------------------------------------------------------------------
  • Feintuning der Memory-Auswahl und Relevanzbewertung
  • Erweiterte Validierung vor dem Abspeichern (OpenAI-Check)
  • Detaillierteres Logging (inkl. Memory-Save-Animationen etc.)
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
from typing import Any, Dict, List, Optional
import aiohttp
from pydantic import BaseModel, Field
from datetime import datetime
import re

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

    class Valves(BaseModel):
        # --- LLM / OpenAI ---
        llm_api_endpoint_url: str = Field(default="https://api.openai.com/v1/chat/completions")
        llm_model_name: str = Field(default="gpt-4o")
        llm_api_key: str = Field(default="changeme-openai-key")

        # --- Memory Server ---
        memory_api_base: str = Field(
            default="http://87.106.217.52:8000",
            description="Base URL deines Memory-Servers (ohne Pfad, http!)"
        )
        memory_api_key: str = Field(default="changeme-supersecretkey")

        # --- Thresholds/Behavior ---
        relevance_threshold: float = Field(default=0.70, description="Relevanz-Schwelle (0..1)")
        max_memories_fetch: int = Field(default=100, description="Wieviele Memories max. holen")

        # --- System Prompts ---
        # WICHTIG: Für Memory-Identifikation, nicht für Chat
        memory_identification_prompt: str = Field(
            default=(
                "You are an automated JSON data extraction system. Your ONLY function is to identify "
                "user-specific, persistent facts, preferences, goals, relationships, or interests from the "
                "user's messages and output them STRICTLY as a JSON array of operations.\n\n"
                "ABSOLUTE OUTPUT REQUIREMENT:\n"
                "- ENTIRE response MUST be ONLY a valid JSON array starting with `[` and ending with `]`.\n"
                "- Each element MUST be: {\"operation\": \"NEW\", \"content\": \"...\", \"tags\": [\"...\"], \"memory_bank\": \"...\"}\n"
                "- If NO relevant user-specific memories are found, output ONLY []\n"
                "- A single memory MUST still be within an array.\n"
                "- DO NOT include ANY text before/after the JSON array. No notes, no markdown.\n\n"
                "ALLOWED TAGS: [\"identity\",\"behavior\",\"preference\",\"goal\",\"relationship\",\"possession\"]\n"
                "MEMORY BANKS: \"General\", \"Personal\", \"Work\"\n"
                "EXAMPLES omitted for brevity. Analyze the following user message(s) and output ONLY the JSON array."
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

    def __init__(self):
        # Initialize valves with default values
        self.valves = self.Valves()
        self._session: Optional[aiohttp.ClientSession] = None

        # simple regexes to block saving question-only/ephemeral statements
        self._block_extract_patterns = [
            r"^\s*(was\s+ist\s+mein\s+name\??)\s*$",
            r"^\s*(wie\s+heiße\s+ich\??)\s*$",
            r"^\s*what'?s\s+my\s+name\??\s*$",
            r"^\s*h+i+(\s+there)?\s*!?\s*$",
            r"^\s*(wie\s+geht'?s|how\s+are\s+you)\b.*$",
        ]

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
            if not content:
                continue
            # sanity filter against greetings + meta statements
            lc = content.lower()
            if lc in {"hi", "hii", "hiii", "hallo", "hey", "wie gehts", "wie geht's"}:
                continue
            if re.search(r"\b(asking for (their|his|her) name|frägt?|fragt? nach seinem namen)\b", lc):
                continue
            out.append(m)

        _log("extract: parsed", {"count": len(out)})
        return out

    async def _upload_new_dedup(self, user_id: str, candidates: List[dict]) -> int:
        """Upload only new memories (dedupe vs server). Returns count uploaded."""
        if not candidates:
            _log("mem: uploaded_new", {"count": 0})
            return 0
        existing = await self._mem_get_existing(user_id)
        existing_texts = {(m.get("text") or "").strip().lower() for m in existing if isinstance(m, dict)}
        batch = []
        skipped_dupes = 0
        for m in candidates:
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if content.strip().lower() in existing_texts:
                skipped_dupes += 1
                continue
            batch.append({
                "id": "",
                "user_id": user_id,
                "text": content,
                "timestamp": 0
            })
        if not batch:
            _log("mem: uploaded_new_detail", {"uploaded": 0, "skipped_dupes": skipped_dupes})
            _log("mem: uploaded_new", {"count": 0})
            return 0
        ok = await self._mem_add_batch(batch)
        _log("mem: uploaded_new_detail", {"uploaded": len(batch) if ok else 0, "skipped_dupes": skipped_dupes})
        _log("mem: uploaded_new", {"count": len(batch) if ok else 0})
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
        _log("inlet: received batch")

        # 1) user_id # !snyk FALSE Positiv! 

        # snyk:ignore:python/UseOfHardcodedCredentials
        # Reason: User ID is dynamically retrieved from Open-Web-UI at runtime
        #         to identify the correct memory context. No static credentials
        #         are stored or loaded from hardcoded strings.
        user_id = self._get_user_id(__user__)

        # last user message
        last_user = ""
        for m in reversed(body.get("messages", [])):
            if m.get("role") == "user" and m.get("content"):
                last_user = m["content"]
                break

        if not last_user:
            return body

        # 2) fetch memories & relevance check
        existing = await self._mem_get_existing(user_id)
        candidates = [(m.get("text") or "") for m in existing if isinstance(m, dict) and (m.get("text") or "").strip()]

        if candidates:
            ranked = await self._rank_relevance(last_user, candidates)
            threshold = self.valves.relevance_threshold
            relevant = [r for r in ranked if r.get("score", 0.0) >= threshold]

            if relevant:
                relevant.sort(key=lambda x: x.get("score", 0.0), reverse=True)
                top = [r["memory"] for r in relevant[:3] if isinstance(r.get("memory"), str)]
                if top:
                    # INJIZIERE NUR KONTEXT, KEINE Antwort generieren/bypassen
                    context = "MEMORY_CONTEXT:\n" + "\n".join(f"- {t}" for t in top)
                    body["messages"].insert(0, {  # ganz vorne als Systemhinweis
                        "role": "system",
                        "content": context
                    })
                    _log("context: injected", {"items": len(top), "first": top[0][:60]})
                    return body  # Modell antwortet selbst

        # 3) Keine relevanten Memories -> neue extrahieren & hochladen
        new_mems = await self._extract_new_memories(last_user)
        await self._upload_new_dedup(user_id, new_mems)

        # Wichtig: KEIN Bypass, Modell antwortet normal
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
