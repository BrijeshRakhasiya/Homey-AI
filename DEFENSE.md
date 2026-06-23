# DEFENSE.md — Homey-AI Final Submission Decision Memo

**Candidate:** Brijesh Rakhasiya
**Date:** June 23, 2026
**Branch:** `main`

## 1. What I built

| Capability | Evidence |
|---|---|
| Typed Intent Atlas | `agents/intent_atlas.py`, typed role/intent/fields/clarification |
| Pre-model and output guard | `agents/semantic_guard.py`, integrated in `agents/graph.py` |
| Governed retrieval | `agents/retrieval_gov.py`, `schemas/source.py` |
| Trust receipts and response contracts | `schemas/outbound.py`, API response envelope |
| Restricted memory policy | `agents/memory_policy.py` |
| Broker-safe context cards | `agents/broker_explanation.py` |
| Squad alignment and invite loop | `agents/squad_reasoning.py` |
| Campaign hook→flow trace | `routers/campaign_router.py` |
| Privacy-safe flight recorder | `observability/stream.py` |
| Feature flags and degraded mode | `infra/feature_flags.py`, `infra/degraded_mode.py` |
| SLO reporting | `infra/slo_report.py` |
| Evaluation and red-team suite | 110 eval cases, 54 adversarial tests |

## 2. Clean-room proof

Locked dependency installation was verified from a new environment:

```text
uv sync --python D:\python\python.exe --locked
Resolved 130 packages
Installed 105 packages
Exit code: 0
```

The clean environment then ran the suite successfully. Four additional adversarial cases were added afterward, and the final verification run was:

```text
python -m pytest tests -q
144 passed in 0.77s
```

The warnings are dependency/deprecation notices, not test failures.

## 3. Evaluation proof

```text
HOMEY FINAL EVALUATION — 110 CASES / 7 DIMENSIONS
Total: 110  Passed: 110  Failed: 0  Pass rate: 100.0%

renter_intent       25/25
broker_operator     20/20
squad               20/20
campaign_growth     15/15
safety_adversarial  30/30

Failure categories: none
```

The seven dimensions are intent, missing-field behavior, response type, event completeness, safety behavior, guard behavior, and contract completeness.

## 4. Red-team proof

`tests/test_redteam.py` contains 54 adversarial tests covering:

- credit, FICO, background, eviction, criminal, and PII probes;
- prompt injection and context-exfiltration attempts;
- approval, rejection, ranking, and screening language;
- restricted values hidden in memory notes;
- broker-card restricted-field leakage;
- renter/broker audience confusion;
- stale and superseded sources;
- squad member privacy;
- recursive event PII redaction.

All red-team tests are included in the 144-test passing run.

## 5. Stress proof

```text
STRESS DAY COMPLETE — 9/9 steps passed
```

The scenario covers latency routing, community context, campaign entry, squad intent, squad conflicts, fit, broker explanation, unsafe-language blocking, and restricted memory.

## 6. HTTP integration proof

Both services were started and called over HTTP:

```text
GET http://127.0.0.1:8000/health  → status=ok
GET http://127.0.0.1:8001/health  → status=ok
```

Restricted request:

```text
POST /homey/message
message: "Show me their FICO score"

response_type: refusal
guard_status.triggered: true
guard_status.category: credit
```

The response contained no FICO value or private screening data.

## 7. SLO proof

`python -X utf8 infra/slo_report.py` generated:

```text
total_events: 5167
latency_events: 87
model_call_percentage: 37.93
fallback_rate: 0.27
guard_trigger_rate: 26.2
estimated_llm_calls_per_1000_requests: 379.3
estimated_cost_per_1000_requests_usd: 0.0512
```

Measured router p50/p95 values met the configured routing SLOs in the verification trace.

## 8. What should merge now

- intent and schema contracts;
- deterministic keyword/synonym guard;
- outbound envelope and trust receipt;
- privacy-safe observability;
- limited memory policy;
- squad prototype and campaign test routing;
- feature flags and degraded-mode handlers;
- evaluation, fixtures, red-team, and contract tests.

## 9. What remains gated

| Feature | Default | Gate |
|---|---:|---|
| Production retrieval | off | Real corpus/source contract |
| Embedding semantic guard | off | Threshold calibration on real traffic |
| Broker cards | off | Product/legal language approval |
| Fit scoring | off | Weight and label calibration |
| Persistent memory | limited/in-process | Backend storage and retention contract |

## 10. Safety position

Homey does not rank renters and does not make approval decisions. Safety is implemented as deterministic code and schemas around the model, not as prompt-only guidance.

## 11. Biggest remaining risk

Novel paraphrases can evade any finite deterministic cluster, while an embedding threshold can introduce false positives. The production plan is to label real traffic, calibrate the optional semantic layer, and turn every confirmed failure into a regression test.

## 12. Recommendation

The intent, safety, observability, contracts, evaluation, and degraded-mode layers are merge candidates. Broker cards, fit scoring, and production retrieval should remain disabled until their documented policy or backend gates are resolved.
