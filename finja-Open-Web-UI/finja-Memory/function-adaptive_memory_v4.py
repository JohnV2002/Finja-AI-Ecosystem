
"""
======================================================================
            Adaptive Memory – External Server Edition
======================================================================

  Project: Adaptive Memory (OpenWebUI Plugin)
  Version: 4.2
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
 Updates 4.2:
 ---------------------------------------------------------------------
  + **Prompt-Feintuning:** Der Prompt zur Extraktion wurde gehärtet. Er
    generalisiert nun von einmaligen Ereignissen zu dauerhaften Fakten
    (z.B. "Ich aß gestern Pizza" -> "User mag Pizza"), was zu qualitativ
    hochwertigeren Erinnerungen führt.

  + **Duales Fallback-System:** Lokales Embedding als Fallback für die
    Relevanz-Prüfung (Phase 1) und die Extraktion (Phase 2) implementiert.
    Das Plugin bleibt damit auch bei einem OpenAI-Ausfall funktionsfähig.

  + **"Local Only"-Modus:** Neue Einstellung `processing_mode` hinzugefügt,
    damit das Plugin auf Wunsch komplett ohne OpenAI betrieben werden kann.

  + **Verbessertes User-Feedback:** Das Plugin gibt dem User jetzt klare und
    freundliche Statusmeldungen im Chat aus (z.B. bei der Analyse, beim
    Speichern oder wenn ein Duplikat gefunden wurde).

  + **Robuste Logik & Refactoring:** Die zentrale `inlet`-Methode wurde 
    grundlegend überarbeitet, um die verschiedenen Modi (OpenAI, Local Only, 
    Fallback) sauber, fehlerresistent und verständlich zu steuern.

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
        llm_model_name: str = Field(default="gpt-4o")
        llm_api_key: str = Field(default="changeme-openai-key")

        # --- Memory Server ---
        memory_api_base: str = Field(
            default="http://87.106.217.52:8000",
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

        # --- NEUE FELDER FÜR FALLBACK ---
        use_local_embedding_fallback: bool = Field(default=True, description="Aktiviert den lokalen Embedding-Fallback bei OpenAI-Fehlern.")
        local_embedding_model: str = Field(default="all-MiniLM-L6-v2", description="Modell für lokale Embeddings.")
        min_similarity_for_upload: float = Field(default=0.95, description="Minimale Ähnlichkeit, um ein Duplikat beim Fallback zu erkennen.")


        # --- System Prompts ---
        # WICHTIG: Für Memory-Identifikation, nicht für Chat
        memory_identification_prompt: str = Field(
            default=(
                "You are an automated JSON data extraction system. Your ONLY function is to identify "
                "user-specific, persistent facts, preferences, goals, relationships, or interests from the "
                "user's messages and output them STRICTLY as a JSON array of operations.\n\n"
                "ABSOLUTE OUTPUT REQUIREMENT:\n"
                "- Your ENTIRE response MUST be ONLY a valid JSON array starting with `[` and ending with `]`.\n"
                "- Each element MUST be: {\"operation\": \"NEW\", \"content\": \"...\", \"tags\": [\"...\"], \"memory_bank\": \"...\"}\n"
                "- EXTRACT ALL DISTINCT FACTS. If a message contains a name AND a preference, create an object for EACH fact.\n"
                "- GENERALIZE FROM SINGLE EVENTS. If a user says 'I ate pizza yesterday', extract the persistent preference 'User likes pizza', not the one-time event.\n"
                "- If NO relevant user-specific memories are found, output ONLY []\n"
                "- DO NOT include ANY text before/after the JSON array. No notes, no markdown.\n\n"
                "ALLOWED TAGS: [\"identity\",\"behavior\",\"preference\",\"goal\",\"relationship\",\"possession\"]\n"
                "MEMORY BANKS: \"General\", \"Personal\", \"Work\"\n\n"
                "EXAMPLE OF CORRECT BEHAVIOR:\n"
                "USER MESSAGE: \"Mein Name ist Peter und ich mag das Spiel Satisfactory.\"\n"
                "YOUR OUTPUT MUST BE:\n"
                "[\n"
                "  {\"operation\": \"NEW\", \"content\": \"User's name is Peter\", \"tags\": [\"identity\"], \"memory_bank\": \"Personal\"},\n"
                "  {\"operation\": \"NEW\", \"content\": \"User likes the game Satisfactory\", \"tags\": [\"preference\", \"behavior\"], \"memory_bank\": \"Personal\"}\n"
                "]\n\n"
                "Now, analyze the following user message(s) and output ONLY the JSON array."
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
         # --- 1. SETUP: Grundlegende Daten vorbereiten ---
        _log("inlet: received batch")

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

        # Lade alle bisherigen Erinnerungen des Users vom Server
        existing = await self._mem_get_existing(user_id)
        # Bereite eine reine Text-Liste der Erinnerungen für die Analyse vor.
        candidates = [(m.get("text") or "") for m in existing if isinstance(m, dict) and (m.get("text") or "").strip()]

        # =================================================================
        # PHASE 1: RELEVANZ-CHECK
        # Prüfen, ob bereits gespeicherte Erinnerungen für die aktuelle Nachricht nützlich sind.
        # =================================================================
        is_context_injected = False # Eine "Flagge", um zu merken, ob wir in dieser Phase schon fertig geworden sind.
        if candidates: # Dieser ganze Block wird nur ausgeführt, wenn es überhaupt Erinnerungen zum Prüfen gibt.
            ranked = []
            
            # --- Pfad 1A: Primärer OpenAI-Pfad für die Relevanz-Analyse ---
            if self.valves.processing_mode == "openai":
                try:
                    _log("relevance: trying OpenAI for ranking...")
                    ranked = await self._rank_relevance(last_user, candidates)
                except Exception as e:
                    # Fehlerbehandlung, wenn die OpenAI-API nicht erreichbar ist.
                    _log(f"relevance: OpenAI failed ({e}), using fallback...")
                    await self._emit_status(__event_emitter__, "⚠️ OpenAI-Relevanzcheck fehlgeschlagen, nutze lokalen Fallback...")
                    if not self.valves.use_local_embedding_fallback:
                        raise e # Wenn der Fallback deaktiviert ist, wird der Fehler trotzdem ausgelöst.
            
            # --- Pfad 1B: Lokaler Pfad (entweder als "local_only"-Modus oder als Fallback) ---
            # Dieser Block wird aktiv, wenn 'ranked' leer ist (also entweder im local_only-Modus oder nach einem OpenAI-Fehler).
            if not ranked and self.valves.use_local_embedding_fallback:
                _log("relevance: using local embeddings for ranking...")
                new_embedding = await self._calculate_embeddings([last_user])
                existing_embeddings = await self._calculate_embeddings(candidates)
                if new_embedding is not None and existing_embeddings is not None:
                    # Berechne die Vektor-Ähnlichkeit und nutze sie als Score.
                    similarities = cosine_similarity(new_embedding, existing_embeddings)[0]
                    ranked = [{"memory": text, "score": float(score)} for text, score in zip(candidates, similarities)]
                    _log(f"relevance: calculated {len(ranked)} scores locally.")

            # --- Auswertung: Egal, woher die "ranked"-Liste kam, wir verarbeiten sie hier. ---
            threshold = self.valves.relevance_threshold
            relevant = [r for r in ranked if r.get("score", 0.0) >= threshold]
            if relevant:
                relevant.sort(key=lambda x: x.get("score", 0.0), reverse=True)
                top = [r["memory"] for r in relevant[:3] if isinstance(r.get("memory"), str)]
                if top:
                    # Wenn wir relevante Erinnerungen gefunden haben, fügen wir sie dem System-Prompt hinzu.
                    context = "MEMORY_CONTEXT:\n" + "\n".join(f"- {t}" for t in top)
                    body["messages"].insert(0, {"role": "system", "content": context})
                    _log("context: injected", {"items": len(top), "first": top[0][:60]})
                    is_context_injected = True # Wen Wir fertig sind!

        # Arbeit ist hier getan und wir überspringen Phase 2.
        if is_context_injected:
            return body

        # =================================================================
        # PHASE 2: NEUE ERINNERUNGEN EXTRAHIEREN
        # Wird nur ausgeführt, wenn in Phase 1 nichts Relevantes gefunden wurde.
        # =================================================================
        
        # --- Pfad 2A: Primärer OpenAI-Pfad für die Extraktion ---
        if self.valves.processing_mode == "openai":
            try:
                _log("extract: trying OpenAI...")
                await self._emit_status(__event_emitter__, "🧠 Analysiere Nachricht auf neue Fakten...")
                new_mems = await self._extract_new_memories(last_user) # Die "intelligente" Extraktion.
                if new_mems:
                    added_count = await self._upload_new_dedup(user_id, new_mems)
                    plural = "Erinnerung" if added_count == 1 else "Erinnerungen"
                    await self._emit_status(__event_emitter__, f"✅ {added_count} neue {plural} gelernt und gespeichert.") 
                else:
                    _log("extract: OpenAI found no new memories to save.")
                    await self._emit_status(__event_emitter__, "ℹ️ Nichts Neues zum Merken gefunden.")
                return body # Wichtig: Nach diesem Pfad sind wir immer fertig, daher hier ein return.
            except Exception as e:
                _log(f"extract: OpenAI failed ({e}), using fallback...")
                await self._emit_status(__event_emitter__, "⚠️ OpenAI nicht erreichbar. Wechsle auf lokale Analyse...")
                if not self.valves.use_local_embedding_fallback:
                    raise e
        
        # --- Pfad 2B: Lokaler Pfad (entweder als "local_only"-Modus oder als Fallback) ---
        _log("extract: using local embeddings for deduplication check...")
        await self._emit_status(__event_emitter__, "⚙️ Führe lokale Analyse durch...")
        if not candidates: # Sonderfall: Dies ist die allererste Erinnerung für diesen User.
            _log("fallback: No existing memories, saving new memory directly.")
            await self._upload_new_dedup(user_id, [{"content": last_user}])
            await self._emit_status(__event_emitter__, "✅ Erster Fakt gelernt und lokal gespeichert.")
        else:
            # Führe einen lokalen Duplikats-Check durch.
            new_embedding = await self._calculate_embeddings([last_user])
            existing_embeddings = await self._calculate_embeddings(candidates)
            if new_embedding is not None and existing_embeddings is not None:
                similarities = cosine_similarity(new_embedding, existing_embeddings)
                max_similarity = np.max(similarities) # Finde die höchste Ähnlichkeit zu einer alten Erinnerung.
                _log(f"fallback: Max similarity to existing memories is {max_similarity:.4f}")

                # Nur speichern, wenn die Ähnlichkeit UNTER dem Duplikats-Schwellenwert liegt.
                if max_similarity < self.valves.min_similarity_for_upload:
                    await self._upload_new_dedup(user_id, [{"content": last_user}])
                    await self._emit_status(__event_emitter__, f"✅ Neuer Fakt gelernt (Ähnlichkeit zu alten Fakten: {max_similarity:.0%}).")
                else:
                    await self._emit_status(__event_emitter__, f"❌ Fakt zu ähnlich, nicht erneut gespeichert (Ähnlichkeit: {max_similarity:.0%}).")
            else:
                _log("fallback: Failed to calculate embeddings, cannot save.")
                await self._emit_status(__event_emitter__, "❌ Lokale Analyse fehlgeschlagen: Embeddings konnten nicht berechnet werden.")

        # Der finale Return, der sicherstellt, dass die Funktion immer ein Dictionary zurückgibt und den Fehler behebt.
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
