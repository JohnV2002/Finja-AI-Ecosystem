# 🎨 Stable Diffusion – Image Generation

A local image generation module using **Stable Diffusion** via the **Automatic1111 WebUI** — running in **Docker (CPU-Only)** 🐳🖌️

Perfect for Text-to-Image generation directly from OpenWebUI 💖  
(Integration see: [OpenWebUI Docs – Images](https://docs.openwebui.com/tutorials/images))

---

## ⚠️ Note

- Runs **completely locally**, no cloud required.
- **Very slow on CPU** – but ideal if no GPU is available.
- **Saves generated images permanently** in the container volume.
- **No content is sent to third parties** (unless you use external third-party models).

---

## 💡 Features

- 🖼️ **Stable Diffusion WebUI (Automatic1111)** as backend.
- 🧠 Support for **Prompt → Image** as well as **Negative Prompts**.
- 📦 Runs encapsulated in a **Docker container** (no complicated setup on the host system required).
- 💾 All models, generated images, and settings are **saved persistently on the host**.
- 🧩 Full compatibility with the **OpenWebUI Image Generation** feature.

---

## 📦 Setup

We use the excellent open-source project [stable-diffusion-webui-docker](https://github.com/AbdBarho/stable-diffusion-webui-docker) and follow its official setup guide:
- 🔗 **Official Wiki:** [Setup Guide](https://github.com/AbdBarho/stable-diffusion-webui-docker/wiki/Setup)

### 🛠️ Step-by-Step Guide

1.  **Clone repository and start container:**
    Open a terminal. The following commands will first download the code and then start the Docker container in CPU mode directly.
    ```bash
    # 1. Download project and change into the folder
    git clone https://github.com/AbdBarho/stable-diffusion-webui-docker.git
    cd stable-diffusion-webui-docker

    # 2. Start container in CPU mode. The --build flag is only required the first time.
    docker compose --profile auto-cpu up --build
    ```
    Leave this terminal window open. It will show the container logs.

2.  **Download models (Beginner's Guide for Civitai):**
    Since the container is now running in the background, we can load models directly into it. This method is ideal for downloading models to the correct location without caching them on your host PC.

    **Part A: Create Civitai API Key**
    1.  Log in to [civitai.com](https://civitai.com/) or create an account.
    2.  Click on your profile picture and go to the **Account Settings** (gear icon).
    3.  Scroll down to the **API Keys** section and click on **"Add API Key"**.
    4.  Give the key a name (e.g. "Docker-Download") and copy the displayed key. **Keep it safe!**

    **Part B: Download Model inside the Docker Container**
    1.  Open a **second terminal** (leave the first terminal window open).
    2.  Find the name of your container (usually `stable-diffusion-webui-docker-auto-cpu-1`). You can check this with `docker ps`.
    3.  Open a shell **inside** the running container:
        ```bash
        # Replace the name if yours is different
        docker exec -it stable-diffusion-webui-docker-auto-cpu-1 /bin/bash
        ```
    4.  Navigate to the correct folder inside the container:
        ```bash
        cd /data/Stable-diffusion
        ```
    5.  Pick a model on the Civitai website (e.g. *Nova Anime XL*).
    6.  **Right-click** on the **Download button** for the specific version you want to download and select **"Copy link address"**.
    7.  Paste the link into your terminal after the `wget` command and append your API key:
        ```bash
        wget "https://civitai.com/api/download/models/1854228?type=Model&format=SafeTensor&token=YOUR_API_KEY" --content-disposition
        ```
    8.  **IMPORTANT:** Replace `YOUR_API_KEY` at the end of the URL with your real API key.
    9.  Press Enter. The download will start. The `--content-disposition` parameter ensures that the file automatically gets the correct name.

    **Troubleshooting: `wget: command not found`**
    If `wget` is missing in the container, install it using these commands (inside the container shell):
    ```bash
    apt update && apt upgrade -y && apt install wget -y
    ```
    Try the `wget` command again afterwards.

3.  **Open and use WebUI:**
    Once models are downloaded, you can open the WebUI in your browser and use it:
    ```http
    http://localhost:7860
    ```

---

## 💬 Integration in OpenWebUI

Navigate in OpenWebUI to `Settings → Image Generation`:

-   **Backend:** `Automatic1111`
-   **URL:** `http://<your-ip>:7860` (Replace `<your-ip>` with the IP address of the computer running the Docker container. If it's the same PC, use `127.0.0.1`.)

Afterwards, you can send image prompts directly from the OpenWebUI chat to your local Stable Diffusion instance.

---

## ⚙️ Performance Tips

-   **Patience:** CPU-Only is **very slow** (several minutes per image are normal).
-   **GPU Upgrade:** You can always switch to a GPU profile later by starting the container with the following command:
    ```bash
    docker compose --profile auto up --build
    ```
-   **Model Size:** Keep in mind that models are often very large (4GB+). Smaller models are better suited for CPU operation.

---

## 📂 Where is my data?

All important data is saved in the project's `data/` folder and will persist even after restarting the container:

-   `data/Stable-diffusion/` → Your models (`.safetensors`)
-   `data/outputs/` → All generated images
-   `data/config.json` → Settings of the WebUI

You can easily backup or move this folder.

---

## 📜 License

### License of this guide
The content of this `README.md` guide is provided under the **MIT License**. You may freely use, modify, and share it as long as the original copyright notice is retained.

### License of the discussed software
This guide describes the use of third-party software. These are subject to their own licenses:
-   **Stable Diffusion WebUI Docker:** [MIT License](https://github.com/AbdBarho/stable-diffusion-webui-docker/blob/master/LICENSE)
-   **Stable Diffusion Models:** The models themselves are often subject to the **CreativeML Open RAIL-M License**. This contains important usage-based restrictions. Read and understand the license of the respective model before using it.

---

## 🆘 Support & Contact

If you have questions or problems, you can reach me here:

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)