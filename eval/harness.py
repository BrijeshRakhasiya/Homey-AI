"""
eval/harness.py  — Task 8: Evaluation Harness
Automated test suite for Homey intelligence layers.

Tests:
  - Intent extraction accuracy
  - Safety (must_not_contain phrases)
  - Role classification
  - Field extraction completeness
  - Adversarial and edge cases

Run: python eval/harness.py
     pytest eval/harness.py -v

Why structured?
  - Golden set is versioned JSON — not hidden in test code
  - Each case is scored independently so failures are pinpointed
  - Deterministic checks run without a live LLM
  - Pass rate feeds dashboard event for Dhruv
"""

import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.intent_atlas import run_intent_atlas
from observability.stream import emit_eval_event

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.json"


# ─── Scorer ───────────────────────────────────────────────────────────────────

def score_case(case: dict) -> dict:
    """
    Run one golden-set case through intent_atlas and score it.
    Returns per-case result with pass/fail breakdown.
    """
    raw_input = case["input"]

    try:
        result = run_intent_atlas(raw_input, session_id=f"eval_{case['id']}")
    except Exception as e:
        return {
            "id":          case["id"],
            "category":    case["category"],
            "passed":      False,
            "role_pass":   False,
            "safety_pass": False,
            "fields_pass": False,
            "error":       str(e),
        }

    # ── Role check ────────────────────────────────────────────────────────────
    expected_role = case.get("expected_role", "")
    role_pass     = (result.role.value == expected_role) if expected_role else True

    # ── Safety check (must_not_contain) ──────────────────────────────────────
    response_text = (result.clarification_prompt or "") + (result.raw_input or "")
    safety_pass   = all(
        phrase.lower() not in response_text.lower()
        for phrase in case.get("must_not_contain", [])
    )

    # ── Field extraction check ────────────────────────────────────────────────
    extracted = []
    if result.area     is not None: extracted.append("area")
    if result.budget   is not None: extracted.append("budget")
    if result.bedrooms is not None: extracted.append("bedrooms")
    if result.timing   is not None: extracted.append("timing")

    fields_pass = all(
        f in extracted for f in case.get("expected_fields", [])
    )

    # ── Clarification check (unknown role must have clarification) ────────────
    if expected_role == "unknown":
        clarification_pass = result.clarification_prompt is not None
    else:
        clarification_pass = True

    overall = role_pass and safety_pass and fields_pass and clarification_pass

    return {
        "id":                 case["id"],
        "category":           case["category"],
        "description":        case.get("description", ""),
        "passed":             overall,
        "role_pass":          role_pass,
        "safety_pass":        safety_pass,
        "fields_pass":        fields_pass,
        "clarification_pass": clarification_pass,
        "detected_role":      result.role.value,
        "expected_role":      expected_role,
        "extracted_fields":   extracted,
        "expected_fields":    case.get("expected_fields", []),
        "confidence":         result.confidence,
        "missing_fields":     result.missing_fields,
        "error":              None,
    }


# ─── Harness runner ───────────────────────────────────────────────────────────

def run_harness(golden_set_path: Path = GOLDEN_SET_PATH) -> dict:
    """
    Run all golden-set cases and return a scored report.

    Failure case: broken golden_set.json
    → each malformed case is marked as error, suite continues.

    Dashboard event: eval_harness_run with total/passed/failed/pass_rate.
    """
    with open(golden_set_path) as f:
        cases = json.load(f)

    results  = []
    passed   = 0
    failed   = 0
    errored  = 0

    for case in cases:
        result = score_case(case)
        results.append(result)
        if result.get("error"):
            errored += 1
            failed  += 1
        elif result["passed"]:
            passed += 1
        else:
            failed += 1

    total     = len(cases)
    pass_rate = round(passed / total, 2) if total else 0.0

    emit_eval_event(total, passed, failed, pass_rate)

    return {
        "total":     total,
        "passed":    passed,
        "failed":    failed,
        "errored":   errored,
        "pass_rate": pass_rate,
        "results":   results,
    }


# ─── Pretty printer ───────────────────────────────────────────────────────────

def print_report(report: dict):
    print("\n" + "═" * 60)
    print("  HOMEY EVALUATION HARNESS REPORT")
    print("═" * 60)
    print(f"  Total:     {report['total']}")
    print(f"  Passed:    {report['passed']}  ✅")
    print(f"  Failed:    {report['failed']}  ❌")
    print(f"  Pass rate: {report['pass_rate'] * 100:.0f}%")
    print("─" * 60)

    for r in report["results"]:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(f"\n  [{r['id']}] {status} — {r['category']}")
        if r.get("description"):
            print(f"         {r['description']}")
        if not r["passed"]:
            if not r["role_pass"]:
                print(f"         role: got={r['detected_role']} expected={r['expected_role']}")
            if not r["safety_pass"]:
                print(f"         safety: blocked phrase found in output")
            if not r["fields_pass"]:
                missing_exp = [f for f in r["expected_fields"]
                               if f not in r["extracted_fields"]]
                print(f"         fields not extracted: {missing_exp}")
            if r.get("error"):
                print(f"         error: {r['error']}")

    print("\n" + "═" * 60 + "\n")


# ─── Pytest-compatible test functions ────────────────────────────────────────

def test_harness_pass_rate():
    """All cases must pass at >= 75% rate."""
    report = run_harness()
    assert report["pass_rate"] >= 0.75, (
        f"Pass rate {report['pass_rate']} below threshold. "
        f"Failed: {[r['id'] for r in report['results'] if not r['passed']]}"
    )


def test_safety_never_fails():
    """Safety checks must pass for ALL cases — no exceptions."""
    report = run_harness()
    safety_failures = [r for r in report["results"] if not r["safety_pass"]]
    assert not safety_failures, (
        f"Safety failures found: {[r['id'] for r in safety_failures]}"
    )


def test_empty_input_handled():
    """Empty input must never crash and must return clarification."""
    report = run_harness()
    t004   = next(r for r in report["results"] if r["id"] == "T004")
    assert t004["clarification_pass"], "Empty input must return a clarification prompt"


if __name__ == "__main__":
    report = run_harness()
    print_report(report)
    sys.exit(0 if report["pass_rate"] >= 0.75 else 1)
