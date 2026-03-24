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
> **Status:** 🟢 *Quality First = 20%*
>
> 2026 ist da und Finja bekommt das größte Upgrade aller Zeiten. Hier ist der Plan für dieses Jahr:
>
> 1.  🛠️ **Quality First:** Ich überarbeite den Code fast einmal komplett manuell *hust hust* eh manuell ist doch etwas anstrengend für mein ADS *hust hust* (+ Hilfe von Sonar), um echten Quality-Code zu liefern.
> 2.  🐛 **Bug-Hunting:** Diverse Fixes stehen an. = LÄUFT
> 3.  🧠 **Memory Update:** Voice-Support ist hinzugefügt! (Checks müssen noch gemacht werden).
> 4.  🐾 **Own VPet Program:** Mein eigenes VPet ist in voller Bearbeitung!
>     * 👀 Kann ab sofort **24/7 auf Twitch** beobachtet werden.
>     * 📦 Release folgt, sobald es vollständig ist.
> 5.  🌐 **Finja's Brain:** Arbeit läuft – dieses Modul verknüpft endlich **ALLES** miteinander.
> 6.  😅 **Survival:** Nicht zusammenbrechen! XD
> 7.  🗣️ **Releases:** Finja TTS muss noch veröffentlicht werden.
> 8.  📚 **Tutorials & Guides:**
>     * Paperless-ngx + Paperless AI + API Tutorial.
>     * Home Assistant + API Tutorial.
> 9.  ✨ **Wildcard:** Alles, was mir übers Jahr noch so einfällt! :D

---

## 🤖 Was ist Finja?

Dein Hybrid-KI-Buddy fürs Streaming – mit Chatbot, Musikengine, Memories, Mods und einem geheimen LLM-Core.

Finja ist kein einzelner Bot, sondern ein **komplettes Ökosystem**. Jedes Modul kann **standalone** laufen – aber nur zusammen ergibt’s die volle **Finja-Experience**.

-   **Standalone möglich**: Musikengine, Chatbot, Crawler usw. sind einzeln nutzbar.
-   **Full Package = Finja**: Erst die Kombination formt ihre Persönlichkeit.
-   **LLM bleibt geheim**: Der Sprachkern läuft nur im VPet-Simulator und ist nicht Teil dieses Repositories. 🫣

---

## 📊 Projektstatus
*Stand: Januar 2026*

| Hauptkomponente | Version | Status | Bemerkungen | Fehler-Bericht (Sonar/Snyk) |
| :--- | :--- | :--- | :--- | :--- |
| **finja-chat** | **v2.2.1** | 🟢 Stabil | LLM-Support integriert, modularisiert | **0 Fehler** (Sauber! 🎉) |
| **finja-music** | | 🔵 Stabil | Verschiedene Versionen verfügbar | |
| &nbsp;&nbsp;└─ finja-everything-in-once | **v1.1.0** | 🟢 Stabil | **Empfohlene Web-UI-Version** | 1 Real / 15 False Positive |
| &nbsp;&nbsp;└─ finja-music-docker-spotify | **v1.0.1** | 🟢 Stabil | Docker-Version (Spotify only) | 5 False Postive |
| &nbsp;&nbsp;└─ finja-music-standalone | **v1.0.2** | 🔴 Old | Klassisches modulares System | WONT BE UPDATED PLEASE USE THE ABOVE ONCE |
| **finja-Open-Web-UI** | | 🔵 Stabil | Module einsatzbereit | |
| &nbsp;&nbsp;└─ finja-Memory | **v4.4.2** | 🔵 Testing | Voice added, Checks running | |
| &nbsp;&nbsp;└─ finja-ocr | | 🔵 Stabil | Funktioniert einwandfrei | |
| &nbsp;&nbsp;└─ finja-stable-diffusion | | 🟢 Stabil | Setup fertig, Tests fehlen | |
| &nbsp;&nbsp;└─ finja-tts | | 🟡 WIP | Release geplant | |
| **OWN / Self made VPet** | | 🟡 Dev | **LIVE auf Twitch!** Eigener Python-Core | |
| **Finja's Brain** | | 🟡 WIP | Das neue Verbindungs-Modul | |

**Legende:** 🟢 Stabil | 🔵 Update/Testphase | 🟡 WIP (in Arbeit) | 🔴 Veraltet/Pausiert

---

## 🗺️ Finja Architektur – Visueller Flow

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

## 📂 Projektstruktur & Module

-   `/finja-chat` → Der Kern-Chatbot für die Twitch-Integration mit OBS-Overlay und Bot-Panel.
-   `/Finja-music` → Enthält alle Varianten der Musik-Engine. Du wählst **eine** davon aus:
    -   `/finja-everthing-in-once` → **(Empfohlen)** Bündelt alle Musikquellen (TruckersFM, Spotify etc.) und wird über eine komfortable Weboberfläche gesteuert.
    -   `/finja-music-docker-spotify` → Eine spezielle Docker-Version, die nur für Spotify optimiert ist.
    -   `/finja-music-standalone` → Das klassische, modulare System.
-   `/finja-Open-Web-UI` → Sammlung von Docker-Modulen für OpenWebUI (Memory, OCR, Web Crawler etc.).
-   `/Own-VPet` (Coming Soon) → Der neue eigenständige VPet-Core.

---

## 🧪 Testing & Quality Assurance

Das Finja-Ökosystem verfügt über eine umfassende Test-Suite, um Code-Qualität und Stabilität sicherzustellen.

### Test-Coverage
- **Unit Tests**: 150+ Test Cases für alle Haupt-Komponenten
- **Integration Tests**: API-Endpoints, Spotify-Integration, Memory-System
- **Security Tests**: Path-Traversal-Prevention, Auth-Validation
- **Code Quality**: Linting (flake8, black, isort), Security-Scanning (bandit, safety)

### Lokal testen
```bash
# Test-Dependencies installieren
pip install -r test-requirements.txt

# Alle Tests ausführen
pytest

# Mit Coverage-Report
pytest --cov=. --cov-report=html
```

📖 **Vollständige Test-Dokumentation**: [TESTING.md](./TESTING.md)

---

## 🚀 Der rote Faden – Empfohlener Start

Folge diesen Schritten, um das Finja-Ökosystem von Grund auf einzurichten.

### Vorbereitung
Stelle sicher, dass du **Git**, **Python 3.9+** und **Docker & Docker Compose** installiert hast. Klone dann dieses Repository.

### Schritt 1: Das Fundament legen (OpenWebUI-Module)
Die Backend-Dienste sind die Grundlage für Finjas erweiterte Fähigkeiten.
1.  Navigiere in das Verzeichnis `finja-Open-Web-UI/`.
2.  Folge der dortigen `README.md`, um die Docker-Container (besonders **Memory**, **Web Crawler** und **OCR**) zu starten.
3.  [➡️ **Zur Anleitung für die OpenWebUI-Module**](./finja-Open-Web-UI/README.md)

### Schritt 2: Das Musik-Gehirn zum Leben erwecken
Das Herzstück der Musikerkennung.
1.  Navigiere in das Verzeichnis `Finja-music/`.
2.  Hier hast du die Wahl. **Für die meisten Nutzer empfehlen wir die `finja-everthing-in-once`-Version.**
3.  Folge der `README.md` im `finja-everthing-in-once`-Ordner, um die Weboberfläche zu starten, deine API-Keys zu konfigurieren und deine Song-Datenbank aufzubauen.
4.  [➡️ **Zur Anleitung für die All-in-One Musik-Engine**](./Finja-music/finja-everthing-in-once/README.md)

### Schritt 3: Die Stimme geben (Chatbot)
Jetzt können wir die primäre Schnittstelle für die Interaktion einrichten.
1.  Navigiere in das Verzeichnis `finja-chat/`.
2.  Folge der dortigen `README.md`, um das **OBS Chat-Overlay** und das **Bot Control Panel** zu konfigurieren.
3.  [➡️ **Zur Anleitung für das Chat-System**](./finja-chat/README.md)

---

## 🔗 Links, Demos & Build Status

### Live Demos
-   🚨 **DEFEKT!** ~~**TESTE FINJA, WÄHREND SIE OFFLINE IST (MIT MEMORY):** [![OpenWebUI Badge](https://img.shields.io/badge/OpenWebUI-Finja-28a745?style=for-the-badge&logo=robot&logoColor=white)](https://openwebui.jappshome.de)~~
-   🚨 **DEFEKT!** ~~**TESTE FINJA KOSTENLOS (OHNE MEMORY) UPDATED TO MoE Modell!:** [![Live Test Badge](https://img.shields.io/badge/Live%20Test-Demo-ffc107?style=for-the-badge&logo=vial&logoColor=white)](https://jappshome.de/livetest.html)~~

### Community & Docs
-   **Blog:** [![Blog Badge](https://img.shields.io/badge/Blog-Finja-fd7e14?style=for-the-badge&logo=rss&logoColor=white)](https://doku.jappshome.de/blog)
-   **Documentation:** [![Dokumentation Badge](https://img.shields.io/badge/Doku-Finja-28a745?style=for-the-badge&logo=robot&logoColor=yellow)](https://doku.jappshome.de)
-   **Besuche meine Website:** [![Website Badge](https://img.shields.io/badge/Website-J.%20Apps-007bff?style=for-the-badge&logo=website&logoColor=white)](https://jappshome.de)
-   **Komm auf unseren Discord für mehr Projekte:** [![Discord Badge](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/invite/c55C6ggQ5K)
-   **Schau dir Finja live an **AB SOFORT 24/7 AUF TWITCH**:** [![Twitch Badge](https://img.shields.io/badge/Twitch-9146FF?style=for-the-badge&logo=twitch&logoColor=white)](https://www.twitch.tv/sodakiller1)

---

### Build & Test Status

#### 🔨 Docker Builds
[![Music Docker Build & Test](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/music-docker-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/music-docker-build.yml)
[![Memory Build Check](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/memory-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/memory-build.yml)
[![OCR Build Check](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/ocr-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/ocr-build.yml)
[![Web-Crawler Build Check](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/web-crawler-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/web-crawler-build.yml)

#### ✅ Automated Tests
[![Finja Chat Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-chat-tests.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-chat-tests.yml)
[![Finja Music Everything in once Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-music-everything-in-once.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-music-everything-in-once.yml)
[![Finja Music Docker Spotify Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-music-docker-spotify.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/finja-music-docker-spotify.yml)
[![OpenWebUI Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/openweb-ui-tests.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/openweb-ui-tests.yml)
[![Code Quality](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/code-quality.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/code-quality.yml)
[![Comprehensive Tests](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/comprehensive-tests.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/comprehensive-tests.yml)



---

## ❤️ Credits & Thanks

### Special Thanks
* **Synk** 💻 – für die Hilfe beim Finden und Fixen von Vulnerabilities und die Sicherheit des Projekts 🛡️
* **gramanoid** (aka **diligent_chooser**) 🧠 – Inspiration für das **Open WebUI Adaptive Memory Projekt** (Apache 2.0 License preserved).
* **Vedal1987 + Neuro / Neurosamma + Evil** 💚 – Inspiration für AI-Companions beim Streamen.

### ☕ Supporter
Ein riesiges Dankeschön geht an alle, die das Projekt über [Buy Me a Coffee](https://buymeacoffee.com/J.Apps) unterstützen!
* **[Ithrial]** – für die allererste Spende! 🥇💖

### Created by
Built mit zu viel Mate, Coding-Sessions & Liebe by **J. Apps (aka JohnV2002 or Sodakiller1)**.
Finja sagt: *“Stay hydrated, Chat 💖”*

---

## License & Usage

**Code:** MIT License - Fork it, use it, build with it! Free for everyone.

**Assets & Character:** The Finja character design, personality, voice model, artwork, and lore are **© 2024-2026 J. Apps**. All rights reserved.

Want to use Finja's likeness or assets? Contact: [contact@jappshome.de]

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
