# 🎨 Finja AI Pixel Canvas v1.2.0

An experimental headless AI pixel art project within the **Finja AI Ecosystem**. Multiple free AI models from OpenRouter (like Gemma and Nemotron) collaborate in a continuous loop to design, place, and paint motifs on a shared 64x64 grid—pixel by pixel.

**Note:** This module operates independently and does not yet communicate directly with the main Finja brain, but integration is planned for the future.

**Changes (v1.2.0):** Finja Canvas reports to the Analytics Collector and Flare (structured `FINJA-104/515/516` errors, CPU and RAM), can run with the painter switched off (`CANVAS_PAINTER_ENABLED=false`, no Recraft credit used), and the container now really resets a full canvas instead of stopping.

**Changes (v1.1.0):** Recraft V4.1 Vector is now the default motif artist. Its transparent SVG motifs are rasterized into canvas pixels and painted over time.

---

## ✨ Features

- **Autonomous AI Painting**: The AI chooses a category and motif; Recraft V4.1 Vector designs it as SVG, which is converted to pixels and slowly painted onto the canvas.
- **Collage Effect**: The AI uses collision detection to place new motifs next to existing ones, resulting in a dense "r/place" style collage instead of just one big drawing.
- **Round-Robin Multi-Model Engine**: Uses an intelligent model chain (via OpenRouter) with built-in fallbacks. It routes around rate-limits and slow reasoning models automatically.
- **Live Frontend**: The `index.html` file serves as a live dashboard that polls the painted pixels in real-time, giving a cool glow effect to the canvas.
- **Auto-Snapshotting**: Once a motif is fully colored, it renders a high-quality PNG snippet to the `gallery/` folder. When the canvas is full, a final masterpiece is saved, and the canvas starts fresh.

---

## 📁 Project Structure

| File | Description |
|------|-------------|
| `painter.py` | The main loop that paints one pixel every interval. |
| `ai_client.py` | OpenRouter API logic with robust fallback models. |
| `plan_drawing.py` | Asks the AI for a motif idea and color palette. |
| `shape_template.py` | Prompts the AI for coordinates and handles canvas placement. |
| `render.py` | Saves snapshots of completed motifs to the `gallery/`. |
| `server.py` | A simple HTTP server to serve the frontend without caching. |
| `reset_canvas.py` | Utility script to manually wipe the canvas and AI plans. |
| `index.html` | The live dashboard frontend. |
| `canvas_stats.py` | Small canvas statistics behind the owner-only diagnostics probe. |
| `core/exceptions.py` | Structured errors (FINJA namespace, module finja-canvas). |
| `analytics_sender.py` | Analytics Contract sender (off unless `ANALYTICS_ENABLED=true`). |

---

## 🚀 Setup & Installation

### 1. Configure Environment
```bash
cp .env.example .env
```
Edit `.env` and add your **OpenRouter API Key**.

### 2. Start the Docker Container
The container uses `docker-compose.yml` to mount the `data/` volume so your canvas state persists between restarts.

```bash
docker compose up -d --build
```
This will automatically:
1. Start the HTTP server on port **7676**.
2. Run the painter loop in the background.

### 3. Watch it Paint
Open your browser and navigate to:
[http://localhost:7676](http://localhost:7676)

You will see the pixels appear one by one as the AI executes its plan.

---

## 🔥 Flare & Analytics (optional)

Everything here is **off by default**; the canvas runs without any backend.

| Setting (`.env`) | Meaning |
|------------------|---------|
| `CANVAS_PAINTER_ENABLED` | `false` serves only the canvas page: no OpenRouter key needed, no Recraft credit used. |
| `CANVAS_BIND` | Address port 7676 listens on (loopback by default; the host's LAN address for OBS). |
| `ANALYTICS_ENABLED`, `ANALYTICS_ENDPOINT`, `ANALYTICS_TOKEN` | Send errors, CPU and RAM to the Analytics Collector, which hands repeated errors to Flare. |
| `CANVAS_PROBE_TOKEN` | Enables the owner-only `/diagnostics/probe?token=…` route (empty = off). |

The compose file joins the external Docker network `flare-finja-private` (shared with the Analytics Collector and Flare); create it once with `docker network create flare-finja-private`.

Errors: `FINJA-104` missing OpenRouter key (Flare asks a person instead of repairing), `FINJA-515` an unexpected painter failure (the painter stops as before), `FINJA-516` the diagnostics probe.

Tests: `python -m pytest` (all) or `python -m unittest discover -s tests -t tests` (what Flare's sandbox runs).

---

## 🧰 Troubleshooting & Tips

| Problem | Solution |
|---------|----------|
| **AI is stuck or not painting** | Check the logs: `docker compose logs -f finja-canvas`. Usually means models are rate-limited or the API key is missing. |
| **I want to reset the canvas manually** | You can run `docker compose exec finja-canvas python reset_canvas.py`. This clears the canvas, colors, and AI plans. |
| **I want the AI to skip to a new motif** | Run `docker compose exec finja-canvas python new_motif.py`. It will stop painting the current one and plan a new one in the next interval. |
| **Where are the finished pictures?** | Check the `gallery/` directory. **Tip:** There's an example image stored there so you can see what a finished AI creation looks like! :3 |

---

## 📜 License

MIT License © 2026 J. Apps

## 🆘 Support & Contact

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)
