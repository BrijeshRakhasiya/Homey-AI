"""
schemas/events.py
Shared dashboard event shapes — every module emits one of these.
Dhruv reads these from observability/traces/stream.jsonl
"""

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, timezone
import uuid


class BaseEvent(BaseModel):
    event_id: str = ""
    event_type: str
    timestamp: str = ""
    session_id: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class IntentEvent(BaseEvent):
    event_type: str = "intent_classified"
    role: str
    confidence: float
    missing_field_count: int


class RetrievalEvent(BaseEvent):
    event_type: str = "retrieval_governed"
    audience: str
    chunks_returned: int
    evidence_sufficient: bool


class GuardEvent(BaseEvent):
    event_type: str = "guard_checked"
    triggered: bool
    reason: Optional[str] = None


class FitEvent(BaseEvent):
    event_type: str = "soft_fit_scored"
    renter_id: str
    fit_label: str
    fit_score: float
    missing_signal_count: int


class SquadEvent(BaseEvent):
    event_type: str = "squad_profile_built"
    squad_id: str
    member_count: int
    conflict_count: int
    alignment_score: float


class CampaignEvent(BaseEvent):
    event_type: str = "campaign_entry_routed"
    source_channel: Optional[str]
    detected_hook: Optional[str]
    target_flow: str


class BrokerEvent(BaseEvent):
    event_type: str = "broker_explanation_generated"
    lead_id: str
    fit_label: str
    restricted_fields_blocked: int


class SchemaEvent(BaseEvent):
    event_type: str = "schema_validation_failed"
    missing_fields: list
    error: str


class MemoryEvent(BaseEvent):
    event_type: str = "memory_stored"
    key: str
    category: str
    will_expire: bool


class LatencyEvent(BaseEvent):
    event_type: str = "latency_route_selected"
    tier: str
    model_called: bool
    cache_hit: bool
    latency_budget_ms: int


class FailureEvent(BaseEvent):
    event_type: str = "failure_logged"
    category: str
    owner: str
    impact: str


class EvalEvent(BaseEvent):
    event_type: str = "eval_harness_run"
    total: int
    passed: int
    failed: int
    pass_rate: float
