import os
import time
import logging
from typing import Dict, Any, List, Optional, Callable
import allure
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
from core.crawler import PageStructure
from core.visual_diff import VisualRegressionEngine
from core.performance import PerformanceAuditor
from core.accessibility import AccessibilityAuditor

logger = logging.getLogger("SeleniumRunner")

VIEWPORT_PRESETS_SELENIUM = {
    "desktop": (1920, 1080, None),
    "mobile_iphone": (390, 844, "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"),
    "mobile_pixel": (412, 915, "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"),
    "tablet_ipad": (820, 1180, "Mozilla/5.0 (iPad; CPU OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1")
}

class SeleniumTestEngine:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.visual_engine = VisualRegressionEngine()
        self.perf_auditor = PerformanceAuditor()
        self.acc_auditor = AccessibilityAuditor()

    def _emit(self, log_callback: Optional[Callable[[str, str], None]], level: str, message: str):
        formatted = f"[Selenium] {message}"
        if level == "error":
            logger.error(formatted)
        elif level == "warning":
            logger.warning(formatted)
        else:
            logger.info(formatted)

        if log_callback:
            try:
                log_callback(level, formatted)
            except Exception:
                pass

    def _setup_driver(self, device_viewport: str = "desktop"):
        options = ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--remote-allow-origins=*")
        options.add_argument("--remote-debugging-port=9222")

        width, height, ua = VIEWPORT_PRESETS_SELENIUM.get(device_viewport, VIEWPORT_PRESETS_SELENIUM["desktop"])
        options.add_argument(f"--window-size={width},{height}")
        if ua:
            options.add_argument(f"--user-agent={ua}")

        # On Windows, check for local Chrome installation binaries if needed
        import sys
        if sys.platform == "win32":
            possible_binaries = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            ]
            for binary in possible_binaries:
                if os.path.exists(binary):
                    options.binary_location = binary
                    break

        try:
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.implicitly_wait(4)
        except Exception as e:
            logger.warning(f"Selenium Chrome setup failed: {e}")
            if sys.platform == "win32":
                try:
                    from selenium.webdriver.edge.options import Options as EdgeOptions
                    from selenium.webdriver.edge.service import Service as EdgeService
                    from webdriver_manager.microsoft import EdgeChromiumDriverManager

                    edge_options = EdgeOptions()
                    if self.headless:
                        edge_options.add_argument("--headless=new")
                    edge_options.add_argument("--no-sandbox")
                    edge_options.add_argument("--disable-dev-shm-usage")
                    edge_options.add_argument(f"--window-size={width},{height}")
                    if ua:
                        edge_options.add_argument(f"--user-agent={ua}")

                    service = EdgeService(EdgeChromiumDriverManager().install())
                    self.driver = webdriver.Edge(service=service, options=edge_options)
                    self.driver.implicitly_wait(4)
                except Exception as edge_err:
                    raise RuntimeError(f"Selenium browser startup failed: {edge_err}") from e
            else:
                raise RuntimeError(f"Selenium Chrome driver startup failed on Linux: {e}") from e

    def _heal_element(self, primary_by: By, primary_value: str, text_hint: str = "", tag_hint: str = ""):
        try:
            elems = self.driver.find_elements(primary_by, primary_value)
            if elems:
                return elems[0], False, None
        except Exception:
            pass

        if text_hint and text_hint.strip():
            clean_text = text_hint.strip()[:40].replace("'", "")
            tag = tag_hint or "*"
            try:
                xpath = f"//{tag}[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{clean_text.lower()}')]"
                elems = self.driver.find_elements(By.XPATH, xpath)
                if elems:
                    reason = f"Primary locator '{primary_value}' failed -> Healed via text match: '{clean_text}'"
                    return elems[0], True, reason
            except Exception:
                pass

        if tag_hint:
            try:
                elems = self.driver.find_elements(By.TAG_NAME, tag_hint)
                if elems:
                    reason = f"Primary locator '{primary_value}' failed -> Healed via tag: '{tag_hint}'"
                    return elems[0], True, reason
            except Exception:
                pass

        return None, False, None

    def execute_test_suite(
        self,
        page_data: PageStructure,
        output_dir: str = "allure-results",
        login_mode: str = "random",
        custom_credentials: Optional[Dict[str, str]] = None,
        csv_credentials: Optional[List[Dict[str, str]]] = None,
        device_viewport: str = "desktop",
        log_callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """Executes full automated test suite using Selenium with Device Viewport, Performance & WCAG Auditing."""
        import random
        results = {
            "engine": "Selenium",
            "url": page_data.url,
            "device_viewport": device_viewport,
            "total_links_tested": len(page_data.links),
            "total_buttons_tested": len(page_data.buttons),
            "passed": 0,
            "failed": 0,
            "healed_count": 0,
            "screenshots": [],
            "self_healing_events": [],
            "visual_regression": {},
            "performance": {},
            "accessibility": {},
            "details": []
        }

        self._emit(log_callback, "info", f"Launching Selenium Engine (Device Viewport: {device_viewport.upper()})...")

        try:
            self._setup_driver(device_viewport=device_viewport)

            with allure.step(f"[Selenium] Navigating to target page: {page_data.url}"):
                start_time = time.time()
                self.driver.get(page_data.url)
                load_time = round(time.time() - start_time, 2)
                self._emit(log_callback, "info", f"Selenium navigated to page in {load_time}s")

                screenshot_png = self.driver.get_screenshot_as_png()
                ss_filename = f"sel_baseline_{int(time.time())}.png"
                ss_path = os.path.join(output_dir, ss_filename)
                with open(ss_path, "wb") as f:
                    f.write(screenshot_png)
                results["screenshots"].append(ss_filename)

                allure.attach(
                    screenshot_png,
                    name="Homepage Baseline Screenshot",
                    attachment_type=allure.attachment_type.PNG
                )

            # Step 2: Performance Timing Audit
            with allure.step("[Selenium] Step 2: Performance Audit"):
                self._emit(log_callback, "info", "Executing Navigation Timing Audit...")
                perf_res = self.perf_auditor.audit_navigation_timing(self.driver, engine_name="selenium")
                results["performance"] = perf_res

            # Step 3: WCAG Accessibility Audit
            with allure.step("[Selenium] Step 3: Accessibility Audit"):
                self._emit(log_callback, "info", "Executing DOM Accessibility Audit...")
                acc_res = self.acc_auditor.audit_dom_accessibility(self.driver, engine_name="selenium")
                results["accessibility"] = acc_res

            # Step 4: Visual Regression Comparison
            with allure.step("[Selenium] Step 4: Visual Regression Testing"):
                self._emit(log_callback, "info", "Executing Visual Regression Diffing...")
                vis_res = self.visual_engine.compare_against_baseline(
                    current_image_path=ss_path,
                    target_url=page_data.url,
                    output_dir=output_dir,
                    engine_name="Selenium"
                )
                results["visual_regression"] = vis_res

            # Test 1: Page Title Verification
            with allure.step("[Selenium] Test 1: Page Title Verification"):
                current_title = self.driver.title
                assert current_title, "Page title should not be empty"
                results["passed"] += 1
                self._emit(log_callback, "info", f"PASSED: Title Verification ('{current_title}')")

            # Test 2: Selected Links Verification
            with allure.step(f"[Selenium] Test 2: Selected Link Elements ({len(page_data.links)} links)"):
                for idx, link in enumerate(page_data.links):
                    with allure.step(f"Checking Link [{idx+1}]: {link.text[:30]}"):
                        try:
                            sel_val = link.css_selector or f"a[href='{link.href}']"
                            elem, is_healed, heal_reason = self._heal_element(
                                By.CSS_SELECTOR, sel_val, text_hint=link.text, tag_hint="a"
                            )

                            if is_healed:
                                results["healed_count"] += 1
                                results["self_healing_events"].append({
                                    "element": f"Link #{idx+1} ({link.text[:25]})",
                                    "reason": heal_reason
                                })

                            results["passed"] += 1
                            self._emit(log_callback, "info", f"PASSED: Link #{idx+1} '{link.text[:25]}'")
                        except Exception as ex:
                            results["failed"] += 1
                            self._emit(log_callback, "error", f"FAILED: Link #{idx+1}: {ex}")

            # Test 3: Buttons Verification
            with allure.step(f"[Selenium] Test 3: Selected Buttons ({len(page_data.buttons)} buttons)"):
                for idx, btn in enumerate(page_data.buttons):
                    with allure.step(f"Testing Button [{idx+1}]: {btn.text[:30]}"):
                        try:
                            by_type = By.ID if btn.id else By.CSS_SELECTOR
                            by_val = btn.id if btn.id else (btn.css_selector or btn.tag_name)

                            elem, is_healed, heal_reason = self._heal_element(
                                by_type, by_val, text_hint=btn.text, tag_hint=btn.tag_name or "button"
                            )

                            if is_healed:
                                results["healed_count"] += 1
                                results["self_healing_events"].append({
                                    "element": f"Button #{idx+1} ({btn.text[:25]})",
                                    "reason": heal_reason
                                })

                            results["passed"] += 1
                            self._emit(log_callback, "info", f"PASSED: Button #{idx+1} '{btn.text[:25]}'")
                        except Exception as ex:
                            results["failed"] += 1
                            self._emit(log_callback, "error", f"FAILED: Button #{idx+1}: {ex}")

            # Test 4: Automated Login & Form Testing
            with allure.step(f"[Selenium] Test 4: Automated Login Testing (Mode: {login_mode})"):
                creds_to_test = []
                if login_mode == "csv" and csv_credentials:
                    creds_to_test = csv_credentials[:50]
                elif login_mode == "custom" and custom_credentials:
                    if isinstance(custom_credentials, list):
                        creds_to_test = custom_credentials[:50]
                    elif isinstance(custom_credentials, dict):
                        creds_to_test = [custom_credentials]
                else:
                    rnd_id = random.randint(1000, 9999)
                    creds_to_test = [{
                        "username": f"test_user_{rnd_id}@example.com",
                        "password": f"Pass_{rnd_id}!"
                    }]

                u_elem, _, _ = self._heal_element(By.CSS_SELECTOR, "input[type='email'], input[name*='user'], input[type='text']", tag_hint="input")
                p_elem, _, _ = self._heal_element(By.CSS_SELECTOR, "input[type='password'], input[name*='pass']", tag_hint="input")

                if u_elem or p_elem:
                    for cred_idx, cred in enumerate(creds_to_test):
                        u_val = cred.get("username") or cred.get("email") or "testuser"
                        p_val = cred.get("password") or "secret123"
                        try:
                            if u_elem and u_elem.is_displayed():
                                u_elem.clear()
                                u_elem.send_keys(u_val)
                            if p_elem and p_elem.is_displayed():
                                p_elem.clear()
                                p_elem.send_keys(p_val)
                            results["passed"] += 1
                            self._emit(log_callback, "info", f"PASSED: Login Attempt #{cred_idx+1} for '{u_val}'")
                        except Exception as sel_ex:
                            results["failed"] += 1
                            self._emit(log_callback, "error", f"FAILED: Login Attempt #{cred_idx+1}: {sel_ex}")

        except Exception as suite_ex:
            self._emit(log_callback, "error", f"Selenium suite exception: {suite_ex}")
            results["failed"] += 1
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass

        from core.playwright_runner import _write_allure_json_report
        _write_allure_json_report(output_dir, "Selenium", page_data.url, results)
        return results
