# 🎨 POD Automation Pilot

A powerful, Al-integrated automation pipeline for Print-on-Demand (POD) creators. This tool scrapes trending prompts from CivitAI, synchronizes with your generation workflow (SwarmUI/Perchance), generates descriptions and tags using local Vision AI (Ollama), and automates the upload process to POD sites, including Redbubble and TeePublic with advanced stealth hardening.

Made mainly as a personal project to study automation frameworks and solutions.

![Project Banner](https://img.shields.io/badge/Status-Public-brightgreen?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)
![AI-Powered](https://img.shields.io/badge/AI-Ollama%20Vision-orange?style=for-the-badge)

---

## 🚀 Key Features

- **🧠 Intelligent Vision Pipeline**: Automatically analyzes your generated art using Ollama (local) or Z.AI (cloud) to create engaging titles, descriptions, and SEO-optimized tags.
- **🐝 SwarmUI Integration**: Directly pulls generation metadata and model information from your SwarmUI instance for consistent tracking.
- **🤖 Specialized POD Bots**:
  - **Redbubble**: Advanced stealth bot with Cloudflare bypass logic, supporting both Visual and Headless modes.
  - **TeePublic**: High-reliability automation including "Quick Create" funnel handling.
- **🌐 Unified Web Dashboard**: A clean, modern interface to review pending images, approve metadata, and trigger multi-platform uploads with one click.
- **🛡️ Stealth Hardened**: Uses Playwright/Botasaurus with advanced fingerprint spoofing (`AutomationControlled`, modern User-Agents) to prevent detection.

---

## 🛠️ Setup Instructions

### 1. Prerequisites
- **Python 3.10+**
- **Ollama** (for local Vision AI)
  - `ollama pull llava` (or your preferred vision model like `GLM-4.6V`)
- **Git**

### 2. Installation
Clone the repository and run the automated dependency installer:

```bash
# Clone the repo
git clone https://github.com/saffta/Automation-Experiment.git
cd Automation-Experiment

# Install dependencies (Windows)
install_dependencies.bat
```

### 3. Configuration
Create a `.env` file in the root directory and add your credentials:

```env
# Redbubble Credentials
REDBUBBLE_EMAIL=your@email.com
REDBUBBLE_PASSWORD=your_password

# TeePublic Credentials
TEEPUBLIC_EMAIL=your@email.com
TEEPUBLIC_PASSWORD=your_password

# Vision AI Settings
OLLAMA_VISION_MODEL=llava
PREFER_OLLAMA=true

# SwarmUI API (Optional)
SWARM_API_URL=http://localhost:7801
```
### 4. Fetch Cookies
Redbubble requires you to store robust cookies for reliable future stealth. Run the below commands and log in manually - the script will automatically store your cookies.

```env
# Fetch Cookies
cd Redbubble-Bot
python fetch_cookies_manually.py
```

---

## 🛰️ Integration Details

### 🌦️ SwarmUI & Civitai Workflow
The Pilot is designed to watch a directory of images (default: `./images/by_status/pending`). It automatically extracts **Civitai IDs** from filenames and cross-references them with your SwarmUI metadata to ensure your descriptions match the creative intent of the generation.

### 👁️ Customizing Vision Models
You can swap out the description engine in the Web UI or via `outputs/src/vision_description.py`. Its been confirmed to work with:
- **Local**: `llava`, `moondream`, `GLM-4.6V-Flash` via Ollama.
- **Cloud**: Z.AI or OpenAI-compatible endpoints for high-fidelity descriptions.

---

## ⌨️ Launching the App

Run the included batch script to start the Web Dashboard:

```bash
launch_app.bat
```

Open your browser to `http://localhost:5001` to begin reviewing and uploading your art!

---

## ⚖️ Liability & Ethics
This tool is for educational and personal workflow optimization purposes. Users are responsible for complying with the Terms of Service of all integrated platforms. Always review generated descriptions to ensure they accurately represent your work.

---
