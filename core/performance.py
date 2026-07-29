import logging
from typing import Dict, Any

logger = logging.getLogger("PerformanceAuditor")

class PerformanceAuditor:
    def audit_navigation_timing(self, page_or_driver, engine_name: str = "playwright") -> Dict[str, Any]:
        """
        Extracts Navigation Timing API metrics from browser session.
        Calculates Time To First Byte (TTFB), DOMContentLoaded, Page Load Time, and Performance Score (0-100).
        """
        metrics = {
            "ttfb_ms": 0,
            "dom_content_loaded_ms": 0,
            "load_time_ms": 0,
            "total_entries": 0,
            "performance_score": 100,
            "status": "success"
        }

        try:
            if engine_name.lower() == "playwright":
                timing_data = page_or_driver.evaluate("""() => {
                    const nav = performance.getEntriesByType('navigation')[0];
                    if (nav) {
                        return {
                            ttfb: Math.round(nav.responseStart - nav.requestStart),
                            domContentLoaded: Math.round(nav.domContentLoadedEventEnd - nav.startTime),
                            loadTime: Math.round(nav.loadEventEnd - nav.startTime),
                            entriesCount: performance.getEntries().length
                        };
                    }
                    return null;
                }""")
            else:
                timing_data = page_or_driver.execute_script("""
                    const nav = performance.getEntriesByType('navigation')[0];
                    if (nav) {
                        return {
                            ttfb: Math.round(nav.responseStart - nav.requestStart),
                            domContentLoaded: Math.round(nav.domContentLoadedEventEnd - nav.startTime),
                            loadTime: Math.round(nav.loadEventEnd - nav.startTime),
                            entriesCount: performance.getEntries().length
                        };
                    }
                    return null;
                """)

            if timing_data:
                ttfb = max(0, timing_data.get("ttfb") or 0)
                dom_content = max(0, timing_data.get("domContentLoaded") or 0)
                load_time = max(0, timing_data.get("loadTime") or 0)

                metrics["ttfb_ms"] = ttfb
                metrics["dom_content_loaded_ms"] = dom_content
                metrics["load_time_ms"] = load_time
                metrics["total_entries"] = timing_data.get("entriesCount", 0)

                # Calculate Performance Health Score (0 - 100)
                score = 100
                if load_time > 4000:
                    score -= 35
                elif load_time > 2500:
                    score -= 20
                elif load_time > 1500:
                    score -= 10

                if ttfb > 800:
                    score -= 25
                elif ttfb > 400:
                    score -= 15

                if dom_content > 3000:
                    score -= 20
                elif dom_content > 1800:
                    score -= 10

                metrics["performance_score"] = max(0, score)

        except Exception as e:
            logger.warning(f"Could not extract performance timing metrics: {e}")
            metrics["status"] = "error"
            metrics["error_msg"] = str(e)

        return metrics
