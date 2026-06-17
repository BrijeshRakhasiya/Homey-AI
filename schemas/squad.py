"""
schemas/squad.py
Squad (group search) typed models.
Private member details must NEVER appear in broker-facing output.
"""

from pydantic import BaseModel
from typing import List, Optional


class SquadMember(BaseModel):
    member_id: str
    stated_budget: Optional[int] = None
    preferred_area: Optional[str] = None
    bedrooms_needed: Optional[int] = None
    move_in_timing: Optional[str] = None


class SquadProfile(BaseModel):
    squad_id: str
    member_count: int
    agreed_budget_max: Optional[int] = None
    agreed_area: Optional[str] = None
    conflict_categories: List[str] = []
    alignment_score: float
    compromise_prompt: Optional[str] = None
    dashboard_event: dict = {}
