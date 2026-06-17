# Homey Intelligence

Homey is a FastAPI-backed demo that ties together intent routing, fit scoring, squad reasoning, memory policy, observability, and a live dashboard API.

---

## Quick Start

```bash
pip install langgraph langchain langchain-groq faiss-cpu sentence-transformers \
            pydantic fastapi uvicorn python-dotenv jsonlines pytest httpx

pytest tests/test_all.py -v && \
python eval/harness.py && \
python stress/combined_stress_day.py
```

For LLM-powered responses, add your Groq key to `.env`:
```
GROQ_API_KEY=your_key_here   # free at console.groq.com
```

To run the dashboard API locally:

```bash
uvicorn dashboard.api:app --reload --port 8001
```

---

## Dashboard API

The dashboard backend lives in [dashboard/api.py](dashboard/api.py). It exposes endpoints for:

1. Renter and broker registration
2. Listing creation and fit evaluation
3. Squad profile generation
4. Chat routing and memory storage
5. Live dashboard data and SSE event streaming

Useful endpoints:

```bash
GET  http://localhost:8001/health
GET  http://localhost:8001/api/dashboard/live
GET  http://localhost:8001/api/events/stream
```

## Architecture

```
User message (WhatsApp/SMS)
         │
         ▼
┌─────────────────────┐
│  Latency Router     │  Task 10 — static/cache/retrieval/llm tier
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Community Context  │  Task 13 — adjust first prompt by source
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Campaign Router    │  Task 7  — hook detection → flow routing
└────────┬────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│            LangGraph Agent               │  Task 4
│                                          │
│  node_route   → Intent Atlas  (Task 2)   │
│  node_retrieve → Retrieval Gov (Task 3)  │
│  node_reason  → LLM / fallback           │
│  node_guard   → phrase blocker           │
│  node_emit    → observability stream     │
└────────┬─────────────────────────────────┘
         │
         ├──► Soft-Fit Engine      Task 5  → soft_fit_scored event
         ├──► Executive Fit        Task 1  → executive_fit_evaluated event
         ├──► Squad Reasoning      Task 6  → squad_profile_built event
         ├──► Broker Explanation   Task 14 → broker_explanation_generated event
         └──► Memory Policy        Task 15 → memory_stored / blocked_memory_attempt

Schema Adapter (Task 11) — wraps all incoming Nikunj payloads
Observability Stream (Task 9) — JSONL log, all events → Dhruv dashboard
Evaluation Harness (Task 8) — 12-case golden set, automated scorer
Failure Notebook (Task 12) — classifies failures → regression tests
```

---

## Task Index

| Task | File | One-line description |
|------|------|---------------------|
| 1 Executive Fit | `agents/soft_fit.py` → `evaluate_executive_fit()` | Property vs renter safe comparison |
| 2 Intent Atlas | `agents/intent_atlas.py` | Raw text → typed IntentState |
| 3 Retrieval Governance | `agents/retrieval_gov.py` | Audience-filtered, stale-aware RAG |
| 4 Agent Workbench | `agents/graph.py` | LangGraph 5-node pipeline |
| 5 Soft-Fit Engine | `agents/soft_fit.py` → `compute_soft_fit()` | Safe weighted fit scoring |
| 6 Squad Reasoning | `agents/squad_reasoning.py` | Group search, conflict detection |
| 7 Campaign Router | `routers/campaign_router.py` | Hook → flow mapping |
| 8 Evaluation Harness | `eval/harness.py` + `eval/golden_set.json` | 12-case automated scorer |
| 9 Observability | `observability/stream.py` | JSONL event logger |
| 10 Latency & Cost | `infra/latency_router.py` | 4-tier cheapest-path router |
| 11 Schema Discipline | `infra/schema_adapter.py` | Field mapping + drift detection |
| 12 Failure Notebook | `eval/failure_notebook.py` | Failure → regression test |
| 13 Community Context | `routers/community_router.py` | Source → first prompt adapter |
| 14 Broker Explanation | `agents/broker_explanation.py` | Safe 4-part broker summary |
| 15 Memory Policy | `agents/memory_policy.py` | Typed memory with expiry + blocks |
| 16 Integration | `infra/integration.py` | FastAPI endpoints for all layers |
| 17 Project Board | `board/project_board.md` | Task status + live defense answers |
| 18 Stress Day | `stress/combined_stress_day.py` | 9-step end-to-end scenario |
| 19 Live Defense | `board/project_board.md` | Prepared answers to review questions |
| 20 Final Submission | `README.md` | This file |

---

## Core API Endpoints

These run through the main integration layer on port 8000.

```bash
# Health check
GET http://localhost:8000/health

# Main message handler (Task 16)
POST http://localhost:8000/homey/message
{"raw_message": "I need a 2BHK in Brooklyn under 3000"}

# Quick intent test
GET http://localhost:8000/homey/intent?message=I need a place in Brooklyn

# Soft-fit scoring
POST http://localhost:8000/homey/fit
{"renter_id":"r001","stated_budget":2800,"property_price":3000,
 "area_match":true,"bedroom_match":true,"timing_match":true,
 "profile_complete":true,"income_verified":true}

# Squad profile
POST http://localhost:8000/homey/squad
{"squad_id":"sq001","members":[
  {"member_id":"a","stated_budget":3000,"preferred_area":"Brooklyn"},
  {"member_id":"b","stated_budget":2500,"preferred_area":"Manhattan"}
]}

# Broker explanation (credit_score will be blocked from output)
POST http://localhost:8000/homey/broker-fit
{"lead_id":"lead001",
 "fit_result":{"fit_label":"moderate","fit_reasons":["budget aligns"],"missing_signals":[]},
 "raw_fields":{"credit_score":720,"income_verified":true}}

# Schema adapter test
POST http://localhost:8000/homey/adapt-renter
{"raw_payload":{"user_id":"r001","max_rent":3000,"neighborhood":"Brooklyn",
                "num_bedrooms":2,"income_status":true,"is_complete":true,
                "move_readiness":"immediate"}}
```

---

## Safety Guarantees

| Rule | Enforced at | Test |
|------|-------------|------|
| No credit/criminal/eviction in fit scoring | `schemas/fit.py` (`extra=forbid`) | `test_credit_score_rejected_by_schema` |
| No internal notes shown to renters | `agents/retrieval_gov.py` → `is_chunk_allowed()` | `test_renter_cannot_see_internal_notes` |
| No approval/rejection language in responses | `agents/graph.py` → `node_guard` | `test_guard_blocks_approved` |
| Restricted fields blocked from broker output | `agents/broker_explanation.py` | `test_restricted_data_blocked` |
| Restricted data never stored in memory | `agents/memory_policy.py` → `NEVER_STORE` | `test_credit_score_blocked` |
| Schema drift caught loudly | `infra/schema_adapter.py` | `test_missing_required_fields_raises` |

---

## Dashboard Events

All events are written to `observability/traces/stream.jsonl` in JSONL format and are surfaced through the dashboard API.

```jsonl
{"event_id":"...","event_type":"intent_classified","role":"renter","confidence":0.82,"missing_field_count":1}
{"event_id":"...","event_type":"retrieval_governed","audience":"renter","chunks_returned":3,"evidence_sufficient":true}
{"event_id":"...","event_type":"guard_checked","triggered":false,"reason":null}
{"event_id":"...","event_type":"soft_fit_scored","renter_id":"r001","fit_label":"moderate","fit_score":0.65}
{"event_id":"...","event_type":"squad_profile_built","squad_id":"sq001","conflict_count":2,"alignment_score":0.5}
{"event_id":"...","event_type":"broker_explanation_generated","fit_label":"moderate","restricted_fields_blocked":3}
{"event_id":"...","event_type":"blocked_memory_attempt","key":"credit_score","reason":"field_in_NEVER_STORE_list"}
{"event_id":"...","event_type":"latency_route_selected","tier":"static","model_called":false}
{"event_id":"...","event_type":"failure_logged","category":"unsafe_phrase","impact":"high"}
{"event_id":"...","event_type":"eval_harness_run","total":12,"passed":10,"pass_rate":0.83}
```

---

## Notes

The safer parts of the system are enforced in code, not in the README:

1. Retrieval is audience-aware and stale-source aware.
2. Guard logic can block unsafe language even when a model tries to produce it.
3. Fit scoring and memory writes reject restricted fields.
4. The dashboard API gives you a single place to inspect live events, sessions, and fit results.
