---
title: OmniTest Autonomous Web Testing Platform
emoji: ⚡
colorFrom: purple
colorTo: cyan
sdk: docker
app_port: 7860
pinned: false
---

# ⚡ OmniTest Autonomous Web Testing Platform

Enterprise AI Web Testing Platform powered by Playwright, Selenium, and Hugging Face AI Models.

## 🚀 Free Hosting Options

### Option 1: Hugging Face Spaces (100% Free - Recommended)
1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. Set Space Name e.g. `omnitest-testing-suite`.
3. Select **Docker** as the SDK.
4. Select **Blank** template.
5. Clone your space repository or upload project files (`Dockerfile`, `server.py`, `core/`, `static/`, `requirements.txt`).
6. Hugging Face Spaces will automatically build the Docker container and launch your live app at `https://huggingface.co/spaces/YOUR_USERNAME/omnitest-testing-suite`!

---

### Option 2: Render.com (100% Free Web Service)
1. Push this project to GitHub.
2. Sign up at [render.com](https://render.com).
3. Click **New +** -> **Web Service**.
4. Connect your GitHub repository.
5. Select **Docker** runtime.
6. Click **Deploy Web Service**! Render will build and host your web dashboard at `https://omnitest-web-runner.onrender.com`.

---

## 🛠️ Local Development
```bash
# Install dependencies
pip install -r requirements.txt
playwright install --with-deps chromium

# Run server
python server.py
# Open http://localhost:8000
```
