# 📚 **Cloud Memory – README**

Ein leichtgewichtiger, blitzschneller **Memory-Service** für AI-Projekte 🚀  
Speichert Erinnerungen (`memories`) **pro Benutzer** und verbindet sich nahtlos mit **OpenWebUI** via dem `adaptive_memory_v4` Plugin.  

---

## 🛣️ Roadmap
1. **More finetuning** – Weitere Optimierungen der Erkennungslogik & Relevanzfilter.  
2. **More validation** – Strengere Validierung vor dem Senden an OpenAI.  
3. **More logging** – Erweiterte Logs, inkl. der coolen Animationen aus dem alten Script („MEMORY SAVED“ etc.).  
4. **More to come?** – Platz für neue Ideen & Features in der Zukunft.  

---

## 🖥️ 2. SERVER

### 📦 2.1 Dockerfile
Dieses Dockerfile erstellt einen Container, in dem der Memory-Server läuft:  
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY memory_service.py .
RUN pip install fastapi uvicorn pydantic
EXPOSE 8000
CMD ["uvicorn", "memory_service:app", "--host", "0.0.0.0", "--port", "8000"]

# This Dockerfile sets up a FastAPI application for the memory service.
# It uses Python 3.11 on a slim base image, installs necessary dependencies,
# and runs the service on port 8000.
```
💡 **Was macht das?**  
- Lädt ein schlankes Python 3.11 Image  
- Kopiert unseren Memory-Server Code (`memory_service.py`) hinein  
- Installiert **FastAPI**, **Uvicorn**, **Pydantic**  
- Startet den Server auf Port **8000**  

---

### 🗄️ 2.2 `memory-server.py`
Der **Memory-Server**:
- Speichert Erinnerungen als **JSON-Dateien pro Benutzer**  
- Bietet eine **REST-API** an:
  - `/add_memory` – einzelne Erinnerung speichern  
  - `/add_memories` – mehrere Erinnerungen speichern (Batch)  
  - `/get_memories` – Erinnerungen abrufen  
  - `/prune` – alte Einträge löschen  
  - `/backup_now` – sofortiges Backup erstellen  
- Nutzt `X-API-Key` für Sicherheit  
- Läuft extrem ressourcenschonend → ideal für V-Server oder Docker-Container  

---

### 🐳 2.3 Setup per Docker
So startest du den Memory-Server in Docker:

1. **Docker-Image bauen**
   ```bash
   docker build -t memory-server .
   ```
2. **Container starten**
   ```bash
   docker run -d      -p 8000:8000      -v $(pwd)/user_memories:/app/user_memories      -e API_KEY=changeme-supersecretkey      --name memory-server      memory-server
   ```
3. **API testen**
   ```bash
   curl -X POST http://localhost:8000/add_memory -H "X-API-Key: changeme-supersecretkey" -H "Content-Type: application/json" -d '{"user_id": "defualt", "text": "Ich liebe Chatbots"}'
   ```

💡 **Tipp:**  
- Mit `-v` mountest du den Speicherordner aus dem Container auf den Host → einfache Backups  
- Mit `--env` kannst du den API-Key setzen  

---

## 🤖 3. `adaptive_memory_v4` – Das Plugin
Das **OpenWebUI Plugin** verbindet dein LLM mit dem Memory-Server.

### 🔍 Was es macht
- **Holt Erinnerungen** von deinem Memory-Server (`/get_memories`) basierend auf der `user_id`
- **Relevanzprüfung**: OpenAI (oder API-kompatibles Modell) bewertet, ob eine gespeicherte Erinnerung für die aktuelle User-Nachricht relevant ist
- **Kontext-Injektion**: Nur relevante Erinnerungen werden dem LLM als **System-Kontext** vorangestellt
- **Memory-Extraktion**: Erkennt aus neuen Nachrichten **faktische, langfristige Infos** (z. B. Name, Vorlieben) und speichert sie
- **Dedupe**: Kein mehrfaches Speichern derselben Info
- **Guards**: Filtert irrelevante Chat-Nachrichten („Hi“, „Wie geht’s?“) aus

---

### 📋 Funktionsablauf
1. **User schreibt eine Nachricht**  
2. Plugin holt alle bisherigen Memories vom Server  
3. Falls welche relevant sind → werden **in den Kontext eingefügt**  
4. Falls keine relevant sind → **OpenAI-Analyse** → neue Memory extrahieren  
5. **Neue relevante Memory → an den Memory-Server senden**  
6. LLM antwortet selbstständig mit erweitertem Kontext

---

### 📜 Vorteile
- **Persönliche Chats**: KI erinnert sich an Namen, Vorlieben, Gesprächsthemen  
- **Skalierbar**: Mehrere Benutzer, getrennte Erinnerungen  
- **Offline-fähig**: Memory-Server kann lokal oder auf V-Server laufen  
- **Einfache Integration**: Funktioniert mit jedem API-kompatiblen LLM

---
