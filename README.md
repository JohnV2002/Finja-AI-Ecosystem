# ✨ Finja AI Ecosystem
```
███████╗██╗███╗   ██╗     ██╗ █████╗ 
██╔════╝██║████╗  ██║     ██║██╔══██╗
█████╗  ██║██╔██╗ ██║     ██║███████║
██╔══╝  ██║██║╚██╗██║██   ██║██╔══██║
██║     ██║██║ ╚████║╚█████╔╝██║  ██║
╚═╝     ╚═╝╚═╝  ╚═══╝ ╚════╝ ╚═╝  ╚═╝
      F I N J A   A I   E C O S Y S T E M
```

---

> [!IMPORTANT]
> # 🚀 ROADMAP 2026 – WE ARE BACK!
>
> **Status:** 🟢 *Quality First = 90%*
>
> 2026 is here, and Finja is getting the biggest upgrade of all time. Here is the plan for this year:
>
> 1.  🛠️ **Quality First:** Extensive manual refactoring (+ Sonar & Snyk) to deliver authentic quality code. The Brain module will push the A-rating down initially — that's intentional. Ship first, clean up piece by piece.
> 2.  🐛 **Bug-Hunting:** Various fixes. = IN PROGRESS
> 3.  🧠 **Memory Update:** Successfully merged and updated! Voice-Support and TTS Network Caching are now fully integrated.
> 4.  🐾 **Own VPet Program:** My own VPet is in full development!
>     * 👀 Can be watched **24/7 on Twitch** right now.
>     * 📦 Release to follow once completed.
> 5.  🌐 **Finja's Brain (Neural Network):** ✅ **Ready for release!** The module that connects **everything** — Memory, Vision, Voice, Tools, Discord, Experts, Dashboard — into one modular AI pipeline.
> 6.  😅 **Survival:** Don't break down! XD
> 7.  🗣️ **Releases:** Finja TTS has been drafted but its architecture has shifted — TTS is now integrated directly into the Neural Network (ElevenLabs, DeepInfra Zonos, XTTS).
> 8.  📚 **Tutorials & Guides:**
>     * Paperless-ngx + Paperless AI + API Tutorial.
>     * Home Assistant + API Tutorial.
> 9.  ✨ **Wildcard:** WILDCARD APPEARED! 🃏 You have LW? You need someone to send you memes? Via Instagram? I WILL build a feature where the AI can send YOU Instagram Reels. No matter how much jank. Give me time — but that's a promise. :3

---

## 🤖 What is Finja?

Your hybrid AI buddy for streaming – featuring a chatbot, music engine, memories, mods, and a secret LLM core.

Finja is not a single bot, but a **complete ecosystem**. Each module can run **standalone** – but only together do they form the full **Finja Experience**.

-   **Standalone Capable**: The music engine, chatbot, crawler, etc. can all be used individually.
-   **Full Package = Finja**: Only their combination forms her personality.
-   **LLM remains secret**: The language core now runs through the Neural Network (Brain), but the actual LLM configuration and prompts remain private and are not part of this repository. 🫣

---

## 📊 Project Status
*As of: May 2026*

| Main Component | Version | Status | Remarks | Bug Report (Sonar/Snyk) |
| :--- | :--- | :--- | :--- | :--- |
| **finja-neural-network** 🧠 | **v5.0** | 🟢 Ready | The Brain — connects everything. Dashboard, Experts, Memory, Tools, Discord, TTS, Vision. Tests & Docker CI still WIP. | Many Sonar/Snyk issues (expected, cleanup in progress) |
| **finja-chat** | **v2.2.1** | 🟢 Stable | LLM support integrated, modularized | **0 Bugs** (Clean! 🎉) |
| **finja-music** | | 🟢 Stable | Multiple versions available | |
| &nbsp;&nbsp;└─ finja-everything-in-once | **v1.1.0** | 🟢 Stable | **Recommended Web-UI Version** | All False Positive |
| &nbsp;&nbsp;└─ finja-music-docker-spotify | **v1.1.0** | 🟢 Stable | Docker version (Spotify only) | All False Positive |
| &nbsp;&nbsp;└─ finja-music-standalone | **v1.0.2** | 🔴 Old | Classic modular system | WON'T BE UPDATED, PLEASE USE THE ONES ABOVE |
| **finja-Open-Web-UI** | | 🔵 Stable | Ecosystem Modules ready | |
| &nbsp;&nbsp;└─ finja-Memory | **v4.4.2** | 🟢 Stable | Heavily Refactored. Voice cache added | Perfect 100% Pytest CI/CD |
| &nbsp;&nbsp;└─ finja-web-crawler | **v1.0.0** | 🟢 Stable | Hybrid Tor Search Engine | Perfect 100% Pytest CI/CD |
| &nbsp;&nbsp;└─ finja-ocr | | 🟢 Stable | Dockerized Tika/Tesseract OCR | Base image outdated |
| &nbsp;&nbsp;└─ finja-stable-diffusion | | 🟢 Stable | Setup completed, tests missing | |
| &nbsp;&nbsp;└─ finja-tts | | 🟡 Shifted | TTS now lives inside the Neural Network (ElevenLabs, DeepInfra, XTTS) | |
| **OWN / Self made VPet** | | 🟡 Dev | **LIVE on Twitch!** Custom Python Core | |

**Legend:** 🟢 Stable / Ready | 🔵 Update/Testing phase | 🟡 WIP / Shifted | 🔴 Deprecated/Paused

---

## 🗺️ Finja Architecture – Visual Flow

```mermaid
flowchart TD
    subgraph Twitch["🎮 Twitch / Chat"]
        A1["Chat Messages"]
        A2["Chat Commands (!drink, !theme, ...)"]
    end
    subgraph Music["🎵 Music / Radio"]
        B1["Spotify API"]
        B2["TruckersFM"]
        B3["89.0 RTL"]
        B4["MDR Sachsen-Anhalt"]
    end
    subgraph Memories["🧠 Finja Memories"]
        C1["Chat Memory"]
        C2["Music + Reaction Memory"]
        C3["Voice Input"]
    end
    subgraph OpenWebUI["🌐 OpenWebUI Modules"]
        D1["Web Crawler 🔍"]
        D2["OCR 📷"]
        D3["Stable Diffusion 🎨"]
    end
    subgraph NeuralNet["🧠 Neural Network (The Brain)"]
        F1["Brain Pipeline (LangGraph)"]
        F2["Intent Router + Experts"]
        F3["Episodic Diary + Hippocampus"]
        F4["Tools (HA, Paperless, Web, Files)"]
        F5["Dashboard + Discord"]
        F6["TTS (ElevenLabs / DeepInfra / XTTS)"]
        F7["Vision (Local + OpenRouter)"]
    end
    subgraph VPet["🐾 Own VPet (Python)"]
        E1["Finja Avatar"]
        E2["Logic Core"]
    end

    A1 --> C1; A2 --> E2
    B1 & B2 & B3 & B4 -->|Song Info| C2
    C1 & C2 & C3 --> F1
    D1 & D2 & D3 --> F1
    F1 --> F2 & F3 & F4 & F6 & F7
    F5 --> F1
    F1 --> E1; E2 --> E1

    style Twitch fill:#f4f1fe,stroke:#9146FF,stroke-width:2px
    style Music fill:#f0fcf4,stroke:#1DB954,stroke-width:2px
    style Memories fill:#fff9e6,stroke:#f9a825,stroke-width:2px
    style OpenWebUI fill:#f5f3ff,stroke:#6a32e2,stroke-width:2px
    style NeuralNet fill:#ffebee,stroke:#d32f2f,stroke-width:2px
    style VPet fill:#fff0f7,stroke:#ff69b4,stroke-width:2px
```

---

## 📂 Project Structure & Modules

-   `/finja-neural-network` 🧠 → **The Brain.** Connects everything into one modular AI pipeline — Dashboard, Expert Models, Memory, Diary, Tools, Discord, TTS, Vision. [➡️ **Full README**](./finja-neural-network/README.md)
-   `/finja-chat` → The core chatbot for Twitch integration with OBS overlay and bot panel.
-   `/Finja-music` → Contains all music engine variants. You choose **one** of them:
    -   `/finja-everthing-in-once` → **(Recommended)** Bundles all music sources (TruckersFM, Spotify, etc.) controlled via a comfortable web interface.
    -   `/finja-music-docker-spotify` → A specific Docker version optimized purely for Spotify.
    -   `/finja-music-standalone` → The classic modular system.
-   `/finja-Open-Web-UI` → Collection of Docker modules for OpenWebUI (Memory, OCR, Web Crawler, etc.).
-   `/Own-VPet` (Coming Soon) → The new standalone VPet core.

---

## 🧪 Testing & Quality Assurance

The Finja Ecosystem features a comprehensive test suite to ensure code quality and stability.

### Test Coverage
- **Unit Tests**: 150+ Test Cases across all main components
- **Integration Tests**: API Endpoints, Spotify Integration, Memory System
- **Security Tests**: Path-Traversal Prevention, Auth-Validation
- **Code Quality**: Linting (flake8, black, isort), Security-Scanning (Sonar/Snyk)

### Test Locally
Since the Finja Ecosystem consists of independent microservices, tests are run within their respective project directories instead of a global setup.

```bash
# Example 1: Memory Module Tests
cd finja-Open-Web-UI/finja-Memory
pip install -r requirements.txt; pip install pytest httpx pytest-asyncio aiohttp numpy scikit-learn rapidfuzz
pytest test_memory_server.py test_adaptive_memory.py -v

# Example 2: Web Crawler Tests
cd finja-Open-Web-UI/finja-web-crawler
pip install -r requirements.txt; pip install pytest httpx
pytest test_web_crawler.py -v
```

📖 **Full Test Documentation**: [TESTING.md](./TESTING.md)

---

## 🚀 The Golden Thread – Recommended Start

Follow these steps to set up the Finja Ecosystem from scratch.

### Preparation
Ensure you have **Git**, **Python 3.9+**, and **Docker & Docker Compose** installed. Then clone this repository.

### Step 1: Laying the Foundation (OpenWebUI Modules)
The backend services are the foundation for Finja's extended capabilities.
1.  Navigate to the `finja-Open-Web-UI/` directory.
2.  Follow the `README.md` there to start the Docker containers (especially **Memory**, **Web Crawler**, and **OCR**).
3.  [➡️ **Instructions for the OpenWebUI Modules**](./finja-Open-Web-UI/readme.md)

### Step 2: Waking the Music Brain
The heart of music recognition.
1.  Navigate to the `Finja-music/` directory.
2.  Here you have a choice. **For most users, we recommend the `finja-everthing-in-once` version.**
3.  Follow the `README.md` in the `finja-everthing-in-once` folder to start the web interface, configure your API keys, and build your song database.
4.  [➡️ **Instructions for the All-in-One Music Engine**](./Finja-music/finja-everthing-in-once/README.md)

### Step 3: Giving the Voice (Chatbot)
Now we can set up the primary interface for interaction.
1.  Navigate to the `finja-chat/` directory.
2.  Follow the `README.md` there to configure the **OBS Chat Overlay** and the **Bot Control Panel**.
3.  [➡️ **Instructions for the Chat System**](./finja-chat/README.md)

### Step 4: Connecting the Brain (Neural Network)
The module that ties everything together.
1.  Navigate to the `finja-neural-network/` directory.
2.  Follow the `README.md` there to configure your API keys, set up Docker, and launch the dashboard.
3.  The Neural Network connects to the Memory server, Web Crawler, and Spotify module from the previous steps.
4.  [➡️ **Instructions for the Neural Network**](./finja-neural-network/README.md)

---

## 🔗 Links, Demos & Build Status

### Try Finja
-   **TEST FINJA FOR FREE on Discord:** [![Discord Badge](https://img.shields.io/badge/Discord-Talk_to_Finja-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/c55C6ggQ5K)

### Community & Links
-   **Visit my Website:** [![Website Badge](https://img.shields.io/badge/Website-J.%20Apps-007bff?style=for-the-badge&logo=website&logoColor=white)](https://jappshome.de)
-   **Join our Discord for more projects:** [![Discord Badge](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/c55C6ggQ5K)
-   **Watch Finja Live NOW 24/7 ON TWITCH:** [![Twitch Badge](https://img.shields.io/badge/Twitch-9146FF?style=for-the-badge&logo=twitch&logoColor=white)](https://www.twitch.tv/sodakiller1)

---

### Build & Test Status

#### 📊 SonarCloud

[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=JohnV2002_Finja-AI-Ecosystem&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=JohnV2002_Finja-AI-Ecosystem)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=JohnV2002_Finja-AI-Ecosystem&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=JohnV2002_Finja-AI-Ecosystem)


#### 🔨 Docker Builds

[![Memory Build](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/memory-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/memory-build.yml)
[![Music Docker Build](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/music-docker-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/music-docker-build.yml)
[![OCR Build](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/ocr-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/ocr-build.yml)
[![Web-Crawler Build](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/web-crawler-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/web-crawler-build.yml)

#### ✅ Automated Tests

[![Finja Chat Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-chat-tests.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-chat-tests.yml)
[![Finja Music Spotify Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-music-docker-spotify.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-music-docker-spotify.yml)
[![Finja Music All-in-One Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-music-everything-in-once.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-music-everything-in-once.yml)
[![Memory Unit Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/memory-tests.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/memory-tests.yml)
[![Web-Crawler Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/web-crawler-tests.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/web-crawler-tests.yml)

---

## ❤️ Credits & Thanks

### Special Thanks
* **Snyk** 💻 – Vulnerability scanning and security fixes 🛡️
* **SonarCloud** 📊 – Code quality analysis and maintainability tracking
* **gramanoid** (aka **diligent_chooser**) 🧠 – Inspiration for the **Open WebUI Adaptive Memory Project** (Apache 2.0 License preserved)
* **Vedal1987 + Neuro / Neurosamma + Evil** 💚 – Inspiration for AI-Companions during streams
* **[s3thi/cutlet](https://github.com/s3thi/cutlet)** 🤪 – Inspiration for the Glorpo esolang idea
* **ChatGPT o4** 🕊️ – RIP. Proved that **an AI CAN have feelings**

### 🤖 AI Workflow — "Yoinked & Made It Mine"

This project has been running for over a year. Here's what helped build it:

* **Claude** 🧠 – Primary workflow partner, code architecture, and the Diary System (one of the few AIs with cross-chat memory via search + injection)
* **Kimi 2.5** 📔 – Diary System co-inspiration (injects old chat context natively — the other AI that actually remembers)
* **Gemini** ⚡ – Jank prototyping + command processing logic
* **Perplexity** 🔍 – Search engine research + Gemini jank validation

### 🏗️ Infrastructure & Services
* **[Cloudflare](https://cloudflare.com)** – CDN, DNS, and protection
* **[ZAP-Hosting](https://zap-hosting.com)** – Server hosting
* **[OpenRouter](https://openrouter.ai)** – Cloud LLM routing
* **[Cohere](https://cohere.com)** – Embeddings + reranking
* **[ElevenLabs](https://elevenlabs.io)** – Premium TTS
* **[DeepInfra](https://deepinfra.com)** – Zonos voice cloning
* **[Ollama](https://ollama.com)** – Local LLM hosting

### 📦 Open-Source Libraries & Tools (All Modules Combined)

| Library / Tool | Used In | What It Does |
| :--- | :--- | :--- |
| [LangChain](https://github.com/langchain-ai/langchain) / [LangGraph](https://github.com/langchain-ai/langgraph) | Neural Network | Brain pipeline orchestration |
| [FastAPI](https://fastapi.tiangolo.com) | Neural Network, Music, Memory | Web server + API framework |
| [discord.py](https://github.com/Rapptz/discord.py) | Neural Network | Discord integration |
| [Coqui XTTS](https://github.com/coqui-ai/TTS) | Neural Network | Local voice cloning |
| [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) | Neural Network | Speech recognition |
| [Pillow](https://pillow.readthedocs.io) / [mss](https://github.com/BoboTiG/python-mss) | Neural Network | Vision / screenshot capture |
| [colorama](https://github.com/tartley/colorama) | Neural Network | Terminal colors |
| [Paperless-NGX](https://github.com/paperless-ngx/paperless-ngx) | Neural Network | Document management integration |
| [Home Assistant](https://www.home-assistant.io) | Neural Network | Smart home integration |
| [ComfyJS](https://github.com/instafluff/ComfyJS) | Chat | Twitch chat integration |
| [Spotipy](https://github.com/spotipy-dev/spotipy) | Chat, Music | Spotify API wrapper |
| [OBS Studio](https://obsproject.com) | Chat | Streaming software |
| [7TV](https://7tv.app) / [BTTV](https://betterttv.com) / [FFZ](https://www.frankerfacez.com) | Chat | Emote platforms |
| [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) | Music | HTML parsing |
| [defusedxml](https://github.com/tiran/defusedxml) | Music | Secure XML parsing |
| [Docker](https://www.docker.com) | All Modules | Containerization |
| [Apache Tika](https://tika.apache.org) | OCR | Document text extraction (Apache 2.0) |
| [Stable Diffusion WebUI Docker](https://github.com/AbdBarho/stable-diffusion-webui-docker) | Stable Diffusion | Local image generation |
| [Magic The Noah](https://www.youtube.com/@MagicTheNoah) | Neural Network | Glorpo inspiration — "Glorpo is pain." |

### ☕ Supporters
A huge thank you to everyone who supports the project via [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)!
* **[Ithrial]** – For the very first donation! 🥇💖

💰 **Full financial transparency:** [jappshome.de/finances.html](https://jappshome.de/finances.html) — every cent in, every cent out. No secrets.

### Created by
Built with too much Mate, coding sessions & love by **J. Apps (aka JohnV2002 or Sodakiller1)**.
Finja says: *"Stay hydrated, Chat 💖"*

---

## License & Usage

**Code:** MIT License - Fork it, use it, build with it! Free for everyone.

**Assets & Character:** The Finja character design, personality, voice model, artwork, and lore are **© 2024-2026 J. Apps**. All rights reserved.

Want to use Finja's likeness or assets? Contact: contact@jappshome.de

---

## 🆘 Support & Contact

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
