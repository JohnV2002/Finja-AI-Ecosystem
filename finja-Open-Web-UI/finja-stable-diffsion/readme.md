# 🎨 Stable Diffusion – Image Generation

Ein lokales Image-Generation-Modul mit **Stable Diffusion** über die **Automatic1111 WebUI** — betrieben in **Docker (CPU-Only)** 🐳🖌️

Perfekt für Text-zu-Bild-Generierung direkt aus OpenWebUI heraus 💖  
(Integration siehe: [OpenWebUI Docs – Images](https://docs.openwebui.com/tutorials/images))

---

## ⚠️ Hinweis

- Läuft **komplett lokal**, keine Cloud nötig.
- **Sehr langsam auf CPU** – aber ideal, wenn keine GPU zur Verfügung steht.
- **Speichert generierte Bilder dauerhaft** im Container-Volume.
- **Keine Inhalte werden an Dritte gesendet** (außer du nutzt externe Modelle von Drittanbietern).

---

## 💡 Features

- 🖼️ **Stable Diffusion WebUI (Automatic1111)** als Backend.
- 🧠 Unterstützung für **Prompt → Bild** sowie **Negative Prompts**.
- 📦 Läuft gekapselt in einem **Docker-Container** (kein kompliziertes Setup am Host-System nötig).
- 💾 Alle Modelle, generierten Bilder und Einstellungen werden **persistent auf dem Host** gespeichert.
- 🧩 Volle Kompatibilität mit der **OpenWebUI Image Generation** Funktion.

---

## 📦 Setup

Wir nutzen das hervorragende Open-Source-Projekt [stable-diffusion-webui-docker](https://github.com/AbdBarho/stable-diffusion-webui-docker) und folgen dessen offiziellem Setup-Guide:
- 🔗 **Offizielles Wiki:** [Setup Guide](https://github.com/AbdBarho/stable-diffusion-webui-docker/wiki/Setup)

### 🛠️ Schritt-für-Schritt-Anleitung

1.  **Repository klonen und Container starten:**
    Öffne ein Terminal. Die folgenden Befehle laden zuerst den Code herunter und starten dann direkt den Docker-Container im CPU-Modus.
    ```bash
    # 1. Projekt herunterladen und in den Ordner wechseln
    git clone [https://github.com/AbdBarho/stable-diffusion-webui-docker.git](https://github.com/AbdBarho/stable-diffusion-webui-docker.git)
    cd stable-diffusion-webui-docker

    # 2. Container im CPU-Modus starten. Das --build Flag ist nur beim ersten Mal nötig.
    docker compose --profile auto-cpu up --build
    ```
    Lasse dieses Terminalfenster geöffnet. Es zeigt die Logs des Containers an.

2.  **Modelle herunterladen (Anfänger-Guide für Civitai):**
    Da der Container nun im Hintergrund läuft, können wir Modelle direkt hineinladen. Diese Methode ist ideal, um Modelle an den richtigen Ort herunterzuladen, ohne sie auf deinem Host-PC zwischenzuspeichern.

    **Teil A: Civitai API-Key erstellen**
    1.  Melde dich auf [civitai.com](https://civitai.com/) an oder erstelle einen Account.
    2.  Klicke auf dein Profilbild und gehe zu den **Account-Einstellungen** (Zahnrad-Symbol).
    3.  Scrolle nach unten zum Abschnitt **API Keys** und klicke auf **"Add API Key"**.
    4.  Gib dem Key einen Namen (z.B. "Docker-Download") und kopiere den angezeigten Key. **Bewahre ihn sicher auf!**

    **Teil B: Modell im Docker-Container herunterladen**
    1.  Öffne ein **zweites Terminal** (das erste Terminalfenster bleibt offen).
    2.  Finde den Namen deines Containers (meistens `stable-diffusion-webui-docker-auto-cpu-1`). Du kannst dies mit `docker ps` überprüfen.
    3.  Öffne eine Shell **innerhalb** des laufenden Containers:
        ```bash
        # Ersetze den Namen, falls deiner abweicht
        docker exec -it stable-diffusion-webui-docker-auto-cpu-1 /bin/bash
        ```
    4.  Navigiere im Container zum richtigen Ordner:
        ```bash
        cd /data/Stable-diffusion
        ```
    5.  Suche dir auf der Civitai-Webseite ein Modell aus (z.B. *Nova Anime XL*).
    6.  Klicke auf den **Download-Button** Mit **Rechtsklick** auf den Link der spezifischen Version, die du laden möchtest, und wähle **"Link-Adresse kopieren"**.
    7.  Füge den Link in deinem Terminal nach dem `wget`-Befehl ein und hänge deinen API-Key an:
        ```bash
        wget "[https://civitai.com/api/download/models/1854228?type=Model&format=SafeTensor&token=DEIN_API_KEY](https://civitai.com/api/download/models/1854228?type=Model&format=SafeTensor&token=DEIN_API_KEY)" --content-disposition
        ```
    8.  **WICHTIG:** Ersetze `DEIN_API_KEY` am Ende der URL durch deinen echten API-Key.
    9.  Drücke Enter. Der Download startet. Der Parameter `--content-disposition` sorgt dafür, dass die Datei automatisch den korrekten Namen erhält.

    **Fehlerbehebung: `wget: command not found`**
    Falls `wget` im Container fehlt, installiere es mit diesen Befehlen (innerhalb der Container-Shell):
    ```bash
    apt update && apt upgrade -y && apt install wget -y
    ```
    Versuche den `wget`-Befehl danach erneut.

3.  **WebUI öffnen und nutzen:**
    Sobald Modelle heruntergeladen sind, kannst du die WebUI in deinem Browser öffnen und sie verwenden:
    ```http
    http://localhost:7860
    ```

---

## 💬 Integration in OpenWebUI

Navigiere in OpenWebUI zu `Einstellungen → Image Generation`:

-   **Backend:** `Automatic1111`
-   **URL:** `http://<deine-ip>:7860` (Ersetze `<deine-ip>` mit der IP-Adresse des Computers, auf dem der Docker-Container läuft. Wenn es derselbe PC ist, nutze `127.0.0.1`.)

Danach kannst du Bild-Prompts direkt aus dem OpenWebUI-Chat an deine lokale Stable Diffusion Instanz senden.

---

## ⚙️ Performance-Tipps

-   **Geduld:** CPU-Only ist **sehr langsam** (mehrere Minuten pro Bild sind normal).
-   **GPU-Upgrade:** Du kannst später jederzeit auf ein GPU-Profil umsteigen, indem du den Container mit folgendem Befehl startest:
    ```bash
    docker compose --profile auto up --build
    ```
-   **Modellgröße:** Beachte, dass Modelle oft sehr groß sind (4GB+). Kleinere Modelle sind für den CPU-Betrieb besser geeignet.

---

## 📂 Wo liegen meine Daten?

Alle wichtigen Daten werden im `data/` Ordner des Projekts gespeichert und bleiben auch nach einem Neustart des Containers erhalten:

-   `data/Stable-diffusion/` → Deine Modelle (`.safetensors`)
-   `data/outputs/` → Alle generierten Bilder
-   `data/config.json` → Einstellungen der WebUI

Du kannst diesen Ordner einfach sichern oder verschieben.

---

## 📜 Lizenz

### Lizenz dieser Anleitung
Der Inhalt dieser `README.md`-Anleitung steht unter der **MIT-Lizenz**. Du kannst sie frei verwenden, verändern und teilen, solange der ursprüngliche Copyright-Hinweis beibehalten wird.

### Lizenz der besprochenen Software
Diese Anleitung beschreibt die Nutzung von Software von Drittanbietern. Diese unterliegen ihren eigenen Lizenzen:
-   **Stable Diffusion WebUI Docker:** [MIT-Lizenz](https://github.com/AbdBarho/stable-diffusion-webui-docker/blob/master/LICENSE)
-   **Stable Diffusion Modelle:** Die Modelle selbst unterliegen oft der **CreativeML Open RAIL-M Lizenz**. Diese enthält wichtige nutzungsbasierte Einschränkungen. Lies und verstehe die Lizenz des jeweiligen Modells, bevor du es nutzt.

---

## 🆘 Support & Kontakt

Bei Fragen oder Problemen erreichst du uns hier:

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)