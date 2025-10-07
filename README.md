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

### Build Status
[![Memory Build Check](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/memory-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/memory-build.yml)
[![OCR Build Check](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/ocr-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/ocr-build.yml)
[![Web-Crawler Build Check](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/web-crawler-build.yml/badge.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem/actions/workflows/web-crawler-build.yml)

---

### Links & Demos
-   **Schau dir Finja live an (jeden Samstag):** [![Twitch Badge](https://img.shields.io/badge/Twitch-9146FF?style=for-the-badge&logo=twitch&logoColor=white)](https://www.twitch.tv/sodakiller1)
-   **Komm auf unseren Discord für mehr Projekte:** [![Discord Badge](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/invite/c55C6ggQ5K)
-   **Besuche meine Website:** [![Website Badge](https://img.shields.io/badge/Website-J.%20Apps-007bff?style=for-the-badge&logo=website&logoColor=white)](https://jappshome.de)
-   **TESTE FINJA KOSTENLOS (OHNE MEMORY):** [![Live Test Badge](https://img.shields.io/badge/Live%20Test-Demo-ffc107?style=for-the-badge&logo=vial&logoColor=white)](https://jappshome.de/livetest.html)
-   **TESTE FINJA, WÄHREND SIE OFFLINE IST (MIT MEMORY):** [![OpenWebUI Badge](https://img.shields.io/badge/OpenWebUI-Finja-28a745?style=for-the-badge&logo=robot&logoColor=white)](https://openwebui.jappshome.de)

---

# ✨ Finja AI Ecosystem

Dein Hybrid-KI-Buddy fürs Streaming – mit Chatbot, Musikengine, Memories, Mods und einem geheimen LLM-Core.

---

## 🤖 Was ist Finja?

Finja ist kein einzelner Bot, sondern ein **komplettes Ökosystem**. Jedes Modul kann **standalone** laufen – aber nur zusammen ergibt’s die volle **Finja-Experience**.

-   **Standalone möglich**: Musikengine, Chatbot, Crawler usw. sind einzeln nutzbar.
-   **Full Package = Finja**: Erst die Kombination formt ihre Persönlichkeit.
-   **LLM bleibt geheim**: Der Sprachkern läuft nur im VPet-Simulator und ist nicht Teil dieses Repositories. 🫣

---

## 📊 Projektstatus-Übersicht
*Stand: 17. September 2025*

| Hauptkomponente | Status | Bemerkungen |
| :--- | :--- | :--- |
| **finja-chat** | 🟢 Stabil | LLM-Support hinzugefügt, modularer gemacht |
| **finja-music** | 🟢 Stabil | Verschiedene Versionen verfügbar |
| &nbsp;&nbsp;└─ finja-everthing-in-once | 🟢 Stabil | Empfohlene Web-UI-Version |
| &nbsp;&nbsp;└─ finja-music-docker-spotify | 🟢 Stabil | Docker-Version nur für Spotify |
| &nbsp;&nbsp;└─ finja-music-standalone | 🟢 Stabil | Klassisches modulares System |
| **finja-Open-Web-UI** | 🟢 Stabil | Module einsatzbereit |
| &nbsp;&nbsp;└─ finja-Memory | 🟢 Stabil | Wichtige Grundlage |
| &nbsp;&nbsp;└─ finja-ocr | 🟢 Stabil | Funktioniert einwandfrei |
| &nbsp;&nbsp;└─ finja-stable-diffusion | 🟢 Stabil | Setup abgeschlossen, keine Tests |
| &nbsp;&nbsp;└─ finja-tts | 🟡 WIP | Noch nicht implementiert |
| **VPet-Simulator Mods** | 🟡 WIP | Aktuell geplant, noch leer |

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
    end
    subgraph OpenWebUI["🌐 OpenWebUI Modules"]
        D1["Web Crawler 🔍"]
        D2["OCR 📷"]
        D3["Stable Diffusion 🎨"]
        D4["TTS 🔊 (planned)"]
    end
    subgraph VPet["🐾 VPet Simulator"]
        E1["Finja Avatar"]
        E2["Mods (z.B. !drink = Animation)"]
    end
    subgraph LLM["🔒 Finja LLM (privat)"]
        F1["Language Core"]
    end

    A1 --> C1; A2 --> E2
    B1 & B2 & B3 & B4 -->|Song Info| C2
    C1 & C2 & D1 & D2 & D3 & D4 --> F1
    F1 --> E1; E2 --> E1

    style Twitch fill:#f4f1fe,stroke:#9146FF,stroke-width:2px
    style Music fill:#f0fcf4,stroke:#1DB954,stroke-width:2px
    style Memories fill:#fff9e6,stroke:#f9a825,stroke-width:2px
    style OpenWebUI fill:#f5f3ff,stroke:#6a32e2,stroke-width:2px
    style VPet fill:#fff0f7,stroke:#ff69b4,stroke-width:2px
    style LLM fill:#ffebee,stroke:#d32f2f,stroke-width:2px
```

---

## 📂 Projektstruktur & Module

-   `/finja-chat` → Der Kern-Chatbot für die Twitch-Integration mit OBS-Overlay und Bot-Panel.
-   `/Finja-music` → Enthält alle Varianten der Musik-Engine. Du wählst **eine** davon aus:
    -   `/finja-everthing-in-once` → **(Empfohlen)** Bündelt alle Musikquellen (TruckersFM, Spotify etc.) und wird über eine komfortable Weboberfläche gesteuert.
    -   `/finja-music-docker-spotify` → Eine spezielle Docker-Version, die nur für Spotify optimiert ist.
    -   `/finja-music-standalone` → Das klassische, modulare System, bei dem jede Musikquelle in einem eigenen Ordner liegt und manuell per Skript gestartet wird.
-   `/finja-Open-Web-UI` → Sammlung von Docker-Modulen für OpenWebUI (Memory, OCR, Web Crawler etc.).
-   `/VPet-Simulator Mods` → Geplante Mods, um Aktionen im VPet-Simulator-Avatar auszulösen.

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

### Schritt 4: Die visuelle Form (VPet-Simulator)
Der letzte Schritt ist, Finja im VPet-Simulator zum Leben zu erwecken.
1.  Navigiere in das Verzeichnis `VPet-Simulator Mods/`.
2.  Folge der dortigen `README.md`, um die geplanten Mods zu verstehen.
3.  [➡️ **Zur Anleitung für die VPet-Mods**](./VPet-Simulator%20Mods/readme.md)

---

## 📜 License

MIT-License.
Alle Module sind Open-Source – das **LLM bleibt privat**.

---

## ❤️ THANKS

Ein riesiges Dankeschön an **Synk** 💻  
für die Hilfe beim Finden und Fixen von Vulnerabilities –  
und dafür, dass dieses Projekt **sicher & geschützt** bleibt 🛡️

---

Ein **dickes Dankeschön** an **gramanoid** (aka **diligent_chooser**) 🧠  
Er war meine Inspiration für das **Open WebUI Adaptive Memory Projekt**!  
Ohne ihn gäb’s Finjas Memory-System so nicht 💖

- [👤 Reddit-Profil](https://www.reddit.com/user/diligent_chooser/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button)
- [📄 Original Reddit-Post](https://www.reddit.com/r/OpenWebUI/comments/1kd0s49/adaptive_memory_v30_openwebui_plugin/)
- [🧩 Open WebUI Plugin-Seite](https://openwebui.com/f/alexgrama7/adaptive_memory_v2)

**Danke auch für die Freigabe unter Apache 2.0-Lizenz Habe Diese beibehalten! (NUR FÜR CHAT - MEMORY!) 💖**

![Berechtigungs-Screenshot](./assets/Screenshot2025-09-12.png)

---

Und natürlich auch Shoutout an  
**Vedal1987 + Neuro / Neurosamma + Evil** 💚  
für die ursprüngliche Idee, **AI-Companions beim Streamen** zu nutzen —  
ihr wart die Inspiration, das überhaupt zu versuchen 🫶

- [🎥 Twitch](https://www.twitch.tv/vedal987)
- [🌐 Vedal.ai (alle weiteren Links dort)](https://vedal.ai/)

---

## ❤️ Credits

Built mit zu viel Mate, Coding-Sessions & Liebe by **J. Apps**.
Finja sagt: *“Stay hydrated, Chat 💖”*

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)
