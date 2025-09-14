# 📚 Finja Cloud Memory

Ein leichtgewichtiger, blitzschneller **Memory-Service** für Finja & AI-Projekte 🚀  
Speichert Erinnerungen (`memories`) **pro Benutzer** und verbindet sich nahtlos mit **OpenWebUI** via dem `adaptive_memory_v4` Plugin.

---

## 🛣️ Roadmap

[➡️ **Unsere vollständige und aktuelle Roadmap findest du hier in der `ROADMAP.md`**](./ROADMAP.md)

Hier ist ein kurzer Auszug der aktuellen Planung:

> -   [ ] **Feinabstimmung:** Weitere Optimierungen der Erkennungslogik & Relevanzfilter.
> -   [ ] **Validierung:** Strengere Überprüfung der extrahierten Fakten vor dem Speichern.
> -   [ ] **Logging:** Erweiterte Logs, inklusive der coolen Terminal-Animationen aus früheren Versionen.
> -   [ ] **Zukünftige Ideen:** Platz für neue Features.


## 🖥️ Der Memory-Server

Der Kern des Systems ist ein kleiner, in Python geschriebener Server, der die Erinnerungen verwaltet.

### Dockerfile

Das `Dockerfile` beschreibt, wie unser Docker-Image gebaut wird.

```dockerfile
FROM python:3.11-slim
WORKDIR /app

# Installiere Abhängigkeiten inkl. python-dotenv
RUN pip install fastapi uvicorn pydantic python-dotenv

# Kopiere Server-Code und .env Datei
COPY memory-server.py .
COPY .env .  # Wichtig: .env für Konfiguration

EXPOSE 8000
CMD ["uvicorn", "memory-server:app", "--host", "0.0.0.0", "--port", "8000"]
```

-   **Was es macht:** Es nutzt ein schlankes Python 3.11 Image, installiert die nötigen Bibliotheken (`FastAPI`, `Uvicorn`, `Pydantic`, `python-dotenv`), kopiert den Code und startet den Server auf Port `8000`.

### `memory-server.py`

Der eigentliche Server-Code bietet eine REST-API mit folgenden Funktionen:

-   Speichert Erinnerungen als **JSON-Dateien pro Benutzer**.
-   Bietet Endpunkte zum Hinzufügen, Abrufen, Löschen und Sichern von Erinnerungen.
-   Sichert den Zugriff über einen `X-API-Key` ab.
-   Läuft extrem ressourcenschonend und ist ideal für kleine V-Server oder Docker-Umgebungen.

### Konfiguration via `.env`

Erstelle eine `.env`-Datei im Hauptverzeichnis des Projekts, um den Server zu konfigurieren.

```bash
# .env Datei
MEMORY_API_KEY=dein-super-sicherer-api-key-hier
# Optional: Weitere Einstellungen
# MAX_RAM_MEMORIES=5000
# BACKUP_INTERVAL=600
```
Für die Entwicklung kannst du eine `.env.example`-Datei bereitstellen, um die benötigten Variablen zu zeigen.

### Setup mit Docker

Folge diesen Schritten, um den Server zu starten:

**1. `.env`-Datei erstellen**
```bash
echo "MEMORY_API_KEY=dein-super-sicherer-production-key-12345" > .env
```

**2. Docker-Image bauen**
```bash
docker build -t finja-memory-server .
```

**3. Container starten**
Du hast zwei Möglichkeiten, den API-Key an den Container zu übergeben:

**Option A (für Entwicklung):** Die `.env`-Datei wird direkt in den Container kopiert.
```bash
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/user_memories:/app/user_memories \
  --name finja-memory-server \
  finja-memory-server
```

**Option B (sicherer für Produktion):** Der Key wird als Umgebungsvariable übergeben.
```bash
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/user_memories:/app/user_memories \
  -e MEMORY_API_KEY="dein-production-key" \
  --name finja-memory-server \
  finja-memory-server
```
**Tipp:** Mit `-v` bindest du den Ordner `user_memories` an deinen Host. So bleiben die Daten auch nach einem Löschen des Containers erhalten und sind leicht zu sichern.

**4. API testen**
```bash
curl -X GET "http://localhost:8000/get_memories?user_id=test" \
  -H "X-API-Key: dein-super-sicherer-production-key-12345"
```

---

## 🤖 Das OpenWebUI Plugin: `adaptive_memory_v4`

Das Plugin ist die Brücke zwischen OpenWebUI und deinem Memory-Server.

### Was es macht

-   **Erinnerungen abrufen:** Holt vor jeder Antwort die relevanten Erinnerungen vom Memory-Server.
-   **Relevanzprüfung:** Ein LLM (z.B. OpenAI) bewertet, ob gespeicherte Fakten zur aktuellen Frage des Nutzers passen.
-   **Kontext-Injektion:** Nur die als relevant markierten Erinnerungen werden dem System-Prompt hinzugefügt, sodass die KI "sich erinnert".
-   **Erinnerungen extrahieren:** Erkennt und speichert neue, langfristig relevante Fakten aus den Antworten des Nutzers (z.B. Name, Hobbys, Vorlieben).
-   **Filter:** Ignoriert irrelevante Nachrichten (z.B. "Hallo", "Wie geht's?") und verhindert doppelte Einträge.

### Vorteile

-   **Personalisierte Gespräche:** Die KI kann sich an Details aus früheren Chats erinnern.
-   **Skalierbar:** Trennt die Erinnerungen für jeden Benutzer sauber.
-   **Flexibel:** Der Memory-Server kann lokal oder auf einem externen Server laufen.

---

## ⚠️ Sicherheitshinweise

### API Key Management

-   Schreibe API-Keys **niemals** direkt in den Code.
-   Füge deine `.env`-Datei zur `.gitignore`-Datei hinzu, um ein versehentliches Hochladen zu verhindern.
-   Nutze für die Produktion immer Umgebungsvariablen (Option B beim Docker-Start).
-   Wechsle deine Keys regelmäßig.

### `.gitignore` Eintrag
```gitignore
# .gitignore
.env
*.env.local
user_memories/
__pycache__/
```

---

## 🚀 Deployment (Produktion)

Ein Beispiel für einen sichereren Startbefehl in einer Produktionsumgebung:

```bash
docker run -d \
  -p 8000:8000 \
  -v /pfad/zum/speicherort:/app/user_memories \
  -e MEMORY_API_KEY="$(cat /pfad/zu/secrets/memory-api-key)" \
  --restart unless-stopped \
  --name finja-memory-server \
  finja-memory-server
```

---

## 💖 Credits & Lizenz

Ein großes Dankeschön geht an **gramanoid (aka diligent_chooser)**, dessen Arbeit die Inspiration für dieses Projekt war.

-   [Original Reddit-Post](https://www.reddit.com/r/OpenWebUI/comments/1kd0s49/adaptive_memory_v30_openwebui_plugin/)
-   [Open WebUI Plugin-Seite](https://openwebui.com/f/alexgrama7/adaptive_memory_v2)

Dieses Projekt steht unter der **[Apache License 2.0](./LICENSE)**.  
Copyright © 2025 J. Apps

> ⚠️ **Hinweis:** Die Lizenz gilt nur für dieses Memory-Projekt. Alle anderen Module des Finja-Ökosystems bleiben unter der MIT-Lizenz.

![Berechtigungs-Screenshot](https://github.com/JohnV2002/Finja-AI-Ecosystem/blob/main/assets/Screenshot2025-09-12.png)

---

## 🆘 Support & Kontakt

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)

---

**Viel Erfolg mit deinem Memory-Server!** 🚀✨