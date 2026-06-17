"""
schemas/memory.py
Memory categories, retention rules, and blocked fields.
"""

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class MemoryCategory(str, Enum):
    DURABLE = "durable"        # preferences, name — keep until user changes
    SESSION = "session"        # current search context — expires at session end
    READINESS = "readiness"    # move-in timing — expires after 30 days
    CORRECTION = "correction"  # user corrections — always overrides older data
    BLOCKED = "blocked"        # must never be stored


NEVER_STORE = [
    "credit_score",
    "criminal_record",
    "eviction_history",
    "ssn",
    "raw_report",
    "dob",
    "medical",
]

EXPIRY_DAYS = {
    MemoryCategory.DURABLE:    None,   # no expiry
    MemoryCategory.SESSION:    0,      # expires at session end
    MemoryCategory.READINESS:  30,
    MemoryCategory.CORRECTION: None,
}


class MemoryEntry(BaseModel):
    key: str
    value: Any
    category: MemoryCategory
    stored_at: datetime
    expires_at: Optional[datetime] = None
