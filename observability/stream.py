"""
observability/stream.py  — Task 9
Structured JSONL event logger.
Logs categories and reason codes ONLY — never raw user data.
Dhruv reads observability/traces/stream.jsonl for dashboard metrics.
"""

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import jsonlines
except ModuleNotFoundError:
    jsonlines = None

LOG_PATH = Path(__file__).parent / "traces" / "stream.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
EVENT_SCHEMA_VERSION = "1.1"
DEFAULT_TENANT_ID = os.getenv("HOMEY_TENANT_ID", "vryfid")
EVENT_HASH_SALT = os.getenv("HOMEY_EVENT_HASH_SALT", "homey-dev-salt")


def _hash_token(value: Any) -> str:
    material = f"{EVENT_HASH_SALT}:{value}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def _sanitize_text(value: Any) -> str:
    text = str(value)
    text = re.sub(r'(["\']).*?\1', '"[REDACTED]"', text)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", text)
    text = re.sub(r"\$\s?\d+(?:,\d{3})*(?:\.\d+)?", "[REDACTED_AMOUNT]", text)
    text = re.sub(r"\b\d{3,}\b", "[REDACTED_NUMBER]", text)
    return text[:160]


def _sanitize_payload(payload: dict) -> dict:
    sanitized = dict(payload)
    sanitized.setdefault("schema_version", EVENT_SCHEMA_VERSION)
    sanitized.setdefault("tenant_id", DEFAULT_TENANT_ID)

    if "session_id" in sanitized:
        sanitized["session_token"] = _hash_token(sanitized.pop("session_id"))

    for key in ("renter_id", "lead_id", "squad_id"):
        if key in sanitized:
            sanitized[key.replace("_id", "_token")] = _hash_token(sanitized.pop(key))

    if "key" in sanitized:
        sanitized["key_hash"] = _hash_token(sanitized.pop("key"))

    if "error" in sanitized and sanitized["error"] is not None:
        sanitized["error"] = _sanitize_text(sanitized["error"])

    if "reason" in sanitized and sanitized["reason"] is not None:
        sanitized["reason"] = _sanitize_text(sanitized["reason"])

    return sanitized


def _emit(payload: dict) -> dict:
    """Write one event line. Falls back to stdout if file not writable."""
    payload = _sanitize_payload(payload)
    payload.setdefault("event_id", str(uuid.uuid4()))
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    try:
        if jsonlines is not None:
            with jsonlines.open(str(LOG_PATH), mode="a") as writer:
                writer.write(payload)
        else:
            with LOG_PATH.open("a", encoding="utf-8") as writer:
                writer.write(json.dumps(payload, ensure_ascii=False) + "\n")
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
    if fit_score >= 0.80:
        score_band = "high"
    elif fit_score >= 0.55:
        score_band = "medium"
    elif fit_score >= 0.30:
        score_band = "low"
    else:
        score_band = "minimal"
    return _emit({
        "event_type": "soft_fit_scored",
        "renter_id": renter_id,
        "fit_label": fit_label,
        "fit_score_band": score_band,
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


def emit_broker_event(lead_id: str, broker_status: str,
                      restricted_blocked: int) -> dict:
    return _emit({
        "event_type": "broker_explanation_generated",
        "lead_id": lead_id,
        "broker_status": broker_status,
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
