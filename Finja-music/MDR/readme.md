📻 MDR – Vollständiges Musikmodul

(Teil 1: Get Content + Teil 2: Brain)

Dieses Modul sorgt dafür, dass dein System erkennt, welcher Song gerade auf MDR Sachsen-Anhalt läuft,
ihn in Genres einordnet, Reaktionen generiert und sich merkt, was es davon hält 🧠💖

⚡ Ohne dieses Modul denkt das System, dass keine Musik läuft – du brauchst beide Teile, damit es „zuhört“ 🎧

📂 Verzeichnisstruktur

So sieht dein MDR/-Ordner am Ende aus:

MDR/
├─ MDR - Get Content/
│   ├─ mdr_nowplaying.py
│   ├─ start_mdr_nowplaying.bat
│   ├─ NowPlaying_MDR.html
│   ├─ nowplaying.txt
│   ├─ now_source.txt
│   └─ outputs/
│       ├─ obs_genres.txt
│       └─ obs_react.txt
│
└─ MUSIK/
    ├─ Memory/
    │   ├─ memory.json
    │   ├─ contexts.json
    │   └─ reactions.json
    ├─ SongsDB/
    │   └─ songs_kb.json
    ├─ exports/
    ├─ cache/
    ├─ missingsongs/
    ├─ config_mdr.json
    ├─ finja_min_writer.py
    ├─ kb_lookup.py
    ├─ kb_probe.py
    └─ run_finja_MDR.bat

🛰️ Teil 1: Get Content – Songs abrufen

Ziel: Holt den aktuellen Song von MDR Sachsen-Anhalt und schreibt ihn in nowplaying.txt

⚙️ Funktionsweise

Ruft nacheinander drei Quellen ab:

ICY-Metadaten direkt vom Stream

Offizielle XML-Titellisten

Fallback: HTML-Webseite mit der Titelliste

Erkennt Titel nur, wenn sie neu und gültig sind (keine Werbung, keine Nachrichten etc.)

Schreibt Titel + Artist als Titel — Artist in nowplaying.txt

Schreibt gleichzeitig die verwendete Quelle (icy, xml, html) in now_source.txt

💡 Bonus: Du kannst parallel einen MDR-Stream im Browser laufen lassen →
So wirkt es für alle, als ob dein Bot „live zuhört“ 🎧💕

⚙️ Setup & Start

Stelle sicher, dass Python 3.9+ installiert ist

(Optional) Passe Umgebungsvariablen im Script an:

MDR_STREAM_URL

MDR_XML_URL

MDR_HTML_URL

MDR_ICY_FORMAT ("title-first" oder "artist-first")

Starte das Skript mit:

start_mdr_nowplaying.bat


💡 Alternativ direkt:

python mdr_nowplaying.py

⚙️ OBS Overlay

Füge NowPlaying_MDR.html als Browserquelle in OBS hinzu

Größe z. B. 720 × 200 px

Optional Parameter: ?dev=1 für Dev-Mode

Die HTML liest:

nowplaying.txt (Titel/Artist)

now_source.txt (Quelle)

später auch obs_genres.txt & obs_react.txt (vom Brain)

🧠 Teil 2: MUSIK – Songs analysieren

Ziel: Nimmt die Titel aus nowplaying.txt und generiert daraus:

Genre-Tags 🎵

Dynamische Reaktionen ✨

Memory-Einträge 🧠

🧠 Funktionsweise

Liest nowplaying.txt aus Teil 1

Sucht den Song in deiner songs_kb.json

Ermittelt Tags & Spezialversionen (Nightcore, Speed Up …)

Bewertet Songs je nach contexts.json (z. B. bei Minecraft chilliger als bei ETS2)

Speichert die Reaktion in memory.json

Schreibt für OBS:

../MDR - Get Content/outputs/obs_genres.txt

../MDR - Get Content/outputs/obs_react.txt

💡 Setup-Varianten

Du hast zwei Möglichkeiten, wie du das Brain einrichtest:

🅐 Eigenständiger MDR-Betrieb (eigenes Brain)

📝 Möglich, aber nicht empfohlen — besser ist das gemeinsame Brain (siehe 🅑)

Stelle sicher, dass MDR - Get Content/ korrekt läuft

Kopiere folgende Dateien aus TruckersFM/MUSIK/ nach MDR/MUSIK/:

Memory/contexts.json

Memory/reactions.json

build_spotify_kb_only.py

Lege exports/ an und füge deine CSV-Exporte hinzu

Erstelle deine eigene KB:

python build_spotify_kb_only.py


→ Erstellt SongsDB/songs_kb.json

Passe config_mdr.json an:

{
  "input_path": "../MDR - Get Content/nowplaying.txt",
  "fixed_outputs": "../MDR - Get Content/outputs",
  "songs_kb_path": "SongsDB/songs_kb.json",
  "kb_index_cache_path": "cache/kb_index.pkl",

  "reactions": {
    "enabled": true,
    "path": "Memory/reactions.json",
    "context": {
      "enabled": true,
      "path": "Memory/contexts.json"
    }
  },

  "memory": {
    "enabled": true,
    "path": "Memory/memory.json"
  }
}


📌 Ohne diese Dateien:

keine Genres (nur Fallback)

keine echten Reaktionen

keine Memories

🅑 MDR nutzt das TruckersFM-Brain (empfohlen 💖)

Empfehlung: Alle Quellen (TruckersFM, MDR Sachsen-Anhalt, 89.0 RTL, Spotify) sollen dasselbe Brain nutzen

Richte TruckersFM/MUSIK/config_min.json komplett ein

Kopiere sie als config_mdr.json nach MDR/MUSIK/

Passe nur die Input/Output-Pfade an:

{
  "input_path": "../MDR - Get Content/nowplaying.txt",
  "fixed_outputs": "../MDR - Get Content/outputs",

  "songs_kb_path": "../../TruckersFM/MUSIK/SongsDB/songs_kb.json",
  "kb_index_cache_path": "../../TruckersFM/MUSIK/cache/kb_index.pkl",

  "reactions": {
    "enabled": true,
    "path": "../../TruckersFM/MUSIK/Memory/reactions.json",
    "context": {
      "enabled": true,
      "path": "../../TruckersFM/MUSIK/Memory/contexts.json"
    }
  },

  "memory": {
    "enabled": true,
    "path": "../../TruckersFM/MUSIK/Memory/memory.json"
  }
}


📌 Vorteile:

MDR nutzt dieselbe KB, Reactions, Contexts & Memory wie TruckersFM

Neue Erinnerungen & Reaktionen wirken sofort überall

Best Practice: Erst TruckersFM sauber einrichten → dann übernehmen

⚡ Starten

Starte Teil 1:

start_mdr_nowplaying.bat


Starte Teil 2:

run_finja_MDR.bat

📺 OBS-Integration

Browserquelle:
MDR - Get Content/NowPlaying_MDR.html

Textquellen:
MDR - Get Content/outputs/obs_genres.txt
MDR - Get Content/outputs/obs_react.txt

⚡ Wichtige Hinweise

.finja_min_writer.lock schützt vor Doppelstart

Strg+C beendet den Writer sauber und löscht die Lock-Datei

Ohne songs_kb.json → keine Genres

Ohne reactions.json → nur generische Texte

Ohne contexts.json → keine Bias → alles neutral

📜 Lizenz

MIT © 2025 – J. Apps
Built with 💖, Mate & einer Prise Chaos ✨