"""
agents/graph.py  — Task 4: Agent Workbench
LangGraph StateGraph where every node has exactly ONE job.

Node chain:
  route → retrieve → reason → guard → emit → END

Why LangGraph instead of one big prompt?
  - Every node is independently testable
  - State is typed — Nikunj can inspect it at any point
  - Guard node catches unsafe language REGARDLESS of what reason node says
  - Timeouts and fallbacks are node-level, not prompt-level
  - Abhishek can inject mock state to test any single node
"""

import asyncio
import os
import re
from typing import TypedDict, Optional, List, Any

from langgraph.graph import StateGraph, END

from agents.intent_atlas import run_intent_atlas
from agents.retrieval_gov import governed_retrieval
from agents.semantic_guard import check_input, check_output, safe_fallback_response
from infra.feature_flags import is_enabled
from observability.stream import (
    emit_guard_event, emit_graph_event, emit_retrieval_event
)

# ─── Shared state ────────────────────────────────────────────────────────────

class HomeyState(TypedDict):
    session_id: str
    raw_input: str
    audience: str                        # "renter" | "broker"
    intent: Optional[dict]
    retrieval: Optional[dict]
    response: Optional[str]
    guard_passed: bool
    events: List[dict]
    error: Optional[str]
    timeout_hit: bool
    nodes_executed: int


# ─── Blocked phrases (guard node) ─────────────────────────────────────────────

BLOCKED_PHRASES = [
    "approved", "rejected", "denied", "not approved",
    "credit score", "criminal record", "eviction",
    "background report", "failed screening",
]

BLOCKED_SEMANTIC_PATTERNS = [
    r"\bmeets the threshold\b",
    r"\bqualif(y|ies|ied|ying) for\b",
    r"\bmeets all requirements\b",
    r"\bpasses the screen(ing)?\b",
    r"\bstrong fit\b",
    r"\bgood fit\b",
    r"\bno issues found\b",
]

SAFE_FALLBACK_RESPONSE = (
    "I can share some helpful context about this listing, "
    "but final decisions are made by the property team after a full review."
)


def _guard_match(response: str) -> Optional[str]:
    normalized = response.lower()
    for phrase in BLOCKED_PHRASES:
        if phrase in normalized:
            return phrase
    for pattern in BLOCKED_SEMANTIC_PATTERNS:
        if re.search(pattern, normalized):
            return pattern
    return None


# ─── Nodes ────────────────────────────────────────────────────────────────────

def node_route(state: HomeyState) -> HomeyState:
    """ONLY job: run Intent Atlas, store typed intent in state."""
    try:
        intent = run_intent_atlas(state["raw_input"], state["session_id"])
        state["intent"] = intent.model_dump()
        state["events"].append(intent.dashboard_event)
    except Exception as e:
        state["error"] = f"route_node_error: {str(e)}"
        state["intent"] = {"role": "unknown", "confidence": 0.0, "missing_fields": []}
    state["nodes_executed"] = state.get("nodes_executed", 0) + 1
    return state


def node_retrieve(state: HomeyState) -> HomeyState:
    """ONLY job: run governed retrieval based on intent."""
    intent = state.get("intent", {})
    role   = intent.get("role", "unknown")

    if not is_enabled("HOMEY_RETRIEVAL"):
        event = emit_retrieval_event(
            state["audience"], 0, False, state["session_id"]
        )
        state["retrieval"] = {
            "chunks": [],
            "evidence_sufficient": False,
            "fallback_message": (
                intent.get("clarification_prompt")
                or "I don't have enough verified listing information right now. "
                   "Tell me your area, budget, and move-in timing."
            ),
            "trust_receipt": {
                "chunks_considered": 0,
                "chunks_allowed": 0,
                "chunks_blocked": 0,
                "chunks_stale": 0,
                "chunks_internal_blocked": 0,
                "freshness_status": "unknown",
                "evidence_sufficient": False,
                "fallback_reason": "retrieval_feature_disabled",
                "source_ids": [],
            },
            "dashboard_event": event,
        }
        state["events"].append(event)
        state["nodes_executed"] += 1
        return state

    # Skip retrieval for unknown role or simple greetings
    if role == "unknown" or not state["raw_input"].strip():
        state["retrieval"] = {
            "chunks": [],
            "evidence_sufficient": False,
            "fallback_message": intent.get("clarification_prompt"),
        }
        state["nodes_executed"] += 1
        return state

    try:
        result = governed_retrieval(
            query=state["raw_input"],
            audience=state["audience"],
            session_id=state["session_id"],
        )
        state["retrieval"] = result.model_dump()
        state["events"].append(result.dashboard_event)
    except Exception as e:
        state["error"]     = f"retrieve_node_error: {str(e)}"
        state["retrieval"] = {
            "chunks": [],
            "evidence_sufficient": False,
            "fallback_message": "Retrieval temporarily unavailable. Please try again shortly.",
        }
    state["nodes_executed"] += 1
    return state


def node_reason(state: HomeyState) -> HomeyState:
    """
    ONLY job: compose a response from retrieved chunks + intent.
    Uses Groq LLM if available; falls back to chunk text if not.
    """
    retrieval = state.get("retrieval", {})
    intent    = state.get("intent", {})

    if not retrieval.get("evidence_sufficient", False):
        state["response"] = (
            retrieval.get("fallback_message")
            or intent.get("clarification_prompt")
            or "Could you tell me a bit more about what you're looking for?"
        )
        state["nodes_executed"] += 1
        return state

    chunks    = retrieval.get("chunks", [])
    context   = "\n".join(c["text"] for c in chunks[:3])
    api_key   = os.getenv("GROQ_API_KEY", "")

    if api_key and api_key != "your_groq_api_key_here":
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            role_desc = intent.get("role", "renter")
            chat = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Homey, a helpful rental assistant for VryfID. "
                            "Answer based ONLY on the provided context. "
                            "Never use words like approved, rejected, denied, or credit score. "
                            "Be concise and helpful. Keep responses under 3 sentences."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Context:\n{context}\n\nUser ({role_desc}) asks: {state['raw_input']}",
                    },
                ],
                max_tokens=256,
                timeout=5.0,
            )
            state["response"] = chat.choices[0].message.content.strip()
        except Exception as e:
            # LLM timeout or error → safe fallback
            state["response"] = (
                f"Based on our listings: {context[:200]}... "
                "Would you like more details on any of these?"
            )
            state["error"] = f"llm_error: {str(e)}"
    else:
        # No API key — use chunk text directly (demo mode)
        state["response"] = (
            f"Here's what I found: {context[:300]}. "
            "Let me know if you need more details!"
        )

    state["nodes_executed"] += 1
    return state


def node_guard(state: HomeyState) -> HomeyState:
    """
    ONLY job: scan response for unsafe/blocked phrases.
    If found → replace with safe fallback + log event.
    This node ALWAYS runs regardless of upstream results.
    """
    response = state.get("response") or ""
    guard_result = check_output(response)
    triggered_phrase = _guard_match(response)

    if guard_result["blocked"] or triggered_phrase:
        state["response"]     = SAFE_FALLBACK_RESPONSE
        state["guard_passed"] = False
        if guard_result["blocked"]:
            state["response"] = safe_fallback_response(guard_result["category"])
        event = emit_guard_event(
            True,
            guard_result["reason"] if guard_result["blocked"] else triggered_phrase,
            state["session_id"],
            layer=guard_result["layer"] if guard_result["blocked"] else "keyword",
            category=guard_result["category"] if guard_result["blocked"] else "approval_language",
        )
    else:
        state["guard_passed"] = True
        event = emit_guard_event(False, None, state["session_id"])

    state["events"].append(event)
    state["nodes_executed"] += 1
    return state


def node_emit(state: HomeyState) -> HomeyState:
    """ONLY job: flush all collected events to observability stream."""
    response_type = "clarification" if not state.get("guard_passed") else "answer"
    if state.get("error"):
        response_type = "error_fallback"

    event = emit_graph_event(
        session_id=state["session_id"],
        nodes_executed=state.get("nodes_executed", 0),
        guard_passed=state.get("guard_passed", True),
        response_type=response_type,
    )
    state["events"].append(event)
    state["nodes_executed"] += 1
    return state


# ─── Graph builder ────────────────────────────────────────────────────────────

def build_homey_graph():
    """Compile the LangGraph StateGraph. Call once at startup."""
    g = StateGraph(HomeyState)
    g.add_node("route",    node_route)
    g.add_node("retrieve", node_retrieve)
    g.add_node("reason",   node_reason)
    g.add_node("guard",    node_guard)
    g.add_node("emit",     node_emit)

    g.set_entry_point("route")
    g.add_edge("route",    "retrieve")
    g.add_edge("retrieve", "reason")
    g.add_edge("reason",   "guard")
    g.add_edge("guard",    "emit")
    g.add_edge("emit",     END)

    return g.compile()


# ─── Public runner ────────────────────────────────────────────────────────────

_graph = None

def run_graph(raw_input: str,
              audience:  str = "renter",
              session_id: str = "default") -> dict:
    """
    Run the full Homey graph for one user message.
    Returns: {response, guard_passed, events, error}
    """
    input_guard = check_input(raw_input)
    if input_guard["blocked"]:
        guard_event = emit_guard_event(
            True,
            input_guard["reason"],
            session_id,
            layer=input_guard["layer"],
            category=input_guard["category"],
        )
        graph_event = emit_graph_event(
            session_id=session_id,
            nodes_executed=1,
            guard_passed=False,
            response_type="refusal",
        )
        return {
            "response": safe_fallback_response(input_guard["category"]),
            "response_type": "refusal",
            "guard_passed": False,
            "guard_status": {
                "input_checked": True,
                "output_checked": False,
                "triggered": True,
                "layer": input_guard["layer"],
                "category": input_guard["category"],
                "reason": input_guard["reason"],
            },
            "events": [guard_event, graph_event],
            "error": None,
            "intent": {
                "role": "unknown",
                "confidence": 1.0,
                "missing_fields": [],
                "clarification_prompt": None,
            },
            "source_receipt": {
                "chunks_considered": 0,
                "chunks_allowed": 0,
                "chunks_blocked": 0,
                "chunks_stale": 0,
                "chunks_internal_blocked": 0,
                "freshness_status": "unknown",
                "evidence_sufficient": False,
                "fallback_reason": "restricted_request",
                "source_ids": [],
            },
        }

    global _graph
    if _graph is None:
        _graph = build_homey_graph()

    initial: HomeyState = {
        "session_id":     session_id,
        "raw_input":      raw_input,
        "audience":       audience,
        "intent":         None,
        "retrieval":      None,
        "response":       None,
        "guard_passed":   True,
        "events":         [],
        "error":          None,
        "timeout_hit":    False,
        "nodes_executed": 0,
    }

    final = _graph.invoke(initial)
    response_type = "answer"
    if not final.get("guard_passed", True):
        response_type = "refusal"
    elif final.get("error"):
        response_type = "fallback"
    elif final.get("intent", {}).get("missing_fields"):
        response_type = "clarification"
    return {
        "response":     final.get("response"),
        "response_type": response_type,
        "guard_passed": final.get("guard_passed"),
        "guard_status": {
            "input_checked": True,
            "output_checked": True,
            "triggered": not final.get("guard_passed", True),
            "layer": None,
            "category": None,
            "reason": None,
        },
        "events":       final.get("events", []),
        "error":        final.get("error"),
        "intent":       final.get("intent"),
        "source_receipt": final.get("retrieval", {}).get("trust_receipt", {
            "chunks_considered": 0,
            "chunks_allowed": 0,
            "chunks_blocked": 0,
            "chunks_stale": 0,
            "chunks_internal_blocked": 0,
            "freshness_status": "unknown",
            "evidence_sufficient": False,
            "fallback_reason": "retrieval_not_used",
            "source_ids": [],
        }),
    }
