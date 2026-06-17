"""
infra/schema_adapter.py  — Task 11: Schema Discipline
Adapter layer between raw backend/provider payloads and canonical Homey objects.

If Nikunj renames a field, this layer catches it loudly and logs a
schema_validation_failed event — never silently passes None to reasoning.

Why structured?
  - Schema drift is silent and deadly in production
  - Adapter is the single place to update field mappings
  - ValidationError is logged as a dashboard event so Nikunj sees it immediately
  - Tests can inject broken payloads without touching the rest of the system
"""

from pydantic import ValidationError
from schemas.fit import RenterProfile
from observability.stream import emit_schema_event, _emit


# ─── Field map: raw backend name → canonical Homey name ──────────────────────
# Update this map when Nikunj changes field names. Never update downstream code.

RENTER_FIELD_MAP: dict[str, str] = {
    "user_id":        "renter_id",
    "max_rent":       "stated_budget",
    "neighborhood":   "stated_area",
    "num_bedrooms":   "bedrooms_needed",
    "move_readiness": "move_in_readiness",
    "income_status":  "income_verified",
    "is_complete":    "profile_complete",
    "has_pet":        "has_pets",
    # Direct names also accepted (idempotent)
    "renter_id":      "renter_id",
    "stated_budget":  "stated_budget",
    "stated_area":    "stated_area",
    "bedrooms_needed": "bedrooms_needed",
    "move_in_readiness": "move_in_readiness",
    "income_verified": "income_verified",
    "profile_complete": "profile_complete",
    "has_pets":       "has_pets",
}

REQUIRED_CANONICAL = [
    "renter_id", "stated_budget", "stated_area",
    "bedrooms_needed", "profile_complete", "income_verified",
]


def adapt_renter_payload(raw: dict) -> RenterProfile:
    """
    Map raw backend payload → canonical RenterProfile.

    Failure case 1: field renamed (e.g. user_id → uid)
    → missing field logged in schema_validation_failed event
    → raises ValueError with clear message for caller to handle safely

    Failure case 2: field has wrong type (e.g. stated_budget = "three thousand")
    → Pydantic ValidationError logged + re-raised as ValueError

    Integration seam: Nikunj's backend POSTs raw JSON to /homey/message
    → this adapter runs first → canonical object flows to reasoning layer
    """
    mapped:  dict  = {}
    missing: list  = []
    unknown: list  = []

    for raw_key, value in raw.items():
        canonical = RENTER_FIELD_MAP.get(raw_key)
        if canonical:
            mapped[canonical] = value
        else:
            unknown.append(raw_key)

    # Identify required fields that could not be mapped
    for field in REQUIRED_CANONICAL:
        if field not in mapped:
            missing.append(field)

    if missing:
        emit_schema_event(missing, f"Required fields not found in payload: {missing}")

    # Log unknown fields (may indicate new fields added by backend)
    if unknown:
        _emit({
            "event_type":     "schema_unknown_fields",
            "unknown_fields": unknown,
            "note":           "These fields exist in payload but have no canonical mapping.",
        })

    try:
        return RenterProfile(**mapped)
    except (ValidationError, TypeError) as e:
        error_msg = str(e)
        emit_schema_event(missing, error_msg)
        raise ValueError(
            f"Schema adaptation failed. "
            f"Missing: {missing}. Unknown: {unknown}. Error: {error_msg}"
        )
