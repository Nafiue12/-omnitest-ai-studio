import logging
from typing import Dict, Any, List

logger = logging.getLogger("AccessibilityAuditor")

class AccessibilityAuditor:
    def audit_dom_accessibility(self, page_or_driver, engine_name: str = "playwright") -> Dict[str, Any]:
        """
        Audits DOM elements for WCAG 2.1 accessibility compliance:
        1. Images missing alt attributes.
        2. Form inputs missing labels or aria-label attributes.
        3. Buttons missing accessible names/labels.
        Calculates Accessibility Health Score (0-100) and outputs violation list.
        """
        results = {
            "accessibility_score": 100,
            "total_violations": 0,
            "violations": [],
            "status": "success"
        }

        audit_script = """() => {
            const violations = [];
            
            // 1. Check Images missing alt tags
            const images = document.querySelectorAll('img');
            images.forEach((img, idx) => {
                const alt = img.getAttribute('alt');
                if (alt === null || alt === undefined) {
                    violations.push({
                        type: 'Missing Image Alt Tag',
                        element: img.outerHTML.slice(0, 100),
                        impact: 'critical',
                        help: 'Image elements must have an alt attribute describing their content.'
                    });
                }
            });

            // 2. Check Form Inputs missing labels
            const inputs = document.querySelectorAll('input:not([type="hidden"]), select, textarea');
            inputs.forEach((inp) => {
                const id = inp.getAttribute('id');
                const ariaLabel = inp.getAttribute('aria-label');
                const ariaLabelledBy = inp.getAttribute('aria-labelledby');
                const placeholder = inp.getAttribute('placeholder');
                
                let hasLabel = false;
                if (id) {
                    const label = document.querySelector(`label[for="${id}"]`);
                    if (label) hasLabel = true;
                }
                if (inp.closest('label')) hasLabel = true;
                if (ariaLabel || ariaLabelledBy || placeholder) hasLabel = true;

                if (!hasLabel) {
                    violations.push({
                        type: 'Unlabelled Form Field',
                        element: inp.outerHTML.slice(0, 100),
                        impact: 'serious',
                        help: 'Form field elements must have an associated label or aria-label.'
                    });
                }
            });

            // 3. Check Buttons missing accessible text
            const buttons = document.querySelectorAll('button, a[role="button"], input[type="submit"], input[type="button"]');
            buttons.forEach((btn) => {
                const text = (btn.innerText || btn.getAttribute('value') || btn.getAttribute('aria-label') || '').trim();
                if (!text) {
                    violations.push({
                        type: 'Empty Button / Missing Accessible Name',
                        element: btn.outerHTML.slice(0, 100),
                        impact: 'critical',
                        help: 'Buttons must contain discernable text or an aria-label.'
                    });
                }
            });

            return violations;
        }"""

        try:
            if engine_name.lower() == "playwright":
                violations = page_or_driver.evaluate(audit_script)
            else:
                violations = page_or_driver.execute_script(f"return ({audit_script})();")

            results["violations"] = violations or []
            results["total_violations"] = len(results["violations"])

            # Calculate Accessibility Score (0 - 100)
            score = 100 - (results["total_violations"] * 8)
            results["accessibility_score"] = max(0, score)

        except Exception as e:
            logger.warning(f"Accessibility audit failed: {e}")
            results["status"] = "error"
            results["error_msg"] = str(e)

        return results
