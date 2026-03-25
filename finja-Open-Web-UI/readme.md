# 🤖 Finja AI Ecosystem for OpenWebUI

Welcome to the Finja AI Ecosystem! 💖

This project is a collection of modular, Docker-based microservices designed to extend **[OpenWebUI](https://openwebui.com/)** and create a richer, more interactive AI experience. Each module is an independent building block that adds a specific capability such as memory, web search, or image generation.

---

## ✨ Ecosystem Overview

All modules are designed to work seamlessly with OpenWebUI and can be easily deployed via Docker and Docker Compose. We maintain strict security standards and automated CI/CD testing across the ecosystem.

| Module | Description | Status |
| :--- | :--- | :--- |
| 🧠 **Cloud Memory** | Long-term memory storage per user and **True TTS Network Caching**. | ✅ Ready (v4.4.2) |
| 🌐 **Web Crawler** | Anonymous web searches via Tor + DDG + Fallbacks to provide up-to-date data. | ✅ Ready (v1.0.0) |
| 📄 **OCR Service** | Extracts text from uploaded documents and images (PDFs, JPGs, etc.). | ✅ Ready |
| 🎨 **Image Generation** | Generates images locally on your own hardware via Stable Diffusion. | ✅ Ready |
| 🗣️ **Text-to-Speech (TTS)** | *Moved:* Speech synthesis module. | 🚧 Moved to Neural System |

---

## 📦 The Modules in Detail

Each module is located in its own subfolder and contains a detailed `readme.md` with specific setup instructions.

### 🧠 Finja Cloud Memory
This module provides a lightweight server that allows the AI to remember facts and details from previous conversations. It is the foundation for personalized interactions.
-   **Key Features:** Stores memories as JSON per user, prevents Path Traversal attacks, includes **True TTS Network Caching** for caching generated voice files, and integrates with the `adaptive_memory_v4` plugin for OpenWebUI. Features a 100% passing Pytest CI/CD pipeline.
-   **Technology:** FastAPI, Python, Docker, Pytest.

[➡️ **Go to the detailed setup guide for the Memory module...**](./finja-Memory/readme.md)

### 🌐 Web Crawler
With this module, your AI can access up-to-date information from the internet. It performs search queries anonymously.
-   **Key Features:** Hybrid search using DuckDuckGo with Google fallback (and Wikipedia Tabby Cat emergency fallback). Anonymized via Tor, protected by bearer tokens, and heavily refactored for low Cognitive Complexity. Features a 100% passing Pytest CI/CD pipeline.
-   **Technology:** FastAPI, Python, Tor, Docker, Pytest.

[➡️ **Go to the detailed setup guide for the Web Crawler...**](./finja-web-crawler/readme.md)

### 📄 OCR Service with Apache Tika
Allows your AI to "read" the content of documents. Upload a PDF, an image, or an Office file, and this module extracts the text so the LLM can process it.
-   **Key Features:** Uses Apache Tika and Tesseract-OCR for broad format support, runs isolated in Docker, and is pre-configured for German and English. *(Note: Base image is outdated; use with caution).*
-   **Technology:** Apache Tika, Tesseract, Docker.

[➡️ **Go to the detailed setup guide for the OCR Service...**](./finja-ocr/readme.md)

### 🎨 Image Generation with Stable Diffusion
Give your AI the ability to paint pictures! This module runs a local instance of the popular Automatic1111 WebUI and enables text-to-image generation directly from the chat.
-   **Key Features:** Runs completely locally (CPU-focused), permanently stores generated images, and is fully compatible with the OpenWebUI image generation feature.
-   **Technology:** Stable Diffusion (Automatic1111), Docker.

[➡️ **Go to the detailed setup guide for Image Generation...**](./finja-stable-diffsion/readme.md)

### 🗣️ Text-to-Speech (TTS) - Architecture Change!
This module was originally intended to give Finja a voice inside OpenWebUI. 
-   **Status Statement:** **No Longer an OpenWebUI Module!** The architecture has changed. The standalone TTS module will instead be integrated directly into **Finja's Neural System** as a core component for voice and speech synthesis in streams and games. (However, note that TTS *caching* is now successfully handled by the `Cloud Memory` module).

[➡️ **Go to the placeholder README for the TTS module...**](./finja-tts/readme.md)

---

## 📜 Licenses

This project uses various licenses for its components. Most modules are under the **MIT License**, with the exception of the **Finja Cloud Memory**, which is released under the **Apache License 2.0**. Please note the `LICENSE` and `NOTICE` files in the respective subfolders.

---

## 🆘 Support & Contact

If you have any questions or problems, you can reach me here:

-   **Email:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)

---
*© 2026 J. Apps*