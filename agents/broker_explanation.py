"""
agents/broker_explanation.py  — Task 14: Broker Explanation
Generates safe, structured summaries for broker/operator view.

Four-part output: summary | evidence | caveat | next_action
Restricted fields are BLOCKED and listed in audit trail.
No approval/rejection language — ever.
"""

from typing import List, Optional
from pydantic import BaseModel
from observability.stream import emit_broker_event

# ─── Output model ─────────────────────────────────────────────────────────────

class BrokerExplanation(BaseModel):
    lead_id: str
    summary: str
    evidence: List[str]
    caveat: Optional[str]
    next_action: str
    restricted_fields_blocked: List[str]
    dashboard_event: dict


# ─── Restricted field list ────────────────────────────────────────────────────

RESTRICTED_FIELDS = [
    "credit_score", "criminal_record", "eviction_history",
    "raw_background_report", "ssn", "dob", "medical_history",
]

# ─── Safe language ────────────────────────────────────────────────────────────

SUMMARY_MAP = {
    "strong":     "This group shows strong alignment with your listing criteria.",
    "moderate":   "This group shows moderate alignment. A follow-up conversation is recommended.",
    "weak":       "This group has some gaps relative to your listing. Review the notes below.",
    "incomplete": "This profile is not yet complete. Additional information is needed.",
}

NEXT_ACTION_MAP = {
    "strong":     "Consider inviting this group to view the property.",
    "moderate":   "Request the missing items listed below before proceeding.",
    "weak":       "Assess whether the gaps are dealbreakers before investing further time.",
    "incomplete": "Ask the renter to complete their profile first.",
}


# ─── Builder ──────────────────────────────────────────────────────────────────

def build_broker_explanation(
    lead_id:    str,
    fit_result: dict,
    raw_fields: dict,
) -> BrokerExplanation:
    """
    Build a broker-safe explanation from soft-fit output.

    Failure case: raw_fields contains credit_score or criminal_record
    → those fields are captured in restricted_fields_blocked
    → they NEVER appear in summary, evidence, caveat, or next_action
    → audit trail shows what was blocked

    Dashboard event: broker_explanation_generated with fit_label
    and restricted_fields_blocked count.
    """
    # Block restricted fields — audit trail only
    blocked = [f for f in RESTRICTED_FIELDS if f in raw_fields]

    fit_label = fit_result.get("fit_label", "incomplete")
    evidence  = fit_result.get("fit_reasons", [])
    missing   = fit_result.get("missing_signals", [])

    summary     = SUMMARY_MAP.get(fit_label, SUMMARY_MAP["incomplete"])
    next_action = NEXT_ACTION_MAP.get(fit_label, NEXT_ACTION_MAP["incomplete"])

    caveat: Optional[str] = None
    if missing:
        caveat = f"Items not yet confirmed: {', '.join(missing)}."
    if blocked:
        caveat_note = (
            f"Note: {len(blocked)} field(s) from the background report "
            "are not included here and require separate review."
        )
        caveat = f"{caveat} {caveat_note}" if caveat else caveat_note

    event = emit_broker_event(lead_id, fit_label, len(blocked))

    return BrokerExplanation(
        lead_id=lead_id,
        summary=summary,
        evidence=evidence,
        caveat=caveat,
        next_action=next_action,
        restricted_fields_blocked=blocked,
        dashboard_event=event,
    )
