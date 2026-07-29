import sys
import argparse
import json
import os
from core.agent import WebTestingAgent
from core.hf_agent import HuggingFaceTestingAgent

# Force UTF-8 output encoding for Windows terminal compatibility
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(
        description="OmniTest Autonomous Web Testing Agent with AI Prompt Studio"
    )
    parser.add_argument("--prompt", help="Natural language prompt (e.g. 'Test https://example.com buttons with Playwright')")
    parser.add_argument("--url", help="Target URL to test (e.g. https://example.com)")
    parser.add_argument("--engine", choices=["selenium", "playwright", "both"], default="both", help="Automation Engine")
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-32B-Instruct", help="AI Model identifier (e.g. Qwen/Qwen2.5-Coder-32B-Instruct, meta-llama/Llama-3.3-70B-Instruct)")
    parser.add_argument("--no-headless", action="store_true", help="Run browser in visible mode (default: headless)")
    parser.add_argument("--output-dir", default="allure-results", help="Directory to store Allure raw results")
    parser.add_argument("--hf-token", help="Optional Model Provider API Token")

    args = parser.parse_args()

    target_url = args.url or "https://example.com"
    engine = args.engine
    model_info = "Manual Settings"

    # If user provided a natural language prompt, interpret it via AI Agent
    if args.prompt:
        print(f"\n🤖 Interpreting Natural Language Prompt via AI Model ('{args.model}')...")
        hf_agent = HuggingFaceTestingAgent(api_token=args.hf_token, default_model=args.model)
        test_plan = hf_agent.interpret_prompt(args.prompt, fallback_url=target_url, model_name=args.model)
        
        target_url = test_plan.target_url
        engine = test_plan.engine
        model_info = f"{test_plan.model_used} -> {test_plan.explanation}"

    print("=" * 70)
    print("OMNITEST AUTONOMOUS WEB TESTING PLATFORM (AI Prompt Powered)")
    print(f"User Prompt: {args.prompt or 'N/A'}")
    print(f"AI Plan    : {model_info}")
    print(f"Target URL : {target_url}")
    print(f"Engine     : {engine.upper()}")
    print(f"Headless   : {not args.no_headless}")
    print(f"Output Dir : {args.output_dir}")
    print("=" * 70)

    agent = WebTestingAgent(output_dir=args.output_dir)
    results = agent.run(
        url=target_url,
        engine=engine,
        headless=not args.no_headless
    )

    discovered = results.get("discovered", {})
    print("\n[+] DISCOVERY SUMMARY:")
    print(f"  * Page Title      : {results.get('page_title')}")
    print(f"  * Links Found     : {discovered.get('total_links')}")
    print(f"  * Buttons Found   : {discovered.get('total_buttons')}")
    print(f"  * Input Fields    : {discovered.get('total_inputs')}")

    print("\n[+] DISCOVERED LINKS (First 5):")
    for link in discovered.get("links", [])[:5]:
        status = link.get('status_msg') or 'Unchecked'
        print(f"  - [{status}] {link.get('text')} -> {link.get('abs_url')}")

    print("\n[+] DISCOVERED BUTTONS (First 5):")
    for btn in discovered.get("buttons", [])[:5]:
        print(f"  - <{btn.get('tag')}> [{btn.get('type')}] Text: '{btn.get('text')}' (Selector: {btn.get('css_selector')})")

    print("\n[+] ENGINE EXECUTION SUMMARY:")
    for eng_name, eng_res in results.get("engine_results", {}).items():
        print(f"  [{eng_name.upper()}] Passed: {eng_res.get('passed', 0)} | Failed: {eng_res.get('failed', 0)}")

    print("\n[+] ALLURE REPORT GENERATION:")
    print(f"  Raw allure results saved to: {os.path.abspath(args.output_dir)}")
    print("  To generate interactive HTML Allure Report, run:")
    print(f"    allure generate {args.output_dir} --clean -o allure-report")
    print("    allure open allure-report")
    print("=" * 70)

if __name__ == "__main__":
    main()
