"""Typed response and error envelopes for Homey's integration boundary."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class TrustReceipt(BaseModel):
    chunks_considered: int = 0
    chunks_allowed: int = 0
    chunks_blocked: int = 0
    chunks_stale: int = 0
    chunks_internal_blocked: int = 0
    freshness_status: Literal["fresh", "stale", "mixed", "unknown"] = "unknown"
    evidence_sufficient: bool = False
    fallback_reason: Optional[str] = None
    source_ids: list[str] = Field(default_factory=list)


class GuardStatus(BaseModel):
    input_checked: bool = True
    output_checked: bool = True
    triggered: bool = False
    layer: Optional[str] = None
    category: Optional[str] = None
    reason: Optional[str] = None


class HomeyResponseEnvelope(BaseModel):
    response: str
    response_type: Literal[
        "answer", "clarification", "refusal", "fallback", "safe_alternative"
    ]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_fields: list[str] = Field(default_factory=list)
    source_receipt: TrustReceipt = Field(default_factory=TrustReceipt)
    guard_status: GuardStatus = Field(default_factory=GuardStatus)
    next_action: Optional[str] = None
    events: list[str] = Field(default_factory=list)
    feature_flags_used: list[str] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    error_type: Literal[
        "low_confidence",
        "schema_drift",
        "retrieval_missing",
        "llm_unavailable",
        "restricted_request",
        "unsafe_copy",
        "stale_source",
        "policy_gated",
    ]
    message: str
    safe_response: str
    fallback_used: bool = True
