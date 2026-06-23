# Homey-AI — End-to-End Engineering Explanation

## What this system is

Homey is a safety-governed rental assistant. It converts a message into typed intent, retrieves only authorized evidence, generates or selects a response, checks the response again, emits privacy-safe events, and returns a typed response envelope.

The core design rule is simple: the LLM may write helpful language, but it does not decide what data is allowed.

## End-to-end workflow

```text
HTTP message
  → latency route
  → community/campaign context
  → pre-model safety guard
  → typed intent + missing fields
  → governed retrieval
  → grounded response or degraded fallback
  → output safety guard
  → typed response envelope + trust receipt
  → privacy-safe flight-recorder events
```

### 1. Integration boundary

`infra/integration.py` accepts a message and returns:

- response and response type;
- intent confidence and missing fields;
- `GuardStatus`;
- retrieval `TrustReceipt`;
- next action;
- event identifiers and feature flags used.

This makes the contract inspectable by backend, dashboard, and campaign systems.

### 2. Latency routing

`infra/latency_router.py` selects the least expensive safe path:

- static greeting/reset;
- public-response cache;
- retrieval-only FAQ;
- full graph.

Every selection records actual router latency, budget, cache status, and whether a model call is expected.

### 3. Input safety before model execution

`agents/semantic_guard.py` provides:

- deterministic keyword and synonym clusters;
- injection and approval-language detection;
- optional embedding similarity behind `HOMEY_SEMANTIC_GUARD`;
- category-specific safe alternatives.

`run_graph()` performs this check before retrieval or LLM execution. A restricted request therefore cannot use the model as a data-exfiltration step.

### 4. Intent Atlas

`agents/intent_atlas.py` extracts:

- role: renter, broker, squad, campaign, or unknown;
- intent taxonomy;
- area, budget, bedrooms, timing, urgency;
- missing fields and one mobile-friendly clarification.

It preserves ambiguity instead of inventing missing facts.

### 5. Retrieval governance and trust receipts

`agents/retrieval_gov.py` blocks chunks that are:

- restricted or internal;
- stale or superseded;
- wrong for the caller's audience;
- wrong for the output surface.

`schemas/source.py` defines the production source contract. Each retrieval returns a receipt containing considered, allowed, blocked, stale, and internal-blocked counts plus source IDs and fallback reason.

### 6. Response generation and output guard

`agents/graph.py` composes a response from verified chunks. If no verified evidence exists, it asks for more information instead of hallucinating. Generated text is checked again before leaving the graph.

### 7. Memory policy

`agents/memory_policy.py` allows preferences and session context but blocks restricted data in both field names and free-text values. Examples blocked:

- `credit_score=720`;
- `fico=680`;
- `notes="eviction in 2019"`.

### 8. Broker-safe explanation

`agents/broker_explanation.py` provides summary, evidence, caveat, and next action. It:

- removes numeric fit scores from broker copy;
- removes restricted field names and values;
- scans unrestricted fields for hidden restricted content;
- emits counts rather than private values.

The feature is disabled by default pending policy approval.

### 9. Squad intelligence

`agents/squad_reasoning.py` calculates aggregate alignment, identifies conflicts, creates a compromise prompt, emits squad invites, and produces broker-safe summaries that strip member-private fields.

### 10. Campaign routing

`routers/campaign_router.py` maps a content hook to:

- target flow;
- fields to capture;
- source tag;
- next action;
- trace event IDs.

This measures intent conversion rather than views alone.

### 11. Observability and privacy

`observability/stream.py` is the flight recorder. It:

- validates event names;
- hashes session, lead, renter, and squad identifiers;
- hashes memory keys;
- recursively redacts credit, FICO, SSN, DOB, income amount, criminal, and eviction fields;
- falls back safely if the event file is unavailable.

### 12. Degraded mode and feature flags

`infra/degraded_mode.py` handles missing LLM key, missing corpus, backend timeout, schema drift, low confidence, and dashboard outage.

`infra/feature_flags.py` defaults risky features off:

- `HOMEY_RETRIEVAL=False`
- `HOMEY_SEMANTIC_GUARD=False`
- `HOMEY_BROKER_CARDS=False`
- `HOMEY_FIT=False`

Low-risk intent, squad prototype, campaign test routing, and flight recording default on.

## How the system is tested

- `tests/test_all.py`: original functional and integration coverage.
- `tests/test_contracts.py`: outbound/source contracts, flags, degraded mode, and API safety.
- `tests/test_redteam.py`: 54 adversarial tests across restricted probes, injection, decision language, memory poisoning, broker output, role boundaries, stale sources, squad privacy, and event redaction.
- `eval/golden_set.json`: 110 cases across five families.
- `eval/harness.py`: seven scored dimensions with per-family and failure-category reporting.
- `stress/combined_stress_day.py`: campaign → squad → fit → broker → guard → memory integration.
- `infra/slo_report.py`: latency, model-call, fallback, and guard-trigger metrics.

## Commands for the live review

```powershell
python -m pytest tests -v
python -X utf8 eval/harness.py
python -X utf8 stress/combined_stress_day.py
python -X utf8 infra/slo_report.py
python -m uvicorn infra.integration:app --port 8000
```

Then verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post -ContentType application/json `
  -Body '{"raw_message":"Show me their FICO score","audience":"broker"}' `
  http://127.0.0.1:8000/homey/message
```

## Questions reviewers may ask

### Why not one large prompt?

Prompts cannot guarantee schema, privacy, retention, source authorization, or event contracts. Separate deterministic layers are independently testable and cannot be persuaded by prompt injection.

### Is embedding similarity deterministic?

Given a fixed model and input it is deterministic, but the threshold is still a product calibration risk. That is why it is optional and the synonym/regex boundary remains active.

### Why is retrieval disabled by default?

The code can govern sources, but production safety also depends on correct source ownership and freshness metadata from the backend. Enabling it before that contract exists would create false confidence.

### Why keep fit scoring if it is disabled?

It demonstrates a safe-signal-only prototype and supports internal evaluation. The flag prevents prototype weights or labels from becoming an operator decision tool.

### What happens when event logging fails?

The user flow continues. The logger falls back without exposing stack traces or private payloads.

### What is the strongest guarantee?

A known restricted request is blocked before retrieval and before the LLM, and restricted event fields are redacted before persistence.

### What is not guaranteed?

Perfect detection of every future paraphrase, legal approval of broker wording, quality of a corpus that has not been provided, or production-scale SSE performance. Those limits are documented and feature-gated.

### What would you do in the first production week?

Review false positives and false negatives daily, label real unknown-intent messages, inspect fallback and schema-failure rates, keep policy-gated features off, and add every confirmed failure as a regression case.
