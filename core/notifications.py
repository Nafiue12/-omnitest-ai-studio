import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("WebhookNotifier")

class WebhookNotifier:
    def send_summary_notification(self, webhook_url: str, summary: Dict[str, Any]) -> bool:
        """
        Posts formatted summary card notifications to Slack, Discord, or Microsoft Teams webhooks.
        """
        if not webhook_url or not webhook_url.startswith("http"):
            return False

        try:
            url = summary.get("target_url", "N/A")
            run_id = summary.get("run_id", "N/A")
            engine = summary.get("engine", "both").upper()
            passed = summary.get("passed_count", 0)
            failed = summary.get("failed_count", 0)
            healed = summary.get("healed_count", 0)
            duration = summary.get("duration_seconds", 0)
            perf_score = summary.get("performance_score", 100)
            access_score = summary.get("accessibility_score", 100)

            # Generic Webhook JSON Payload
            payload = {
                "text": f"⚡ *Autonomous Web Testing Agent Report*",
                "attachments": [
                    {
                        "color": "#34d399" if failed == 0 else "#f87171",
                        "title": f"Test Execution Complete - {url}",
                        "fields": [
                            {"title": "Run ID", "value": run_id, "short": True},
                            {"title": "Engine", "value": engine, "short": True},
                            {"title": "Passed Tests", "value": str(passed), "short": True},
                            {"title": "Failed Tests", "value": str(failed), "short": True},
                            {"title": "Self-Healed Selectors", "value": str(healed), "short": True},
                            {"title": "Duration", "value": f"{duration}s", "short": True},
                            {"title": "Performance Score", "value": f"{perf_score}/100", "short": True},
                            {"title": "Accessibility Score", "value": f"{access_score}/100", "short": True}
                        ]
                    }
                ]
            }

            res = requests.post(webhook_url, json=payload, timeout=8)
            if res.status_code < 400:
                logger.info(f"Successfully posted test summary webhook notification to {webhook_url}")
                return True
            else:
                logger.warning(f"Webhook notification returned status {res.status_code}")
                return False

        except Exception as e:
            logger.warning(f"Failed to post webhook notification: {e}")
            return False
