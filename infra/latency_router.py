"""
infra/latency_router.py  — Task 10: Latency and Cost
Four-tier routing: deterministic first, expensive LLM last.

Tier 1 — Static   : known greeting/reset → instant reply, 0 model calls
Tier 2 — Cache    : seen before → cached reply, 0 model calls
Tier 3 — Retrieval: FAQ-type → retrieval only, 0 model calls
Tier 4 — Full LLM : complex/personal → full graph, model called

Why structured?
  - Latency budgets are enforced per tier, not per prompt
  - Cache is public-doc only — user-specific state is never cached
  - Tier selection is testable without running any model
  - Dhruv can track tier distribution to measure cost
"""

import hashlib
from typing import Optional
from pydantic import BaseModel
from observability.stream import emit_latency_event


# ─── Static responses (Tier 1) ────────────────────────────────────────────────

STATIC_RESPONSES: dict[str, str] = {
    "hi":      "Hi! Are you looking to rent a home, or do you manage properties?",
    "hello":   "Hello! How can Homey help you today?",
    "hey":     "Hey! What are you looking for today?",
    "reset":   "Sure! Let's start fresh. What are you looking for?",
    "restart": "No problem — let's start over. Are you a renter or a property manager?",
    "help":    "I can help you find rentals, check readiness, or answer property questions.",
    "stop":    "Got it. You can text me anytime to restart your search.",
    "cancel":  "Okay, your search has been paused. Text anytime to continue.",
}

# ─── FAQ patterns (Tier 3) ────────────────────────────────────────────────────

FAQ_PATTERNS: list[str] = [
    "what documents",
    "how does vryfid",
    "what is homey",
    "how long does",
    "what is required",
    "how do i verify",
    "what is income verification",
    "how do i apply",
    "what is a verified listing",
]

# ─── Latency budgets (ms) ─────────────────────────────────────────────────────

LATENCY_BUDGETS: dict[str, int] = {
    "static":         10,
    "cache":          50,
    "retrieval_only": 400,
    "full_llm":       2000,
}

# ─── In-memory cache (public docs only) ──────────────────────────────────────
# Replace with Redis in production.
_cache: dict[str, str] = {}


def _cache_key(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


# ─── Output model ─────────────────────────────────────────────────────────────

class LatencyRoute(BaseModel):
    tier:             str
    response:         Optional[str]   # set for static/cache tiers
    latency_budget_ms: int
    model_called:     bool
    cache_hit:        bool
    dashboard_event:  dict


# ─── Router ───────────────────────────────────────────────────────────────────

def route_for_latency(raw_input: str) -> LatencyRoute:
    """
    Pick the cheapest safe execution path for this message.

    Failure case: model timeout (handled in graph.py node_reason).
    This function itself never fails — always returns a valid tier.

    Dashboard event: latency_route_selected with tier and model_called.
    """
    text = raw_input.strip().lower()

    # ── Tier 1: Static ────────────────────────────────────────────────────────
    if text in STATIC_RESPONSES:
        event = emit_latency_event("static", False, False,
                                   LATENCY_BUDGETS["static"])
        return LatencyRoute(
            tier="static",
            response=STATIC_RESPONSES[text],
            latency_budget_ms=LATENCY_BUDGETS["static"],
            model_called=False,
            cache_hit=False,
            dashboard_event=event,
        )

    # ── Tier 2: Cache hit ─────────────────────────────────────────────────────
    key = _cache_key(text)
    if key in _cache:
        event = emit_latency_event("cache", False, True,
                                   LATENCY_BUDGETS["cache"])
        return LatencyRoute(
            tier="cache",
            response=_cache[key],
            latency_budget_ms=LATENCY_BUDGETS["cache"],
            model_called=False,
            cache_hit=True,
            dashboard_event=event,
        )

    # ── Tier 3: Retrieval only ────────────────────────────────────────────────
    if any(p in text for p in FAQ_PATTERNS):
        event = emit_latency_event("retrieval_only", False, False,
                                   LATENCY_BUDGETS["retrieval_only"])
        return LatencyRoute(
            tier="retrieval_only",
            response=None,
            latency_budget_ms=LATENCY_BUDGETS["retrieval_only"],
            model_called=False,
            cache_hit=False,
            dashboard_event=event,
        )

    # ── Tier 4: Full LLM ──────────────────────────────────────────────────────
    event = emit_latency_event("full_llm", True, False,
                               LATENCY_BUDGETS["full_llm"])
    return LatencyRoute(
        tier="full_llm",
        response=None,
        latency_budget_ms=LATENCY_BUDGETS["full_llm"],
        model_called=True,
        cache_hit=False,
        dashboard_event=event,
    )


def store_in_cache(raw_input: str, response: str) -> None:
    """
    Cache a public, non-personal response.
    Never cache user-specific data (names, addresses, budgets).
    """
    key = _cache_key(raw_input)
    _cache[key] = response
