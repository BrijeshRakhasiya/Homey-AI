"""
infra/integration.py  — Task 16: Integration Handshake
FastAPI app that wraps all Homey intelligence layers.
This is the single seam where Nikunj's backend connects.

Endpoints:
  POST /homey/message      — main message handler
  POST /homey/fit          — soft-fit scoring
  POST /homey/squad        — squad profile builder
  POST /homey/broker-fit   — broker explanation
  POST /homey/adapt-renter — schema adapter test
  GET  /health             — health check

Run: uvicorn infra.integration:app --reload --port 8000
Test: curl -X POST http://localhost:8000/homey/message \
        -H "Content-Type: application/json" \
        -d '{"raw_message": "I need a 2BHK in Brooklyn under 3000"}'
"""

import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

from agents.intent_atlas import run_intent_atlas
from agents.graph import run_graph
from agents.soft_fit import compute_soft_fit, evaluate_executive_fit
from agents.squad_reasoning import build_squad_profile
from agents.broker_explanation import build_broker_explanation
from agents.memory_policy import MemoryStore
from routers.campaign_router import route_campaign_entry
from routers.community_router import get_community_context
from infra.latency_router import route_for_latency
from infra.schema_adapter import adapt_renter_payload
from agents.retrieval_gov import bootstrap_retrieval_index
from infra.feature_flags import flags_used_in_response, is_enabled
from schemas.outbound import GuardStatus, TrustReceipt
from schemas.fit import SoftFitInput, PropertyRequirement, RenterProfile
from schemas.squad import SquadMember

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("HOMEY_RETRIEVAL", "false").lower() == "true":
        bootstrap_retrieval_index()
    yield


app = FastAPI(
    title="Homey Intelligence API",
    description="VryfID Homey AI layer — all 20 sprint tasks integrated",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session-level memory (one per session in production)
_memory_stores: dict[str, MemoryStore] = {}


def get_memory(session_id: str) -> MemoryStore:
    if session_id not in _memory_stores:
        _memory_stores[session_id] = MemoryStore()
    return _memory_stores[session_id]


# ─── Request / Response models ────────────────────────────────────────────────

class MessageRequest(BaseModel):
    raw_message: str
    session_id: Optional[str] = None
    source_channel: Optional[str] = None
    audience: Optional[str] = "renter"
    community_tag: Optional[str] = None


class MessageResponse(BaseModel):
    session_id: str
    response: Optional[str]
    intent: Optional[dict]
    clarification_prompt: Optional[str]
    community_first_prompt: Optional[str]
    latency_tier: str
    guard_passed: bool
    events: list
    error: Optional[str] = None
    response_type: str = "answer"
    confidence: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    source_receipt: TrustReceipt = Field(default_factory=TrustReceipt)
    guard_status: GuardStatus = Field(default_factory=GuardStatus)
    next_action: Optional[str] = None
    feature_flags_used: list[str] = Field(default_factory=list)


class FitRequest(BaseModel):
    renter_id: str
    stated_budget: int
    property_price: int
    area_match: bool
    bedroom_match: bool
    timing_match: bool
    profile_complete: bool
    income_verified: bool
    urgency: Optional[str] = "unknown"


class SquadRequest(BaseModel):
    squad_id: str
    members: list


class BrokerFitRequest(BaseModel):
    lead_id: str
    fit_result: dict
    raw_fields: dict


class AdaptRenterRequest(BaseModel):
    raw_payload: dict


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/homey/message", response_model=MessageResponse)
def process_message(req: MessageRequest):
    """
    Main message endpoint. Runs:
    1. Latency router (pick cheapest path)
    2. Community context (adjust first prompt)
    3. Campaign router (if hook detected)
    4. Full graph (route → retrieve → reason → guard → emit)

    Failure case: any layer raises → 500 with safe error message,
    never expose internal stack trace to client.

    Integration seam: Nikunj's WhatsApp webhook calls this endpoint.
    """
    session_id = req.session_id or str(uuid.uuid4())
    events     = []

    try:
        # ── Latency routing (Task 10) ──────────────────────────────────────
        latency = route_for_latency(req.raw_message)
        events.append(latency.dashboard_event)

        # ── Community context (Task 13) ────────────────────────────────────
        community = get_community_context(req.community_tag)
        events.append(community.dashboard_event)

        # ── Static / cache tier: skip graph ───────────────────────────────
        if latency.tier in ("static", "cache") and latency.response:
            intent_result = run_intent_atlas(req.raw_message, session_id)
            return MessageResponse(
                session_id=session_id,
                response=latency.response,
                intent=intent_result.model_dump(),
                clarification_prompt=None,
                community_first_prompt=community.first_prompt,
                latency_tier=latency.tier,
                guard_passed=True,
                events=events,
                response_type="answer",
                confidence=intent_result.confidence,
                missing_fields=intent_result.missing_fields,
                source_receipt=TrustReceipt(
                    fallback_reason="static_route",
                    evidence_sufficient=False,
                ),
                guard_status=GuardStatus(
                    input_checked=True, output_checked=False, triggered=False
                ),
                next_action=intent_result.clarification_prompt,
                feature_flags_used=flags_used_in_response(
                    ["HOMEY_INTENT_V2", "HOMEY_FLIGHT_RECORDER"]
                ),
            )

        # ── Campaign entry (Task 7) ────────────────────────────────────────
        if req.source_channel:
            campaign = route_campaign_entry(req.raw_message, req.source_channel)
            events.append(campaign.dashboard_event)

        # ── Full graph (Task 4) ────────────────────────────────────────────
        graph_result = run_graph(
            raw_input=req.raw_message,
            audience=req.audience or "renter",
            session_id=session_id,
        )
        events.extend(graph_result.get("events", []))

        return MessageResponse(
            session_id=session_id,
            response=graph_result.get("response"),
            intent=graph_result.get("intent"),
            clarification_prompt=(
                graph_result.get("intent", {}).get("clarification_prompt")
                if graph_result.get("intent") else None
            ),
            community_first_prompt=community.first_prompt,
            latency_tier=latency.tier,
            guard_passed=graph_result.get("guard_passed", True),
            events=events,
            error=graph_result.get("error"),
            response_type=graph_result.get("response_type", "answer"),
            confidence=(graph_result.get("intent") or {}).get("confidence", 0.0),
            missing_fields=(graph_result.get("intent") or {}).get("missing_fields", []),
            source_receipt=graph_result.get("source_receipt", {}),
            guard_status=graph_result.get("guard_status", {}),
            next_action=(
                (graph_result.get("intent") or {}).get("clarification_prompt")
                or "Continue with the safest relevant next step"
            ),
            feature_flags_used=flags_used_in_response([
                "HOMEY_INTENT_V2", "HOMEY_RETRIEVAL",
                "HOMEY_SEMANTIC_GUARD", "HOMEY_FLIGHT_RECORDER",
            ]),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Homey encountered an error. Please try again. [{type(e).__name__}]",
        )


@app.post("/homey/fit")
def score_fit(req: FitRequest):
    """
    Task 5: Soft-Fit Engine.
    Score renter-property fit using only safe signals.
    credit_score, criminal_record etc. are rejected by schema (extra=forbid).
    """
    if not is_enabled("HOMEY_FIT"):
        raise HTTPException(
            status_code=403,
            detail="policy_gated: HOMEY_FIT is disabled pending calibration and approval",
        )
    try:
        inp    = SoftFitInput(**req.model_dump())
        result = compute_soft_fit(inp)
        return result.model_dump()
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Blocked field detected or invalid input: {str(e)}",
        )


@app.post("/homey/squad")
def build_squad(req: SquadRequest):
    """
    Task 6: Squad Reasoning.
    Build shared profile, detect conflicts, generate compromise prompt.
    """
    try:
        members = [SquadMember(**m) for m in req.members]
        result  = build_squad_profile(req.squad_id, members)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/homey/broker-fit")
def broker_fit(req: BrokerFitRequest):
    """
    Task 14: Broker Explanation.
    Safe 4-part summary for broker. Restricted fields blocked from output.
    """
    if not is_enabled("HOMEY_BROKER_CARDS"):
        raise HTTPException(
            status_code=403,
            detail="policy_gated: HOMEY_BROKER_CARDS is disabled pending legal review",
        )
    result = build_broker_explanation(
        lead_id=req.lead_id,
        fit_result=req.fit_result,
        raw_fields=req.raw_fields,
    )
    return result.model_dump()


@app.post("/homey/adapt-renter")
def adapt_renter(req: AdaptRenterRequest):
    """
    Task 11: Schema Discipline.
    Test the adapter with a raw backend payload.
    """
    try:
        canonical = adapt_renter_payload(req.raw_payload)
        return {"status": "ok", "canonical": canonical.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/homey/intent")
def classify_intent(message: str, session_id: str = "default"):
    """Task 2: Intent Atlas — quick GET for testing."""
    result = run_intent_atlas(message, session_id)
    return result.model_dump()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "homey-intelligence",
        "version": "1.0.0",
        "tasks_implemented": 20,
    }
