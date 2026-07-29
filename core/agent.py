import os
import json
import logging
import shutil
import time
import uuid
from typing import Dict, Any, Optional, Union, List, Callable
from core.crawler import WebCrawler, PageStructure, LinkItem, ButtonItem, InputItem
from core.selenium_runner import SeleniumTestEngine
from core.playwright_runner import PlaywrightTestEngine
from core.database import TestDatabase
from core.notifications import WebhookNotifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebTestingAgent")

class WebTestingAgent:
    def __init__(self, output_dir: str = "allure-results", db_path: str = "test_history.db"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.crawler = WebCrawler()
        self.db = TestDatabase(db_path=db_path)
        self.notifier = WebhookNotifier()

    def _clean_output_dir(self):
        """Cleans previous test screenshots, videos, and result JSONs before running new tests."""
        logger.info(f"Cleaning previous test artifacts in '{self.output_dir}'...")
        if os.path.exists(self.output_dir):
            for fname in os.listdir(self.output_dir):
                fpath = os.path.join(self.output_dir, fname)
                try:
                    if os.path.isfile(fpath) or os.path.islink(fpath):
                        os.unlink(fpath)
                    elif os.path.isdir(fpath):
                        shutil.rmtree(fpath)
                except Exception as e:
                    logger.warning(f"Error removing old artifact '{fpath}': {e}")

    def crawl_url(self, url: str, check_links: bool = True) -> PageStructure:
        """Crawls target URL and returns structured PageStructure data."""
        return self.crawler.fetch_and_parse(url, check_links=check_links)

    def run(
        self,
        url: str,
        engine: str = "both",
        headless: bool = True,
        selected_links: Optional[list] = None,
        selected_buttons: Optional[list] = None,
        selected_inputs: Optional[list] = None,
        login_mode: str = "random",
        custom_credentials: Optional[Union[list, dict]] = None,
        csv_credentials: Optional[list] = None,
        custom_links: Optional[list] = None,
        custom_buttons: Optional[list] = None,
        custom_inputs: Optional[list] = None,
        device_viewport: str = "desktop",
        webhook_url: Optional[str] = None,
        log_callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """Full Agent Pipeline: Device Emulation, Performance Audits, WCAG Audits, Visual Diffing & Webhooks."""
        run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        start_time = time.time()
        self._clean_output_dir()

        if log_callback:
            log_callback("info", f"Starting Agent Execution Pipeline [Run ID: {run_id}]")
            log_callback("info", f"Target: {url} | Engine: {engine} | Viewport: {device_viewport.upper()}")

        # Step 1: Element Discovery
        page_structure = self.crawl_url(url)

        # Inject Custom Links
        if custom_links:
            for cl in custom_links:
                c_href = cl.get("href") or cl.get("abs_url") or "#"
                c_text = cl.get("text") or "Custom Link"
                c_sel = cl.get("selector") or f"a[href='{c_href}']"
                page_structure.links.append(
                    LinkItem(
                        text=c_text,
                        href=c_href,
                        absolute_url=c_href,
                        is_internal=True,
                        status_code=200,
                        status_msg="Custom Added",
                        css_selector=c_sel
                    )
                )

        # Inject Custom Buttons
        if custom_buttons:
            for cb in custom_buttons:
                c_text = cb.get("text") or "Custom Button"
                c_sel = cb.get("selector") or "button"
                c_tag = cb.get("tag") or "button"
                c_id = cb.get("id") or (c_sel.replace("#", "") if c_sel.startswith("#") else "")
                page_structure.buttons.append(
                    ButtonItem(
                        text=c_text,
                        id=c_id,
                        name="",
                        tag_name=c_tag,
                        button_type="custom",
                        css_selector=c_sel
                    )
                )

        # Inject Custom Inputs
        if custom_inputs:
            for ci in custom_inputs:
                c_type = ci.get("type") or "text"
                c_name = ci.get("name") or "custom_input"
                c_sel = ci.get("selector") or f"input[name='{c_name}']"
                c_id = ci.get("id") or (c_sel.replace("#", "") if c_sel.startswith("#") else "")
                c_placeholder = ci.get("placeholder") or c_name
                page_structure.inputs.append(
                    InputItem(
                        type=c_type,
                        name=c_name,
                        id=c_id,
                        placeholder=c_placeholder,
                        css_selector=c_sel
                    )
                )

        filtered_links = page_structure.links
        if selected_links is not None and len(selected_links) > 0:
            filtered_links = [l for i, l in enumerate(page_structure.links) if i in selected_links]

        filtered_buttons = page_structure.buttons
        if selected_buttons is not None and len(selected_buttons) > 0:
            filtered_buttons = [b for i, b in enumerate(page_structure.buttons) if i in selected_buttons]

        filtered_inputs = page_structure.inputs
        if selected_inputs is not None and len(selected_inputs) > 0:
            filtered_inputs = [inp for i, inp in enumerate(page_structure.inputs) if i in selected_inputs]

        target_page_structure = PageStructure(
            url=page_structure.url,
            title=page_structure.title,
            links=filtered_links,
            buttons=filtered_buttons,
            inputs=filtered_inputs,
            meta=page_structure.meta
        )

        summary = {
            "run_id": run_id,
            "target_url": url,
            "page_title": page_structure.title,
            "engine": engine,
            "login_mode": login_mode,
            "device_viewport": device_viewport,
            "passed_count": 0,
            "failed_count": 0,
            "healed_count": 0,
            "performance_score": 100,
            "accessibility_score": 100,
            "duration_seconds": 0.0,
            "discovered": {
                "total_links": len(page_structure.links),
                "total_buttons": len(page_structure.buttons),
                "total_inputs": len(page_structure.inputs),
                "selected_links_count": len(filtered_links),
                "selected_buttons_count": len(filtered_buttons),
                "selected_inputs_count": len(filtered_inputs),
            },
            "engine_results": {}
        }

        engine_lower = engine.lower()
        test_kwargs = {
            "output_dir": self.output_dir,
            "login_mode": login_mode,
            "custom_credentials": custom_credentials,
            "csv_credentials": csv_credentials,
            "device_viewport": device_viewport,
            "log_callback": log_callback
        }

        perf_scores = []
        acc_scores = []

        if engine_lower in ["selenium", "both"]:
            selenium_engine = SeleniumTestEngine(headless=headless)
            res = selenium_engine.execute_test_suite(target_page_structure, **test_kwargs)
            summary["engine_results"]["selenium"] = res
            summary["passed_count"] += res.get("passed", 0)
            summary["failed_count"] += res.get("failed", 0)
            summary["healed_count"] += res.get("healed_count", 0)
            if res.get("performance", {}).get("performance_score") is not None:
                perf_scores.append(res["performance"]["performance_score"])
            if res.get("accessibility", {}).get("accessibility_score") is not None:
                acc_scores.append(res["accessibility"]["accessibility_score"])

        if engine_lower in ["playwright", "both"]:
            playwright_engine = PlaywrightTestEngine(headless=headless)
            res = playwright_engine.execute_test_suite(target_page_structure, **test_kwargs)
            summary["engine_results"]["playwright"] = res
            summary["passed_count"] += res.get("passed", 0)
            summary["failed_count"] += res.get("failed", 0)
            summary["healed_count"] += res.get("healed_count", 0)
            if res.get("performance", {}).get("performance_score") is not None:
                perf_scores.append(res["performance"]["performance_score"])
            if res.get("accessibility", {}).get("accessibility_score") is not None:
                acc_scores.append(res["accessibility"]["accessibility_score"])

        duration = round(time.time() - start_time, 2)
        summary["duration_seconds"] = duration

        if perf_scores:
            summary["performance_score"] = int(sum(perf_scores) / len(perf_scores))
        if acc_scores:
            summary["accessibility_score"] = int(sum(acc_scores) / len(acc_scores))

        # Save discovery summary JSON
        with open(os.path.join(self.output_dir, "discovery_summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        # Save to SQLite Database
        self.db.save_run(
            run_id=run_id,
            target_url=url,
            page_title=page_structure.title,
            engine=engine,
            login_mode=login_mode,
            passed_count=summary["passed_count"],
            failed_count=summary["failed_count"],
            healed_count=summary["healed_count"],
            performance_score=summary["performance_score"],
            accessibility_score=summary["accessibility_score"],
            duration_seconds=duration,
            summary_data=summary
        )

        # Post Webhook Notification if configured
        if webhook_url:
            if log_callback:
                log_callback("info", f"Posting summary webhook notification to {webhook_url}...")
            self.notifier.send_summary_notification(webhook_url, summary)

        if log_callback:
            log_callback("info", f"Execution Complete in {duration}s! (Passed: {summary['passed_count']}, Perf: {summary['performance_score']}/100, Acc: {summary['accessibility_score']}/100)")

        return summary
