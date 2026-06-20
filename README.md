# Homey Intelligence

Homey Intelligence is a small Python project that classifies rental messages, applies safe retrieval, produces broker-safe explanations, manages memory policy, and emits structured observability events.

This repo is designed to be easy to run locally and easy to hand off to another engineer.

## What is in this project

### Core files

| File | What it does |
|------|--------------|
| `agents/intent_atlas.py` | Classifies each incoming message as `renter`, `broker`, `squad`, or `unknown`. This is the first typed step in the pipeline. |
| `infra/schema_adapter.py` | Converts raw backend payloads into the canonical Homey schema so the rest of the system sees consistent fields. |
| `observability/stream.py` | Writes structured JSONL events for dashboarding, debugging, and run audits. |
| `agents/retrieval_gov.py` | Handles retrieval with audience filtering, freshness checks, and safe fallback behavior. |
| `agents/broker_explanation.py` | Produces broker-facing text without leaking restricted data or approval language. |
| `agents/memory_policy.py` | Controls what can be stored in memory and blocks sensitive or restricted fields. |
| `agents/graph.py` | Connects route → retrieve → reason → guard → emit into one deterministic pipeline. |
| `infra/integration.py` | FastAPI service that exposes the main Homey HTTP endpoints. |
| `infra/latency_router.py` | Chooses the cheapest safe path for each request based on message complexity. |
| `routers/community_router.py` | Adds community-aware context for known sources like NYU or other tags. |
| `routers/campaign_router.py` | Detects campaign hooks and maps them to the correct flow. |
| `agents/soft_fit.py` | Computes fit scoring from safe signals only and keeps restricted fields out of the score path. |
| `agents/squad_reasoning.py` | Builds shared squad profiles and highlights conflicts or compromises. |
| `eval/harness.py` | Runs the full evaluation suite and prints a human-readable report. |
| `stress/combined_stress_day.py` | Runs an end-to-end stress scenario across the main system layers. |
| `tests/test_all.py` | Main test file covering intent, retrieval, guard, fit, memory, routing, and observability behavior. |
| `tests/test_integration_api.py` | FastAPI smoke tests for the HTTP layer. |

## Requirements

- Python `3.13.3`
- `uv`

The repo already includes:

- `.python-version`
- `pyproject.toml`
- `uv.lock`

## Setup

### 1) Install `uv`

If you do not have `uv`, install it from [astral.sh/uv](https://astral.sh/uv).

### 2) Use the exact Python version

```bash
uv python install 3.13.3
uv venv --python 3.13.3
```

### 3) Activate the virtual environment

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

### 4) Install exact dependencies

```bash
uv sync --locked
```

## Set up `.env`

1. Copy the example file:

```powershell
Copy-Item .env.example .env
```

2. Open `.env` and fill in what you need.

Minimum useful values:

```env
GROQ_API_KEY=your_groq_api_key_here
HOMEY_CORPUS_DIR=
HOMEY_SEMANTIC_GUARD=false
HOMEY_RETRIEVAL=false
HOMEY_FIT=false
HOMEY_TENANT_ID=vryfid
```

Notes:

- `GROQ_API_KEY` is optional for tests, but needed if you want the LLM-backed path.
- The repo can run without the key.
- If you later wire real retrieval documents, set `HOMEY_CORPUS_DIR` or the S3 variables in `.env.example`.

## Run the project

### Run all tests

```bash
pytest -q
```

### Run the evaluation harness

```bash
python -X utf8 eval/harness.py
```

### Run the stress scenario

```bash
python -X utf8 stress/combined_stress_day.py
```

### Start the API

```bash
python -X utf8 -m uvicorn infra.integration:app --port 8000
```

### Check the health endpoint

```bash
curl http://127.0.0.1:8000/health
```

## What to expect

- Tests and scripts are deterministic in the local setup.
- On Windows, `-X utf8` avoids console encoding issues for the harness and stress script.
- Retrieval can fall back to sample corpus data until the real backend corpus is connected.

## Clean-room proof

For the exact validation transcript and environment notes, see `docs/CLEAN_ROOM_PROOF.md`.

## Current status

- The first mergeable slice is the typed intent path plus schema and observability plumbing.
- Retrieval, broker explanation, and memory policy are safer now, but still depend on backend and policy decisions for full production use.

## Project layout

```text
agents/         Core reasoning, retrieval, fit, memory, and graph logic
infra/          API layer, schema adapter, and routing helpers
routers/        Community and campaign routing helpers
schemas/        Pydantic models and shared data contracts
observability/   JSONL event stream and trace output
eval/           Evaluation harness and golden-set cases
stress/         End-to-end stress scenario
tests/          Pytest coverage for the system
board/          Project status and task tracking
docs/           Proof and handoff documents
```
