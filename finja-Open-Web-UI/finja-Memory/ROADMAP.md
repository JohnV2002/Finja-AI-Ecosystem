# 🧠 Memory & Filter – Roadmap

An overview of the remaining features for the Finja Memory Service and the OpenWebUI Plugin.

---

## 🟡 Priority 1: Security

### SECURE FILE STORAGE (Encryption)

- **Core idea:** Encrypt user data at rest to protect it from unauthorized access (even by the admin).

- **Approaches:** Server-side (master key or user-specific derived key) vs. Client-side (plugin encrypts before sending).

- **Challenge:** Key management without a user password, protection from admin vs. editability.

### NEED HELP with this!

### Private Memory Lock (Encryption - Part of Priority 1)

- **Application:** Applies to the "Secrets" memory bank.

- **Implementation:** An optional passphrase per user_id is used to encrypt and decrypt memories client-side in the plugin (via AES-GCM). The server only stores the encrypted ciphertext.

### I NEED HELP with this!

---

## 🟡 Priority 0.5: Backups & Better User Feedback

### Offline Backup (Docker Integrated)

-   **Storage Location:** `/backups/YYYY-MM-DD/<user_id>.tar.gz` inside the Docker volume.
-   **Retention:** A code constant `BACKUP_RETENTION_DAYS = 14` in `memory-server.py` defines how long backups are kept. (Optionally toggleable)
-   **Endpoints:** `POST /backup_all_now` (Admin) and an extended `POST /backup_now` function.

---

## 🟢 Priority 0.4: Advanced Memory Features

### Memory Chaining (Graph/Cluster)

-   **Logic (Plugin only):** When saving a new memory, thematically similar "neighbors" (cosine ≥ 0.85) are found. The IDs of these neighbors are stored in `meta.links`.

---

## 🔵 Priority 0.3: Structure & Interaction

### Memory Banks (Categories)

-   **(Partially implemented)** The `/get_memories` endpoint still needs to be extended with a `bank` parameter to filter by categories. The basic structure already exists.

### "Search+Ask" Mode

-   **User query:** "Finja, what do you know about XYZ?"
-   **Process:** The plugin recognizes the intent and calls the new endpoint `GET /search_ask?user_id&query=...`. The server returns the top K most relevant memories, which the plugin aggregates into an answer.

### Memory Stats Dashboard (Base)

-   **(Partially implemented)** The `GET /memory_stats` endpoint exists, but needs to be expanded with more detailed statistics like `hits`, `rejects`, `duplicates`, and a breakdown by `bank`.

---

## 🟣 Priority 0.2: Live Updates & On-Demand Summaries

-   **WebSocket Push:** A `/ws` endpoint on the server sends live events (`added`, `rejected`, `duplicate`, `backup_done`) to a potential dashboard.
-   **Memory Story Mode:** When asked "Tell me what you know about me", the plugin calls `GET /story?user_id`, fetches representative memories, and has the LLM summarize them into a story.
-   **Plugin API Improvements:** Introduction of API keys with scopes (read/write) and optional webhooks.

---

## 🟤 Priority 0.1: Long-term Management & Visualization

-   **Memory Expiry:** **(Partially implemented)** The `expires_at` field exists. The server-side logic that automatically deletes expired memories is missing.
-   **Auto-Prune:** Optionally deletes unwelcomed/unimportant memories (low score, no access) after N days.
-   **Memory Visualizer (Long-term vision):** A frontend built on top of the statistics and WebSocket endpoints.
-   **Retrieval:** Via a new endpoint `GET /download_backup?user_id&date=...` (HARD! Must be made difficult to use just like deleting data to prevent misuse - implementation uff)

---

## ✍️ Remaining Mini Specs

### Extended Fields (MemoryItem)
```python
vector: Optional[List[float]] = None # For persistent vector cache
```

### New Endpoints
- `POST /add_voice_memory`
- `GET /search_ask`
- `GET /story`
- `GET /ws` (WebSocket)
- `POST /backup_all_now`
- `GET /download_backup`

### Important Configuration Variables
- `EMBEDDINGS_MODEL=all-MiniLM-L6-v2`
- `MIN_RELEVANCE_ON_UPLOAD=0.45`
- `DUP_COSINE=0.92`
- `DUP_LEV=0.90`
- `MIN_CHARS=8`
- `MIN_TOKENS=2`
- `BACKUP_RETENTION_DAYS=14`
- `DEV_SANDBOX=0|1`