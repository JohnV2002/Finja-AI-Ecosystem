# 📚 Finja Cloud Memory v4.4.2

A lightweight, lightning-fast external **Memory Service** acting as long-term memory for AI projects like Finja. This system is designed for seamless integration with **OpenWebUI** via the `adaptive_memory_v4` Plugin.

---

## 🚨 Important Note: External Server Required!

This system consists of two parts: the **Server** (this repository) and the **Plugin**. The plugin will **NOT** work without the memory server described here.

> Please follow the setup guide first to start the server via Docker before installing the plugin in OpenWebUI.

---

### 🛡️ Critical Security Update

⚠️ **Action required:** Older versions of the Docker container contained a vulnerability in the `starlette` library.

To patch this vulnerability, **you must update `requirements.txt`** and rebuild the container!

**Step 1: Update `requirements.txt`**
Download the latest version of the file or run `git pull` to ensure that `starlette>=1.0.0` is included.

**Step 2: Rebuild Container**
Execute the following command to apply the changes:
```bash
docker-compose up -d --build
```
---

## 🆕 Updates & Changelog (v4.4.2 Unified)

This update unifies the Server and the Plugin under version 4.4.2 and brings massive improvements across the board.

* **Massive SonarQube Refactoring:** Greatly reduced cognitive complexity across the plugin. Monolithic functions have been broken down into single-purpose helper methods for enhanced maintainability.
* **Comprehensive Test Suite Added:** Introduced a full `pytest` test suite (`test_memory_server.py` and `test_adaptive_memory.py`) to verify both FastAPI endpoints and internal OpenWebUI Plugin logic. Ready for GitHub Actions CI!
* **True TTS Network Caching:** Fully integrated robust `/upload_tts_cache` and `/get_tts_audio` endpoints, replacing previous placeholder logic. The server now natively accepts generated audio files (e.g., `.wav`) from OpenWebUI and streams them back instantaneously to clients, functioning as a real caching layer to save precious generation time.
* **Security Hardening (Path Traversal):** Implemented critical security improvements in the `/delete_user_memories` and `/add_voice_memory` endpoints. Additional checks (Empty-String & Path Canonicalization) now prevent potential Path-Traversal attacks.
* **Code Quality & Modernization:** Migrated FastAPI endpoints to the new `Annotated` syntax to resolve IDE warnings. Properly documented all HTTP Exceptions in the endpoint schemas. Resolved false-positive warnings for Hardcoded Credentials.
* **Dependency Security Fix:** Updated `starlette` and other dependencies in `requirements.txt` to close known vulnerabilities.

---

## ✨ Features

### Server (`memory-server.py`)
-   **Intelligent RAM Cache:** Keeps active user data in memory for lightning-fast reads and automatically frees memory after a period of inactivity.
-   **Persistent Storage:** Saves all memories as portable JSON files per user inside a Docker volume.
-   **Voice-Memory Scaffold:** Provides API endpoints for accepting voice files (`/add_voice_memory`) and caching voice output (`/get_or_create_speech`), prepared for STT/TTS models.
-   **Data Control:** Includes an API endpoint (`/delete_user_memories`) allowing the plugin to securely and completely delete all of a user's data upon request.
-   **Security:** Access is secured via an `X-API-Key` defined in a `.env` file.
-   **Backup Endpoints:** Includes `/backup_all_now` (Admin) to save all data and `/backup_now` (Placeholder for User backups).

### Plugin (`adaptive_memory_v4.py`)
-   **Flexible Provider Selection:**
    -   **Extraction:** Choose between OpenAI (`openai`) and a local LLM (`local`, e.g., Ollama).
    -   **Relevance:** Choose between OpenAI (`openai`), local LLM (`local`), or purely local embeddings (`embedding`).
    -   **Local Embeddings:** Choose between the `sentence-transformers` library (`sentence_transformer`) or the Ollama Embeddings API (`ollama`).
-   **Intelligent Extraction:** Uses the configured LLM to extract permanent facts from conversations while generalizing from one-time events.
-   **Performance & Cost Optimization:**
    -   A **"Topic Cache"** avoids unnecessary API requests as long as the conversation topic remains the same (uses local embeddings).
    -   A **Local Pre-Filtering** (uses local embeddings) drastically reduces the number of memories sent to the LLM for relevance checks.
-   **Robust Deduplication:** Employs multi-stage validation (Cosine Similarity via OpenAI or local embeddings & Levenshtein distance) to block duplicate memories.
-   **Fallback System:** Uses local embeddings as a fallback for relevance/deduplication if the selected LLM provider fails.
-   **User Experience:**
    -   A **Server Connection Check** provides a clear error message on startup if the server is unreachable.
    -   **Clear User Feedback** in chat informs about all plugin actions.
    -   A **Two-Step Confirmation** via chat command allows users to control the deletion of their own data.
-   **Vision Update:** The plugin intercepts the output of Vision Models and saves it into memory. It features "inlet" and "outlet" modes to parse AI payloads natively.
-   **Filter Expansion:** A Regex filter natively blocks the storage of image generation prompts (e.g. "create an image...").

---

## 🚀 Setup with Docker Compose (Recommended)

This is the easiest and most secure method to start the server.

### 1. Create Configuration File
Create a `.env` file in the root directory. This is where your secret API keys will be stored.

```ini
# .env
MEMORY_API_KEY="your-super-secure-key-12345"
# OPENAI_API_KEY="sk-your-openai-key" # Optional, only if OpenAI is used as a provider
```
> ⚠️ **Important:** Be sure to add the `.env` file to your `.gitignore` so your API keys never end up on GitHub!

### 2. Start Server
1.  **Correct Permissions (One-time):** Run `sudo chown -R $(id -u):$(id -g) .` in the project folder to avoid permission issues with Docker.
2.  **Start Container:** Run the following command in the terminal:
    ```bash
    docker-compose up -d --build
    ```
    -   `up`: Starts the service.
    -   `-d`: Starts the container in the background (detached mode).
    -   `--build`: Rebuilds the Docker image if there were changes.

### 3. Test API
Once the container is running, you can test the API. The expected response on an empty server is `[]`.

**With PowerShell:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/get_memories?user_id=test" -Headers @{"X-API-Key" = "your-super-secure-key-12345"}
```

**With cURL:**
```bash
curl -X GET "http://localhost:8000/get_memories?user_id=test" -H "X-API-Key: your-super-secure-key-12345"
```

---

## ⚙️ Plugin Configuration (Valves)

You can find the core settings for the `adaptive_memory_v4.py` plugin directly in the `Valves` class in the code. Adjust these as needed:

-   `extraction_provider`: Choose "openai" or "local".
-   `relevance_provider`: Choose "openai", "local", or "embedding".
-   `openai_...`: Settings for the OpenAI API (Key is only required if OpenAI is selected as a provider).
-   `local_llm_...`: Settings for your local LLM (e.g., Ollama Chat API).
-   `local_embedding_provider`: Choose "sentence_transformer" or "ollama".
-   `sentence_transformer_model`: Model for the `sentence-transformers` library.
-   `ollama_embedding_...`: Settings for the Ollama Embeddings API.
-   `memory_api_base`, `memory_api_key`: Connection to the Memory Server.
-   *...and various other Thresholds & Filters.*

---

## 🛣️ Roadmap

The complete and up-to-date roadmap is maintained in the `ROADMAP.md` file to keep this README clean.

[➡️ **View the full Roadmap (ROADMAP.md)**](./ROADMAP.md)

---

## 💖 Credits & License

A huge thank you goes out to **gramanoid (aka diligent_chooser)**, whose work was the inspiration for this project.

-   [Original Reddit Post](https://www.reddit.com/r/OpenWebUI/comments/1kd0s49/adaptive_memory_v30_openwebui_plugin/)
-   [Open WebUI Plugin Page](https://openwebui.com/f/alexgrama7/adaptive_memory_v2)

This project is licensed under the **[Apache License 2.0](./LICENSE)**.
Copyright © 2026 J. Apps

> ⚠️ **Note:** The license applies only to this Memory project. All other modules within the Finja Ecosystem remain under the MIT License.

![Permission Screenshot](https://github.com/JohnV2002/Finja-AI-Ecosystem/blob/main/assets/Screenshot2025-09-12.png)

---

## 🆘 Support & Contact

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)

---

**Good luck with your Memory Server!** 🚀✨