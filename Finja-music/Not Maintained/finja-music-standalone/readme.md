# 🎶 Finja-Music-Standalone (⚠️ Unmaintained)

> **This module is no longer maintained.**
> Please use one of the actively maintained alternatives:
>
> - **[finja-everything-in-one](../finja-everything-in-one/)** — Recommended all-in-one setup
> - **[finja-music-docker-spotify](../finja-music-docker-spotify/)** — Docker-based Spotify integration
>
> This standalone version remains available as-is for reference, but will not receive updates or bug fixes.

---

## 💡 Core Concept: One Brain, Many Ears

The system is based on a two-part architecture that applies to every music source:

1. **Part 1: Get Content (The Ears)**
   A specialized script per source (e.g. `truckersfm_nowplaying.py` for TruckersFM) with one job: detect the currently playing song and write it to a simple text file (`nowplaying.txt`).

2. **Part 2: MUSIK/Brain (The Brain)**
   A central script that reads the `nowplaying.txt` from an active source. It matches the song against a knowledge base, determines genres, picks a fitting reaction, and stores memories. The output is written to files displayed by your OBS overlay.

**The recommended method is to use ONE central brain for ALL sources.**

```mermaid
flowchart TD
    subgraph Sources (Ears)
        A[🚚 TruckersFM]
        B[🎧 Spotify]
        C[📻 MDR]
        D[📡 89.0 RTL]
    end

    subgraph Processing
        E((nowplaying.txt))
        F[🧠 Central Music Brain]
    end

    subgraph Output
        G[📝 OBS Files]
        H[💖 OBS Overlay]
    end

    A --> E
    B --> E
    C --> E
    D --> E
    E --> F
    F --> G
    G --> H
```

---

## 🎵 Supported Music Sources

| Source | Method | Status |
| :--- | :--- | :--- |
| **🚚 TruckersFM** | Web scraping of the official website. | ✅ Ready |
| **🎧 Spotify** | Official Spotify Web API. | ✅ Ready |
| **📻 MDR** | Hybrid (ICY metadata, XML feed, web scraping). | ✅ Ready |
| **📡 89.0 RTL** | Chrome Debugging Protocol (CDP). | ✅ Ready |

---

## 📂 Modules

Each module lives in its own subfolder with detailed `README.md` files.

### 🚚 TruckersFM
The foundation of the system. Fetches song info by scraping the TruckersFM website. The `MUSIK` folder here serves as the central brain.

[➡️ **TruckersFM module guide...**](./TruckersFM/README.md)

### 🎧 Spotify
Connects your Spotify account via the official API. Requires one-time authentication.

[➡️ **Spotify module guide...**](./Spotify/README.md)

### 📻 MDR (MDR Sachsen-Anhalt)
A robust script that checks multiple sources (stream metadata, XML, website) to reliably detect the current MDR song.

[➡️ **MDR module guide...**](./MDR/README.md)

### 📡 89.0 RTL
Uses the Chrome Debugging Protocol to read the song title directly from the 89.0 RTL web player. Requires a running Chrome instance.

[➡️ **89.0 RTL module guide...**](./RTL/README.md)

---

## 📜 License

All modules in this project are licensed under the **MIT License**.

Made with ❤️ by [Sodakiller1](https://twitch.tv/sodakiller1) (J. Apps / JohnV2002)

---

## 🆘 Support & Contact

- **Email:** contact@jappshome.de
- **Website:** [jappshome.de](https://jappshome.de)
- **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)