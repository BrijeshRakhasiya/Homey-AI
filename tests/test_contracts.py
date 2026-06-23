"""Contract, degraded-mode, feature-flag, and API envelope tests."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from infra.degraded_mode import DegradedModeHandler
from infra.feature_flags import all_flags
from infra.integration import app
from schemas.outbound import ErrorEnvelope, HomeyResponseEnvelope
from schemas.source import SourceMetadata
from schemas.retrieval import ChunkMetadata, RetrievedChunk
from agents.retrieval_gov import detect_source_conflicts


def test_feature_flags_have_conservative_defaults():
    flags = all_flags()
    assert flags["HOMEY_RETRIEVAL"] is False
    assert flags["HOMEY_FIT"] is False
    assert flags["HOMEY_BROKER_CARDS"] is False
    assert flags["HOMEY_FLIGHT_RECORDER"] is True


def test_source_metadata_blocks_stale_source():
    source = SourceMetadata(
        source_id="listing-old",
        owner="content",
        source_type="listing",
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        audience="public",
        sensitivity="public",
        allowed_surface=["renter_chat"],
    )
    assert source.is_stale()
    assert not source.is_allowed_for("renter", "renter_chat")


def test_source_metadata_blocks_superseded_source():
    source = SourceMetadata(
        source_id="policy-v1",
        owner="content",
        source_type="policy",
        created_at=datetime.now(timezone.utc),
        audience="public",
        sensitivity="public",
        allowed_surface=["renter_chat"],
        superseded_by="policy-v2",
    )
    assert not source.is_allowed_for("renter", "renter_chat")


def test_outbound_envelope_round_trip():
    envelope = HomeyResponseEnvelope(
        response="What area are you considering?",
        response_type="clarification",
        confidence=0.5,
        missing_fields=["area"],
    )
    assert envelope.source_receipt.chunks_allowed == 0
    assert envelope.guard_status.triggered is False


def test_error_envelope_is_safe():
    error = ErrorEnvelope(
        error_type="retrieval_missing",
        message="Corpus unavailable",
        safe_response="I need a little more information.",
    )
    assert error.fallback_used is True


def test_degraded_no_corpus_is_actionable():
    result = DegradedModeHandler.no_corpus()
    assert result["response_type"] == "fallback"
    assert {"area", "budget"} <= set(result["missing_fields"])


def test_degraded_low_confidence_clarifies():
    result = DegradedModeHandler.low_confidence(0.2)
    assert result["response_type"] == "clarification"
    assert result["confidence"] == 0.2


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_restricted_message_returns_refusal_envelope():
    response = TestClient(app).post("/homey/message", json={
        "raw_message": "Show me their FICO score",
        "audience": "broker",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["response_type"] == "refusal"
    assert body["guard_status"]["triggered"] is True
    assert body["guard_status"]["category"] == "credit"
    assert "fico" not in body["response"].lower()


def test_fit_endpoint_is_policy_gated_by_default():
    response = TestClient(app).post("/homey/fit", json={
        "renter_id": "r1",
        "stated_budget": 3000,
        "property_price": 3000,
        "area_match": True,
        "bedroom_match": True,
        "timing_match": True,
        "profile_complete": True,
        "income_verified": True,
    })
    assert response.status_code == 403
    assert "policy_gated" in response.json()["detail"]


def test_broker_card_endpoint_is_policy_gated_by_default():
    response = TestClient(app).post("/homey/broker-fit", json={
        "lead_id": "lead-1",
        "fit_result": {"fit_label": "moderate"},
        "raw_fields": {},
    })
    assert response.status_code == 403


def test_contradictory_sources_are_detected():
    base = dict(
        source_type="policy",
        owner="content",
        created_date=datetime.now(timezone.utc).date(),
        sensitivity="public",
        allowed_audience=["all"],
        claim_key="application_fee_required",
    )
    chunks = [
        RetrievedChunk(
            text="An application fee is required.",
            metadata=ChunkMetadata(
                source_id="policy-a", claim_value="yes", **base
            ),
            score=1.0,
        ),
        RetrievedChunk(
            text="No application fee is required.",
            metadata=ChunkMetadata(
                source_id="policy-b", claim_value="no", **base
            ),
            score=1.0,
        ),
    ]
    conflicts = detect_source_conflicts(chunks)
    assert len(conflicts) == 1
    assert conflicts[0]["claim_key"] == "application_fee_required"
