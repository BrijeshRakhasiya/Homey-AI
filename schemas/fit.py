"""
schemas/fit.py
Signal taxonomy for the Soft-Fit Engine.
ALLOWED_SIGNALS: safe to use in scoring.
BLOCKED_SIGNALS: must NEVER appear in fit logic or broker output.
"""

from pydantic import BaseModel, ConfigDict
from typing import List, Optional


# ─── Signal Taxonomy ──────────────────────────────────────────────────────────

ALLOWED_SIGNALS = [
    "budget_match",       # stated_budget vs property price
    "area_match",         # preferred area vs property location
    "bedroom_match",      # bedrooms needed vs available
    "timing_match",       # move-in readiness vs availability date
    "profile_complete",   # has the renter finished their profile
    "income_verified",    # income status (boolean only, NOT the amount)
    "urgency_level",      # how soon they need to move
]

BLOCKED_SIGNALS = [
    "credit_score",
    "criminal_record",
    "eviction_history",
    "race",
    "religion",
    "nationality",
    "raw_background_report",
    "medical_history",
    "ssn",
    "dob",
]

SIGNAL_WEIGHTS = {
    "budget_match":     0.30,
    "area_match":       0.25,
    "bedroom_match":    0.15,
    "timing_match":     0.15,
    "profile_complete": 0.10,
    "income_verified":  0.05,
}


# ─── Input / Output Models ────────────────────────────────────────────────────

class SoftFitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")   # reject credit_score etc.

    renter_id: str
    stated_budget: int
    property_price: int
    area_match: bool
    bedroom_match: bool
    timing_match: bool
    profile_complete: bool
    income_verified: bool
    urgency: str = "unknown"   # "immediate" | "flexible" | "unknown"


class SoftFitOutput(BaseModel):
    renter_id: str
    fit_score: float
    fit_label: str             # "strong" | "moderate" | "weak" | "incomplete"
    fit_reasons: List[str]
    missing_signals: List[str]
    safe_label: str            # broker-safe language, no approval words
    dashboard_event: dict


class PropertyRequirement(BaseModel):
    area: str
    max_budget: int
    min_bedrooms: int
    move_in_date: str
    pet_friendly: bool = False


class RenterProfile(BaseModel):
    renter_id: str
    stated_budget: int
    stated_area: str
    bedrooms_needed: int
    move_in_readiness: str     # "immediate" | "30_days" | "60_days"
    profile_complete: bool
    income_verified: bool
    has_pets: bool = False


class FitResult(BaseModel):
    renter_id: str
    fit_level: str             # "strong_match" | "partial_match" | "needs_info"
    fit_reasons: List[str]
    missing_info: List[str]
    safe_summary: str
    dashboard_event: dict
