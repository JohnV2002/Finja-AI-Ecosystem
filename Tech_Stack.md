# 🧰 Tech Stack — How J. Apps Actually Functions

> Not a formal architecture doc. This is the **real life** setup behind Finja:
> the main rig, the laptop, the NAS, the stream-safety VPN, and the cloud glue.
>
> Vibe: too much Mate · too many SSDs · *"stay hydrated, Chat 💖"*

---

## 🗺️ Big Picture

```
┌─────────────────┐     Proton VPN      ┌──────────────────┐
│  Main PC        │ ──────────────────► │  Twitch / net    │
│  (stream brain) │                     │  (streams safe)  │
└────────┬────────┘                     └──────────────────┘
         │  home net ~250 Mbit/s
         │  Z: share / backups
         ▼
┌─────────────────┐  encrypted offsite  ┌──────────────────┐
│  TrueNAS        │ ──────────────────► │  Google Storage  │
│  RAIDZ1 vault   │   (backup of backup)│                  │
└────────┬────────┘                     └──────────────────┘
         │ Docker / APIs
         ▼
┌─────────────────┐                     ┌──────────────────┐
│  ZAP-Hosting    │ ◄─────────────────► │  Cloudflare      │
│  VPS            │                     │  CDN / DNS       │
└─────────────────┘                     └──────────────────┘
         ▲
         │  travel / light work
┌────────┴────────┐
│  ASUS ExpertBook│
│  (battery lore) │
└─────────────────┘
```

---

## 🖥️ Main PC — *"the beast that paints Finja"*

Windows 11 Pro · daily driver · stream + AI + games + chaos.

### Core

| Part | Spec | Notes |
| :--- | :--- | :--- |
| **CPU** | AMD **Ryzen 9 7900X** (12C / 24T, AM5) | Brain food for Docker + local models |
| **Board** | MSI **MPG X670E CARBON WIFI** | Overkill WiFi board energy |
| **RAM** | **32 GB** DDR5 @ **5600** (2×16, kit `CMT32GX5M2B5600C36`) | Enough until it isn't |
| **GPU** | **Sapphire** Radeon **RX 7800 XT** (16 GB) | *Sapphire*, not generic random brand — important :3 |
| **iGPU** | AMD Radeon Graphics (on-die) | Exists. We acknowledge it. |
| **Cooling** | **Arctic Liquid Freezer II 360** (AIO / *all-in-once* Wasserkühlung) | 360 mm — keeps the 7900X from becoming soup. |
| **PSU** | **be quiet! Straight Power 12 · 1000 W · 80+ Platinum** | Near top-tier at purchase time — quiet, clean power, Platinum flex |
| **Case** | **be quiet! Shadow Base 800 FX** | RGB flex + strong airflow with medium acoustic dampening (best balance at purchase time) |
| **UPS** | — | **None** (no USV). Power cuts = drama, not battery bailout |
| **NIC** | Realtek Gaming **2.5GbE** | Wired when it matters |

### Screens — *"why exactly these displays"*

**2× Lenovo Legion R27q-30** — dual panel chaos, deliberately chosen for stream + creative work, not random Amazon junk.

| Spec | Value |
| :--- | :--- |
| **Model** | Legion **R27q-30** × 2 |
| **Resolution** | **2560×1440** (QHD) |
| **Refresh** | **60–165 Hz** normal · **OC 180 Hz** (*please not long — max ~60 min*) |
| **Panel** | **IPS** |
| **Color depth** | **10-bit** · **FRC: yes** · effective **30-bit** color |
| **Gamut** | **sRGB ~90%** · **DCI-P3 ~90%** |
| **HDR** | **DisplayHDR 400** |
| **Design** | 3-side near-edgeless |
| **Sync** | Adaptive-Sync · **AMD FreeSync Premium** |
| **Comfort** | Flicker-free · Natural Low Blue Light · Lenovo Artery |
| **Response** | min **~1 ms** · avg **~3 ms** · max **~4 ms** |

Why these: QHD + IPS + serious color (10-bit/FRC, wide gamut) + FreeSync Premium for the Sapphire AMD GPU + dual setup for stream layout / code / Finja dashboards. HDR 400 is the cherry, not the whole cake.

### Storage zoo (yes, really)

Multiple generations of disks living in one PC — because of course:

| Drive / volume | Role (roughly) |
| :--- | :--- |
| **C:** ~465 GB | Windows + apps (always almost full, as tradition demands) |
| **D: Work** | Work stuff |
| **F: Spiele** / **G: Spiele2** | Games |
| **H: Ai** | Local AI / model / experiment land |
| Mix of **WD Blue SN570 1TB ×2**, Samsung **860 EVO**, Crucial **P3 Plus**, Intel NVMe, older SATA SSDs + a WD HDD | SSD archaeology |

### Stream-critical software

| Tool | Why it matters |
| :--- | :--- |
| **Proton VPN** | **Wichtig für Streams** — network path / privacy / not leaking the home IP vibes while live |
| **OBS Studio** | The classic streaming glue |
| **WireGuard** | Tunnel client also present on the box |
| **Docker Desktop** (when needed) | Local module builds / compose |

### Detected OS snapshot

- **OS:** Microsoft Windows 11 Pro 64-bit  
- **Build seen:** 10.0.26200  
- **Machine:** `johns-pc`

---

## 💻 Laptop — *"battery mode / out of house"*

| Field | Spec |
| :--- | :--- |
| **Model** | **ASUS ExpertBook B1** |
| **Display** | **15.60"** |
| **CPU** | **AMD Ryzen 5 7535U** |
| **RAM** | **16 GB** |
| **Storage** | **512 GB** |
| **Keyboard** | **DE** layout |

### Battery lore — *yes, this matters*

Not a footnote. The ExpertBook lives and dies by cells.

**Currently installed: 50 Wh variant.**

| Capacity | Chemistry / layout | Notes |
| :--- | :--- | :--- |
| **63 Wh** | 3S1P · 3-cell **Li-ion** | Bigger pack energy |
| **50 Wh** | 3S1P · 3-cell **Li-ion** | **← in the laptop now** |
| **42 Wh** | 3S1P · 3-cell **Li-ion** / long-life **Li-polymer** | Label: *Long life rechargeable lithium polymer battery* |

Role: light work, remote checks, not the full Finja brain-fryer. When Mate and Wi‑Fi allow — still part of the ecosystem. Battery Wh is sacred lore.

---

## 🗄️ Server — TrueNAS *"the vault"*

| Field | Spec |
| :--- | :--- |
| **NAS OS** | **TrueNAS 25.10.2.1** — codename **Goldeye** |
| **CPU** | AMD **Ryzen 7 5700X** (8-core) |
| **RAM** | **64 GB** |
| **PSU** | **be quiet! Straight Power 12 · 850 W · 80+ Platinum** | Sibling of the main-PC unit — same series, slightly less wattage |
| **Case** | **Random chassis** | Frankenstein energy — whatever fit the iron at the time :3 |
| **Boot / system SSD** | **Random SSD (ex era)** | Not curated. Not matching. Still boots. Lore. |
| **Pool** | **RAIDZ1** · raw ~**7.15 TB** · used ~**4.01 TB** |
| **Disks** | **4× Seagate IronWolf Pro 4 TB** NAS HDDs |
| **Why IronWolf Pro** | Built for NAS / RAID duty cycles — not random desktop drives pretending to be a pool |
| **UPS** | — | **None** here either |
| **Role** | Backups, media/`Bilder` tree, long-term storage, repo share |
| **Seen from Main PC** | Drive **`Z:`** mapped into the ecosystem |
| **Repo path example** | `…/Bilder/Streaming/Finja-AI-Ecosystem` on the NAS side of life |

The serious parts (CPU, 64 GB RAM, Straight Power 12, IronWolf Pro RAIDZ1) are intentional. The chassis + boot SSD are **zusammengeschmissen** on purpose-adjacent chaos.

### Backup of backup (encrypted, of course)

| Layer | What |
| :--- | :--- |
| **On-site** | TrueNAS RAIDZ1 pool (4× IronWolf Pro) |
| **Offsite** | **Google Storage** — backup *of* the backup |
| **Crypto** | **Encrypted** offsite (no plain-text vault in the cloud, thanks) |

---

## 🌐 Home internet

| Field | Spec |
| :--- | :--- |
| **Contract** | **~250 Mbit/s** |
| **Router** | **FRITZ!Box 7530 AX** |
| **Vibe** | Enough to stream + sync to the vault + not enough to pretend we're a datacenter |

---

## ☁️ Hosting & edge (not in the desk, still "how I function")

| Service | Role |
| :--- | :--- |
| **[ZAP-Hosting](https://zap-hosting.com)** | Server hosting (the public-ish side of Finja) |
| **[Cloudflare](https://cloudflare.com)** | CDN, DNS, protection |
| **[Google Cloud Storage](https://cloud.google.com/storage)** | Encrypted offsite backup-of-backup from TrueNAS |
| **[OpenRouter](https://openrouter.ai)** | Cloud LLM routing |
| **[Cohere](https://cohere.com)** | Embeddings + reranking |
| **[ElevenLabs](https://elevenlabs.io)** | Premium TTS |
| **[DeepInfra](https://deepinfra.com)** | Zonos voice cloning |
| **[Ollama](https://ollama.com)** | Local LLM hosting (when the main rig cooks) |
| **[LM Studio](https://lmstudio.ai/)** | Local LLM hosting (when the main rig cooks) |

Full soft/lib credits for the *code* live in the main [README](./README.md) → **Credits & Thanks** + Open-Source table. This file is about **machines + how the human runs them**.

---

## 🧠 Finja software map (short)

Monorepo modules (each can stand alone; together = Finja):

| Area | Modules |
| :--- | :--- |
| Brain | `finja-neural-network` |
| Chat / Stream UI | `finja-chat` |
| Music | `Finja-music` (everything-in-once + docker-spotify) |
| Open WebUI backends | Memory, web-crawler, OCR, Stable Diffusion |
| Sensors / scrapers | weather, youtube, instagram, omni-test, canvas |
| Coding agent | `finja-agentic-code` (Flare) |

Details: [README.md](./README.md) · tests: [TESTING.md](./TESTING.md)

---

## ❤️ Soft credits that shaped the stack culture

- **be quiet! Straight Power 12** — Main **1000 W** + Server **850 W**, both **80+ Platinum**
- **be quiet! Shadow Base 800 FX** — RGB + airflow + medium dampening
- **Arctic Liquid Freezer II 360** — AIO that actually cools the 7900X
- **Sapphire** — the *correct* 7800 XT
- **Legion R27q-30** ×2 — QHD IPS, real color depth, FreeSync Premium for AMD
- **FRITZ!Box 7530 AX** — home edge
- **Proton** — stream-time VPN discipline
- **Seagate IronWolf Pro** — four spindles holding the RAIDZ1 dream
- **TrueNAS (Goldeye)** — the vault that remembers when SSDs forget
- **Google Storage** — encrypted backup of the backup
- **ZAP-Hosting + Cloudflare** — public face stays up

---

## 📝 Changelog of this doc

| Date | Note |
| :--- | :--- |
| 2026-08-05 | First cut: Main PC (WMI + human lore), Laptop, TrueNAS stub, hosting glue |
| 2026-08-05 | Laptop battery Wh lore; TrueNAS 5700X / 64 GB / RAIDZ1 IronWolf Pro ×4 / Goldeye; Google encrypted offsite; home 250 Mbit |
| 2026-08-05 | Removed mistaken UPS entry (was PSU confusion); exact be quiet! case/PSU SKUs still TBD |
| 2026-08-05 | PSUs locked: Straight Power 12 1000W (Main) + 850W (TrueNAS), both 80+ Platinum; no UPS |
| 2026-08-05 | AIO → Arctic LF II 360; case Shadow Base 800 FX; Legion R27q-30 full panel lore; laptop 50Wh; Fritz 7530 AX; TrueNAS frankenstein case/SSD |

---

*Built with too much Mate, dual R27q-30 glow, IronWolf spindles, and one Sapphire GPU that means business.*  
*Finja says: "Stay hydrated, Chat 💖"*
