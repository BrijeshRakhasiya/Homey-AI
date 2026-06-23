"""
agents/squad_reasoning.py  — Task 6: Squad Reasoning
Handles group searches: roommates, friends, partners, classmates.

Key rules:
  - Private member details stay OUT of broker-facing output
  - Conflict detected early → compromise prompt returned
  - 1-member "squad" → routed as normal renter
  - Alignment score aggregated for dashboard visibility
"""

from typing import List
from schemas.squad import SquadMember, SquadProfile
from observability.stream import emit_squad_event, emit_event

_MEMBER_PRIVATE_FIELDS = {
    "budget_exact", "income_amount", "credit_hint", "immigration_status",
    "ssn", "dob", "credit_score", "criminal_record", "eviction_history",
}


def emit_squad_invite(squad_id: str, missing_member_hint: str = "member_pending") -> str:
    event = emit_event("squad_invite_created", {
        "squad_id": squad_id,
        "missing_member_hint": missing_member_hint,
        "invite_reason": "squad_alignment_incomplete",
    })
    return event["event_id"]


def emit_squad_alignment(squad_id: str, alignment_score: float,
                         conflict_count: int, missing_count: int = 0) -> dict:
    return emit_event("squad_alignment_updated", {
        "squad_id": squad_id,
        "alignment_score": round(alignment_score, 2),
        "conflict_count": conflict_count,
        "missing_members": missing_count,
    })


def get_broker_safe_squad_summary(squad_profile: dict) -> dict:
    """Return aggregate squad state with all member-private fields removed."""
    import copy
    safe = copy.deepcopy(squad_profile)
    for member in safe.get("members", []):
        for field in _MEMBER_PRIVATE_FIELDS:
            member.pop(field, None)
    return safe


def build_squad_profile(
    squad_id: str,
    members: List[SquadMember],
) -> SquadProfile:
    """
    Build a shared squad profile from multiple member intents.

    Failure case: only 1 member → alignment_score=1.0, no conflicts,
    compromise_prompt=None. Route as renter.

    Failure case: all members have None budget → agreed_budget_max=None,
    budget_range_conflict NOT raised, clarification prompt instead.

    Dashboard event: squad_profile_built with alignment_score and conflict_count.
    """
    if len(members) == 1:
        event = emit_squad_event(squad_id, 1, 0, 1.0)
        return SquadProfile(
            squad_id=squad_id,
            member_count=1,
            agreed_budget_max=members[0].stated_budget,
            agreed_area=members[0].preferred_area,
            conflict_categories=[],
            alignment_score=1.0,
            compromise_prompt=None,
            dashboard_event=event,
        )

    conflicts: list[str] = []

    # ── Budget conflicts ──────────────────────────────────────────────────────
    budgets = [m.stated_budget for m in members if m.stated_budget is not None]
    if len(budgets) >= 2 and (max(budgets) - min(budgets)) >= 500:
        conflicts.append("budget_range_conflict")

    # ── Area conflicts ────────────────────────────────────────────────────────
    areas = [m.preferred_area.lower() for m in members
             if m.preferred_area is not None]
    unique_areas = list(set(areas))
    if len(unique_areas) > 1:
        conflicts.append("area_preference_conflict")

    # ── Timing conflicts ──────────────────────────────────────────────────────
    timings = [m.move_in_timing for m in members if m.move_in_timing is not None]
    if len(set(timings)) > 1:
        conflicts.append("timing_conflict")

    # ── Bedroom conflicts ─────────────────────────────────────────────────────
    bedrooms = [m.bedrooms_needed for m in members if m.bedrooms_needed is not None]
    if len(set(bedrooms)) > 1:
        conflicts.append("bedroom_need_conflict")

    # ── Alignment score ───────────────────────────────────────────────────────
    max_possible = 4
    alignment = round(1.0 - len(conflicts) / max_possible, 2)

    # ── Agreed values (conservative) ─────────────────────────────────────────
    agreed_budget = min(budgets) if budgets else None
    agreed_area   = unique_areas[0] if len(unique_areas) == 1 else None

    # ── Compromise prompt (first conflict only — mobile friendly) ─────────────
    compromise: str | None = None
    if "budget_range_conflict" in conflicts:
        compromise = (
            f"Your group has a budget range of ${min(budgets):,}–${max(budgets):,}. "
            "What is the maximum monthly rent everyone is comfortable with?"
        )
    elif "area_preference_conflict" in conflicts:
        areas_display = ", ".join(a.title() for a in unique_areas)
        compromise = (
            f"Your group prefers different areas ({areas_display}). "
            "Can you agree on one neighborhood to focus on first?"
        )
    elif "timing_conflict" in conflicts:
        compromise = (
            "Your group has different move-in dates in mind. "
            "What is the earliest date everyone can be ready to move?"
        )

    event = emit_squad_event(squad_id, len(members), len(conflicts), alignment)
    emit_squad_alignment(squad_id, alignment, len(conflicts))

    return SquadProfile(
        squad_id=squad_id,
        member_count=len(members),
        agreed_budget_max=agreed_budget,
        agreed_area=agreed_area,
        conflict_categories=conflicts,
        alignment_score=alignment,
        compromise_prompt=compromise,
        dashboard_event=event,
    )
