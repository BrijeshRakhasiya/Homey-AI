"""Governed source metadata used by retrieval and trust receipts."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SourceMetadata(BaseModel):
    source_id: str
    owner: str
    source_type: Literal[
        "listing", "policy", "faq", "broker_note", "internal", "campaign"
    ]
    created_at: datetime
    expires_at: Optional[datetime] = None
    audience: Literal["public", "renter", "broker", "internal"]
    sensitivity: Literal["public", "low", "medium", "restricted"]
    allowed_surface: list[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    confidence_floor: float = Field(default=0.0, ge=0.0)
    claim_key: Optional[str] = None
    claim_value: Optional[str] = None

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return False
        current = now or datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return current > expires

    def is_allowed_for(self, role: str, surface: str) -> bool:
        if self.is_stale() or self.superseded_by is not None:
            return False
        if self.sensitivity == "restricted" or self.audience == "internal":
            return False
        if role == "renter" and self.audience not in {"public", "renter"}:
            return False
        if role == "broker" and self.audience not in {"public", "renter", "broker"}:
            return False
        return surface in self.allowed_surface
