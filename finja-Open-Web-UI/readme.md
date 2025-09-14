# 🤖 Finja AI Ecosystem for OpenWebUI

Willkommen zum Finja AI Ecosystem! 💖

Dieses Projekt ist eine Sammlung von modularen, Docker-basierten Microservices, die entwickelt wurden, um **[OpenWebUI](https://openwebui.com/)** zu erweitern und eine reichhaltigere, interaktivere KI-Erfahrung zu schaffen. Jedes Modul ist ein eigenständiger Baustein, der eine spezifische Fähigkeit wie Gedächtnis, Websuche oder Bilderzeugung hinzufügt.

---

## ✨ Das Ökosystem im Überblick

Alle Module sind so konzipiert, dass sie nahtlos mit OpenWebUI zusammenarbeiten und einfach per Docker und Docker Compose bereitgestellt werden können.

| Modul | Beschreibung | Status |
| :--- | :--- | :--- |
| 🧠 **Cloud Memory** | Speichert Langzeit-Erinnerungen pro Nutzer für persönliche Gespräche. | ✅ Einsatzbereit |
| 📄 **OCR Service** | Extrahiert Text aus hochgeladenen Dokumenten und Bildern (PDFs, JPGs etc.). | ✅ Einsatzbereit |
| 🎨 **Image Generation** | Generiert Bilder lokal auf deiner eigenen Hardware via Stable Diffusion. | ✅ Einsatzbereit |
| 🌐 **Web Crawler** | Führt anonyme Websuchen durch, um der KI aktuelle Informationen zu liefern. | ✅ Einsatzbereit |
| 🗣️ **Text-to-Speech (TTS)** | Wandelt Textantworten der KI in gesprochene Sprache um. | 🚧 In Planung |

---

## 📦 Die Module im Detail

Jedes Modul befindet sich in einem eigenen Unterordner und enthält eine detaillierte `README.md` mit spezifischen Setup-Anweisungen.

### 🧠 Finja Cloud Memory
Dieses Modul stellt einen leichtgewichtigen Server bereit, der es der KI ermöglicht, sich an Fakten und Details aus früheren Gesprächen zu erinnern. Es ist die Grundlage für eine personalisierte Interaktion.

-   **Hauptmerkmale:** Speichert Erinnerungen als JSON pro Benutzer, bietet eine sichere REST-API und integriert sich in das `adaptive_memory_v4` Plugin von OpenWebUI.
-   **Technologie:** FastAPI, Python, Docker.

[➡️ **Zur ausführlichen Anleitung & Setup für das Memory-Modul...**](./finja-cloud-memory/README.md)

### 📄 OCR-Service mit Apache Tika
Ermöglicht es deiner KI, den Inhalt von Dokumenten zu "lesen". Lade eine PDF, ein Bild oder eine Office-Datei hoch, und dieses Modul extrahiert den Text, damit das LLM ihn verarbeiten kann.

-   **Hauptmerkmale:** Nutzt Apache Tika und Tesseract-OCR für eine breite Formatunterstützung, läuft isoliert in Docker und ist für Deutsch und Englisch vorkonfiguriert.
-   **Technologie:** Apache Tika, Tesseract, Docker.

[➡️ **Zur ausführlichen Anleitung & Setup für den OCR-Service...**](./tika-ocr-service/README.md)

### 🎨 Image Generation mit Stable Diffusion
Gib deiner KI die Fähigkeit, Bilder zu malen! Dieses Modul betreibt eine lokale Instanz der beliebten Automatic1111 WebUI und ermöglicht die Text-zu-Bild-Generierung direkt aus dem Chat.

-   **Hauptmerkmale:** Läuft komplett lokal (CPU-fokussiert), speichert generierte Bilder dauerhaft und ist vollständig mit der OpenWebUI-Bilderzeugungsfunktion kompatibel.
-   **Technologie:** Stable Diffusion (Automatic1111), Docker.

[➡️ **Zur ausführlichen Anleitung & Setup für die Image Generation...**](./stable-diffusion-cpu/README.md)

### 🌐 Web Crawler
Mit diesem Modul kann deine KI auf aktuelle Informationen aus dem Internet zugreifen. Es führt Suchanfragen anonym über Tor durch und liefert saubere Ergebnisse zurück.

-   **Hauptmerkmale:** Hybrid-Suche über DuckDuckGo mit Google-Fallback, Anonymisierung via Tor, Schutz per Bearer-Token.
-   **Technologie:** FastAPI, Python, Tor, Docker.

[➡️ **Zur ausführlichen Anleitung & Setup für den Web Crawler...**](./finja-web-crawler/README.md)

### 🗣️ Text-to-Speech (TTS) - In Planung!
Dieses Modul wird es Finja ermöglichen, ihre Antworten laut auszusprechen. Es ist derzeit noch in der Konzeptionsphase.

-   **Hauptmerkmale (geplant):** Anbindung an OpenWebUI, um Textantworten in eine Audiodatei umzuwandeln und im Frontend abzuspielen.
-   **Status:** Work in Progress. Die `README.md` im Ordner ist aktuell ein Platzhalter.

[➡️ **Zur Platzhalter-README für das TTS-Modul...**](./finja-tts-service/README.md)

---

## 📜 Lizenzen

Dieses Projekt verwendet verschiedene Lizenzen für seine Komponenten. Die meisten Module stehen unter der **MIT-Lizenz**, mit Ausnahme des **Finja Cloud Memory**, das unter der **Apache License 2.0** veröffentlicht wird. Bitte beachte die `LICENSE`-Dateien in den jeweiligen Unterordnern und oder Datein.

---

## 🆘 Support & Kontakt

Bei Fragen oder Problemen erreichst du uns hier:

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)