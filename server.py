import os
import json
import logging
import subprocess
import shutil
import csv
import io
import asyncio
import zipfile
from typing import Optional, List, Dict, Any, Union
from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel

from core.agent import WebTestingAgent
from core.crawler import WebCrawler
from core.database import TestDatabase
from core.hf_agent import HuggingFaceTestingAgent

app = FastAPI(title="Autonomous Web Testing Agent Dashboard", version="3.0.0")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
BASELINES_DIR = os.path.abspath("baselines")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(BASELINES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

OUTPUT_DIR = "allure-results"
REPORT_DIR = "allure-report"
agent = WebTestingAgent(output_dir=OUTPUT_DIR)
crawler = WebCrawler()
db = TestDatabase()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

def broadcast_log_sync(level: str, text: str):
    msg = {"type": "log", "level": level, "text": text}
    try:
        current_loop = asyncio.get_event_loop()
        if current_loop.is_running():
            current_loop.create_task(manager.broadcast(msg))
    except Exception:
        pass

class CrawlRequest(BaseModel):
    url: str
    check_links: Optional[bool] = True

class AIPromptRequest(BaseModel):
    prompt: str
    fallback_url: Optional[str] = "https://example.com"
    hf_token: Optional[str] = None
    model_name: Optional[str] = None
    headless: Optional[bool] = True

class TestRequest(BaseModel):
    url: str
    engine: Optional[str] = "both"
    headless: Optional[bool] = True
    selected_links: Optional[List[int]] = None
    selected_buttons: Optional[List[int]] = None
    selected_inputs: Optional[List[int]] = None
    login_mode: Optional[str] = "random"
    custom_credentials: Optional[Union[List[Dict[str, str]], Dict[str, str]]] = None
    csv_credentials: Optional[List[Dict[str, str]]] = None
    custom_links: Optional[List[Dict[str, Any]]] = None
    custom_buttons: Optional[List[Dict[str, Any]]] = None
    custom_inputs: Optional[List[Dict[str, Any]]] = None
    device_viewport: Optional[str] = "desktop"
    webhook_url: Optional[str] = None

class ExportScriptRequest(BaseModel):
    url: str
    engine: Optional[str] = "playwright"
    login_mode: Optional[str] = "random"

def try_generate_allure_cli():
    allure_cmd = shutil.which("allure")
    if allure_cmd or sys_has_allure():
        try:
            cmd = ["allure", "generate", OUTPUT_DIR, "--clean", "-o", REPORT_DIR]
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if res.returncode == 0:
                return True
        except Exception as e:
            logging.warning(f"Allure CLI execution error: {e}")
    return False

def sys_has_allure():
    try:
        res = subprocess.run("allure --version", shell=True, capture_output=True)
        return res.returncode == 0
    except Exception:
        return False

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Autonomous Web Testing Agent Active</h2>")

@app.websocket("/ws/test-logs")
async def websocket_logs_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "info", "text": "Connected to Web Testing Agent Live WebSocket Stream"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/crawl")
def crawl_webpage(req: CrawlRequest):
    try:
        page_data = crawler.fetch_and_parse(req.url, check_links=req.check_links)
        return {
            "status": "success",
            "url": page_data.url,
            "title": page_data.title,
            "total_links": len(page_data.links),
            "total_buttons": len(page_data.buttons),
            "total_inputs": len(page_data.inputs),
            "links": [
                {
                    "text": l.text,
                    "href": l.href,
                    "abs_url": l.absolute_url,
                    "is_internal": l.is_internal,
                    "status_code": l.status_code,
                    "status_msg": l.status_msg,
                    "selector": l.css_selector
                } for l in page_data.links
            ],
            "buttons": [
                {
                    "text": b.text,
                    "id": b.id,
                    "name": b.name,
                    "tag": b.tag_name,
                    "type": b.button_type,
                    "selector": b.css_selector
                } for b in page_data.buttons
            ],
            "inputs": [
                {
                    "type": i.type,
                    "name": i.name,
                    "id": i.id,
                    "placeholder": i.placeholder,
                    "selector": i.css_selector
                } for i in page_data.inputs
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/upload-csv")
async def upload_csv_credentials(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        text = contents.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        credentials = []
        for row in reader:
            cleaned_row = {k.strip().lower(): v.strip() for k, v in row.items() if k and v}
            if cleaned_row:
                credentials.append(cleaned_row)
        return {
            "status": "success",
            "filename": file.filename,
            "total_rows": len(credentials),
            "credentials": credentials
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV file: {str(e)}")

@app.post("/api/run-tests")
def run_agent_tests(req: TestRequest):
    try:
        results = agent.run(
            url=req.url,
            engine=req.engine,
            headless=req.headless,
            selected_links=req.selected_links,
            selected_buttons=req.selected_buttons,
            selected_inputs=req.selected_inputs,
            login_mode=req.login_mode,
            custom_credentials=req.custom_credentials,
            csv_credentials=req.csv_credentials,
            custom_links=req.custom_links,
            custom_buttons=req.custom_buttons,
            custom_inputs=req.custom_inputs,
            device_viewport=req.device_viewport or "desktop",
            webhook_url=req.webhook_url,
            log_callback=broadcast_log_sync
        )

        allure_cli_generated = try_generate_allure_cli()

        return {
            "status": "completed",
            "results": results,
            "allure_cli_generated": allure_cli_generated,
            "allure_results_dir": os.path.abspath(OUTPUT_DIR)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai-prompt-test")
def run_ai_prompt_test(req: AIPromptRequest):
    try:
        hf_agent = HuggingFaceTestingAgent(api_token=req.hf_token, default_model=req.model_name or "Qwen/Qwen2.5-Coder-32B-Instruct")
        test_plan = hf_agent.interpret_prompt(req.prompt, fallback_url=req.fallback_url, model_name=req.model_name)
        
        results = agent.run(
            url=test_plan.target_url,
            engine=test_plan.engine,
            headless=req.headless,
            log_callback=broadcast_log_sync
        )
        
        allure_cli_generated = try_generate_allure_cli()

        return {
            "status": "completed",
            "prompt": req.prompt,
            "ai_plan": {
                "target_url": test_plan.target_url,
                "engine": test_plan.engine,
                "model_used": test_plan.model_used,
                "explanation": test_plan.explanation,
                "test_links": test_plan.test_links,
                "test_buttons": test_plan.test_buttons,
                "test_inputs": test_plan.test_inputs,
                "check_accessibility": test_plan.check_accessibility,
                "check_performance": test_plan.check_performance
            },
            "results": results,
            "allure_cli_generated": allure_cli_generated,
            "allure_results_dir": os.path.abspath(OUTPUT_DIR)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
def get_test_run_history():
    history = db.get_history(limit=30)
    return {"status": "success", "total": len(history), "history": history}

@app.get("/api/history/{run_id}")
def get_test_run_details(run_id: str):
    run_details = db.get_run_details(run_id)
    if not run_details:
        raise HTTPException(status_code=404, detail="Run ID not found")
    return {"status": "success", "run": run_details}

@app.get("/api/visual-baselines")
def get_visual_baselines():
    baselines = []
    if os.path.exists(BASELINES_DIR):
        for f in os.listdir(BASELINES_DIR):
            if f.endswith(".png") or f.endswith(".jpg"):
                baselines.append({
                    "filename": f,
                    "path": os.path.join(BASELINES_DIR, f),
                    "size_kb": round(os.path.getsize(os.path.join(BASELINES_DIR, f)) / 1024, 1)
                })
    return {"status": "success", "total": len(baselines), "baselines": baselines}

@app.get("/api/baseline/{filename}")
def get_baseline_image(filename: str):
    fpath = os.path.join(BASELINES_DIR, filename)
    if os.path.exists(fpath):
        return FileResponse(fpath, media_type="image/png")
    raise HTTPException(status_code=404, detail="Baseline image not found")

@app.post("/api/export-script")
def export_pytest_script(req: ExportScriptRequest):
    script_content = f'''"""
Standalone Automated Test Script with Device Viewport & Auditing
Generated by Autonomous Web Testing Agent
Target URL: {req.url}
Engine: {req.engine}
"""
import pytest
from playwright.sync_api import sync_playwright

def test_autonomous_web_suite():
    url = "{req.url}"
    print(f"Executing standalone test suite against {{url}}...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={{"width": 1280, "height": 720}})
        page = context.new_page()
        
        response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
        assert response and response.status == 200, f"Failed to load {{url}}"
        
        title = page.title()
        assert title, "Page title must not be empty"
        print(f"Verified Page Title: {{title}}")
        
        page.screenshot(path="exported_baseline.png", full_page=True)
        print("Saved execution screenshot to exported_baseline.png")
        
        page.close()
        browser.close()

if __name__ == "__main__":
    test_autonomous_web_suite()
'''
    return PlainTextResponse(script_content, media_type="text/plain", headers={"Content-Disposition": "attachment; filename=test_suite.py"})

@app.get("/api/allure-report-data")
def get_allure_parsed_report():
    if not os.path.exists(OUTPUT_DIR):
        return {"status": "empty", "tests": []}

    tests = []
    containers = {}
    attachments = {}

    for fname in os.listdir(OUTPUT_DIR):
        fpath = os.path.join(OUTPUT_DIR, fname)
        if fname.endswith("-result.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    tests.append(json.load(f))
            except Exception:
                pass
        elif fname.endswith("-container.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    containers[data.get("uuid")] = data
            except Exception:
                pass
        elif fname.endswith("-attachment.txt") or fname.endswith("-attachment.json"):
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    attachments[fname] = f.read()
            except Exception:
                pass

    return {
        "status": "success",
        "total_test_files": len(tests),
        "tests": tests,
        "containers": containers,
        "attachments": attachments
    }

@app.get("/api/generate-allure-report")
def generate_allure_report_endpoint():
    cli_generated = try_generate_allure_cli()
    report_data = get_allure_parsed_report()

    videos = []
    screenshots = []
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            if f.endswith(".webm") or f.endswith(".mp4"):
                videos.append(f)
            elif f.endswith(".png") or f.endswith(".jpg"):
                screenshots.append(f)

    if isinstance(report_data, dict):
        report_data["allure_cli_generated"] = cli_generated
        report_data["videos"] = videos
        report_data["screenshots"] = screenshots
    return report_data

@app.get("/api/download-report")
def download_test_report_archive():
    if not os.path.exists(OUTPUT_DIR) or not os.listdir(OUTPUT_DIR):
        raise HTTPException(status_code=404, detail="No test results available to download.")

    zip_filename = "test_report_archive.zip"
    zip_path = os.path.join(os.path.dirname(__file__), zip_filename)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(OUTPUT_DIR):
            for file in files:
                fpath = os.path.join(root, file)
                arcname = os.path.relpath(fpath, OUTPUT_DIR)
                zipf.write(fpath, arcname)

    return FileResponse(zip_path, filename=zip_filename, media_type="application/zip")

@app.get("/api/generate-playwright-report")
def generate_playwright_report_endpoint():
    report_data = get_allure_parsed_report()

    videos = []
    screenshots = []
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            if f.endswith(".webm") or f.endswith(".mp4"):
                videos.append(f)
            elif f.endswith(".png") or f.endswith(".jpg"):
                screenshots.append(f)

    discovery = {}
    disc_path = os.path.join(OUTPUT_DIR, "discovery_summary.json")
    if os.path.exists(disc_path):
        try:
            with open(disc_path, "r", encoding="utf-8") as f:
                discovery = json.load(f)
        except Exception:
            pass

    return {
        "status": "success",
        "playwright_data": discovery.get("engine_results", {}).get("playwright", {}),
        "allure_tests": report_data.get("tests", []),
        "containers": report_data.get("containers", {}),
        "attachments": report_data.get("attachments", {}),
        "videos": videos,
        "screenshots": screenshots,
        "discovered": discovery.get("discovered", {})
    }

@app.get("/api/attachment/{filename}")
def get_attachment_file(filename: str):
    fpath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(fpath):
        media_type = None
        if filename.endswith(".webm"):
            media_type = "video/webm"
        elif filename.endswith(".mp4"):
            media_type = "video/mp4"
        elif filename.endswith(".png"):
            media_type = "image/png"
        elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
            media_type = "image/jpeg"
        return FileResponse(fpath, media_type=media_type)
    raise HTTPException(status_code=404, detail="Attachment file not found")

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host=host, port=port, reload=False)
