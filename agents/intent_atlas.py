"""
agents/intent_atlas.py  — Task 2: Intent Atlas
Turns raw renter/broker/squad text into a typed IntentState.
Preserves ambiguity — never invents facts.
Emits intent_classified event to observability stream.

Why a structured layer (not a single prompt)?
  - Each field is independently testable with pytest
  - Confidence score is computable without an LLM call
  - Missing fields drive the clarification prompt — deterministic, not hallucinated
  - Downstream nodes (graph.py) branch on typed role, not raw text
"""

import re
from typing import Optional
from schemas.intent import IntentState, UserRole
from observability.stream import emit_intent_event

# ─── Keyword dictionaries ─────────────────────────────────────────────────────

BROKER_KEYWORDS = [
    "candidate", "tenant list", "find me renters", "my clients",
    "on behalf of", "landlord", "property manager", "owner",
    "list my property", "manage properties",
]

SQUAD_KEYWORDS = [
    "roommate", "my friend", "we are", "group", "sibling",
    "partner", "couple", "together", "us two", "classmate",
    "me and my", "we need", "our budget",
]

RENTER_KEYWORDS = [
    "looking for", "need a place", "find apartment", "rent",
    "searching for", "want to rent", "need to move", "moving to",
    "2bhk", "1bhk", "studio", "bedroom",
]

URGENCY_IMMEDIATE = ["asap", "immediately", "urgent", "right away", "this week"]
URGENCY_FLEXIBLE  = ["flexible", "no rush", "sometime", "few months", "whenever"]

KNOWN_AREAS = [
    "brooklyn", "manhattan", "queens", "bronx", "staten island",
    "nyu", "jersey city", "hoboken", "astoria", "williamsburg",
    "bushwick", "harlem", "upper east side", "upper west side",
    "downtown", "midtown", "flushing", "jackson heights", "park slope",
]

AREA_ALIASES = {"bk": "Brooklyn", "jc": "Jersey City"}

CAMPAIGN_KEYWORDS = [
    "verified drop", "referral link", "referral code", "housing event",
    "housing fair", "preview challenge", "first look", "rent detective",
    "tiktok", "instagram dm", "facebook post",
]


# ─── Extractors ───────────────────────────────────────────────────────────────

def _extract_budget(text: str) -> Optional[int]:
    """Extract budget from text. Handles: $3000, 3k, 3,000, under 3000."""
    patterns = [
        r'\$\s*(\d{1,2})[kK]',           # $3k
        r'(\d{1,2})[kK]\s*(?:a month|/mo|per month)?',  # 3k a month
        r'\$\s*(\d{1,5})',                # $3000
        r'under\s+(\d{1,5})',            # under 3000
        r'around\s+(\d{1,5})',           # around 3000
        r'budget.*?(\d{1,5})',           # budget of 3000
        r'(\d{4,5})\s*(?:a month|/mo)', # 3000 a month
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if val < 100:          # treat as thousands
                val *= 1000
            if 400 <= val <= 30000:
                return val
    return None


def _extract_bedrooms(text: str) -> Optional[int]:
    """Extract bedroom count. Handles: 2BHK, 2 bed, 2-bedroom, studio."""
    if "studio" in text.lower():
        return 0
    patterns = [
        r'(\d)\s*b(?:hk|ed|edroom)',
        r'(\d)\s*-\s*bed',
        r'(\d)\s*br\b',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _extract_area(text: str) -> Optional[str]:
    """Match known area names in text."""
    text_lower = text.lower()
    for area in KNOWN_AREAS:
        if area in text_lower:
            return area.title()
    for alias, normalized in AREA_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text_lower):
            return normalized
    return None


def _extract_timing(text: str) -> Optional[str]:
    """Extract move-in timing hints."""
    months = ["january","february","march","april","may","june",
              "july","august","september","october","november","december"]
    text_lower = text.lower()
    for month in months:
        if month in text_lower:
            return month.capitalize()
    patterns = [r'(?:in|by|from)\s+(\w+\s+\d{4})', r'(\d{1,2}/\d{4})']
    for pattern in patterns:
        m = re.search(pattern, text_lower)
        if m:
            return m.group(1)
    return None


def _detect_urgency(text: str) -> str:
    text_lower = text.lower()
    if any(k in text_lower for k in URGENCY_IMMEDIATE):
        return "immediate"
    if any(k in text_lower for k in URGENCY_FLEXIBLE):
        return "flexible"
    return "unknown"


def _detect_role(text: str) -> tuple[UserRole, float]:
    text_lower = text.lower()
    if any(k in text_lower for k in CAMPAIGN_KEYWORDS):
        return UserRole.CAMPAIGN, 0.84
    if any(k in text_lower for k in BROKER_KEYWORDS):
        return UserRole.BROKER, 0.87
    if any(k in text_lower for k in SQUAD_KEYWORDS):
        return UserRole.SQUAD, 0.82
    if any(k in text_lower for k in RENTER_KEYWORDS):
        return UserRole.RENTER, 0.78
    return UserRole.UNKNOWN, 0.25


def _detect_intent(text: str, role: UserRole) -> str:
    from agents.semantic_guard import check_input
    guard = check_input(text)
    if guard["blocked"]:
        return {
            "approval_language": "approval_language",
            "prompt_injection": "prompt_injection",
            "pii": "restricted_data_probe",
            "credit": "restricted_data_probe",
            "criminal": "restricted_data_probe",
            "eviction": "restricted_data_probe",
            "protected_class": "restricted_data_probe",
        }.get(guard["category"], "restricted_data_probe")
    lower = text.lower()
    if role == UserRole.CAMPAIGN:
        return "campaign_entry"
    if role == UserRole.BROKER:
        return "broker_request"
    if role == UserRole.SQUAD:
        if any(term in lower for term in ("invite", "add them", "hasn't signed up", "has not signed up")):
            return "squad_invite"
        if any(term in lower for term in ("but i", "disagree", "different", "conflict", "except")):
            return "squad_conflict"
        if any(term in lower for term in ("what info", "summary", "verified so far")):
            return "squad_info"
        return "squad_search"
    if any(term in lower for term in (
        "how does", "what docs", "what documents", "what is homey",
        "average rent", "rent stabilized", "rent-stabilized",
        "can i afford", "what neighborhoods",
    )):
        return "renter_info"
    if any(term in lower for term in ("help me", "search for me", "process work")):
        return "support"
    if role == UserRole.RENTER:
        return "renter_search"
    return "unknown"


# ─── Clarification prompt builder ─────────────────────────────────────────────

CLARIFICATION_MAP = {
    "budget":    "What's your monthly budget?",
    "bedrooms":  "How many bedrooms do you need?",
    "area":      "Which neighborhood are you looking in?",
    "user_role": "Are you looking to rent, or do you manage properties?",
    "timing":    "When are you looking to move in?",
}


# ─── Main function ────────────────────────────────────────────────────────────

def run_intent_atlas(raw_input: str,
                     session_id: str = "default") -> IntentState:
    """
    Convert raw user message into typed IntentState.

    Failure case: empty / gibberish input
    → role=UNKNOWN, confidence=0.0, clarification_prompt set, no fields invented.
    """
    if not raw_input or not raw_input.strip():
        event = emit_intent_event("unknown", 0.0, 4, session_id)
        return IntentState(
            raw_input=raw_input,
            role=UserRole.UNKNOWN,
            intent="unknown",
            confidence=0.0,
            missing_fields=["user_role", "area", "budget", "bedrooms"],
            clarification_prompt="Hi! Are you looking to rent a home, or do you manage properties?",
            dashboard_event=event,
        )

    text = raw_input.strip()
    role, confidence = _detect_role(text)
    budget   = _extract_budget(text)
    bedrooms = _extract_bedrooms(text)
    area     = _extract_area(text)
    timing   = _extract_timing(text)
    urgency  = _detect_urgency(text)
    intent_name = _detect_intent(text, role)

    # Collect missing fields (only for renter/squad flows)
    missing: list[str] = []
    if role == UserRole.UNKNOWN:
        missing.append("user_role")
    if role in (UserRole.RENTER, UserRole.SQUAD, UserRole.CAMPAIGN, UserRole.UNKNOWN):
        if budget   is None: missing.append("budget")
        if bedrooms is None: missing.append("bedrooms")
        if area     is None: missing.append("area")
        if timing   is None: missing.append("timing")

    # Clarification — ask about FIRST missing field only (mobile-friendly)
    clarification: Optional[str] = None
    if missing:
        clarification = CLARIFICATION_MAP.get(missing[0])

    event = emit_intent_event(role.value, confidence, len(missing), session_id)

    return IntentState(
        raw_input=raw_input,
        role=role,
        intent=intent_name,
        confidence=confidence,
        area=area,
        budget=budget,
        bedrooms=bedrooms,
        timing=timing,
        urgency=urgency,
        missing_fields=missing,
        clarification_prompt=clarification,
        dashboard_event=event,
    )
