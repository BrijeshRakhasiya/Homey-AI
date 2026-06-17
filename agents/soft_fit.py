"""
agents/soft_fit.py  — Task 5: Soft-Fit Engine
Score renter-property fit using ONLY safe signals.

BLOCKED: credit_score, criminal_record, eviction_history, and all
         protected-class fields. Pydantic rejects them at input.

Why structured? Because the block list is a policy — it must be
enforced at schema level, not as a prompt instruction that can drift.
"""

from schemas.fit import (
    SoftFitInput, SoftFitOutput, SIGNAL_WEIGHTS,
    PropertyRequirement, RenterProfile, FitResult
)
from observability.stream import emit_fit_event


# ─── Safe language map ────────────────────────────────────────────────────────

SAFE_LABELS = {
    "strong": (
        "This profile shows strong alignment with your listing criteria."
    ),
    "moderate": (
        "This profile shows moderate alignment. "
        "A follow-up conversation is recommended."
    ),
    "weak": (
        "This profile has some gaps relative to your listing. "
        "Review the items below before proceeding."
    ),
    "incomplete": (
        "More information is needed before this profile can be evaluated."
    ),
}


# ─── Core scorer ─────────────────────────────────────────────────────────────

def compute_soft_fit(inp: SoftFitInput) -> SoftFitOutput:
    """
    Compute a weighted fit score using only ALLOWED_SIGNALS.

    Failure case: credit_score field in request
    → Pydantic raises ValidationError (extra=forbid) before this runs.
    → Caller should catch and return safe error response.

    Dashboard event: soft_fit_scored with renter_id, fit_label, fit_score.
    """
    scores:  dict[str, float] = {}
    reasons: list[str]        = []
    missing: list[str]        = []

    # Budget (30%)
    ratio = inp.stated_budget / inp.property_price if inp.property_price else 0.0
    scores["budget_match"] = min(ratio, 1.0)
    if ratio >= 0.9:
        reasons.append("stated budget aligns with property price")
    elif ratio >= 0.7:
        reasons.append("budget is close — worth discussing")
        missing.append("budget gap may need discussion")
    else:
        missing.append("significant budget gap")

    # Area (25%)
    scores["area_match"] = 1.0 if inp.area_match else 0.0
    if inp.area_match:
        reasons.append("preferred area matches property location")
    else:
        missing.append("area preference differs from property location")

    # Bedrooms (15%)
    scores["bedroom_match"] = 1.0 if inp.bedroom_match else 0.0
    if inp.bedroom_match:
        reasons.append("bedroom count aligns with availability")
    else:
        missing.append("bedroom count does not match")

    # Timing (15%)
    scores["timing_match"] = 1.0 if inp.timing_match else 0.4
    if inp.timing_match:
        reasons.append("move-in timing is compatible")
    else:
        missing.append("move-in timing not yet confirmed")

    # Profile completeness (10%)
    scores["profile_complete"] = 1.0 if inp.profile_complete else 0.0
    if not inp.profile_complete:
        missing.append("profile is not fully completed")

    # Income verified (5%)
    scores["income_verified"] = 1.0 if inp.income_verified else 0.0
    if not inp.income_verified:
        missing.append("income has not been verified yet")

    # Weighted total
    total = sum(scores[k] * SIGNAL_WEIGHTS[k] for k in SIGNAL_WEIGHTS)
    total = round(total, 3)

    # Label
    if total >= 0.80:
        label = "strong"
    elif total >= 0.55:
        label = "moderate"
    elif total >= 0.30:
        label = "weak"
    else:
        label = "incomplete"

    event = emit_fit_event(inp.renter_id, label, total, len(missing))

    return SoftFitOutput(
        renter_id=inp.renter_id,
        fit_score=total,
        fit_label=label,
        fit_reasons=reasons,
        missing_signals=missing,
        safe_label=SAFE_LABELS[label],
        dashboard_event=event,
    )


# ─── Executive Fit (Task 1) ───────────────────────────────────────────────────

def evaluate_executive_fit(
    prop: PropertyRequirement,
    renter: RenterProfile,
) -> FitResult:
    """
    Task 1: Match renter profile against property requirement.
    Uses only stated preferences — no screening data.

    Failure case: renter with no area, no budget, profile_complete=False
    → fit_level = "needs_info", safe_summary explains what's missing.
    """
    reasons: list[str] = []
    missing: list[str] = []

    if renter.stated_budget and renter.stated_budget <= prop.max_budget:
        reasons.append("stated budget is within the property range")
    else:
        missing.append("budget alignment needs confirmation")

    if renter.stated_area and renter.stated_area.lower() == prop.area.lower():
        reasons.append("preferred area matches property location")
    elif renter.stated_area:
        missing.append("area preference differs from listing location")
    else:
        missing.append("preferred area not specified")

    if renter.bedrooms_needed >= prop.min_bedrooms:
        reasons.append("bedroom requirement aligns")
    else:
        missing.append("bedroom count does not match listing")

    if not prop.pet_friendly and renter.has_pets:
        missing.append("property does not accept pets")

    if not renter.profile_complete:
        missing.append("profile is not yet fully completed")

    if not renter.income_verified:
        missing.append("income verification is pending")

    if len(reasons) >= 3 and not missing:
        fit_level = "strong_match"
    elif len(reasons) >= 1:
        fit_level = "partial_match"
    else:
        fit_level = "needs_info"

    reasons_text = ", ".join(reasons) if reasons else "limited available information"
    missing_text = f" Items to confirm: {', '.join(missing)}." if missing else ""
    safe_summary = (
        f"This profile shows {fit_level.replace('_', ' ')} "
        f"based on {reasons_text}.{missing_text}"
    )

    event = {
        "event_type": "executive_fit_evaluated",
        "renter_id":    renter.renter_id,
        "fit_level":    fit_level,
        "reason_count": len(reasons),
        "missing_count": len(missing),
    }

    return FitResult(
        renter_id=renter.renter_id,
        fit_level=fit_level,
        fit_reasons=reasons,
        missing_info=missing,
        safe_summary=safe_summary,
        dashboard_event=event,
    )
