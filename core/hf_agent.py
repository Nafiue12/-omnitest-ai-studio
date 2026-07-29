import re
import json
import logging
import urllib.parse
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("HuggingFaceAgent")

# Default serverless supported Hugging Face model
DEFAULT_HF_MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"

FALLBACK_MODELS = [
    "Qwen/Qwen2.5-Coder-32B-Instruct",
    "deepseek-ai/DeepSeek-R1",
    "meta-llama/Llama-3.3-70B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-Coder-7B-Instruct"
]

@dataclass
class AITestPlan:
    prompt: str
    target_url: str
    engine: str  # 'selenium', 'playwright', 'both'
    test_links: bool
    test_buttons: bool
    test_inputs: bool
    check_accessibility: bool
    check_performance: bool
    link_filter: Optional[str]
    button_filter: Optional[str]
    model_used: str
    explanation: str

class HuggingFaceTestingAgent:
    """
    AI Agent powered by Hugging Face lightweight free models to interpret
    natural language prompts and automatically trigger web test execution plans.
    """
    def __init__(self, api_token: Optional[str] = None, default_model: str = DEFAULT_HF_MODEL):
        self.api_token = api_token
        self.default_model = default_model
        self._inference_client = None
        self._init_client()

    def _init_client(self):
        try:
            from huggingface_hub import InferenceClient
            # Initialize InferenceClient (token optional for public free models)
            self._inference_client = InferenceClient(token=self.api_token)
            logger.info(f"Initialized HuggingFace InferenceClient with model: {self.default_model}")
        except Exception as e:
            logger.warning(f"Could not initialize HuggingFace InferenceClient: {e}")
            self._inference_client = None

    def interpret_prompt(self, prompt: str, fallback_url: str = "https://example.com", model_name: Optional[str] = None) -> AITestPlan:
        """
        Takes a natural language prompt from the user and extracts an automated execution plan.
        Tries Hugging Face model inference first, falling back to smart NLP parsing.
        """
        selected_model = model_name or self.default_model
        logger.info(f"Interpreting user prompt with HuggingFace AI (Model: {selected_model}): '{prompt}'")
        
        # 1. Try Hugging Face Inference API
        plan_dict = None
        used_model = "Smart NLP Parser (Offline Fallback)"

        if self._inference_client:
            candidate_models = [selected_model] + [m for m in FALLBACK_MODELS if m != selected_model]
            for m_name in candidate_models:
                try:
                    plan_dict = self._call_hf_model(m_name, prompt, fallback_url)
                    if plan_dict and plan_dict.get("target_url"):
                        used_model = f"AI Model ({m_name})"
                        logger.info(f"Successfully received plan from AI model: {m_name}")
                        break
                except Exception as ex:
                    logger.warning(f"AI model {m_name} call failed/rate limited: {ex}")

        # 2. Fallback to smart rule-based NLP parser if HF API call unavailable
        if not plan_dict:
            plan_dict = self._parse_prompt_fallback(prompt, fallback_url)

        return AITestPlan(
            prompt=prompt,
            target_url=plan_dict.get("target_url", fallback_url),
            engine=plan_dict.get("engine", "both"),
            test_links=plan_dict.get("test_links", True),
            test_buttons=plan_dict.get("test_buttons", True),
            test_inputs=plan_dict.get("test_inputs", True),
            check_accessibility=plan_dict.get("check_accessibility", True),
            check_performance=plan_dict.get("check_performance", True),
            link_filter=plan_dict.get("link_filter"),
            button_filter=plan_dict.get("button_filter"),
            model_used=used_model,
            explanation=plan_dict.get("explanation", f"Converted prompt into test plan for {plan_dict.get('target_url')}")
        )

    def _call_hf_model(self, model_name: str, prompt: str, fallback_url: str) -> Optional[Dict[str, Any]]:
        system_instruction = (
            "You are a web test automation assistant. "
            "Convert the user prompt into a valid JSON test plan with keys: "
            "target_url (string), engine ('selenium'|'playwright'|'both'), "
            "test_links (bool), test_buttons (bool), test_inputs (bool), "
            "check_accessibility (bool), check_performance (bool), "
            "link_filter (string or null), button_filter (string or null), explanation (string). "
            "Return ONLY the JSON object, no conversational markdown text."
        )

        user_message = f"User Request: {prompt}\nDefault URL if not specified: {fallback_url}"
        
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_message}
        ]

        response = self._inference_client.chat_completion(
            messages=messages,
            model=model_name,
            max_tokens=350,
            temperature=0.1
        )

        content = response.choices[0].message.content.strip()
        
        # Extract JSON substring
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        return json.loads(content)

    def _parse_prompt_fallback(self, prompt: str, fallback_url: str) -> Dict[str, Any]:
        """Smart rule-based NLP prompt parser fallback."""
        prompt_lower = prompt.lower()

        # 1. Extract URL
        url_match = re.search(r'https?://[^\s,"]+', prompt)
        if url_match:
            target_url = url_match.group(0).rstrip(".")
        else:
            domain_match = re.search(r'(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}', prompt)
            if domain_match:
                target_url = f"https://{domain_match.group(0)}"
            else:
                target_url = fallback_url

        # 2. Extract Automation Engine
        engine = "both"
        if "selenium" in prompt_lower and "playwright" not in prompt_lower:
            engine = "selenium"
        elif "playwright" in prompt_lower and "selenium" not in prompt_lower:
            engine = "playwright"

        # 3. Features to test
        test_links = True
        test_buttons = True
        test_inputs = True
        
        if "only link" in prompt_lower or "just link" in prompt_lower:
            test_buttons = False
            test_inputs = False
        elif "only button" in prompt_lower or "just button" in prompt_lower:
            test_links = False
            test_inputs = False
        elif "form" in prompt_lower or "input" in prompt_lower:
            test_inputs = True

        check_accessibility = "accessib" in prompt_lower or "a11y" in prompt_lower or "contrast" in prompt_lower
        check_performance = "perform" in prompt_lower or "speed" in prompt_lower or "load" in prompt_lower or "metric" in prompt_lower

        # Default features enabled if general test requested
        if not check_accessibility and not check_performance:
            check_accessibility = True
            check_performance = True

        # Extract keyword filters (e.g. "links containing login", "buttons named submit")
        link_filter = None
        link_match = re.search(r'links?\s+(?:containing|with|named)\s+["\']?([^"\'\s,]+)["\']?', prompt_lower)
        if link_match:
            link_filter = link_match.group(1)

        button_filter = None
        btn_match = re.search(r'buttons?\s+(?:containing|with|named)\s+["\']?([^"\'\s,]+)["\']?', prompt_lower)
        if btn_match:
            button_filter = btn_match.group(1)

        return {
            "target_url": target_url,
            "engine": engine,
            "test_links": test_links,
            "test_buttons": test_buttons,
            "test_inputs": test_inputs,
            "check_accessibility": check_accessibility,
            "check_performance": check_performance,
            "link_filter": link_filter,
            "button_filter": button_filter,
            "explanation": f"Smart AI parsed target '{target_url}' with {engine.upper()} engine."
        }
