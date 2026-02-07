# 🎶 Finja Music System

Welcome to the Finja Music System! 💖

A collection of modules that fetch live music information from various sources (web radio, Spotify), process it intelligently, and integrate it as a dynamic overlay into your OBS streaming setup.

The heart of the system is a central "music brain" that learns what music you like and responds with personalized reactions.

---

## ✨ Choose Your Version: All-in-One or Docker?

This project comes in two actively maintained variants. Choose what fits you best.

### 🚀 All-in-One Edition (Recommended)
Everything in one folder, controlled via a comfortable web interface.
- **Ideal for:** Beginners and most users.
- **Pros:** Easy point-and-click operation, central management of all sources, minimal terminal work.

### 🐳 Docker Edition
Containerized Spotify integration for self-hosted environments.
- **Ideal for:** Server setups, advanced users, and those who prefer Docker.
- **Pros:** Isolated, reproducible, easy deployment.

> ⚠️ **Note:** A legacy modular/standalone version exists under [`Not Maintained/finja-music-standalone/`](./Not%20Maintained/finja-music-standalone/) for reference only. It will not receive updates.

---

## 🚀 All-in-One Edition (Recommended)

This version bundles all music modules into a single folder, controlled via a web interface.

### Features
- **Central Control:** A web UI (`Musik.html`) to manage the entire system.
- **Multi-Source Support:** Enable detection for TruckersFM, Spotify, 89.0 RTL, or MDR with a single click.
- **Intelligent Music Brain:** Uses a central knowledge base (`songs_kb.json`) to recognize genres and generate dynamic reactions.
- **Integrated DB Tools:** Build and expand your song database directly from Spotify playlists via the web UI.
- **Conflict Resolution:** A dedicated web UI (`ArtistNotSure.html`) to fix ambiguous artist assignments.

### Folder Structure
```plaintext
finja-everything-in-one/
├── config/                  # Configuration files
├── MDRHilfe/                # Helper scripts for MDR
├── Memory/                  # Finja's long-term memory & profiles
├── missingsongs/            # Logs for unknown songs
├── Nowplaying/              # Central output files for OBS
├── OBSHTML/                 # All HTML overlays and control pages
├── RTLHilfe/                # Helper scripts for 89.0 RTL
├── SongsDB/                 # The central song database
├── start_server.bat         # Starts the main web server
└── webserver.py             # Web server code
```

### Setup & Start

**Step 1: Configure Spotify API**
1. Open `finja-everything-in-one/config/config_spotify.json`.
2. Enter your `client_id`, `client_secret`, and `refresh_token`.
> 🔴 **IMPORTANT:** This file contains sensitive credentials! Never upload it to a public repository.

**Step 2: Build Database (Optional)**
1. Export your Spotify playlists as `.csv` files.
2. Place them in a new folder: `finja-everything-in-one/exports/`.
3. Use the web interface later to build the database.

**Step 3: Start Server**
Double-click `start_server.bat`. The server runs as long as the console window stays open.

**Step 4: Open Web Interface**
Open your browser and navigate to: `http://localhost:8022/Musik.html`.

### Using the Web Interface
- **Music Sources:** Choose which source Finja should "listen" to with a button press. For RTL & MDR, start the corresponding "helpers" in the lower section of the page first.
- **DB & Helper Scripts:** Use the tools to build your song database from `.csv` exports, enrich missing song info, or resolve artist conflicts.

### OBS Integration
- **Browser Source:** Add a browser source in OBS and select the appropriate HTML overlay from the `OBSHTML` folder as a local file.
- **Text Sources:** The overlays automatically read data from the `Nowplaying` folder. No path adjustments needed!

---

## 💡 Core Concept: One Brain, Many Ears

The entire system is based on a two-part architecture that applies to every music source:

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

    A & B & C & D --> E --> F --> G --> H
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

## 📂 Project Structure

```plaintext
finja-music/
├── finja-everything-in-one/         # 🚀 Recommended — All-in-One Edition
├── finja-music-docker-spotify/      # 🐳 Docker Edition
└── Not Maintained/
    └── finja-music-standalone/      # ⚠️ Legacy modular system (archived)
```

---

## 📜 License

All modules in this project are licensed under the **MIT License**.

Made with ❤️ by [Sodakiller1](https://twitch.tv/sodakiller1) (J. Apps / JohnV2002)

*Built with 💖, Mate, and a pinch of chaos ✨*

---

## 🆘 Support & Contact

- **Email:** contact@jappshome.de
- **Website:** [jappshome.de](https://jappshome.de)
- **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)