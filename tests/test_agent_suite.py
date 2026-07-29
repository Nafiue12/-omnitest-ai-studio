import os
import pytest
import allure
from core.agent import WebTestingAgent

TARGET_URL = os.getenv("TEST_URL", "https://example.com")
TEST_ENGINE = os.getenv("TEST_ENGINE", "both")

@allure.epic("Automated Web Testing Agent")
@allure.feature("Links & Buttons Auto-Fetch & Execution")
class TestAgentSuite:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = WebTestingAgent(output_dir="allure-results")
        self.page_data = self.agent.crawl_url(TARGET_URL)

    @allure.title("Crawl & Extract Page Structure")
    def test_crawl_structure(self):
        assert self.page_data.title is not None
        assert isinstance(self.page_data.links, list)
        assert isinstance(self.page_data.buttons, list)

    @allure.title("Execute Engine Automation Suite")
    def test_run_engines(self):
        results = self.agent.run(url=TARGET_URL, engine=TEST_ENGINE, headless=True)
        for engine_name, res in results.get("engine_results", {}).items():
            assert res.get("failed", 0) == 0, f"Engine {engine_name} had test failures"
