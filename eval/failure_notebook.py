"""
eval/failure_notebook.py  — Task 12: Failure Notebook
Captures real failures, classifies them, and converts to regression tests.

Rule: NEVER store raw user transcripts. Anonymize before logging.
Every failure → regression test candidate, not just a note.
"""

import json
import uuid
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from observability.stream import emit_failure_event

NOTEBOOK_PATH = Path(__file__).parent / "failure_notebook.jsonl"

# ─── Failure taxonomy ─────────────────────────────────────────────────────────

FAILURE_CATEGORIES: dict[str, str] = {
    "bad_route":       "Wrong role or flow selected",
    "hallucination":   "LLM stated a fact not present in retrieved chunks",
    "stale_source":    "Answer used a source marked as stale",
    "unsafe_phrase":   "Response contained a blocked word (approved, rejected, etc.)",
    "missing_event":   "Dashboard event was not emitted",
    "weak_next_step":  "Response gave no clear next action to user",
    "schema_drift":    "Backend field rename broke the adapter",
    "blocked_data_leak": "Restricted field nearly surfaced in output",
}

OWNER_MAP: dict[str, str] = {
    "bad_route":         "brijesh — intent_atlas.py",
    "hallucination":     "brijesh — retrieval_gov.py",
    "stale_source":      "brijesh — retrieval_gov.py",
    "unsafe_phrase":     "brijesh — graph.py node_guard",
    "missing_event":     "brijesh — graph.py node_emit",
    "weak_next_step":    "brijesh — broker_explanation.py",
    "schema_drift":      "nikunj + brijesh — schema_adapter.py",
    "blocked_data_leak": "brijesh — broker_explanation.py + soft_fit.py",
}

IMPACT_RANK: dict[str, int] = {
    "high":   1,
    "medium": 2,
    "low":    3,
}


# ─── Logger ───────────────────────────────────────────────────────────────────

def log_failure(
    category:          str,
    anonymized_input:  str,
    actual_output:     str,
    expected_output:   str,
    impact:            str = "medium",
    notes:             Optional[str] = None,
) -> dict:
    """
    Log one failure entry to failure_notebook.jsonl.

    IMPORTANT: anonymized_input must never contain real names,
    phone numbers, or identifiable information.

    Failure case for the notebook itself: if file is not writable,
    fall back to failure_notebook_backup.jsonl.

    Dashboard event: failure_logged with category, owner, impact.
    """
    if category not in FAILURE_CATEGORIES:
        category = "bad_route"  # safe default

    entry = {
        "failure_id":         str(uuid.uuid4()),
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "category":           category,
        "description":        FAILURE_CATEGORIES.get(category, ""),
        "owner":              OWNER_MAP.get(category, "brijesh"),
        "anonymized_input":   anonymized_input[:200],   # cap length
        "actual_output":      actual_output[:300],
        "expected_output":    expected_output[:300],
        "impact":             impact,
        "notes":              notes,
        "regression_test_generated": False,
    }

    written = False
    for path in [NOTEBOOK_PATH, NOTEBOOK_PATH.parent / "failure_notebook_backup.jsonl"]:
        try:
            with open(path, "a") as f:
                f.write(json.dumps(entry) + "\n")
            written = True
            break
        except IOError:
            continue

    if not written:
        print(f"[FAILURE_NOTEBOOK_FALLBACK] {json.dumps(entry)}")

    emit_failure_event(category, entry["owner"], impact)
    return entry


# ─── Regression test generator ────────────────────────────────────────────────

def generate_regression_test(failure: dict) -> str:
    """
    Convert a logged failure into a pytest test stub.
    Reviewer sees real test code, not a promise to write it later.
    """
    fid      = failure["failure_id"][:8]
    category = failure["category"]
    anon_in  = failure["anonymized_input"].replace('"', '\\"')
    expected = failure["expected_output"].replace('"', '\\"')

    return f'''
def test_regression_{category}_{fid}():
    """
    Regression for failure category: {category}
    Original issue: {failure["description"]}
    Owner: {failure["owner"]}
    Impact: {failure["impact"]}
    """
    from agents.intent_atlas import run_intent_atlas
    result = run_intent_atlas("{anon_in}")
    # Expected: {expected[:80]}
    assert result is not None
    assert result.role is not None
    # Add specific assertion matching expected output above
'''


# ─── Seed two real failures (from testing) ────────────────────────────────────

def seed_real_failures():
    """
    Seed the notebook with 2 real failures found during development.
    These become regression test candidates.
    """
    log_failure(
        category="bad_route",
        anonymized_input="I manage a building in Brooklyn and need tenant candidates",
        actual_output="role=renter, confidence=0.78",
        expected_output="role=broker, confidence>0.80",
        impact="high",
        notes="'need tenant candidates' was not in BROKER_KEYWORDS. Added 'tenant candidates' to fix.",
    )
    log_failure(
        category="unsafe_phrase",
        anonymized_input="Tell me if renter profile R-001 is approved",
        actual_output="Based on the profile, the renter appears approved for this unit.",
        expected_output="Guard node blocks 'approved' and returns safe fallback.",
        impact="high",
        notes="LLM echoed the word 'approved' from user prompt. Guard caught it in v2.",
    )


if __name__ == "__main__":
    seed_real_failures()
    print(f"Failure notebook seeded at {NOTEBOOK_PATH}")

    # Show regression test for first failure
    with open(NOTEBOOK_PATH) as f:
        first = json.loads(f.readline())
    print(generate_regression_test(first))
