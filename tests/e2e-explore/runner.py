"""Browser-Use Scenario Runner.

Liest ein Markdown-Szenario aus scenarios/ ein, faehrt es mit Browser-Use
gegen E2E_BASE_URL und gibt Exit-Code 0 bei Erfolg, 1 bei Fail.

Aufruf:
    python runner.py scenarios/brand_voice_wizard.md
    python runner.py --all  # alle Szenarien sequenziell

Env-Vars (Pflicht):
    ANTHROPIC_API_KEY    - LLM-Backend
    E2E_BASE_URL         - z.B. http://localhost:8601
    E2E_API_KEY          - X-API-Key fuer Tenant-Auth

Optional:
    BROWSER_USE_MAX_STEPS   - Limit (Default 30)
    BROWSER_USE_LLM_MODEL   - Default 'claude-sonnet-4-6'
    BROWSER_USE_HEADLESS    - 'true' (Default in CI) / 'false'
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    from browser_use import Agent, Browser, BrowserConfig
    from langchain_anthropic import ChatAnthropic
except ImportError as e:
    print(f"FEHLER: browser-use oder langchain-anthropic fehlt: {e}", file=sys.stderr)
    print("Installation: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(2)


SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def load_scenario(path: Path) -> tuple[str, str]:
    """Liest Markdown-Szenario und extrahiert Title + Body."""
    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else path.stem
    body = "\n".join(lines[1:]).strip()
    return title, body


def build_prompt(title: str, body: str, base_url: str, api_key: str) -> str:
    """Baut den Browser-Use-Prompt aus dem Szenario."""
    return f"""Szenario: {title}

Du testest die UI von Content Autopilot v2 unter {base_url}.
WICHTIG vor Start: oeffne die DevTools-Console und setze
  localStorage.setItem('apiKey', '{api_key}')
und reloade die Seite, BEVOR du das eigentliche Szenario startest.

Aufgabe:
{body}

Berichte am Ende KURZ:
- 'PASS' wenn das Szenario erfolgreich war
- 'FAIL: <Grund>' wenn es nicht ging
Schreibe keine Romane, nur den Status.
"""


async def run_scenario(scenario_path: Path) -> bool:
    """Fuehrt ein einzelnes Szenario aus. Returnt True bei PASS."""
    base_url = os.environ.get("E2E_BASE_URL", "http://localhost:8601")
    api_key = os.environ.get("E2E_API_KEY", "ci-test-tenant-key")
    max_steps = int(os.environ.get("BROWSER_USE_MAX_STEPS", "30"))
    model = os.environ.get("BROWSER_USE_LLM_MODEL", "claude-sonnet-4-6")
    headless = os.environ.get("BROWSER_USE_HEADLESS", "true").lower() == "true"

    title, body = load_scenario(scenario_path)
    prompt = build_prompt(title, body, base_url, api_key)

    print(f"\n=== Szenario: {title} ===")
    print(f"    Pfad: {scenario_path}")
    print(f"    URL:  {base_url}")
    print(f"    Max-Steps: {max_steps}, Model: {model}, Headless: {headless}")

    browser = Browser(config=BrowserConfig(headless=headless))
    llm = ChatAnthropic(model=model, temperature=0.0)
    agent = Agent(task=prompt, llm=llm, browser=browser, max_actions_per_step=3)

    try:
        result = await agent.run(max_steps=max_steps)
        # Ergebnis-Auswertung — Browser-Use gibt eine final_result-Property
        final = str(result.final_result() or "").strip()
        print(f"\n    Ergebnis: {final[:200]}")
        if final.startswith("PASS"):
            return True
        if final.startswith("FAIL"):
            return False
        # Heuristik: kein klares PASS/FAIL → fail-safe als FAIL werten
        print(f"    [warn] Kein eindeutiges PASS/FAIL — werte als FAIL.")
        return False
    finally:
        await browser.close()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", nargs="?", help="Pfad zum Szenario-MD")
    parser.add_argument("--all", action="store_true", help="Alle Szenarien")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("FEHLER: ANTHROPIC_API_KEY env-var fehlt.", file=sys.stderr)
        return 2

    if args.all:
        scenarios = sorted(SCENARIOS_DIR.glob("*.md"))
    elif args.scenario:
        scenarios = [Path(args.scenario)]
    else:
        parser.error("entweder --all oder einen Szenario-Pfad angeben")

    if not scenarios:
        print(f"Keine Szenarien gefunden in {SCENARIOS_DIR}.", file=sys.stderr)
        return 2

    results = {}
    for sc in scenarios:
        if not sc.exists():
            print(f"FEHLER: {sc} nicht gefunden.", file=sys.stderr)
            results[sc.name] = False
            continue
        results[sc.name] = await run_scenario(sc)

    print("\n=== Zusammenfassung ===")
    for name, passed in results.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")

    all_passed = all(results.values())
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
