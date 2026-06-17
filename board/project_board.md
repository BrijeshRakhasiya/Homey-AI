# Homey Intelligence Sprint — Project Board
**Candidate:** Brijesh Rakhasiya | **Status:** Sprint Complete

---

## Task Status

| # | Task | Owner | Branch | Status | Artifact | Dashboard Event |
|---|------|-------|--------|--------|----------|-----------------|
| 1 | Executive Fit | Brijesh | feat/soft-fit | ✅ Done | `agents/soft_fit.py` → `evaluate_executive_fit()` | `executive_fit_evaluated` |
| 2 | Intent Atlas | Brijesh | feat/intent-atlas | ✅ Done | `agents/intent_atlas.py` | `intent_classified` |
| 3 | Retrieval Governance | Brijesh | feat/retrieval-gov | ✅ Done | `agents/retrieval_gov.py` | `retrieval_governed` |
| 4 | Agent Workbench | Brijesh | feat/agent-graph | ✅ Done | `agents/graph.py` | `graph_completed` |
| 5 | Soft-Fit Engine | Brijesh | feat/soft-fit | ✅ Done | `agents/soft_fit.py` → `compute_soft_fit()` | `soft_fit_scored` |
| 6 | Squad Reasoning | Brijesh | feat/squad | ✅ Done | `agents/squad_reasoning.py` | `squad_profile_built` |
| 7 | Campaign Entry Router | Brijesh | feat/routers | ✅ Done | `routers/campaign_router.py` | `campaign_entry_routed` |
| 8 | Evaluation Harness | Brijesh | feat/eval | ✅ Done | `eval/harness.py` + `eval/golden_set.json` | `eval_harness_run` |
| 9 | Observability Stream | Brijesh | feat/observability | ✅ Done | `observability/stream.py` | All event types |
| 10 | Latency and Cost | Brijesh | feat/infra | ✅ Done | `infra/latency_router.py` | `latency_route_selected` |
| 11 | Schema Discipline | Brijesh | feat/infra | ✅ Done | `infra/schema_adapter.py` | `schema_validation_failed` |
| 12 | Failure Notebook | Brijesh | feat/eval | ✅ Done | `eval/failure_notebook.py` | `failure_logged` |
| 13 | Micro-Community Context | Brijesh | feat/routers | ✅ Done | `routers/community_router.py` | `community_context_applied` |
| 14 | Broker Explanation | Brijesh | feat/broker | ✅ Done | `agents/broker_explanation.py` | `broker_explanation_generated` |
| 15 | Memory Policy | Brijesh | feat/memory | ✅ Done | `agents/memory_policy.py` | `memory_stored` / `blocked_memory_attempt` |
| 16 | Integration Handshake | Brijesh | feat/api | ✅ Done | `infra/integration.py` | `api_request_received` |
| 17 | Project Board | Brijesh | — | ✅ Done | `board/project_board.md` | — |
| 18 | Combined Stress Day | Brijesh | feat/stress | ✅ Done | `stress/combined_stress_day.py` | All 10+ events |
| 19 | Live Defense | Brijesh | — | ✅ Ready | `board/project_board.md` (answers below) | — |
| 20 | Final Submission | Brijesh | main | ✅ Done | `README.md` + full repo | — |

---

## Run Commands

```bash
# Install
pip install langgraph langchain langchain-groq faiss-cpu sentence-transformers \
            pydantic fastapi uvicorn python-dotenv jsonlines pytest httpx

# Run all tests
pytest tests/test_all.py -v

# Run evaluation harness
python eval/harness.py

# Run stress day (end-to-end)
python stress/combined_stress_day.py

# Seed failure notebook
python eval/failure_notebook.py

# Start API
uvicorn infra.integration:app --reload --port 8000

# Test API (curl)
curl -X POST http://localhost:8000/homey/message \
  -H "Content-Type: application/json" \
  -d '{"raw_message": "I need a 2BHK in Brooklyn under 3000"}'
```

---

## Live Defense — Prepared Answers (Task 19)

**Q: Why structured layers instead of one big prompt?**
A structured layer is testable, versionable, and debuggable independently. A long prompt cannot be unit tested — a field change breaks everything silently. Each layer here (intent, retrieval, guard, fit) can be tested with one pytest command, owned by one person, and updated without touching the others. The guard node catching "approved" does not care what the LLM said — it runs always. That guarantee is impossible in a prompt.

**Q: What intentional automation did you block?**
Ranking renters using credit score, criminal record, or eviction history. Blocked at three levels: schema (`extra=forbid` on SoftFitInput), fit engine (not in ALLOWED_SIGNALS), and broker explanation (appears in `restricted_fields_blocked` audit list, never in output text).

**Q: What is the riskiest production assumption?**
That the guard node's phrase list covers all unsafe language. The LLM may paraphrase "approved" as "meets the criteria" — semantically equivalent but not caught by string matching. Mitigation: add semantic similarity check in guard node v2, and track guard trigger rate in Dhruv's dashboard to catch drift early.

**Q: What is the fastest safe MVP slice to merge first?**
Intent Atlas (`agents/intent_atlas.py`) + Observability Stream + `POST /homey/message`. This alone makes every message typed and logged. Nikunj can wire it to the WhatsApp webhook in one afternoon. No LLM key needed for the intent layer — it runs deterministically.

**Q: What metric improves in week 1 after integration?**
`intent_classified` event volume with role distribution breakdown. Dhruv can see renter vs broker vs squad vs unknown split from day one. Unknown rate above 30% means Homey needs better onboarding prompts — a measurable signal, not a guess.

**Q: What would make this unsafe if reused by another team member?**
If someone copies the broker_explanation module but removes the `RESTRICTED_FIELDS` block list, the raw credit/eviction data from `raw_fields` would flow into broker output. The block list must stay in the module, not in a config file that can be accidentally omitted.

---

## Integration Seams

| Layer | Connects to | Via |
|-------|-------------|-----|
| `intent_atlas` | Nikunj backend | Called first on every incoming message |
| `retrieval_gov` | Nikunj FAISS index | `build_index()` at startup, `governed_retrieval()` per query |
| `soft_fit` | Nikunj renter profiles | `POST /homey/fit` with adapted payload |
| `broker_explanation` | Dhruv dashboard | `broker_explanation_generated` event + response JSON |
| `observability/stream.jsonl` | Dhruv analytics | File read or `GET /events` endpoint (Nikunj to add) |
| `schema_adapter` | Nikunj raw payload | Called before any reasoning layer |

---

## Blockers

| Blocker | Owner | Resolution |
|---------|-------|------------|
| Real FAISS index with VryfID listing docs | Nikunj | Need doc corpus to run `build_index()` with real data |
| Groq API key for LLM calls | Brijesh | Free key from console.groq.com — already in `.env` template |
| WhatsApp webhook URL for live testing | Nikunj | Need endpoint to wire `POST /homey/message` |
| Policy decision on which broker fields are allowed | Aiden/Legal | Affects `RESTRICTED_FIELDS` list in `broker_explanation.py` |

---

## Decision Memo

1. **Ready to merge now:** Intent Atlas, Observability Stream, Schema Adapter, Soft-Fit Engine, Broker Explanation, Memory Policy, Campaign Router, Community Router, Latency Router, Evaluation Harness, Failure Notebook, `POST /homey/message` API.

2. **Needs Nikunj's backend contract first:** Retrieval Governance (need real doc corpus and FAISS index path), Schema Adapter field map (need confirmed field names from backend).

3. **Needs policy decision before going live:** Broker Explanation `RESTRICTED_FIELDS` list (legal must confirm which fields are completely off-limits vs allowed with consent).

4. **Biggest remaining risk:** Guard node uses string matching, not semantic matching. A paraphrased blocked phrase will pass. Week 2 priority: add embedding-based similarity check.

5. **First metric that proves value after week 1:** Intent classification accuracy — specifically the unknown-role rate. If it drops below 15% within one week of real traffic, the intent atlas is working. Dashboard event: `intent_classified` with `role=unknown` count.
