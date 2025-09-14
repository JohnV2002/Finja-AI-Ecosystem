# 📄 OCR-Service mit Apache Tika 🧠

Ein eigenständiger OCR-Service, basierend auf **[Apache Tika](https://github.com/apache/tika-docker)** und **[Docker](https://www.docker.com/)**, der perfekt mit der **[OpenWebUI Document Extraction](https://docs.openwebui.com/features/document-extraction/apachetika)** Funktion zusammenarbeitet. 💖

Er extrahiert Text aus Bildern, PDFs und Office-Dokumenten, inklusive eingebautem **Tesseract-OCR** für gescannte Inhalte. 🖼️➡️📄

---

## ⚠️ WICHTIG – Datenschutz & Speicherung

Bitte lies diese Punkte sorgfältig durch, bevor du den Service nutzt:

-   **Temporäre Speicherung:** Der Tika-Container selbst ist "stateless" und speichert nichts dauerhaft, legt aber während der Verarbeitung kurzzeitig temporäre Dateien an.
-   **Speicherung in OpenWebUI:** OpenWebUI **speichert** die extrahierten Texte in seiner eigenen Vektor-Datenbank, damit dein LLM später darauf zugreifen kann.
-   **Adaptive Memory Risiko:** Wenn du in OpenWebUI das **"Adaptive Memory v4"**-Feature aktiviert hast, können extrahierte Inhalte **an eine externe API (z.B. OpenAI) gesendet** und dort **dauerhaft gespeichert werden!**
    -   **Beispiel:** Ein Bild mit dem Text "Mein Hund ist glücklich" könnte dazu führen, dass Adaptive Memory den Fakt "Der Hund des Nutzers ist glücklich" speichert.
-   **Haftungsausschluss:** Die Nutzung erfolgt auf eigene Gefahr. Ich übernehme keine Haftung für eure Daten. Wenn du unsicher bist, deaktiviere die entsprechenden Features in OpenWebUI.

---

## ⚡ Features

-   🖼️ Vollautomatische **OCR** für gescannte Dokumente (PDF, JPG, PNG, etc.).
-   📑 **Metadaten-Extraktion** aus Office-Dateien (DOCX, PPTX, XLSX).
-   🤖 Kompatibel mit der **OpenWebUI Document Extraction**.
-   🐋 Läuft isoliert in **Docker**, keine lokale Installation nötig.
-   🌍 **Mehrsprachige OCR** (Deutsch & Englisch sind im Setup enthalten).
-   🧪 Unterstützt die Endpunkte `/tika`, `/rmeta/text` und `/unpack`.

---

## 🚀 Setup: Wähle deine Methode

Für dieses Setup wird ein benutzerdefiniertes Docker-Image gebaut, um deutsche Sprachpakete für die Texterkennung (OCR) hinzuzufügen. Die dafür nötigen Dateien (`docker-compose.yml` und `Dockerfile`) sind bereits im Projektordner enthalten.

### Methode 1: Docker Compose im Terminal (Empfohlen)

Dies ist der schnellste und direkteste Weg, um den Service zu starten.

**1. Projektordner öffnen**
Lade dieses Projekt herunter (z.B. als ZIP) und entpacke es. Öffne danach ein Terminal und navigiere in den Projektordner, in dem sich die `docker-compose.yml` befindet.

**2. Service starten und bauen**
Führe den folgenden Befehl aus. Er baut das Docker-Image mit den deutschen Sprachpaketen und startet anschließend den Container. Das `--build` Flag ist nur beim ersten Start notwendig.
```bash
docker compose up --build -d
```

**3. Überprüfen**
Warte einen Moment und prüfe dann mit diesem Befehl, ob der Server korrekt antwortet:
```bash
curl -s http://localhost:9998/tika | head
```
Wenn die Antwort `Apache Tika Server` enthält, ist alles bereit! ✨

### Methode 2: Portainer Web-Oberfläche (Anfängerfreundlich)

Diese Methode ist ideal, wenn du deine Container lieber über eine grafische Oberfläche verwaltest. Da ein benutzerdefiniertes Image gebaut werden muss, ist ein kleiner Schritt im Terminal trotzdem notwendig.

**1. Vorbereitung im Terminal (einmalig)**
Lade das Projekt auf deinen Docker-Host herunter und navigiere im Terminal in den Projektordner. Führe dort einmalig den `build`-Befehl aus, um das Image mit den deutschen Sprachpaketen zu erstellen:
```bash
# Stelle sicher, dass du im richtigen Ordner bist
docker compose build
```
Dieser Befehl baut nur das Image `tika-ocr-deu:latest`, ohne den Container zu starten.

**2. Stack in Portainer anlegen**
1.  Logge dich in Portainer ein.
2.  Gehe zu **Stacks** und klicke auf **"Add stack"**.
3.  Gib dem Stack einen Namen, z.B. `tika-service`.
4.  Wähle als Build-Methode **"Web editor"**.
5.  Füge einen **angepassten** `docker-compose`-Inhalt ein. Dieser ist fast identisch mit der Datei im Projekt, aber **ohne den `build:`-Abschnitt**, da wir das Image ja bereits erstellt haben:
    ```yaml
    version: "3.9"

    services:
      tika:
        image: tika-ocr-deu:latest # Wir verweisen auf das zuvor gebaute Image
        container_name: tika
        ports:
          - "9998:9998"
        environment:
          - JAVA_OPTS=-Xms256m -Xmx1g
        healthcheck:
          test: ["CMD", "curl", "-f", "http://localhost:9998/tika"]
          interval: 15s
          timeout: 5s
          retries: 10
        restart: unless-stopped
    ```
6.  Klicke auf **"Deploy the stack"**. Portainer startet nun den Container aus dem lokal gebauten Image.

---

## 💬 Nutzung mit OpenWebUI

1.  Gehe in deine **OpenWebUI Einstellungen → Document Extraction**.
2.  Aktiviere **"Apache Tika"**.
3.  Trage die URL deines Tika-Servers ein:
    ```http
    http://<DEINE-IP>:9998
    ```
    (Nutze `127.0.0.1`, wenn OpenWebUI auf derselben Maschine läuft).
4.  Speichern. **Fertig!** 💖

---

## 🧪 Beispiel-Requests via `curl`

Du kannst den Service auch direkt testen:

**Nur den reinen Text extrahieren:**
```bash
curl -H "Accept: text/plain" -T dein-dokument.pdf http://localhost:9998/tika
```

**Text inklusive Metadaten als JSON erhalten:**
```bash
curl -H "Accept: application/json" -T dein-dokument.pdf http://localhost:9998/rmeta/text
```

---

## 💡 Tipps & Tricks

-   **Große PDFs:** Erhöhe den Arbeitsspeicher für Java in der `docker-compose.yml`, z.B. `JAVA_OPTS=-Xmx2g`.
-   **Mehr Sprachen:** Füge weitere `tesseract-ocr-<lang>` Pakete in der `Dockerfile` hinzu (z.B. `tesseract-ocr-fra` für Französisch).
-   **Sicherheit:** Setze optional einen Reverse Proxy (z.B. Traefik oder Nginx) vor den Service, um ihn abzusichern.

---

## 📜 Lizenz

Dieses Setup basiert auf dem offiziellen Docker-Image `apache/tika-docker` und `logicalspark/docker-tikaserver`.

-   **Apache Tika Lizenz:** [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
-   **Anpassungen & Setup-Anleitung:** © 2025 J. Apps

---

## 🆘 Support & Kontakt

Bei Fragen oder Problemen erreichst du uns hier:

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)