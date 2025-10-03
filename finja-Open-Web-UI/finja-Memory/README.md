# 📚 Finja Cloud Memory v1.2.0

Ein leichtgewichtiger, blitzschneller und externer **Memory-Service**, der als Langzeitgedächtnis für KI-Projekte wie Finja dient. Dieses System ist für die nahtlose Integration mit **OpenWebUI** über das `adaptive_memory_v4` Plugin konzipiert.

---

## 🚨 Wichtiger Hinweis: Externer Server Zwingend Erforderlich!

Dieses System besteht aus zwei Teilen: dem **Server** (dieses Repository) und dem **Plugin**. Das Plugin funktioniert **NICHT** ohne den hier beschriebenen Memory-Server.

> Bitte folge zuerst der Setup-Anleitung, um den Server via Docker zu starten, bevor du das Plugin in OpenWebUI installierst.

---

## ✨ Features

### Server (`memory-server.py`)
-   **Intelligenter RAM-Cache:** Hält aktive User-Daten im Arbeitsspeicher für blitzschnelle Lesezugriffe und gibt den Speicher nach einer Zeit der Inaktivität automatisch wieder frei.
-   **Persistente Speicherung:** Sichert alle Erinnerungen als portable JSON-Dateien pro Benutzer in einem Docker-Volume.
-   **Voice-Memory-Gerüst:** Bietet API-Endpunkte zur Annahme von Sprachdateien (`/add_voice_memory`) und zum Caching von Sprachausgaben (`/get_or_create_speech`), vorbereitet für STT/TTS-Modelle.
-   **Datenkontrolle:** Enthält einen API-Endpunkt (`/delete_user_memories`), der es dem Plugin ermöglicht, alle Daten eines Benutzers auf Anfrage sicher und vollständig zu löschen.
-   **Sicherheit:** Der Zugriff wird über einen `X-API-Key` in einer `.env`-Datei abgesichert.

### Plugin (`adaptive_memory_v4.py`)
-   **Intelligente Extraktion:** Nutzt konfigurierbare LLMs (z.B. `gpt-4o-mini`), um aus Gesprächen dauerhafte Fakten zu extrahieren und dabei von einmaligen Ereignissen zu generalisieren (z.B. "Ich aß gestern Pizza" -> "User mag Pizza").
-   **Performance & Kosten-Optimierung:**
    -   Ein **"Themen-Cache"** vermeidet unnötige API-Anfragen, solange das Gesprächsthema gleich bleibt.
    -   Eine **lokale Vor-Filterung** reduziert die Anzahl der an OpenAI gesendeten Erinnerungen drastisch.
-   **Robuste Duplikats-Erkennung:** Verwendet eine mehrstufige Prüfung (Cosine Similarity & Levenshtein-Distanz), um doppelte Erinnerungen zu blockieren.
-   **"Local Only"-Modus & Fallback:** Funktioniert dank lokaler Embedding-Modelle auch komplett ohne OpenAI oder als Fallback bei API-Fehlern.
-   **Benutzerfreundlichkeit:**
    -   Ein **Server-Verbindungs-Check** gibt beim Start eine klare Fehlermeldung, falls der Server nicht erreichbar ist.
    -   **Klares User-Feedback** im Chat informiert über alle Aktionen des Plugins.
    -   Eine **Zwei-Stufen-Bestätigung** per Chat-Befehl ermöglicht dem User, die Löschung seiner Daten selbst zu steuern.

---

## 🚀 Setup mit Docker Compose (Empfohlen)

Dies ist die einfachste und sicherste Methode, den Server zu starten.

**1. Konfigurationsdatei erstellen**

Erstelle im Hauptverzeichnis eine `.env`-Datei. Hier werden deine geheimen API-Keys gespeichert.
```ini
# .env
MEMORY_API_KEY="dein-super-sicherer-key-12345"
OPENAI_API_KEY="sk-dein-openai-key-falls-benoetigt" # Ab jetzt Optional :3
```
> ⚠️ **Wichtig:** Füge die `.env`-Datei unbedingt zu deiner `.gitignore`-Datei hinzu, damit deine API-Keys niemals auf GitHub landen!

**2. Server starten**

1.  **Berechtigungen korrigieren (einmalig):** Führe im Projektordner `sudo chown -R $(id -u):$(id -g) .` aus, um Berechtigungsprobleme mit Docker zu vermeiden.
2.  **Container starten:** Führe den folgenden Befehl im Terminal aus:
    ```bash
    docker-compose up -d --build
    ```
    -   `up`: Startet den Service.
    -   `-d`: Startet den Container im Hintergrund (detached mode).
    -   `--build`: Baut das Docker-Image neu, falls es Änderungen gab.

**3. API testen**

Nachdem der Container läuft, kannst du die API testen. Die erwartete Antwort bei einem leeren Server ist `[]`.

-   **Mit PowerShell:**
    ```powershell
    Invoke-WebRequest -Uri "http://localhost:8000/get_memories?user_id=test" -Headers @{"X-API-Key" = "dein-super-sicherer-key-12345"}
    ```
-   **Mit cURL:**
    ```bash
    curl -X GET "http://localhost:8000/get_memories?user_id=test" -H "X-API-Key: dein-super-sicherer-key-12345"
    ```

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