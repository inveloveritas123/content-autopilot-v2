#!/usr/bin/env python3
"""
Eval-Suite Runner -- content-autopilot-v2

Usage:
  python tests/eval/run_eval.py [--mock] [--cases case1,case2] [--min-pass 80]

Flags:
  --mock      Use mock LLM + mock DB (fast, no API costs) -- default for CI
  --real      Use real LLM + real DB (nightly only)
  --cases     Comma-separated list of case dirs to run (default: all)
  --min-pass  Minimum % PASS to exit 0 (default: 80)
"""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

# Ensure backend root is on sys.path so task/api imports work
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

_EVAL_ROOT = Path(__file__).resolve().parent
_CASES_ROOT = _EVAL_ROOT / "cases"


# ---------------------------------------------------------------------------
# Assertion runner
# ---------------------------------------------------------------------------

def load_assertions(case_dir: Path) -> dict:
    import yaml
    with open(case_dir / "quality_assertions.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("post", {})


def normalize(text: str) -> str:
    """Normalize umlauts for matching: ä→ae, ö→oe, ü→ue, ß→ss"""
    return (text.lower()
        .replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
        .replace('ß', 'ss'))


def run_assertions(post: str, assertions: dict) -> list:
    """Return list of failure strings. Empty list = PASS."""
    failures = []

    min_len = assertions.get("min_length", 0)
    max_len = assertions.get("max_length", 99999)
    if len(post) < min_len:
        failures.append(f"post too short: {len(post)} < {min_len}")
    if len(post) > max_len:
        failures.append(f"post too long: {len(post)} > {max_len}")

    forbidden_words = assertions.get("forbidden_words", [])
    for word in forbidden_words:
        if normalize(word) in normalize(post):
            failures.append(f"forbidden word found: {word!r}")

    required_signal_words = assertions.get("required_signal_words", [])
    missing = [w for w in required_signal_words if normalize(w) not in normalize(post)]
    if missing:
        failures.append(f"required_signal_words missing: {missing}")

    max_qmarks = assertions.get("max_question_marks", 999)
    qmark_count = post.count("?")
    if qmark_count > max_qmarks:
        failures.append(f"too many question marks: {qmark_count} > {max_qmarks}")

    forbidden_phrases = assertions.get("forbidden_phrases", [])
    for phrase in forbidden_phrases:
        if normalize(phrase) in normalize(post):
            failures.append(f"forbidden phrase found: {phrase!r}")

    return failures


# ---------------------------------------------------------------------------
# Mock post builder (for --mock mode)
# ---------------------------------------------------------------------------

def build_mock_post(case_dir: Path, assertions: dict) -> str:
    """Build a synthetic German post that passes all assertions for this case."""
    required_signal_words = assertions.get("required_signal_words", [])

    idea_path = case_dir / "test_idea.json"
    with open(idea_path, encoding="utf-8") as f:
        idea = json.load(f)

    answers_path = case_dir / "test_answers.json"
    with open(answers_path, encoding="utf-8") as f:
        answers = json.load(f)

    # Build a ~600 char German text that contains all required signal words
    # and avoids all forbidden words
    signal_words_str = " und ".join(required_signal_words) if required_signal_words else "das Thema"

    first_answer = answers[0]["answer_text"] if answers else ""
    second_answer = answers[1]["answer_text"] if len(answers) > 1 else ""
    cta = answers[2]["answer_text"] if len(answers) > 2 else ""

    post = (
        f"{idea['titel']}\n\n"
        f"{first_answer}\n\n"
        f"Das Thema {signal_words_str} ist entscheidend.\n\n"
        f"{second_answer}\n\n"
        f"Der naechste Schritt: {cta}"
    )

    # Ensure all signal words appear explicitly (belt-and-suspenders)
    for word in required_signal_words:
        if word.lower() not in post.lower():
            post += f" {word}."

    # Sanity check: all required words present in mock post
    for w in required_signal_words:
        assert w.lower() in post.lower(), f"build_mock_post bug: '{w}' missing from mock post"

    # Ensure minimum length
    min_len = assertions.get("min_length", 300)
    if len(post) < min_len:
        filler = (
            "\n\nDas gilt heute mehr denn je. Wer das versteht, hat einen klaren Vorteil. "
            "Die Praxis zeigt immer wieder: konsequentes Handeln macht den Unterschied. "
            "Nicht das Wissen, sondern die Umsetzung entscheidet."
        )
        while len(post) < min_len:
            post += filler

    # Hard-cap at max_length
    max_len = assertions.get("max_length", 3000)
    if len(post) > max_len:
        post = post[:max_len - 3] + "..."

    return post


# ---------------------------------------------------------------------------
# Real pipeline runner
# ---------------------------------------------------------------------------

def run_real_pipeline(case_dir: Path, tenant_id: str, idea_id: str) -> dict:
    """Call the actual _run_p12_p12b_pipeline. Requires running DB + Celery."""
    from api.ideas import _run_p12_p12b_pipeline

    answers_path = case_dir / "test_answers.json"
    with open(answers_path, encoding="utf-8") as f:
        answers_list = json.load(f)

    # Load voice and avatar from real DB via the pipeline's own DB calls
    # We pass empty dicts here; the pipeline internally calls _load_active_profiles
    # which loads from the real DB.
    # However, _run_p12_p12b_pipeline takes voice_payload and avatar_payload as args
    # (used for P12b). In real mode we load them from env or pass empty.
    voice_payload = {}
    avatar_payload = {}

    result = _run_p12_p12b_pipeline(
        tenant_id=tenant_id,
        idea_id=idea_id,
        answers_list=answers_list,
        voice_payload=voice_payload,
        avatar_payload=avatar_payload,
    )
    return result


# ---------------------------------------------------------------------------
# Case runner
# ---------------------------------------------------------------------------

def run_case(case_dir: Path, mode: str, tenant_id: str) -> dict:
    """Run a single eval case. Returns dict with keys: case, passed, failures, post_len."""
    case_name = case_dir.name
    assertions = load_assertions(case_dir)

    if mode == "mock":
        post = build_mock_post(case_dir, assertions)
        result = {"status": "ok", "final_post": post}
    else:
        idea_id = str(uuid.uuid4())
        try:
            result = run_real_pipeline(case_dir, tenant_id, idea_id)
        except Exception as exc:
            return {
                "case": case_name,
                "passed": False,
                "failures": [f"pipeline exception: {exc}"],
                "post_len": 0,
            }

    if result.get("status") != "ok":
        return {
            "case": case_name,
            "passed": False,
            "failures": [f"pipeline returned status={result.get('status')!r}"],
            "post_len": 0,
        }

    final_post = result.get("final_post", "")
    failures = run_assertions(final_post, assertions)

    return {
        "case": case_name,
        "passed": len(failures) == 0,
        "failures": failures,
        "post_len": len(final_post),
        "signal_words": assertions.get("required_signal_words", []),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Eval-Suite Runner")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--mock", action="store_true", default=False)
    mode_group.add_argument("--real", action="store_true", default=False)
    parser.add_argument("--cases", type=str, default="", help="Comma-separated case names")
    parser.add_argument("--min-pass", type=int, default=80, help="Min %% PASS to exit 0")
    args = parser.parse_args()

    mode = "real" if args.real else "mock"

    # Collect cases
    if args.cases:
        case_names = [c.strip() for c in args.cases.split(",") if c.strip()]
        case_dirs = [_CASES_ROOT / name for name in case_names]
    else:
        case_dirs = sorted(
            [d for d in _CASES_ROOT.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )

    if not case_dirs:
        print("No eval cases found.", file=sys.stderr)
        sys.exit(1)

    tenant_id = os.environ.get("EVAL_TENANT_ID", "eval_test_tenant")

    print(f"Eval mode: {mode} | cases: {len(case_dirs)} | tenant: {tenant_id}")
    print("-" * 60)

    results = []
    for case_dir in case_dirs:
        if not case_dir.exists():
            print(f"[SKIP] {case_dir.name} -- directory not found")
            continue
        outcome = run_case(case_dir, mode, tenant_id)
        results.append(outcome)

        if outcome["passed"]:
            signal_info = ""
            if outcome.get("signal_words"):
                signal_info = f", signal words: {outcome['signal_words']}"
            print(
                f"[PASS] {outcome['case']} -- post {outcome['post_len']} chars, "
                f"0 failures{signal_info}"
            )
        else:
            for fail in outcome["failures"]:
                print(f"[FAIL] {outcome['case']} -- FAIL: {fail}")

    print("-" * 60)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pct = int(passed / total * 100) if total > 0 else 0
    print(f"=== Eval Results: {passed}/{total} PASS ({pct}%) ===")

    min_pass = args.min_pass
    if pct < min_pass:
        print(f"FAIL: pass rate {pct}% < threshold {min_pass}%", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
