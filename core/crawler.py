import logging
import urllib.parse
from dataclasses import dataclass
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebCrawler")

@dataclass
class LinkItem:
    text: str
    href: str
    absolute_url: str
    is_internal: bool
    status_code: Optional[int] = None
    status_msg: Optional[str] = None
    css_selector: str = ""

@dataclass
class ButtonItem:
    text: str
    id: str
    name: str
    tag_name: str
    button_type: str
    role: str = ""
    onclick: str = ""
    css_selector: str = ""
    xpath: str = ""

@dataclass
class InputItem:
    type: str
    name: str = ""
    id: str = ""
    placeholder: str = ""
    css_selector: str = ""

@dataclass
class PageStructure:
    url: str
    title: str
    links: List[LinkItem]
    buttons: List[ButtonItem]
    inputs: List[InputItem]
    meta: Dict[str, str]

class WebCrawler:
    def __init__(self, user_agent: Optional[str] = None, timeout: int = 10):
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.timeout = timeout
        self.headers = {"User-Agent": self.user_agent}

    def _fetch_dynamic_html(self, url: str) -> str:
        """Fallback to Playwright headless browser to render dynamic JavaScript SPAs."""
        try:
            from playwright.sync_api import sync_playwright
            logger.info(f"Using headless browser fallback to render dynamic DOM for: {url}")
            with sync_playwright() as p:
                chromium_args = [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--no-first-run",
                    "--no-zygote"
                ]
                browser = p.chromium.launch(headless=True, args=chromium_args)
                context = browser.new_context(user_agent=self.user_agent, ignore_https_errors=True)
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                page = context.new_page()
                try:
                    page.goto(url, wait_until="networkidle", timeout=15000)
                except Exception:
                    page.goto(url, wait_until="load", timeout=15000)
                page.wait_for_timeout(2000)
                content = page.content()
                context.close()
                browser.close()
                return content
        except Exception as e:
            logger.warning(f"Headless Playwright DOM fetch failed: {e}")
            return ""

    def fetch_and_parse(self, url: str, check_links: bool = True) -> PageStructure:
        """Fetches target URL, parses HTML, extracts links, buttons, inputs. Supports dynamic JS sites."""
        logger.info(f"Crawling URL: {url}")
        
        parsed_base = urllib.parse.urlparse(url)
        base_domain = parsed_base.netloc
        html_text = ""

        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            if response.status_code == 200:
                html_text = response.text
        except Exception as ex:
            logger.warning(f"Static HTTP request failed for {url}: {ex}. Trying headless browser fallback...")

        # If static request failed or returned empty DOM, fallback to Playwright headless browser
        if not html_text or len(html_text) < 300:
            html_text = self._fetch_dynamic_html(url)

        soup = BeautifulSoup(html_text or "<html></html>", "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else "No Title"

        # Check if static HTML produced zero interactive elements (likely dynamic SPA app)
        initial_buttons = len(soup.find_all(["button", "input"]))
        initial_links = len(soup.find_all("a", href=True))
        if initial_buttons == 0 and initial_links == 0:
            dynamic_html = self._fetch_dynamic_html(url)
            if dynamic_html:
                html_text = dynamic_html
                soup = BeautifulSoup(html_text, "html.parser")
                title = soup.title.string.strip() if soup.title and soup.title.string else title

        # 1. Links Extraction
        links: List[LinkItem] = []
        for index, a_tag in enumerate(soup.find_all("a", href=True)):
            href = a_tag["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            text = a_tag.get_text(strip=True) or (a_tag.get("title") or "Unnamed Link")
            abs_url = urllib.parse.urljoin(url, href)
            is_internal = urllib.parse.urlparse(abs_url).netloc == base_domain

            # Build simple CSS selector
            elem_id = a_tag.get("id")
            if elem_id:
                selector = f"#{elem_id}"
            else:
                selector = f"a:nth-of-type({index + 1})"

            links.append(LinkItem(
                text=text,
                href=href,
                absolute_url=abs_url,
                is_internal=is_internal,
                css_selector=selector
            ))

        # Check HTTP status for first N links to identify broken links
        if check_links:
            self._verify_links(links[:20])

        # 2. Buttons Extraction
        buttons: List[ButtonItem] = []
        
        # Standard <button> tags
        for idx, btn in enumerate(soup.find_all("button")):
            text = btn.get_text(strip=True) or btn.get("value", "") or btn.get("aria-label", f"Button-{idx+1}")
            b_id = btn.get("id", "")
            b_name = btn.get("name", "")
            b_type = btn.get("type", "button")
            b_role = btn.get("role", "button")
            b_onclick = btn.get("onclick", "")
            
            selector = f"#{b_id}" if b_id else f"button:nth-of-type({idx+1})"
            xpath = f"//*[@id='{b_id}']" if b_id else f"//button[{idx+1}]"

            buttons.append(ButtonItem(
                text=text,
                id=b_id,
                name=b_name,
                tag_name="button",
                button_type=b_type,
                role=b_role,
                onclick=b_onclick,
                css_selector=selector,
                xpath=xpath
            ))

        # <input type="button|submit|reset">
        for idx, inp in enumerate(soup.find_all("input", type=["button", "submit", "reset"])):
            text = inp.get("value", "") or inp.get("name", f"InputBtn-{idx+1}")
            b_id = inp.get("id", "")
            b_name = inp.get("name", "")
            b_type = inp.get("type", "button")
            
            selector = f"#{b_id}" if b_id else f"input[type='{b_type}']:nth-of-type({idx+1})"
            xpath = f"//*[@id='{b_id}']" if b_id else f"//input[@type='{b_type}'][{idx+1}]"

            buttons.append(ButtonItem(
                text=text,
                id=b_id,
                name=b_name,
                tag_name="input",
                button_type=b_type,
                role="button",
                onclick=inp.get("onclick", ""),
                css_selector=selector,
                xpath=xpath
            ))

        # Elements with role="button" or onclick attributes
        for idx, role_btn in enumerate(soup.find_all(attrs={"role": "button"})):
            if role_btn.name in ["button", "input"]:
                continue
            text = role_btn.get_text(strip=True) or f"RoleButton-{idx+1}"
            b_id = role_btn.get("id", "")
            selector = f"#{b_id}" if b_id else f"{role_btn.name}[role='button']:nth-of-type({idx+1})"
            xpath = f"//*[@id='{b_id}']" if b_id else f"//{role_btn.name}[@role='button'][{idx+1}]"

            buttons.append(ButtonItem(
                text=text,
                id=b_id,
                name=role_btn.get("name", ""),
                tag_name=role_btn.name,
                button_type="role-button",
                role="button",
                onclick=role_btn.get("onclick", ""),
                css_selector=selector,
                xpath=xpath
            ))

        # 3. Inputs Extraction
        inputs: List[InputItem] = []
        for idx, inp in enumerate(soup.find_all(["input", "textarea", "select"])):
            inp_type = inp.get("type", inp.name)
            if inp_type in ["button", "submit", "reset", "hidden"]:
                continue
            b_id = inp.get("id", "")
            b_name = inp.get("name", "")
            placeholder = inp.get("placeholder", "")
            selector = f"#{b_id}" if b_id else f"{inp.name}:nth-of-type({idx+1})"

            inputs.append(InputItem(
                type=inp_type,
                name=b_name,
                id=b_id,
                placeholder=placeholder,
                css_selector=selector
            ))

        # Meta attributes
        meta = {
            "description": "",
            "keywords": ""
        }
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            meta["description"] = meta_desc.get("content", "")

        return PageStructure(
            url=url,
            title=title,
            links=links,
            buttons=buttons,
            inputs=inputs,
            meta=meta
        )

    def _verify_links(self, links: List[LinkItem]):
        """Helper to quickly check HTTP response status of discovered links."""
        for item in links:
            try:
                res = requests.head(item.absolute_url, headers=self.headers, timeout=5, allow_redirects=True)
                if res.status_code >= 400:
                    res = requests.get(item.absolute_url, headers=self.headers, timeout=5)
                item.status_code = res.status_code
                item.status_msg = "OK" if res.status_code < 400 else f"HTTP {res.status_code}"
            except Exception as e:
                item.status_code = 0
                item.status_msg = f"Failed: {str(e)}"
