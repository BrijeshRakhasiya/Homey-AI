# RISK MEMO — Homey-AI Production Risk Assessment

This memo separates working prototype guarantees from decisions that still require real traffic, backend contracts, or policy approval.

## 1. HIGH — Semantic threshold is not calibrated on real traffic

The optional embedding guard uses a prototype similarity threshold. Keyword and synonym protection remains active, but `HOMEY_SEMANTIC_GUARD` defaults to `False` until the threshold is evaluated on at least 500 representative messages. Owner: Brijesh + Aiden.

## 2. HIGH — Evaluation data is synthetic

The 110-case suite covers five required families and 30 adversarial cases, but synthetic language cannot represent every abbreviation, typo, or social-engineering attack. Treat 100% as a regression baseline, not proof of production perfection. Owner: Brijesh.

## 3. HIGH — Broker-card language needs policy review

Even neutral labels may be interpreted as screening signals. `HOMEY_BROKER_CARDS=False` and no comparative renter ranking is implemented. Owner: Aiden + legal.

## 4. HIGH — Fit weights are prototype assumptions

Budget, area, bedroom, timing, completeness, and verification weights are not calibrated against VryfID funnel outcomes. `HOMEY_FIT=False` prevents external use. Owner: Aiden + Brijesh.

## 5. MEDIUM — Real corpus contract is unavailable

Retrieval governance works against typed metadata and local fixtures, but the production source feed, ownership rules, and refresh contract are backend-gated. `HOMEY_RETRIEVAL=False`. Owner: Nikunj.

## 6. MEDIUM — Memory is in-process

Restricted writes are blocked and TTL behavior exists, but memory does not persist across restarts. A production store must enforce tenant boundaries and TTL server-side. Owner: Nikunj.

## 7. MEDIUM — Squad invite delivery is not connected

Homey emits `squad_invite_created`, but SMS, email, or WhatsApp delivery requires a downstream contract. No contact details are placed in the event. Owner: Nikunj + Gabe.

## 8. MEDIUM — Feature flags require deployment changes

Flags are environment-based, not remotely managed. Emergency shutdown requires an environment update and restart. Owner: Nikunj.

## 9. LOW — LLM provider throttling

Groq can time out or rate-limit. The graph falls back to grounded/static behavior and emits a fallback event, but quality may be lower. Owner: Brijesh.

## 10. LOW — Dashboard SSE concurrency is untested

The demo event stream is suitable for evaluation but has not been load-tested for multiple operators. Production should use a managed event sink. Owner: Dhruv.

