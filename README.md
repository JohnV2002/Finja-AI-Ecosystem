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
> 1.  🛠️ **Quality First:** Extensive manual refactoring (+ Sonar & Snyk) to deliver authentic quality code.
> 2.  🐛 **Bug-Hunting:** Various fixes. = IN PROGRESS
> 3.  🧠 **Memory Update:** Successfully merged and updated! Voice-Support and TTS Network Caching are now fully integrated.
> 4.  🐾 **Own VPet Program:** My own VPet is in full development!
>     * 👀 Can be watched **24/7 on Twitch** right now.
>     * 📦 Release to follow once completed.
> 5.  🌐 **Finja's Brain:** Work is underway – this module will finally connect **EVERYTHING** together.
> 6.  😅 **Survival:** Don't break down! XD
> 7.  🗣️ **Releases:** Finja TTS has been drafted but its architecture has shifted toward Finja's Neural System.
> 8.  📚 **Tutorials & Guides:**
>     * Paperless-ngx + Paperless AI + API Tutorial.
>     * Home Assistant + API Tutorial.
> 9.  ✨ **Wildcard:** Whatever else comes to mind throughout the year! :D

---

## 🤖 What is Finja?

Your hybrid AI buddy for streaming – featuring a chatbot, music engine, memories, mods, and a secret LLM core.

Finja is not a single bot, but a **complete ecosystem**. Each module can run **standalone** – but only together do they form the full **Finja Experience**.

-   **Standalone Capable**: The music engine, chatbot, crawler, etc. can all be used individually.
-   **Full Package = Finja**: Only their combination forms her personality.
-   **LLM remains secret**: The language core runs exclusively inside the VPet simulator and is not part of this repository. 🫣

---

## 📊 Project Status
*As of: March 2026*

| Main Component | Version | Status | Remarks | Bug Report (Sonar/Snyk) |
| :--- | :--- | :--- | :--- | :--- |
| **finja-chat** | **v2.2.1** | 🟢 Stable | LLM support integrated, modularized | **0 Bugs** (Clean! 🎉) |
| **finja-music** | | 🟢 Stable | Multiple versions available | |
| &nbsp;&nbsp;└─ finja-everything-in-once | **v1.1.0** | 🟢 Stable | **Recommended Web-UI Version** | 1 Real / 15 False Positive |
| &nbsp;&nbsp;└─ finja-music-docker-spotify | **v1.1.0** | 🟢 Stable | Docker version (Spotify only) | 5 False Positive |
| &nbsp;&nbsp;└─ finja-music-standalone | **v1.0.2** | 🔴 Old | Classic modular system | WON'T BE UPDATED, PLEASE USE THE ONES ABOVE |
| **finja-Open-Web-UI** | | 🔵 Stable | Ecosystem Modules ready | |
| &nbsp;&nbsp;└─ finja-Memory | **v4.4.2** | 🟢 Stable | Heavily Refactored. Voice cache added | Perfect 100% Pytest CI/CD |
| &nbsp;&nbsp;└─ finja-web-crawler | **v1.0.0** | 🟢 Stable | Hybrid Tor Search Engine | Perfect 100% Pytest CI/CD |
| &nbsp;&nbsp;└─ finja-ocr | | 🟢 Stable | Dockerized Tika/Tesseract OCR | Base image outdated |
| &nbsp;&nbsp;└─ finja-stable-diffusion | | 🟢 Stable | Setup completed, tests missing | |
| &nbsp;&nbsp;└─ finja-tts | | 🟡 WIP | Architectural shift to Neural System | |
| **OWN / Self made VPet** | | 🟡 Dev | **LIVE on Twitch!** Custom Python Core | |
| **Finja's Brain** | | 🟡 WIP | The new interconnection module | |

**Legend:** 🟢 Stable | 🔵 Update/Testing phase | 🟡 WIP (Work in Progress) | 🔴 Deprecated/Paused

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
        C3["Voice Input (New)"]
    end
    subgraph OpenWebUI["🌐 OpenWebUI Modules"]
        D1["Web Crawler 🔍"]
        D2["OCR 📷"]
        D3["Stable Diffusion 🎨"]
        D4["TTS 🔊 (planned)"]
    end
    subgraph VPet["🐾 Own VPet (Python)"]
        E1["Finja Avatar"]
        E2["Logic Core"]
    end
    subgraph Brain["🔗 Finja's Brain"]
        F1["Central Logic Hub"]
    end

    A1 --> C1; A2 --> E2
    B1 & B2 & B3 & B4 -->|Song Info| C2
    C1 & C2 & C3 & D1 & D2 & D3 & D4 --> F1
    F1 --> E1; E2 --> E1

    style Twitch fill:#f4f1fe,stroke:#9146FF,stroke-width:2px
    style Music fill:#f0fcf4,stroke:#1DB954,stroke-width:2px
    style Memories fill:#fff9e6,stroke:#f9a825,stroke-width:2px
    style OpenWebUI fill:#f5f3ff,stroke:#6a32e2,stroke-width:2px
    style VPet fill:#fff0f7,stroke:#ff69b4,stroke-width:2px
    style Brain fill:#ffebee,stroke:#d32f2f,stroke-width:2px
```

---

## 📂 Project Structure & Modules

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

---

## 🔗 Links, Demos & Build Status

### Live Demos
-   🚨 **BROKEN!** ~~**TEST FINJA WHILE SHE IS OFFLINE (WITH MEMORY):** [![OpenWebUI Badge](https://img.shields.io/badge/OpenWebUI-Finja-28a745?style=for-the-badge&logo=robot&logoColor=white)](https://openwebui.jappshome.de)~~
-   🚨 **BROKEN!** ~~**TEST FINJA FOR FREE (WITHOUT MEMORY) UPDATED TO MoE Model!:** [![Live Test Badge](https://img.shields.io/badge/Live%20Test-Demo-ffc107?style=for-the-badge&logo=vial&logoColor=white)](https://jappshome.de/livetest.html)~~

### Community & Docs
-   **Blog:** [![Blog Badge](https://img.shields.io/badge/Blog-Finja-fd7e14?style=for-the-badge&logo=rss&logoColor=white)](https://doku.jappshome.de/blog)
-   **Documentation:** [![Documentation Badge](https://img.shields.io/badge/Doku-Finja-28a745?style=for-the-badge&logo=robot&logoColor=yellow)](https://doku.jappshome.de)
-   **Visit my Website:** [![Website Badge](https://img.shields.io/badge/Website-J.%20Apps-007bff?style=for-the-badge&logo=website&logoColor=white)](https://jappshome.de)
-   **Join our Discord for more projects:** [![Discord Badge](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/invite/c55C6ggQ5K)
-   **Watch Finja Live **NOW 24/7 ON TWITCH**:** [![Twitch Badge](https://img.shields.io/badge/Twitch-9146FF?style=for-the-badge&logo=twitch&logoColor=white)](https://www.twitch.tv/sodakiller1)

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
* **Snyk** 💻 – For the help in finding and fixing vulnerabilities, and securing the project 🛡️
* **gramanoid** (aka **diligent_chooser**) 🧠 – Inspiration for the **Open WebUI Adaptive Memory Project** (Apache 2.0 License preserved).
* **Vedal1987 + Neuro / Neurosamma + Evil** 💚 – Inspiration for AI-Companions during streams.

### ☕ Supporters
A huge thank you to everyone who supports the project via [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)!
* **[Ithrial]** – For the very first donation! 🥇💖

### Created by
Built with too much Mate, coding sessions & love by **J. Apps (aka JohnV2002 or Sodakiller1)**.
Finja says: *“Stay hydrated, Chat 💖”*

---

## License & Usage

**Code:** MIT License - Fork it, use it, build with it! Free for everyone.

**Assets & Character:** The Finja character design, personality, voice model, artwork, and lore are **© 2024-2026 J. Apps**. All rights reserved.

Want to use Finja's likeness or assets? Contact: contact@jappshome.de

---

## 🆘 Support & Contact

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
