"""
routers/campaign_router.py  — Task 7: Campaign Entry Router
Maps Gabe's content hooks to the right Homey flow.

Every campaign entry becomes a structured event so Dhruv
can measure hook→flow→conversion in the dashboard.

No fake scarcity. No qualification language.
"""

from typing import Optional
from pydantic import BaseModel
from observability.stream import emit_campaign_event


# ─── Hook taxonomy ────────────────────────────────────────────────────────────

CAMPAIGN_HOOKS: dict[str, list[str]] = {
    "verified_drop": [
        "verified listing", "verified drop", "vryfid drop",
        "verified unit", "confirmed listing",
    ],
    "preview_challenge": [
        "sneak peek", "first look", "preview", "coming soon", "exclusive look",
    ],
    "readiness_scan": [
        "ready to move", "am i ready", "readiness check",
        "check my readiness", "how ready",
    ],
    "squad_invite": [
        "bring your roommate", "squad search", "group search",
        "search together", "invite my friend", "roommate search",
    ],
    "referral_unlock": [
        "referral", "invite a friend", "unlock", "refer a friend",
        "share and earn",
    ],
    "text_anything": [
        "text homey anything", "ask homey", "any question",
        "text us anything", "ask anything",
    ],
}

HOOK_TO_FLOW: dict[str, str] = {
    "preview_challenge": "listing_preview_flow",
    "readiness_scan":    "readiness_check_flow",
    "verified_drop":     "verified_listing_flow",
    "squad_invite":      "squad_search_flow",
    "referral_unlock":   "referral_flow",
    "text_anything":     "open_query_flow",
}

CHANNEL_MAP: dict[str, str] = {
    "tiktok":    "short_form_video",
    "instagram": "social_story",
    "shul":      "community_newsletter",
    "nyu":       "university_network",
    "referral":  "word_of_mouth",
    "email":     "direct_email",
    "sms":       "direct_sms",
}


# ─── Output model ─────────────────────────────────────────────────────────────

class CampaignEntry(BaseModel):
    raw_message: str
    source_channel: Optional[str]
    detected_hook: Optional[str]
    target_flow: str
    community_tag: Optional[str]
    dashboard_event: dict


# ─── Router ───────────────────────────────────────────────────────────────────

def route_campaign_entry(
    raw_message: str,
    source_channel: Optional[str] = None,
) -> CampaignEntry:
    """
    Detect hook from message and route to appropriate Homey flow.

    Failure case: no recognizable hook, no source channel
    → target_flow = "open_query_flow" (never block entry)
    → dashboard event still fires so Dhruv can see unknown-hook rate

    Dashboard event: campaign_entry_routed with source_channel,
    detected_hook, and target_flow.
    """
    msg_lower = raw_message.lower()

    detected_hook: Optional[str] = None
    for hook, keywords in CAMPAIGN_HOOKS.items():
        if any(kw in msg_lower for kw in keywords):
            detected_hook = hook
            break

    target_flow   = HOOK_TO_FLOW.get(detected_hook, "open_query_flow")
    community_tag = None
    if source_channel:
        community_tag = CHANNEL_MAP.get(source_channel.lower())

    event = emit_campaign_event(source_channel, detected_hook, target_flow)

    return CampaignEntry(
        raw_message=raw_message,
        source_channel=source_channel,
        detected_hook=detected_hook,
        target_flow=target_flow,
        community_tag=community_tag,
        dashboard_event=event,
    )
