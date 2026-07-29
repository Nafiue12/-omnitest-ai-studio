import os
import re
import logging
from typing import Dict, Any
from PIL import Image, ImageChops

logger = logging.getLogger("VisualRegressionEngine")

class VisualRegressionEngine:
    def __init__(self, baselines_dir: str = "baselines"):
        self.baselines_dir = os.path.abspath(baselines_dir)
        os.makedirs(self.baselines_dir, exist_ok=True)

    def _url_to_slug(self, url: str, engine_suffix: str = "") -> str:
        """Converts target URL into a safe filename slug for baseline storage."""
        slug = re.sub(r'[^a-zA-Z0-9]', '_', url.replace('https://', '').replace('http://', ''))
        slug = re.sub(r'_+', '_', slug).strip('_')[:50]
        if engine_suffix:
            return f"{slug}_{engine_suffix}.png"
        return f"{slug}.png"

    def compare_against_baseline(
        self,
        current_image_path: str,
        target_url: str,
        output_dir: str,
        engine_name: str = "playwright",
        tolerance: float = 0.05
    ) -> Dict[str, Any]:
        """
        Compares current screenshot against stored URL baseline image.
        If baseline does not exist, saves current image as new baseline.
        If baseline exists, computes pixel mismatch %, generates diff overlay mask image,
        and returns visual comparison metrics.
        """
        if not os.path.exists(current_image_path):
            return {
                "status": "error",
                "message": f"Current screenshot not found at {current_image_path}",
                "mismatch_percentage": 0.0,
                "visual_status": "ERROR"
            }

        baseline_filename = self._url_to_slug(target_url, engine_name.lower())
        baseline_path = os.path.join(self.baselines_dir, baseline_filename)

        # Case 1: First run - save baseline image
        if not os.path.exists(baseline_path):
            try:
                with Image.open(current_image_path) as img:
                    img.convert("RGB").save(baseline_path)
                logger.info(f"Created new visual baseline: {baseline_path}")
                return {
                    "status": "baseline_created",
                    "baseline_filename": baseline_filename,
                    "baseline_path": baseline_path,
                    "mismatch_percentage": 0.0,
                    "visual_status": "NEW_BASELINE",
                    "diff_filename": None,
                    "message": "First execution: Established baseline screenshot."
                }
            except Exception as e:
                logger.error(f"Failed to create baseline image: {e}")
                return {
                    "status": "error",
                    "message": str(e),
                    "mismatch_percentage": 0.0,
                    "visual_status": "ERROR"
                }

        # Case 2: Baseline exists - run pixel-by-pixel diffing safely
        try:
            current_img = Image.open(current_image_path).convert("RGB")
            baseline_img = Image.open(baseline_path).convert("RGB")

            # Normalize dimensions if they differ slightly
            width = max(current_img.width, baseline_img.width)
            height = max(current_img.height, baseline_img.height)

            if current_img.size != (width, height):
                current_img = current_img.resize((width, height), Image.Resampling.LANCZOS)
            if baseline_img.size != (width, height):
                baseline_img = baseline_img.resize((width, height), Image.Resampling.LANCZOS)

            # Compute difference mask
            diff_img = ImageChops.difference(current_img, baseline_img)

            threshold = 255 * 3 * tolerance
            differing_pixels = 0
            total_pixels = width * height

            overlay = Image.new("RGB", (width, height), (0, 0, 0))
            overlay_pixels = overlay.load()
            current_pixels = current_img.load()
            diff_pixels_raw = diff_img.load()

            for y in range(height):
                for x in range(width):
                    p_diff = diff_pixels_raw[x, y]
                    # Safely sum RGB channels regardless of 3-tuple vs 4-tuple format
                    diff_sum = p_diff[0] + p_diff[1] + p_diff[2]

                    if diff_sum > threshold:
                        differing_pixels += 1
                        overlay_pixels[x, y] = (236, 72, 153)  # Highlight in magenta/pink
                    else:
                        p_curr = current_pixels[x, y]
                        overlay_pixels[x, y] = (
                            int(p_curr[0] * 0.4),
                            int(p_curr[1] * 0.4),
                            int(p_curr[2] * 0.4)
                        )

            mismatch_pct = round((differing_pixels / total_pixels) * 100, 2)

            diff_filename = f"vis_diff_{engine_name.lower()}_{int(os.path.getmtime(current_image_path))}.png"
            diff_output_path = os.path.join(output_dir, diff_filename)
            overlay.save(diff_output_path)

            # Close image file handlers
            current_img.close()
            baseline_img.close()
            diff_img.close()

            # Determine visual status badge
            if mismatch_pct == 0.0:
                visual_status = "PASSED"
            elif mismatch_pct <= 2.0:
                visual_status = "MINOR_DIFF"
            elif mismatch_pct <= 5.0:
                visual_status = "VISUAL_WARNING"
            else:
                visual_status = "VISUAL_FAIL"

            logger.info(f"Visual Diff Result: {mismatch_pct}% mismatch | Status: {visual_status}")

            return {
                "status": "success",
                "mismatch_percentage": mismatch_pct,
                "visual_status": visual_status,
                "baseline_filename": baseline_filename,
                "baseline_path": baseline_path,
                "diff_filename": diff_filename,
                "diff_path": diff_output_path,
                "differing_pixels": differing_pixels,
                "total_pixels": total_pixels
            }

        except Exception as e:
            logger.error(f"Error during visual regression diffing: {e}")
            return {
                "status": "error",
                "message": str(e),
                "mismatch_percentage": 0.0,
                "visual_status": "ERROR"
            }
