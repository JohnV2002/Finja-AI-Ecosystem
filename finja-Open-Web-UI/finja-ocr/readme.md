# 📄 OCR Service with Apache Tika 🧠

A standalone OCR service, based on **[Apache Tika](https://github.com/apache/tika-docker)** and **[Docker](https://www.docker.com/)**, that works perfectly with the **[OpenWebUI Document Extraction](https://docs.openwebui.com/features/document-extraction/apachetika)** feature. 💖

It extracts text from images, PDFs, and Office documents, including built-in **Tesseract OCR** for scanned content. 🖼️➡️📄

> [!WARNING]
> **Outdated Base Image:** The base Docker image used for this service (`logicalspark/docker-tikaserver:latest`) was last updated over **3 years ago**. Please use it with caution and be aware that it may lack recent security patches or features.

---

## ⚠️ IMPORTANT – Privacy & Storage

Please read these points carefully before using the service:

-   **Temporary Storage:** The Tika container itself is "stateless" and does not store anything permanently, but it creates temporary files for a short time during processing.
-   **Storage in OpenWebUI:** OpenWebUI **stores** the extracted texts in its own vector database so your LLM can access them later.
-   **Adaptive Memory Risk:** If you have enabled the **"Adaptive Memory v4"** feature in OpenWebUI, extracted content can be **sent to an external API (e.g., OpenAI)** and **stored there permanently!**
    -   **Example:** An image containing the text "My dog is happy" could lead Adaptive Memory to store the fact "The user's dog is happy."
-   **Disclaimer:** Use at your own risk. I assume no liability for your data. If you are unsure, disable the corresponding features in OpenWebUI.

---

## ⚡ Features

-   🖼️ Fully automated **OCR** for scanned documents (PDF, JPG, PNG, etc.).
-   📑 **Metadata Extraction** from Office files (DOCX, PPTX, XLSX).
-   🤖 Compatible with **OpenWebUI Document Extraction**.
-   🐋 Runs isolated in **Docker**, no local installation required.
-   🌍 **Multilingual OCR** (German & English are included in the setup).
-   🧪 Supports the endpoints `/tika`, `/rmeta/text`, and `/unpack`.

---

## 🚀 Setup: Choose Your Method

This setup builds a custom Docker image to add German language packages for text recognition (OCR). The necessary files (`docker-compose.yml` and `Dockerfile`) are already included in the project folder.

### Method 1: Docker Compose in Terminal (Recommended)

This is the fastest and most direct way to start the service.

**1. Open Project Folder**
Download this project (e.g., as a ZIP) and extract it. Then open a terminal and navigate to the project folder where the `docker-compose.yml` is located.

**2. Build and Start Service**
Run the following command. It builds the Docker image with the German language packages and then starts the container. The `--build` flag is only necessary for the first start.
```bash
docker compose up --build -d
```

**3. Verify**
Wait a moment and then check if the server responds correctly with this command:
```bash
curl -s http://localhost:9998/tika | head
```
If the response contains `Apache Tika Server`, everything is ready! ✨

### Method 2: Portainer Web Interface (Beginner Friendly)

This method is ideal if you prefer managing your containers via a graphical interface. Since a custom image needs to be built, a small terminal step is still required.

**1. Preparation in Terminal (One-time)**
Download the project to your Docker host and navigate to the project folder in the terminal. Run the `build` command once to create the image with the German language packages:
```bash
# Make sure you are in the correct folder
docker compose build
```
This command only builds the `tika-ocr-deu:latest` image without starting the container.

**2. Create Stack in Portainer**
1.  Log into Portainer.
2.  Gehe to **Stacks** and click on **"Add stack"**.
3.  Give the stack a name, e.g., `tika-service`.
4.  Select **"Web editor"** as the build method.
5.  Paste a **customized** `docker-compose` content. This is almost identical to the file in the project, but **without the `build:` section**, since we already created the image:
    ```yaml
    version: "3.9"

    services:
      tika:
        image: tika-ocr-deu:latest # We reference the previously built image
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
6.  Click on **"Deploy the stack"**. Portainer will now start the container from the locally built image.

---

## 💬 Usage with OpenWebUI

1.  Go to your **OpenWebUI Settings → Document Extraction**.
2.  Enable **"Apache Tika"**.
3.  Enter the URL of your Tika server:
    ```http
    http://<YOUR-IP>:9998
    ```
    (Use `127.0.0.1` if OpenWebUI is running on the same machine).
4.  Save. **Done!** 💖

---

## 🧪 Example Requests via `curl`

You can also test the service directly:

**Extract plain text only:**
```bash
curl -H "Accept: text/plain" -T your-document.pdf http://localhost:9998/tika
```

**Get text including metadata as JSON:**
```bash
curl -H "Accept: application/json" -T your-document.pdf http://localhost:9998/rmeta/text
```

---

## 💡 Tips & Tricks

-   **Large PDFs:** Increase the RAM for Java in the `docker-compose.yml`, e.g., `JAVA_OPTS=-Xmx2g`.
-   **More Languages:** Add more `tesseract-ocr-<lang>` packages in the `Dockerfile` (e.g., `tesseract-ocr-fra` for French).
-   **Security:** Optionally set up a reverse proxy (e.g., Traefik or Nginx) in front of the service to secure it.

---

## 📜 License

This setup is based on the official Docker images `apache/tika-docker` and `logicalspark/docker-tikaserver`.

-   **Apache Tika License:** [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
-   **Modifications & Setup Guide:** © 2026 J. Apps

---

## 🆘 Support & Contact

If you have any questions or problems, you can reach me here:

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)