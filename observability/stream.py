"""
observability/stream.py  — Task 9
Structured JSONL event logger.
Logs categories and reason codes ONLY — never raw user data.
Dhruv reads observability/traces/stream.jsonl for dashboard metrics.
"""

import jsonlines
import uuid
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOG_PATH = Path(__file__).parent / "traces" / "stream.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _emit(payload: dict) -> dict:
    """Write one event line. Falls back to stdout if file not writable."""
    payload.setdefault("event_id", str(uuid.uuid4()))
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    try:
        with jsonlines.open(str(LOG_PATH), mode="a") as writer:
            writer.write(payload)
    except IOError:
        print(f"[OBS_FALLBACK] {payload}", file=sys.stdout)
    return payload


# ─── Public emitters ──────────────────────────────────────────────────────────

def emit_intent_event(role: str, confidence: float,
                      missing_count: int, session_id: str) -> dict:
    return _emit({
        "event_type": "intent_classified",
        "role": role,
        "confidence": confidence,
        "missing_field_count": missing_count,
        "session_id": session_id,
    })


def emit_retrieval_event(audience: str, chunks_returned: int,
                         evidence_sufficient: bool, session_id: str) -> dict:
    return _emit({
        "event_type": "retrieval_governed",
        "audience": audience,
        "chunks_returned": chunks_returned,
        "evidence_sufficient": evidence_sufficient,
        "session_id": session_id,
    })


def emit_guard_event(triggered: bool, reason: Optional[str],
                     session_id: str) -> dict:
    return _emit({
        "event_type": "guard_checked",
        "triggered": triggered,
        "reason": reason,
        "session_id": session_id,
    })


def emit_fit_event(renter_id: str, fit_label: str,
                   fit_score: float, missing_count: int) -> dict:
    return _emit({
        "event_type": "soft_fit_scored",
        "renter_id": renter_id,
        "fit_label": fit_label,
        "fit_score": fit_score,
        "missing_signal_count": missing_count,
    })


def emit_squad_event(squad_id: str, member_count: int,
                     conflict_count: int, alignment_score: float) -> dict:
    return _emit({
        "event_type": "squad_profile_built",
        "squad_id": squad_id,
        "member_count": member_count,
        "conflict_count": conflict_count,
        "alignment_score": alignment_score,
    })


def emit_campaign_event(source_channel: Optional[str],
                        detected_hook: Optional[str],
                        target_flow: str) -> dict:
    return _emit({
        "event_type": "campaign_entry_routed",
        "source_channel": source_channel,
        "detected_hook": detected_hook,
        "target_flow": target_flow,
    })


def emit_broker_event(lead_id: str, fit_label: str,
                      restricted_blocked: int) -> dict:
    return _emit({
        "event_type": "broker_explanation_generated",
        "lead_id": lead_id,
        "fit_label": fit_label,
        "restricted_fields_blocked": restricted_blocked,
    })


def emit_schema_event(missing_fields: list, error: str) -> dict:
    return _emit({
        "event_type": "schema_validation_failed",
        "missing_fields": missing_fields,
        "error": error,
    })


def emit_memory_event(key: str, category: str, will_expire: bool) -> dict:
    return _emit({
        "event_type": "memory_stored",
        "key": key,
        "category": category,
        "will_expire": will_expire,
    })


def emit_blocked_memory_event(key: str) -> dict:
    return _emit({
        "event_type": "blocked_memory_attempt",
        "key": key,
        "reason": "field_in_NEVER_STORE_list",
    })


def emit_latency_event(tier: str, model_called: bool,
                       cache_hit: bool, budget_ms: int) -> dict:
    return _emit({
        "event_type": "latency_route_selected",
        "tier": tier,
        "model_called": model_called,
        "cache_hit": cache_hit,
        "latency_budget_ms": budget_ms,
    })


def emit_failure_event(category: str, owner: str, impact: str) -> dict:
    return _emit({
        "event_type": "failure_logged",
        "category": category,
        "owner": owner,
        "impact": impact,
    })


def emit_eval_event(total: int, passed: int,
                    failed: int, pass_rate: float) -> dict:
    return _emit({
        "event_type": "eval_harness_run",
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
    })


def emit_graph_event(session_id: str, nodes_executed: int,
                     guard_passed: bool, response_type: str) -> dict:
    return _emit({
        "event_type": "graph_completed",
        "session_id": session_id,
        "nodes_executed": nodes_executed,
        "guard_passed": guard_passed,
        "response_type": response_type,
    })
