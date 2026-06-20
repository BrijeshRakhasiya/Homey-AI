"""
agents/broker_explanation.py  
Safe 4-part broker explanation with two-layer restricted data blocking.

Layer 1 (v1): field NAME in RESTRICTED_FIELDS list
Layer 2 (v2): field VALUE contains restricted content patterns
              catches: notes="fico 680 eviction 2019"

Output changes from v1:
  - fit_score REMOVED from broker output (Aiden's point #6)
  - fit_label REPLACED with: "ready_to_proceed" | "needs_follow_up" | "needs_more_info"
  - No numeric scores, no "strong/weak" labels in broker-facing text
"""

import re
from typing import Any, List, Optional
from pydantic import BaseModel
from observability.stream import emit_broker_event


# ── Restricted field names (Layer 1) ──────────────────────────────────────────
RESTRICTED_FIELDS: list[str] = [
    "credit_score", "criminal_record", "eviction_history",
    "raw_background_report", "ssn", "dob", "medical_history",
    "fico", "screening_result", "risk_level",
]

# ── Restricted content patterns (Layer 2) ─────────────────────────────────────
RESTRICTED_CONTENT_PATTERNS: dict[str, str] = {
    "eviction_content":  r'\beviction\b',
    "criminal_content":  r'\bcriminal\b|\barrest\b|\bconviction\b',
    "credit_content":    r'\bfico\b|\bcredit[\s_]?score\b|\b[5-8]\d{2}\s*score\b',
    "screening_content": r'\bscreening\b|\bbackground[\s_]?report\b',
}


def _scan_value_for_restricted_content(value: Any) -> list[str]:
    """Return list of content pattern labels found in value."""
    hits = []
    val_str = str(value).lower()
    for label, pattern in RESTRICTED_CONTENT_PATTERNS.items():
        if re.search(pattern, val_str):
            hits.append(label)
    return hits


# ── Output model ───────────────────────────────────────────────────────────────

class BrokerExplanation(BaseModel):
    lead_id: str
    # No fit_score exposed to broker — internal only
    broker_status: str            # "ready_to_proceed" | "needs_follow_up" | "needs_more_info"
    summary: str                  # safe, factual, no score/label
    evidence: List[str]           # observable alignment signals
    caveat: Optional[str]         # what is missing or unconfirmed
    next_action: str              # concrete next step
    restricted_fields_blocked: List[str]   # audit trail (names only, no values)
    dashboard_event: dict


# ── Safe language maps (no approval words) ────────────────────────────────────

BROKER_STATUS_MAP: dict[str, str] = {
    "strong":     "ready_to_proceed",
    "moderate":   "needs_follow_up",
    "weak":       "needs_more_info",
    "incomplete": "needs_more_info",
}

SUMMARY_MAP: dict[str, str] = {
    "strong":     "This group's stated preferences align with your listing on all key dimensions.",
    "moderate":   "This group shows alignment on several dimensions. A follow-up conversation is recommended.",
    "weak":       "This group has notable gaps relative to your listing. Review the items below.",
    "incomplete": "This profile is not yet complete. Additional information is needed before evaluation.",
}

NEXT_ACTION_MAP: dict[str, str] = {
    "strong":     "Consider inviting this group to view the property.",
    "moderate":   "Request the missing items listed below before scheduling a viewing.",
    "weak":       "Assess whether the gaps are dealbreakers before investing further time.",
    "incomplete": "Ask the renter to complete their profile first.",
}


# ── Builder ────────────────────────────────────────────────────────────────────

def build_broker_explanation(
    lead_id:    str,
    fit_result: dict,
    raw_fields: dict,
) -> BrokerExplanation:
    """
    Build broker-safe explanation.

    Layer 1: field names in RESTRICTED_FIELDS → blocked, audit trail entry.
    Layer 2: field values containing restricted content → value redacted, audit trail entry.

    fit_score is NEVER included in broker output.
    fit_label is translated to broker_status (no approval connotation).

    Adversarial test C2:
      Input: raw_fields = {"notes": "renter has eviction 2019, fico 680"}
      Layer 1: "notes" not in RESTRICTED_FIELDS → passes name check.
      Layer 2: value contains "eviction" + "fico" → blocked, redacted.
      Output: "notes[content:eviction_content,credit_content]" in restricted_fields_blocked.
              notes value NEVER reaches summary or evidence text.
    """
    blocked: list[str] = []
    safe_raw: dict     = {}

    for field, value in raw_fields.items():
        # Layer 1: name check
        if field in RESTRICTED_FIELDS:
            blocked.append(field)
            continue  # don't include in safe_raw

        # Layer 2: value content check
        if isinstance(value, str):
            content_hits = _scan_value_for_restricted_content(value)
            if content_hits:
                label = f"{field}[content:{','.join(content_hits)}]"
                blocked.append(label)
                safe_raw[field] = "[REDACTED — restricted content detected]"
                continue

        safe_raw[field] = value

    fit_label     = fit_result.get("fit_label", "incomplete")
    evidence      = fit_result.get("fit_reasons", [])
    missing       = fit_result.get("missing_signals", [])
    broker_status = BROKER_STATUS_MAP.get(fit_label, "needs_more_info")
    summary       = SUMMARY_MAP.get(fit_label, SUMMARY_MAP["incomplete"])
    next_action   = NEXT_ACTION_MAP.get(fit_label, NEXT_ACTION_MAP["incomplete"])

    caveat: Optional[str] = None
    if missing:
        caveat = f"Items not yet confirmed: {', '.join(missing)}."
    if blocked:
        note = (f"{len(blocked)} field(s) from background or screening data "
                "require separate review and are not shown here.")
        caveat = f"{caveat} {note}" if caveat else note

    event = emit_broker_event(lead_id, broker_status, len(blocked))

    return BrokerExplanation(
        lead_id=lead_id,
        broker_status=broker_status,
        summary=summary,
        evidence=evidence,
        caveat=caveat,
        next_action=next_action,
        restricted_fields_blocked=blocked,
        dashboard_event=event,
    )
