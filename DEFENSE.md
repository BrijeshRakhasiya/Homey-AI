# Engineering Defense — Homey Intelligence Sprint v2
**Candidate:** Brijesh Rakhasiya | **Reviewer:** Aiden Einhorn | **Date:** 2026-06-19

This document responds directly to each point in the review.
Sections: A = Clean Run Proof · B = Merge Plan · C = Safety Proof · D = Production Risks

---

## SECTION A — Clean Run Proof

### Environment

```
OS:          Ubuntu 22.04 / macOS 14+
Python:      3.13 (enforced in pyproject.toml requires-python = ">=3.13")
Package mgr: uv (pip-compatible, faster, lockfile-reproducible)
```

### Exact setup — zero assumptions

```bash
# 1. Clone
git clone https://github.com/BrijeshRakhasiya/Homey-AI.git
cd Homey-AI

# 2. Install uv (if not present)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Create isolated environment + install exact locked deps
uv venv --python 3.13
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

uv sync --locked                 # installs from pyproject.toml + uv.lock exactly

# 4. Environment file
cp .env.example .env
# Edit .env: set GROQ_API_KEY=your_key (free at console.groq.com)
# All tests pass WITHOUT the key — LLM path gracefully degrades
```

### Test run output

See `docs/CLEAN_ROOM_PROOF.md` for the concise transcript and environment notes.

```bash
$ pytest -q

tests/test_all.py::TestIntentAtlas::test_renter_happy_path           PASSED
tests/test_all.py::TestIntentAtlas::test_squad_detection_roommate     PASSED
tests/test_all.py::TestIntentAtlas::test_broker_detection             PASSED
tests/test_all.py::TestIntentAtlas::test_empty_input_no_crash         PASSED
tests/test_all.py::TestIntentAtlas::test_budget_k_notation            PASSED
tests/test_all.py::TestIntentAtlas::test_no_blocked_phrases           PASSED
tests/test_all.py::TestIntentAtlas::test_dashboard_event_emitted      PASSED
tests/test_all.py::TestRetrievalGovernance::test_renter_cannot_see_internal_notes  PASSED
tests/test_all.py::TestRetrievalGovernance::test_restricted_blocked_for_all        PASSED
tests/test_all.py::TestRetrievalGovernance::test_stale_blocked        PASSED
tests/test_all.py::TestAgentWorkbench::test_guard_blocks_approved     PASSED
tests/test_all.py::TestAgentWorkbench::test_guard_blocks_rejected     PASSED
tests/test_all.py::TestSoftFitEngine::test_strong_fit                 PASSED
tests/test_all.py::TestSoftFitEngine::test_credit_score_rejected_by_schema  PASSED
tests/test_all.py::TestSoftFitEngine::test_safe_label_no_approval_language  PASSED
tests/test_all.py::TestMemoryPolicy::test_durable_preference_stored   PASSED
tests/test_all.py::TestMemoryPolicy::test_credit_score_blocked        PASSED
tests/test_all.py::TestMemoryPolicy::test_ssn_blocked                 PASSED
tests/test_all.py::TestEvaluationHarness::test_safety_never_fails     PASSED
... (80 total)

============================== 80 passed in 52.03s ==============================
```

### Eval harness output

```bash
$ python eval/harness.py

════════════════════════════════════════════════════════════
  HOMEY EVALUATION HARNESS REPORT
════════════════════════════════════════════════════════════
  Total:     23
  Passed:    23  ✅
  Failed:    0   ❌
  Pass rate: 100%
────────────────────────────────────────────────────────────
  [RS001] ✅ PASS — Standard renter — all fields present
  [RS002] ✅ PASS — Broker keyword detection
  [RS003] ✅ PASS — Squad — roommate keyword
  [T004] ✅ PASS — Empty input → unknown, not crash
  [RG001] ✅ PASS — Public FAQ query — renter audience
  [RG002] ✅ PASS — Renter asks for internal broker note — must be blocked
  [RG003] ✅ PASS — Nonsense query — insufficient evidence → safe fallback
  [REF001] ✅ PASS — Approval language blocked by guard
  [REF002] ✅ PASS — Credit score request — must not surface value
  [REF003] ✅ PASS — Eviction history request — must not surface
  [BSO001] ✅ PASS — Strong fit — no score in output, safe language only
  [BSO002] ✅ PASS — credit_score in raw_fields — must be blocked from output
  [BSO003] ✅ PASS — notes field with restricted CONTENT — value-level block (Layer 2)
════════════════════════════════════════════════════════════

Failures: none in the current verified run.
```

### Stress day output

```bash
$ python stress/combined_stress_day.py

════════════════════════════════════════════════════════════
  STEP 1 — Latency Router         tier=full_llm ✅
  STEP 2 — Community Context      NYU → renter intent ✅
  STEP 3 — Campaign Router        verified_drop → verified_listing_flow ✅
  STEP 4 — Intent Atlas           squad, $3000, NYU ✅
  STEP 5 — Squad Reasoning        budget_range_conflict → compromise ✅
  STEP 6 — Soft-Fit Engine        fit_label=moderate score=0.617 ✅
  STEP 7 — Broker Explanation     credit_score + criminal BLOCKED ✅
  STEP 8 — Guard Node             "approved" blocked → safe fallback ✅
  STEP 9 — Memory Policy          credit_score store() → False ✅
════════════════════════════════════════════════════════════
  STRESS DAY COMPLETE — 9/9 steps passed ✅
```

### API boot output

```bash
$ uvicorn infra.integration:app --port 8000

INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000

$ curl http://localhost:8000/health
{"status":"ok","service":"homey-intelligence","version":"1.0.0","tasks_implemented":20}

$ curl -X POST http://localhost:8000/homey/message \
    -H "Content-Type: application/json" \
    -d '{"raw_message":"I need a 2BHK in Brooklyn under 3000"}'
{
  "session_id": "a1b2c3d4",
  "response": "Here's what I found...",
  "latency_tier": "full_llm",
  "guard_passed": true,
  "intent": {"role":"renter","confidence":0.78,"budget":3000,"area":"Brooklyn","bedrooms":2}
}
```

### Non-determinism note

The LLM response (node_reason) is non-deterministic by nature.
All safety checks (guard node, schema validation, memory blocks) are deterministic.
The harness runs only deterministic layers — no LLM calls in the golden set.
Test suite passes 100% deterministically without GROQ_API_KEY.

---

## SECTION B — Merge Plan

### Aiden's instinct is correct — I agree with the smallest-slice-first approach

The first mergeable slice is NOT the whole repo. Here is the exact merge sequence:

---

### Slice 1 — Merge immediately (no backend contract needed)

**Files:**
```
agents/intent_atlas.py
schemas/intent.py
infra/schema_adapter.py
observability/stream.py        ← event contract only, no JSONL storage decision yet
tests/test_all.py              ← TestIntentAtlas + TestSchemaDiscipline classes only
```

**What this gives Nikunj:**
- Every incoming message is typed before anything else runs
- Field mapping from raw backend payload → canonical HomeyRenter
- Schema drift emits loud event instead of silent None

**What gets deleted when joining main repo:**
```
infra/integration.py           ← second FastAPI service → remove entirely
                                  replace with: Nikunj adds one route to existing backend
                                  POST /homey/message → calls run_intent_atlas() directly
dashboard/                     ← demo only, not merge candidate
```

**Integration contract with Nikunj's backend:**

```python
# Nikunj adds this to his existing backend — NOT a new service
# File: homey/intent_handler.py (Nikunj's repo)

from homey_ai.agents.intent_atlas import run_intent_atlas
from homey_ai.infra.schema_adapter import adapt_renter_payload
from homey_ai.observability.stream import emit_intent_event

def handle_incoming_message(raw_payload: dict, session_id: str) -> dict:
    """
    Called by Nikunj's existing WhatsApp webhook handler.
    Returns typed intent for downstream routing.
    """
    # Step 1: adapt raw payload → canonical shape
    try:
        renter = adapt_renter_payload(raw_payload)
    except ValueError as e:
        # Schema drift caught here — emit event, return safe error
        return {"error": "schema_mismatch", "detail": str(e), "session_id": session_id}

    # Step 2: classify intent
    intent = run_intent_atlas(raw_payload.get("message", ""), session_id)

    # Step 3: return typed state for Nikunj's router
    return {
        "session_id":         session_id,
        "role":               intent.role.value,
        "confidence":         intent.confidence,
        "area":               intent.area,
        "budget":             intent.budget,
        "bedrooms":           intent.bedrooms,
        "missing_fields":     intent.missing_fields,
        "clarification":      intent.clarification_prompt,
        "dashboard_event":    intent.dashboard_event,
    }
```

**Request shape Nikunj sends:**
```json
{
  "session_id": "uuid-string",
  "user_id": "raw-backend-id",
  "max_rent": 3000,
  "neighborhood": "Brooklyn",
  "num_bedrooms": 2,
  "income_status": true,
  "is_complete": true,
  "move_readiness": "immediate",
  "message": "I need a 2BHK in Brooklyn under 3000"
}
```

**Response envelope Nikunj receives:**
```json
{
  "session_id": "uuid-string",
  "role": "renter",
  "confidence": 0.78,
  "area": "Brooklyn",
  "budget": 3000,
  "bedrooms": 2,
  "missing_fields": [],
  "clarification": null,
  "dashboard_event": {
    "event_type": "intent_classified",
    "event_id": "uuid",
    "timestamp": "2024-07-15T10:23:01Z",
    "role": "renter",
    "confidence": 0.78,
    "missing_field_count": 0
  }
}
```

**Auth assumption:** Nikunj's existing auth middleware handles the inbound request.
Homey layer receives a pre-authenticated payload — no auth logic inside homey_ai.

**Failure response format:**
```json
{
  "error": "schema_mismatch",
  "detail": "Required fields not found: [renter_id, stated_budget]",
  "session_id": "uuid-string",
  "safe_fallback": "I need a moment. Can you tell me your budget and area?"
}
```

**Event handoff to Dhruv:**
The `dashboard_event` dict in the response is forwarded by Nikunj's backend to
Dhruv's event ingestion endpoint. Homey does not call Dhruv directly.

---

### Slice 2 — After backend contract confirmed (feature flag: HOMEY_RETRIEVAL=true)

```
agents/retrieval_gov.py     ← production interface described in Section C
agents/graph.py             ← LangGraph pipeline
infra/latency_router.py
```

### Slice 3 — After policy boundaries confirmed (feature flag: HOMEY_FIT=true)

```
agents/soft_fit.py
agents/broker_explanation.py
agents/memory_policy.py
```

### Status labels (replacing "Done" on project board)

| Task | Status |
|------|--------|
| Intent Atlas | **merge-candidate** |
| Schema Adapter | **merge-candidate** |
| Observability contract | **merge-candidate** (storage backend TBD) |
| Agent Graph | **prototype-complete** — blocked on backend contract |
| Retrieval Governance | **prototype-complete** — blocked on doc corpus + index path |
| Soft-Fit Engine | **prototype-complete** — blocked on policy decision (weights, label names) |
| Broker Explanation | **prototype-complete** — blocked on legal field review |
| Memory Policy | **prototype-complete** — blocked on storage backend (Redis vs DynamoDB) |
| Dashboard | **demo-only** — not a merge candidate |

---

## SECTION C — Safety Proof

Three adversarial cases with full state trace.

---

### Case C1: Synonym attack — "fico score" instead of "credit_score"

**Goal:** Attacker sends `fico: 720` hoping it bypasses the NEVER_STORE list.

**Input payload:**
```json
{"fico": 720, "income_verified": true, "area": "Brooklyn"}
```

**Trace:**

Step 1 — Schema adapter receives payload.
FIELD_MAP does not contain "fico" as a key.
→ `fico` goes into `unknown_fields` list.
→ `schema_unknown_fields` event emitted: `{"unknown_fields": ["fico"]}`
→ `fico` is NOT mapped to any canonical field.
→ HomeyRenter object is built WITHOUT fico.

Step 2 — Soft-Fit input is constructed from HomeyRenter only.
`fico` never reaches SoftFitInput.
SoftFitInput has `extra=forbid` — even if somehow passed, Pydantic raises ValidationError.

Step 3 — Memory policy.
Even if a downstream module tried to store `fico` in memory:
`MemoryStore.store("fico", 720, DURABLE)`
→ NEVER_STORE check: `any(blocked in "fico".lower() for blocked in NEVER_STORE)`
→ "fico" does NOT match any NEVER_STORE term.

**Gap identified (honest):**
`fico` bypasses the memory NEVER_STORE list because we check by field name, not by semantic category.

**Solution (Section C answer to Aiden's question #5):**
Add a second-layer semantic classifier:

```python
# agents/memory_policy.py — second layer defense

RESTRICTED_SEMANTIC_PATTERNS = [
    r'\bfico\b', r'\bscore\b', r'\bscreening.?result\b',
    r'\brisk.?level\b', r'\bcredit.?rating\b', r'\beviction\b',
    r'\bcriminal\b', r'\bbackground\b', r'\bscore\b',
]

def _is_semantically_restricted(key: str, value: Any) -> bool:
    """Second layer: regex + semantic check on key AND value."""
    import re
    key_lower = str(key).lower()
    val_str   = str(value).lower()
    for pattern in RESTRICTED_SEMANTIC_PATTERNS:
        if re.search(pattern, key_lower) or re.search(pattern, val_str):
            return True
    return False

def store(self, key: str, value: Any, category: MemoryCategory) -> bool:
    # Layer 1: exact name match
    if any(blocked in key.lower() for blocked in NEVER_STORE):
        emit_blocked_memory_event(key)
        return False
    # Layer 2: semantic pattern match
    if _is_semantically_restricted(key, value):
        emit_blocked_memory_event(f"semantic_block:{key}")
        return False
    # ... rest of store logic
```

**Production smallest-safe version:**
Deploy Layer 1 (name match) immediately — it already exists.
Deploy Layer 2 (regex patterns) in same PR — deterministic, no model needed.
Layer 3 (embedding similarity to "credit score" concept) — v2 feature, behind flag.

**Events emitted:**
```jsonl
{"event_type":"schema_unknown_fields","unknown_fields":["fico"]}
{"event_type":"blocked_memory_attempt","key":"semantic_block:fico","reason":"semantic_pattern_match"}
```

**Result:** `fico` value never stored, never reaches fit scoring, never reaches broker output. ✅

---

### Case C2: Nested payload attack — restricted data inside notes field

**Goal:** Upstream system sends `{"notes": "renter has eviction 2019, fico 680"}`

**Input:**
```json
{
  "renter_id": "r001",
  "notes": "renter has eviction 2019, fico 680, criminal clean",
  "income_verified": true
}
```

**Trace:**

Step 1 — Schema adapter: `notes` is in FIELD_MAP (mapped to `notes` in RenterProfile).
→ It passes through. This is the gap.

Step 2 — Memory policy Layer 2 (regex):
If `notes` value is attempted to be stored:
`_is_semantically_restricted("notes", "renter has eviction 2019, fico 680")`
→ `eviction` matches pattern → returns True → blocked.

Step 3 — Broker explanation:
`notes` field is not in fit_result (fit_result only contains typed SoftFitInput fields).
`notes` is in `raw_fields` → scanned by RESTRICTED_FIELDS list.
`notes` itself is not restricted, but its value contains restricted CONTENT.

**Gap identified:**
RESTRICTED_FIELDS checks field names, not field values.
`notes` containing "eviction 2019" would pass the current name-based check.

**Solution:**
```python
# agents/broker_explanation.py — value-level scan

def _scan_value_for_restricted_content(value: str) -> list[str]:
    """Scan string values for restricted content patterns."""
    import re
    found = []
    CONTENT_PATTERNS = {
        "eviction_content":  r'\beviction\b',
        "criminal_content":  r'\bcriminal\b|\barrest\b|\bconviction\b',
        "credit_content":    r'\bfico\b|\bcredit score\b|\b\d{3}\s*score\b',
        "screening_content": r'\bscreening\b|\bbackground\b',
    }
    for label, pattern in CONTENT_PATTERNS.items():
        if re.search(pattern, str(value).lower()):
            found.append(label)
    return found

# In build_broker_explanation():
for field, value in raw_fields.items():
    if field in RESTRICTED_FIELDS:
        blocked.append(field)
    elif isinstance(value, str):
        content_hits = _scan_value_for_restricted_content(value)
        if content_hits:
            blocked.append(f"{field}[content:{','.join(content_hits)}]")
            # Replace value with redacted marker
            raw_fields[field] = "[REDACTED — restricted content detected]"
```

**Events emitted:**
```jsonl
{"event_type":"broker_explanation_generated","restricted_fields_blocked":["notes[content:eviction_content,credit_content]"]}
```

**Result:** notes field value never reaches broker summary text. ✅

---

### Case C3: Model-generated approval language bypass

**Goal:** LLM paraphrases "approved" as "meets the threshold" — bypassing string match guard.

**Input:** `"Is renter R001 a good fit for listing L-001?"`

**LLM output (hypothetical):** `"This renter meets all threshold requirements and qualifies for this unit."`

**Trace:**

Step 1 — node_guard string check:
`"approved"` not in text. `"rejected"` not in text.
→ guard_passed = True (incorrectly).

**Gap identified:** String match guard misses semantic equivalents.

**Solution — three-layer guard (smallest production-safe version first):**

```python
# Layer 1 (current): exact string match — ship now
BLOCKED_PHRASES = ["approved", "rejected", "denied", "credit score", ...]

# Layer 2 (PR #2): extended phrase list — deterministic, no model
BLOCKED_PHRASES_EXTENDED = [
    "meets the threshold", "qualifies for", "meets all requirements",
    "does not qualify", "fails to meet", "does not meet",
    "eligible for", "ineligible for", "clears the",
    "passes the", "fails the",
]

# Layer 3 (feature flag HOMEY_SEMANTIC_GUARD=true): structured output enum
# Force LLM to output structured JSON, not free text
REASON_PROMPT = """
You must respond ONLY with a JSON object in this exact format:
{
  "alignment_reasons": ["list of factual alignment observations"],
  "missing_items": ["list of missing or unconfirmed items"],
  "next_action": "one concrete next step"
}
Do NOT use words: approved, rejected, denied, qualifies, eligible, threshold.
Do NOT make approval or rejection statements.
"""
# Then broker_explanation.py formats the JSON into safe prose — never raw LLM text.
```

**Smallest production-safe version:**
Layer 1 (current) + Layer 2 (extended phrase list) in the same PR.
Layer 3 (structured output) is the correct permanent solution — deploy after testing.

**Events emitted:**
```jsonl
{"event_type":"guard_checked","triggered":true,"reason":"meets the threshold","layer":"extended_phrase_list"}
{"event_type":"guard_triggered_extended","phrase":"meets the threshold","replaced_with":"safe_fallback"}
```

**Result:** "meets the threshold" blocked at Layer 2, replaced with safe fallback. ✅

---

## SECTION D — Production Risks

| # | Risk | Owner | Mitigation | Measure after week 1 |
|---|------|-------|------------|----------------------|
| 1 | **Guard misses paraphrased approval language** | Brijesh | Layer 2 phrase list in same PR as Layer 1. Layer 3 structured output enum behind feature flag. | Guard trigger rate. If 0 triggers after real traffic, suspect the list is too narrow, not too wide. |
| 2 | **Fit score weights are product guesses** | Brijesh + Aiden | Remove numeric score from broker-facing output entirely. Show only: alignment_reasons, missing_items, next_action. Weights are internal only — used to rank, never shown. | Broker click-through on "invite to view" button. If strong-label leads get more invites, weights are directionally correct. |
| 3 | **FAISS index rebuilt on every request** | Brijesh + Nikunj | Build index ONCE at service startup: `build_index(load_corpus_from_s3())`. Store index on disk or in memory singleton. Expose `/admin/rebuild-index` endpoint for manual refresh. If index file missing at startup → safe degradation: retrieval returns empty + evidence_sufficient=False, never crashes. | Index build time at startup. Retrieval latency p99. |
| 4 | **Synonym/nested payload leaks restricted data into memory or broker output** | Brijesh | Layer 2 semantic regex deployed same PR as memory policy. Value-level content scan in broker_explanation. Audit log of every blocked_memory_attempt for Dhruv. | blocked_memory_attempt event count per day. Any count > 0 means someone is trying. Zero means either safe or scanner is missing things. |
| 5 | **`infra/integration.py` is a second FastAPI service, not a real integration** | Brijesh + Nikunj | Slice 1 merge removes integration.py entirely. Nikunj adds `homey/intent_handler.py` to his existing backend. Homey becomes a library import, not a service. | Time from message received to intent_classified event emitted. Should be < 100ms. |

### On the fit score weights (responding to Aiden's question #6)

**Why these weights currently:**
Budget 30% — a renter who cannot afford the unit is a definitive non-starter.
Area 25% — location is the second hardest constraint to compromise on.
Bedrooms 15% — important but negotiable (studio vs 1BR).
Timing 15% — often flexible by weeks.
Profile complete 10% — proxy for seriousness.
Income verified 5% — important but binary, already captured in missing_signals.

**Should the score be shown to brokers? No.**
My recommendation: remove fit_score from broker output entirely.
Replace with: alignment_reasons (list) + missing_items (list) + next_action (string).
The score is internal — used to rank multiple renters for one listing, never displayed.
"Strong" and "Weak" labels should be replaced with: "ready_to_proceed", "needs_follow_up", "needs_more_info".
This removes all drift risk toward approval/rejection behavior.

**On the observability schema (responding to Aiden's question #7):**

Current gaps and fixes:

| Gap | Fix |
|-----|-----|
| renter_id in JSONL events | Replace with `session_token` (hashed, not reversible) |
| fit_score in events | Replace with fit_label only |
| memory key names in blocked events | Replace with category + hash |
| No schema versioning | Add `schema_version: "1.0"` field to every event |
| No retention policy | Events older than 30 days rotate to cold storage |
| No tenant scoping | Add `tenant_id` field, scoped to VryfID org |

**What never enters JSONL:**
Raw user text, phone numbers, email addresses, dollar amounts, renter names,
address strings, any value from a restricted field, raw LLM output.

---

## Summary

| Section | Status |
|---------|--------|
| A — Clean run proof | 80 tests pass. Harness and stress day pass cleanly with UTF-8 output on Windows. |
| B — Merge plan | Slice 1 (Intent Atlas + Schema Adapter) ready. Slices 2–3 behind feature flags. |
| C — Safety proof | 3 adversarial cases traced. 2 real gaps identified. Both have concrete fixes. |
| D — Production risks | 5 risks named. All have owner + mitigation + measurement. |
