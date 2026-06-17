"""
stress/combined_stress_day.py  — Task 18: Combined Stress Day
End-to-end scenario: campaign entry → squad search → conflict → broker view → restricted block.

This is the single script that proves all layers work TOGETHER under real-world complexity.

Run: python stress/combined_stress_day.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routers.campaign_router import route_campaign_entry
from routers.community_router import get_community_context
from agents.intent_atlas import run_intent_atlas
from agents.squad_reasoning import build_squad_profile
from agents.soft_fit import compute_soft_fit, evaluate_executive_fit
from agents.broker_explanation import build_broker_explanation
from agents.memory_policy import MemoryStore
from agents.graph import run_graph
from infra.latency_router import route_for_latency
from schemas.squad import SquadMember
from schemas.fit import SoftFitInput, PropertyRequirement, RenterProfile


def separator(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print('═' * 60)


def run_stress_day() -> dict:
    """
    Scenario:
    Priya texts Homey from a TikTok verified-drop campaign.
    She and her roommate Sara are looking for a place near NYU.
    They have a budget conflict (Priya: $3000, Sara: $2500).
    Broker asks for fit summary — credit data is in raw payload but gets blocked.
    System stays safe and useful throughout.
    """

    all_events   = []
    steps_passed = 0
    steps_failed = []

    # ─── Step 1: Latency routing ──────────────────────────────────────────────
    separator("STEP 1 — Latency Router")
    latency = route_for_latency("I saw the verified drop on TikTok!")
    all_events.append(latency.dashboard_event)
    print(f"  Tier:         {latency.tier}")
    print(f"  Model called: {latency.model_called}")
    print(f"  Budget (ms):  {latency.latency_budget_ms}")
    assert latency.tier == "full_llm", "TikTok message should hit full_llm tier"
    steps_passed += 1
    print("  ✅ PASSED")

    # ─── Step 2: Community context ────────────────────────────────────────────
    separator("STEP 2 — Community Context (NYU)")
    community = get_community_context("nyu")
    all_events.append(community.dashboard_event)
    print(f"  Source tag:    {community.source_tag}")
    print(f"  Likely intent: {community.likely_intent}")
    print(f"  First prompt:  {community.first_prompt}")
    assert community.likely_intent == "renter"
    steps_passed += 1
    print("  ✅ PASSED")

    # ─── Step 3: Campaign entry ───────────────────────────────────────────────
    separator("STEP 3 — Campaign Entry Router (TikTok)")
    campaign = route_campaign_entry(
        "I saw your verified drop on TikTok!",
        source_channel="tiktok",
    )
    all_events.append(campaign.dashboard_event)
    print(f"  Source channel: {campaign.source_channel}")
    print(f"  Detected hook:  {campaign.detected_hook}")
    print(f"  Target flow:    {campaign.target_flow}")
    assert campaign.target_flow == "verified_listing_flow"
    steps_passed += 1
    print("  ✅ PASSED")

    # ─── Step 4: Intent Atlas ─────────────────────────────────────────────────
    separator("STEP 4 — Intent Atlas (squad message)")
    intent = run_intent_atlas(
        "me and my roommate are looking for a 2BHK near NYU around 3k",
        session_id="stress_001",
    )
    all_events.append(intent.dashboard_event)
    print(f"  Role:       {intent.role}")
    print(f"  Confidence: {intent.confidence}")
    print(f"  Budget:     ${intent.budget:,}" if intent.budget else "  Budget: None")
    print(f"  Area:       {intent.area}")
    print(f"  Bedrooms:   {intent.bedrooms}")
    assert intent.role.value == "squad", f"Expected squad, got {intent.role}"
    assert intent.budget == 3000
    steps_passed += 1
    print("  ✅ PASSED")

    # ─── Step 5: Squad Reasoning ──────────────────────────────────────────────
    separator("STEP 5 — Squad Reasoning (budget conflict)")
    squad = build_squad_profile(
        squad_id="sq_stress_001",
        members=[
            SquadMember(
                member_id="priya",
                stated_budget=3000,
                preferred_area="nyu",
                bedrooms_needed=2,
                move_in_timing="august",
            ),
            SquadMember(
                member_id="sara",
                stated_budget=2500,
                preferred_area="brooklyn",
                bedrooms_needed=2,
                move_in_timing="september",
            ),
        ],
    )
    all_events.append(squad.dashboard_event)
    print(f"  Members:          {squad.member_count}")
    print(f"  Conflicts:        {squad.conflict_categories}")
    print(f"  Alignment score:  {squad.alignment_score}")
    print(f"  Compromise:       {squad.compromise_prompt}")
    assert "budget_range_conflict" in squad.conflict_categories
    assert squad.compromise_prompt is not None
    steps_passed += 1
    print("  ✅ PASSED")

    # ─── Step 6: Soft-Fit Engine ──────────────────────────────────────────────
    separator("STEP 6 — Soft-Fit Engine (conservative budget)")
    fit = compute_soft_fit(SoftFitInput(
        renter_id="sq_stress_001",
        stated_budget=2500,      # conservative: Sara's lower budget
        property_price=2800,
        area_match=False,        # conflict — no agreed area
        bedroom_match=True,
        timing_match=False,      # conflict — different timing
        profile_complete=True,
        income_verified=True,
        urgency="flexible",
    ))
    all_events.append(fit.dashboard_event)
    print(f"  Fit label:   {fit.fit_label}")
    print(f"  Fit score:   {fit.fit_score}")
    print(f"  Reasons:     {fit.fit_reasons}")
    print(f"  Missing:     {fit.missing_signals}")
    print(f"  Safe label:  {fit.safe_label}")
    assert fit.fit_label in ("moderate", "weak")
    steps_passed += 1
    print("  ✅ PASSED")

    # ─── Step 7: Broker Explanation (credit data attempted) ──────────────────
    separator("STEP 7 — Broker Explanation (restricted data BLOCKED)")
    raw_fields_with_restricted = {
        "income_verified": True,
        "profile_complete": True,
        "credit_score": 720,           # must be blocked
        "criminal_record": "none",     # must be blocked
        "eviction_history": "none",    # must be blocked
    }
    broker_exp = build_broker_explanation(
        lead_id="sq_stress_001",
        fit_result=fit.model_dump(),
        raw_fields=raw_fields_with_restricted,
    )
    all_events.append(broker_exp.dashboard_event)
    print(f"  Summary:           {broker_exp.summary}")
    print(f"  Evidence:          {broker_exp.evidence}")
    print(f"  Caveat:            {broker_exp.caveat}")
    print(f"  Next action:       {broker_exp.next_action}")
    print(f"  Blocked fields:    {broker_exp.restricted_fields_blocked}")

    # Critical: restricted fields must NOT appear in broker-facing text
    broker_text = (
        broker_exp.summary + " " +
        " ".join(broker_exp.evidence) + " " +
        (broker_exp.caveat or "") + " " +
        broker_exp.next_action
    )
    assert "720" not in broker_text,           "Credit score leaked into broker text!"
    assert "credit_score" not in broker_text,  "credit_score field name leaked!"
    assert "criminal" not in broker_text.lower(), "Criminal record leaked!"
    assert len(broker_exp.restricted_fields_blocked) == 3
    steps_passed += 1
    print("  ✅ PASSED — restricted data successfully blocked")

    # ─── Step 8: Guard node via full graph ───────────────────────────────────
    separator("STEP 8 — Guard Node (unsafe phrase blocked)")
    graph_result = run_graph(
        raw_input="Is this renter approved for the listing?",
        audience="broker",
        session_id="stress_guard_001",
    )
    all_events.extend(graph_result.get("events", []))
    print(f"  Response:     {graph_result.get('response')}")
    print(f"  Guard passed: {graph_result.get('guard_passed')}")
    response_text = graph_result.get("response", "").lower()
    assert "approved" not in response_text, "Guard failed — 'approved' found in response!"
    steps_passed += 1
    print("  ✅ PASSED — guard blocked unsafe phrase")

    # ─── Step 9: Memory Policy (restricted field rejected) ───────────────────
    separator("STEP 9 — Memory Policy (credit_score rejected)")
    from agents.memory_policy import MemoryStore
    from schemas.memory import MemoryCategory
    mem = MemoryStore()

    stored_safe    = mem.store("preferred_area", "Brooklyn", MemoryCategory.DURABLE)
    blocked_credit = mem.store("credit_score",   720,       MemoryCategory.DURABLE)

    print(f"  Stored preferred_area: {stored_safe}")
    print(f"  Stored credit_score:   {blocked_credit}  (must be False)")
    print(f"  Retrieve area:         {mem.get('preferred_area')}")
    print(f"  Retrieve credit:       {mem.get('credit_score')}  (must be None)")
    assert stored_safe    is True
    assert blocked_credit is False
    assert mem.get("preferred_area") == "Brooklyn"
    assert mem.get("credit_score")   is None
    steps_passed += 1
    print("  ✅ PASSED — memory policy blocks restricted fields")

    # ─── Final summary ────────────────────────────────────────────────────────
    separator(f"STRESS DAY COMPLETE — {steps_passed}/9 steps passed")
    print(f"\n  Total dashboard events emitted: {len(all_events)}")
    for i, ev in enumerate(all_events, 1):
        print(f"  [{i:02d}] {ev.get('event_type', ev.get('event', 'unknown'))}")

    print(f"\n  {'✅ ALL STEPS PASSED' if steps_passed == 9 else '❌ SOME STEPS FAILED'}")
    print()

    return {
        "steps_passed": steps_passed,
        "steps_total":  9,
        "all_passed":   steps_passed == 9,
        "events_emitted": len(all_events),
        "events":       all_events,
    }


if __name__ == "__main__":
    result = run_stress_day()
    sys.exit(0 if result["all_passed"] else 1)
