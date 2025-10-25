# 📚 Finja Cloud Memory v1.3.1

Ein leichtgewichtiger, blitzschneller und externer **Memory-Service**, der als Langzeitgedächtnis für KI-Projekte wie Finja dient. Dieses System ist für die nahtlose Integration mit **OpenWebUI** über das `adaptive_memory_v4` Plugin konzipiert.

---

## 🚨 Wichtiger Hinweis: Externer Server Zwingend Erforderlich!

Dieses System besteht aus zwei Teilen: dem **Server** (dieses Repository) und dem **Plugin**. Das Plugin funktioniert **NICHT** ohne den hier beschriebenen Memory-Server.

> Bitte folge zuerst der Setup-Anleitung, um den Server via Docker zu starten, bevor du das Plugin in OpenWebUI installierst.

---

## ✨ Features

### Server (`memory-server.py` - v1.3.1)
-   **Intelligenter RAM-Cache:** Hält aktive User-Daten im Arbeitsspeicher für blitzschnelle Lesezugriffe und gibt den Speicher nach einer Zeit der Inaktivität automatisch wieder frei.
-   **Persistente Speicherung:** Sichert alle Erinnerungen als portable JSON-Dateien pro Benutzer in einem Docker-Volume.
-   **Voice-Memory-Gerüst:** Bietet API-Endpunkte zur Annahme von Sprachdateien (`/add_voice_memory`) und zum Caching von Sprachausgaben (`/get_or_create_speech`), vorbereitet für STT/TTS-Modelle.
-   **Datenkontrolle:** Enthält einen API-Endpunkt (`/delete_user_memories`), der es dem Plugin ermöglicht, alle Daten eines Benutzers auf Anfrage sicher und vollständig zu löschen.
-   **Sicherheit:** Der Zugriff wird über einen `X-API-Key` in einer `.env`-Datei abgesichert.
-   **Backup-Endpunkte:** Enthält `/backup_all_now` (Admin) zum Sichern aller Daten und `/backup_now` (Platzhalter für User-Backups).

### Plugin (`adaptive_memory_v4.py` - v4.3.11)
-   **Flexible Provider-Wahl:**
    -   **Extraktion:** Wähle zwischen OpenAI (`openai`) und einem lokalen LLM (`local`, z.B. Ollama).
    -   **Relevanz:** Wähle zwischen OpenAI (`openai`), lokalem LLM (`local`) oder rein lokalen Embeddings (`embedding`).
    -   **Lokale Embeddings:** Wähle zwischen der `sentence-transformers`-Bibliothek (`sentence_transformer`) oder der Ollama Embeddings API (`ollama`).
-   **Intelligente Extraktion:** Nutzt den konfigurierten LLM, um aus Gesprächen dauerhafte Fakten zu extrahieren und dabei von einmaligen Ereignissen zu generalisieren.
-   **Performance & Kosten-Optimierung:**
    -   Ein **"Themen-Cache"** vermeidet unnötige API-Anfragen, solange das Gesprächsthema gleich bleibt (nutzt lokale Embeddings).
    -   Eine **lokale Vor-Filterung** (nutzt lokale Embeddings) reduziert die Anzahl der an den LLM für die Relevanzprüfung gesendeten Erinnerungen drastisch.
-   **Robuste Duplikats-Erkennung:** Verwendet eine mehrstufige Prüfung (Cosine Similarity via OpenAI oder lokalem Embedding & Levenshtein-Distanz), um doppelte Erinnerungen zu blockieren.
-   **Fallback-System:** Nutzt lokale Embeddings als Fallback für Relevanz/Deduplikation, wenn der ausgewählte LLM-Provider fehlschlägt.
-   **Benutzerfreundlichkeit:**
    -   Ein **Server-Verbindungs-Check** gibt beim Start eine klare Fehlermeldung, falls der Server nicht erreichbar ist.
    -   **Klares User-Feedback** im Chat informiert über alle Aktionen des Plugins.
    -   Eine **Zwei-Stufen-Bestätigung** per Chat-Befehl ermöglicht dem User, die Löschung seiner Daten selbst zu steuern.
-   **Stabilität:** Enthält diverse Bugfixes für Fehlerbehandlung, Provider-Logik und Statusmeldungen.

---

## 🚀 Setup mit Docker Compose (Empfohlen)

Dies ist die einfachste und sicherste Methode, den Server zu starten.

### 1. Konfigurationsdatei erstellen
Erstelle im Hauptverzeichnis eine `.env`-Datei. Hier werden deine geheimen API-Keys gespeichert.

```ini
# .env
MEMORY_API_KEY="dein-super-sicherer-key-12345"
# OPENAI_API_KEY="sk-dein-openai-key" # Optional, nur wenn OpenAI als Provider genutzt wird
```
> ⚠️ **Wichtig:** Füge die `.env`-Datei unbedingt zu deiner `.gitignore`-Datei hinzu, damit deine API-Keys niemals auf GitHub landen!

### 2. Server starten
1.  **Berechtigungen korrigieren (einmalig):** Führe im Projektordner `sudo chown -R $(id -u):$(id -g) .` aus, um Berechtigungsprobleme mit Docker zu vermeiden.
2.  **Container starten:** Führe den folgenden Befehl im Terminal aus:
    ```bash
    docker-compose up -d --build
    ```
    -   `up`: Startet den Service.
    -   `-d`: Startet den Container im Hintergrund (detached mode).
    -   `--build`: Baut das Docker-Image neu, falls es Änderungen gab.

### 3. API testen
Nachdem der Container läuft, kannst du die API testen. Die erwartete Antwort bei einem leeren Server ist `[]`.

**Mit PowerShell:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/get_memories?user_id=test" -Headers @{"X-API-Key" = "dein-super-sicherer-key-12345"}
```

**Mit cURL:**
```bash
curl -X GET "http://localhost:8000/get_memories?user_id=test" -H "X-API-Key: dein-super-sicherer-key-12345"
```

---

## ⚙️ Plugin Konfiguration (Valves)

Die wichtigsten Einstellungen für das `adaptive_memory_v4.py` Plugin findest du direkt in der `Valves`-Klasse im Code. Passe diese nach Bedarf an:

-   `extraction_provider`: Wähle "openai" oder "local".
-   `relevance_provider`: Wähle "openai", "local" oder "embedding".
-   `openai_...`: Einstellungen für die OpenAI API (Key wird nur benötigt, wenn OpenAI als Provider gewählt ist).
-   `local_llm_...`: Einstellungen für deinen lokalen LLM (z.B. Ollama Chat API).
-   `local_embedding_provider`: Wähle "sentence_transformer" oder "ollama".
-   `sentence_transformer_model`: Modell für die `sentence-transformers` Bibliothek.
-   `ollama_embedding_...`: Einstellungen für die Ollama Embeddings API.
-   `memory_api_base`, `memory_api_key`: Verbindung zum Memory Server.
-   *...und weitere Thresholds und Filter.*

---

## 🛣️ Roadmap

Die vollständige und aktuelle Roadmap wird jetzt in der Datei `ROADMAP.md` gepflegt, um diese README übersichtlich zu halten.

[➡️ **Zur vollständigen Roadmap (ROADMAP.md)**](./ROADMAP.md)

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