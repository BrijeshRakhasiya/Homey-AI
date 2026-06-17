"""
routers/community_router.py  — Task 13: Micro-Community Context
Adapts Homey's opening message based on WHERE the user came from.

Rules:
  - Source tag adjusts first prompt and tone ONLY
  - No demographic inference from source
  - No protected-class assumptions
  - Core contracts stay identical regardless of community
  - Unknown source → safe default profile
"""

from typing import Optional
from pydantic import BaseModel
from observability.stream import _emit


# ─── Community profiles ───────────────────────────────────────────────────────

COMMUNITY_PROFILES: dict[str, dict] = {
    "nyu": {
        "likely_intent":  "renter",
        "first_prompt":   (
            "Hey! Looking for a place near campus? "
            "Tell me your budget and move-in date and I'll get started."
        ),
        "tone": "casual_friendly",
    },
    "jersey_city": {
        "likely_intent":  "renter",
        "first_prompt":   (
            "Welcome! Are you relocating to Jersey City? "
            "What are you looking for in a rental?"
        ),
        "tone": "professional_warm",
    },
    "shul": {
        "likely_intent":  "renter",
        "first_prompt":   (
            "Hi! Looking for a home in the community? "
            "What neighborhood and budget do you have in mind?"
        ),
        "tone": "community_warm",
    },
    "brooklyn": {
        "likely_intent":  "renter",
        "first_prompt":   (
            "Hi! Brooklyn is a great choice. "
            "What's your budget and how many bedrooms do you need?"
        ),
        "tone": "casual_friendly",
    },
    "manhattan": {
        "likely_intent":  "renter",
        "first_prompt":   (
            "Hi there! Looking in Manhattan? "
            "Let me know your budget and preferred neighborhood."
        ),
        "tone": "professional_warm",
    },
    "default": {
        "likely_intent":  "unknown",
        "first_prompt":   (
            "Hi! I'm Homey. "
            "Are you looking to rent a home, or do you manage properties?"
        ),
        "tone": "neutral_friendly",
    },
}


# ─── Output model ─────────────────────────────────────────────────────────────

class CommunityContext(BaseModel):
    source_tag:     str
    likely_intent:  str
    first_prompt:   str
    tone:           str
    dashboard_event: dict


# ─── Router ───────────────────────────────────────────────────────────────────

def get_community_context(source_tag: Optional[str]) -> CommunityContext:
    """
    Return a community-specific context object.

    Failure case: unknown or None source_tag
    → falls through to "default" profile, never raises.

    Dashboard event: community_context_applied with source_tag
    and likely_intent so Dhruv can track channel mix.
    """
    tag     = (source_tag or "default").lower().strip()
    profile = COMMUNITY_PROFILES.get(tag, COMMUNITY_PROFILES["default"])

    event = _emit({
        "event_type":    "community_context_applied",
        "source_tag":    tag,
        "likely_intent": profile["likely_intent"],
    })

    return CommunityContext(
        source_tag=tag,
        likely_intent=profile["likely_intent"],
        first_prompt=profile["first_prompt"],
        tone=profile["tone"],
        dashboard_event=event,
    )
