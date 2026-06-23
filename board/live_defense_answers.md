# Live Defense Answers

## 1. What command runs the complete evaluation?

```powershell
python -m pytest tests -v
python -X utf8 eval/harness.py
```

The harness runs 110 cases across renter, broker, squad, campaign, and safety families. Earlier calibration failures were mainly guard-policy interpretation and intent taxonomy mismatches; the fixes were made in the classifier and guard, not hidden by lowering the threshold.

## 2. What is the smallest safe merge?

Merge Intent Atlas, outbound schemas, the flight recorder, deterministic guard clusters, feature flags, degraded-mode handlers, evaluation data, and tests. Keep broker cards, fit scoring, and production retrieval disabled until policy/backend approval.

## 3. How do you prevent restricted-data leakage?

Five boundaries:

1. Input guard blocks credit, background, eviction, PII, decision language, and injection attempts before retrieval or LLM execution.
2. Retrieval filters stale, internal, restricted, wrong-audience, wrong-surface, and superseded sources.
3. Memory checks both key and free-text value before storing.
4. Broker cards remove restricted keys and scan nested text.
5. Observability recursively redacts sensitive event fields.

## 4. What if the corpus is missing, stale, contradictory, or malformed?

Missing corpus returns an actionable fallback. Stale and superseded chunks are filtered and counted in the trust receipt. Contradictory content should emit `source_conflict_detected` and route to review. Invalid metadata fails validation rather than entering retrieval.

## 5. What proves value after seven days?

`guard_checked` grouped by category shows prevented unsafe requests. `intent_classified` volume and unknown-rate show how much traffic Homey understands. Both are useful without exposing renter data.

## 6. What does campaign routing add beyond views?

It connects a content hook to a target flow, captured fields, classified intent, and conversation completion. That distinguishes awareness from qualified engagement without claiming an applicant is qualified.

## 7. How does squad reasoning create growth safely?

It emits invite and alignment events using squad identifiers and aggregate state. Broker summaries strip each member's exact budget, income, screening hints, and PII.

## 8. What is most likely to fail in production?

Novel paraphrases around restricted concepts. Deterministic clusters are the always-on floor; the embedding layer stays flag-gated until calibrated on real messages.

## 9. Where is deterministic logic used?

Intent extraction, schema validation, feature flags, source authorization, memory policy, PII scrubbing, response contracts, and keyword/synonym safety checks are deterministic. LLM generation runs only after these boundaries.

## 10. What did you intentionally refuse to build?

Comparative renter ranking. It creates fair-housing and product risk. The safe alternative is a per-lead completeness summary and neutral next action.

## 11. What if product asks for “best renter”?

Explain the risk, refuse to ship ranking without legal approval, and propose a broker task list: request documents, schedule viewing, clarify timing, or wait for squad alignment.

## 12. What should be measured at 7, 30, and 90 days?

- 7 days: guard-trigger rate, fallback rate, schema failures, unknown-intent rate.
- 30 days: clarification completion, confidence distribution, squad invite-to-alignment conversion.
- 90 days: campaign-to-completed-conversation conversion, broker-card-to-viewing conversion, eval trend, and attack-category trend.

