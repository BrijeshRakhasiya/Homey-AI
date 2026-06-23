"""
schemas/intent.py
Typed state object for intent classification.
Every message Homey receives produces one of these.
"""

from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class UserRole(str, Enum):
    RENTER = "renter"
    BROKER = "broker"
    SQUAD = "squad"
    CAMPAIGN = "campaign"
    UNKNOWN = "unknown"


class IntentState(BaseModel):
    raw_input: str
    role: UserRole
    intent: str = "unknown"
    confidence: float                    # 0.0 to 1.0
    area: Optional[str] = None
    budget: Optional[int] = None
    bedrooms: Optional[int] = None
    timing: Optional[str] = None
    urgency: Optional[str] = "unknown"   # "immediate" | "flexible" | "unknown"
    missing_fields: List[str] = []
    clarification_prompt: Optional[str] = None
    dashboard_event: dict = {}
