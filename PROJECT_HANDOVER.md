# 🚀 OmniTest AI Studio — Project Handover & Agent Memory

> **Note for AI Agents & Developers**: This document contains the complete context, architecture, history of changes, and technical decisions made for **OmniTest AI Studio**. Read this file to seamlessly resume development across different environments or AI accounts.

---

## 📌 Project Overview
**OmniTest AI Studio** is an autonomous, AI-driven end-to-end web testing platform. It extracts DOM structures from web applications (including dynamic SPAs), uses AI to generate test scenarios, and executes automated test suites across **Playwright** and **Selenium** engines with live WebSocket stream logging, performance audits, WCAG accessibility checks, visual regression diffs, evidence screenshots, and full screen recordings.

* **GitHub Repository**: `https://github.com/Nafiue12/-omnitest-ai-studio.git`
* **Production Deployment**: Cloud Docker Container on **Render.com**
* **Base Container Image**: `mcr.microsoft.com/playwright/python:v1.45.0-jammy`
* **Python Version**: 3.10+ / 3.14 (FastAPI + Uvicorn)

---

## 🏗️ Technology Stack & Architecture

```
                      ┌─────────────────────────────────────────┐
                      │          Glassmorphism Web UI           │
                      │       (static/index.html, app.js)       │
                      └────────────────────┬────────────────────┘
                                           │ HTTP & WebSocket
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │           FastAPI Backend Server        │
                      │               (server.py)               │
                      └────────────────────┬────────────────────┘
                                           │
          ┌────────────────────────────────┼────────────────────────────────┐
          ▼                                ▼                                ▼
┌──────────────────┐            ┌─────────────────────┐          ┌──────────────────────┐
│  DOM Crawler &   │            │ Playwright Engine   │          │  Selenium Engine     │
│ Dynamic SPA Fetch│            │ (playwright_runner) │          │  (selenium_runner)   │
│   (crawler.py)   │            └──────────┬──────────┘          └──────────┬───────────┘
└──────────────────┘                       │                                │
                                           ▼                                ▼
                                ┌──────────────────────────────────────────────────┐
                                │ Evidence Attachments: Screenshots & Video (.webm)│
                                └──────────────────────────────────────────────────┘
```

### Key Components
1. **`server.py`**:
   - FastAPI server with thread-safe execution locks (`agent_execution_lock = threading.Lock()`).
   - `/ws/logs` WebSocket endpoint for real-time live terminal streaming using `asyncio.run_coroutine_threadsafe`.
   - Serving attachment files (`/api/attachment/{filename}`) for `.webm` video recordings and `.png` screenshots.

2. **`core/agent.py`**:
   - Master pipeline controller orchestrating DOM crawling, AI strategy generation, test suite execution, database history logging (SQLite), and report generation.

3. **`core/playwright_runner.py`**:
   - Primary test execution engine using Playwright Python (`playwright==1.45.0`).
   - Captures Core Web Vitals (TTFB, Load time), WCAG 2.1 DOM accessibility compliance, and visual regression pixel diffs.
   - Implements locator self-healing (`_heal_locator`) with backward compatibility alias (`_heal_element = _heal_locator`).
   - Records full browser execution video (`.webm`) and baseline screenshots (`.png`).
   - Handles rate limiting (HTTP 429/403) with anti-bot desktop headers, backoff retries, un-lazy DOM image hydration, and non-blocking status toasts.

4. **`core/selenium_runner.py`**:
   - Secondary test execution engine using Selenium WebDriver.
   - Detects system Chromium (`/usr/bin/chromedriver`) in Linux Docker containers and provides graceful fallback if unprivileged cloud displays are constrained.

5. **`core/crawler.py`**:
   - DOM parser using BeautifulSoup4 and headless Playwright fallback for dynamic JavaScript SPAs (React, Vue, Next.js).

6. **`core/hf_agent.py`**:
   - AI router integrating Hugging Face Inference API (`Qwen/Qwen2.5-Coder-32B-Instruct`) for test strategy planning and locator healing.

---

## 🛠️ Complete Timeline of Major Fixes & Enhancements

| Issue / Feature | Root Cause | Solution Implemented | Commit |
| :--- | :--- | :--- | :--- |
| **Duplicate Concurrent Suite Runs** | Render 512MB RAM exhaustion caused server crashes on double-click. | Added `agent_execution_lock = threading.Lock()` in `server.py` & UI button disabled guards in `static/app.js`. | `0d12618` |
| **Playwright Version Mismatch** | Playwright Python version mismatched host Docker image drivers. | Pinned `playwright==1.45.0` in `requirements.txt` and added `RUN playwright install chromium` in `Dockerfile`. | `576c89c` |
| **Missing Screen Recordings on Errors** | `context.close()` was at the end of happy path; assertion errors skipped video saving. | Moved `context.close()`, `browser.close()`, and `.webm` video extraction into a `finally:` block in `playwright_runner.py`. | `0e2e1d3` |
| **Selenium Binary Location Exception** | `options.binary_location = None` threw `TypeError` in Selenium Python. | Changed `None` assignment to `options.binary_location = ""` and simplified container setup. | `0e2e1d3` |
| **`AttributeError: _heal_element`** | Method was renamed to `_heal_locator`. | Added backward compatibility alias `_heal_element = _heal_locator` in `PlaywrightTestEngine`. | `654fda3` |
| **Linux Selenium Display Exit** | Root Chromium process exited in unprivileged Docker containers. | Added `--disable-setuid-sandbox` and `--no-zygote` flags, and added graceful Playwright fallback. | `80d1fc7` |
| **Blank White Screen in Video/SS** | Default Linux `/dev/shm` 64MB memory limit crashed Chromium GPU compositor. | Added `--disable-dev-shm-usage`, `--no-sandbox`, `--disable-gpu`, `--force-color-profile=srgb`, and `--enable-surface-synchronization`. | `3f65623` |
| **HTTP 429 Rate Limit Blank Pages** | Cloud IPs hitting target sites were served empty 429 rate limit pages. | Added desktop HTTP headers, 3s backoff retry, DOM image un-lazy hydration, and non-blocking top toast alert. | `d83bdff` |
| **Viewport Canvas Clipping** | `full_page=True` clipped `100vh` flexbox layouts into blank white boxes. | Changed `page.screenshot` to exact viewport `full_page=False` and added `emulate_media(media="screen")`. | `9571852` |
| **Static Video Recordings** | Full-screen banner overlay obscured live browser test interactions. | Changed banner overlay to a non-blocking top-right toast banner and added live element scrolling (`scroll_into_view_if_needed`), mouse hovering (`loc.hover`), and typing animations. | `65b03b4` |

---

## 🚦 Verification Commands

Before committing future updates, run the automated test suite locally:

```bash
# Run pytest verification suite
python -m pytest

# Run FastAPI server locally
python server.py
# Server will run at http://localhost:8000
```

---

## 📌 Instructions for the Next AI Agent

1. **Repository Link**: `https://github.com/Nafiue12/-omnitest-ai-studio.git`
2. **Current Branch**: `main` (all changes are committed and pushed).
3. **Environment**:
   - Python 3.10+
   - Playwright 1.45.0
   - Selenium 4.x
   - Pytest 9.x
4. **Key Design Principle**: Always ensure browser resource finalization (`context.close()`, `video.path()`) is inside a `finally:` block to guarantee evidence capture. When modifying launch options, preserve Docker Chromium flags (`--no-sandbox`, `--disable-dev-shm-usage`).

---

*Handover document generated successfully on July 30, 2026.*
