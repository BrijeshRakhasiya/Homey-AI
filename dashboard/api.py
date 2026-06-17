"""FastAPI backend for the Homey dashboard and live event stream.

Run locally with: uvicorn dashboard.api:app --reload --port 8001
"""
import sys, json, uuid, time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

from agents.intent_atlas import run_intent_atlas
from agents.graph import run_graph
from agents.soft_fit import compute_soft_fit, evaluate_executive_fit
from agents.squad_reasoning import build_squad_profile
from agents.broker_explanation import build_broker_explanation
from agents.memory_policy import MemoryStore
from routers.campaign_router import route_campaign_entry
from routers.community_router import get_community_context
from infra.latency_router import route_for_latency
from schemas.fit import SoftFitInput, PropertyRequirement, RenterProfile
from schemas.squad import SquadMember
from schemas.memory import MemoryCategory

STREAM_PATH   = Path(__file__).parent.parent / "observability" / "traces" / "stream.jsonl"
NOTEBOOK_PATH = Path(__file__).parent.parent / "eval" / "failure_notebook.jsonl"
STREAM_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Homey Live Dashboard API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_sessions:      dict[str, dict]        = {}
_memory_stores: dict[str, MemoryStore] = {}
_renters:       dict[str, dict]        = {}
_brokers:       dict[str, dict]        = {}
_fit_results:   list[dict]             = []
_squad_results: list[dict]             = []

def get_session(sid: str) -> dict:
    if sid not in _sessions:
        _sessions[sid] = {
            "session_id": sid, "role": "unknown",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "messages": [], "events": [], "intents": [],
            "fit_scores": [], "squads": [], "guard_hits": [],
        }
    return _sessions[sid]

def get_mem(sid: str) -> MemoryStore:
    if sid not in _memory_stores:
        _memory_stores[sid] = MemoryStore()
    return _memory_stores[sid]

def read_jsonl(path: Path) -> list[dict]:
    if not path.exists(): return []
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try: out.append(json.loads(line))
                    except: pass
    except: pass
    return out

def now_iso(): return datetime.now(timezone.utc).isoformat()

class ChatReq(BaseModel):
    message: str
    session_id: Optional[str] = None
    source_channel: Optional[str] = None
    community_tag: Optional[str] = None
    audience: Optional[str] = "renter"

class RenterReq(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    budget: int
    area: str
    bedrooms: int
    move_in_date: str
    urgency: Optional[str] = "flexible"
    has_pets: Optional[bool] = False
    notes: Optional[str] = None

class BrokerReq(BaseModel):
    name: str
    email: str
    company: Optional[str] = None

class ListingReq(BaseModel):
    broker_id: str
    title: str
    area: str
    price: int
    bedrooms: int
    move_in_date: str
    pet_friendly: Optional[bool] = False
    description: Optional[str] = None

class FitReq(BaseModel):
    renter_id: str
    listing_id: str
    session_id: Optional[str] = None

class SquadReq(BaseModel):
    session_id: Optional[str] = None
    squad_id: str
    members: list

class MemReq(BaseModel):
    session_id: str
    key: str
    value: str
    category: str = "durable"

@app.post("/api/renter/register")
def register_renter(req: RenterReq):
    rid = "R-" + str(uuid.uuid4())[:8].upper()
    profile = {
        "renter_id": rid, "name": req.name, "email": req.email,
        "phone": req.phone, "budget": req.budget, "area": req.area,
        "bedrooms": req.bedrooms, "move_in_date": req.move_in_date,
        "urgency": req.urgency, "has_pets": req.has_pets,
        "notes": req.notes, "profile_complete": True,
        "income_verified": False, "registered_at": now_iso(),
    }
    _renters[rid] = profile
    from observability.stream import _emit
    _emit({"event_type": "renter_registered", "renter_id": rid,
           "area": req.area, "budget": req.budget, "bedrooms": req.bedrooms})
    return {"renter_id": rid, "profile": profile, "message": f"Renter {req.name} registered successfully"}

@app.get("/api/renters")
def list_renters():
    return {"renters": list(_renters.values()), "total": len(_renters)}

@app.get("/api/renter/{renter_id}")
def get_renter(renter_id: str):
    r = _renters.get(renter_id)
    if not r: return {"error": "Renter not found"}
    fits = [f for f in _fit_results if f.get("renter_id") == renter_id]
    return {"renter": r, "fit_history": fits}

@app.put("/api/renter/{renter_id}/verify-income")
def verify_income(renter_id: str):
    if renter_id not in _renters:
        return {"error": "Renter not found"}
    _renters[renter_id]["income_verified"] = True
    from observability.stream import _emit
    _emit({"event_type": "income_verified", "renter_id": renter_id})
    return {"renter_id": renter_id, "income_verified": True}

@app.post("/api/broker/register")
def register_broker(req: BrokerReq):
    bid = "B-" + str(uuid.uuid4())[:8].upper()
    profile = {
        "broker_id": bid, "name": req.name, "email": req.email,
        "company": req.company, "listings": [], "registered_at": now_iso(),
    }
    _brokers[bid] = profile
    from observability.stream import _emit
    _emit({"event_type": "broker_registered", "broker_id": bid, "name": req.name})
    return {"broker_id": bid, "profile": profile}

@app.get("/api/brokers")
def list_brokers():
    return {"brokers": list(_brokers.values()), "total": len(_brokers)}

@app.post("/api/listing/add")
def add_listing(req: ListingReq):
    if req.broker_id not in _brokers:
        return {"error": "Broker not found. Register broker first."}
    lid = "L-" + str(uuid.uuid4())[:8].upper()
    listing = {
        "listing_id": lid, "broker_id": req.broker_id,
        "broker_name": _brokers[req.broker_id]["name"],
        "title": req.title, "area": req.area, "price": req.price,
        "bedrooms": req.bedrooms, "move_in_date": req.move_in_date,
        "pet_friendly": req.pet_friendly, "description": req.description,
        "added_at": now_iso(), "fit_requests": [],
    }
    _brokers[req.broker_id]["listings"].append(listing)
    from observability.stream import _emit
    _emit({"event_type": "listing_added", "listing_id": lid,
           "broker_id": req.broker_id, "area": req.area, "price": req.price})
    return {"listing_id": lid, "listing": listing}

@app.get("/api/listings")
def list_all_listings():
    all_listings = []
    for b in _brokers.values():
        all_listings.extend(b.get("listings", []))
    return {"listings": all_listings, "total": len(all_listings)}

@app.post("/api/fit/evaluate")
def evaluate_fit(req: FitReq):
    renter = _renters.get(req.renter_id)
    if not renter:
        return {"error": f"Renter {req.renter_id} not found"}

    listing = None
    for b in _brokers.values():
        for l in b.get("listings", []):
            if l["listing_id"] == req.listing_id:
                listing = l
                break

    if not listing:
        return {"error": f"Listing {req.listing_id} not found"}

    area_match    = renter["area"].lower() == listing["area"].lower()
    bedroom_match = renter["bedrooms"] >= listing["bedrooms"]
    timing_match  = renter["move_in_date"] <= listing["move_in_date"]

    try:
        fit_input = SoftFitInput(
            renter_id=req.renter_id,
            stated_budget=renter["budget"],
            property_price=listing["price"],
            area_match=area_match,
            bedroom_match=bedroom_match,
            timing_match=timing_match,
            profile_complete=renter["profile_complete"],
            income_verified=renter["income_verified"],
            urgency=renter.get("urgency", "flexible"),
        )
        fit_result = compute_soft_fit(fit_input)
    except ValidationError as e:
        return {"error": str(e)}

    raw_fields = {k: v for k, v in renter.items()}
    broker_exp = build_broker_explanation(
        lead_id=req.renter_id,
        fit_result=fit_result.model_dump(),
        raw_fields=raw_fields,
    )

    result = {
        "renter_id":  req.renter_id, "renter_name": renter["name"],
        "listing_id": req.listing_id, "listing_title": listing["title"],
        "broker_id":  listing["broker_id"],
        "fit_score":  fit_result.fit_score,
        "fit_label":  fit_result.fit_label,
        "fit_reasons": fit_result.fit_reasons,
        "missing_signals": fit_result.missing_signals,
        "safe_label": fit_result.safe_label,
        "broker_summary":  broker_exp.summary,
        "broker_evidence": broker_exp.evidence,
        "broker_caveat":   broker_exp.caveat,
        "broker_next":     broker_exp.next_action,
        "restricted_blocked": broker_exp.restricted_fields_blocked,
        "evaluated_at": now_iso(),
    }
    _fit_results.append(result)

    listing["fit_requests"].append({
        "renter_id": req.renter_id, "renter_name": renter["name"],
        "fit_label": fit_result.fit_label, "fit_score": fit_result.fit_score,
        "evaluated_at": now_iso(),
    })

    session_id = req.session_id or "default"
    get_session(session_id)["fit_scores"].append(result)

    return result

@app.get("/api/fit/all")
def all_fits():
    return {"fits": _fit_results, "total": len(_fit_results)}

@app.post("/api/squad")
def build_squad(req: SquadReq):
    session_id = req.session_id or "default"
    session    = get_session(session_id)
    try:
        members = [SquadMember(**m) for m in req.members]
        result  = build_squad_profile(req.squad_id, members)
        data    = result.model_dump()
        session["squads"].append(data)
        session["events"].append(data["dashboard_event"])
        _squad_results.append(data)
        return {"session_id": session_id, **data}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/chat")
def chat(req: ChatReq):
    session_id = req.session_id or str(uuid.uuid4())
    session    = get_session(session_id)

    latency   = route_for_latency(req.message)
    community = get_community_context(req.community_tag)
    session["events"].extend([latency.dashboard_event, community.dashboard_event])

    campaign = None
    if req.source_channel:
        campaign = route_campaign_entry(req.message, req.source_channel)
        session["events"].append(campaign.dashboard_event)

    if latency.tier in ("static", "cache") and latency.response:
        intent_result = run_intent_atlas(req.message, session_id)
        session["intents"].append(intent_result.model_dump())
        session["events"].append(intent_result.dashboard_event)
        _record_message(session, req.message, latency.response, latency.tier, True, intent_result.model_dump())
        return {"session_id": session_id, "response": latency.response,
                "latency_tier": latency.tier, "guard_passed": True,
                "intent": intent_result.model_dump()}

    graph_result = run_graph(raw_input=req.message,
                             audience=req.audience or "renter",
                             session_id=session_id)
    session["events"].extend(graph_result.get("events", []))
    intent = graph_result.get("intent", {})
    if intent:
        session["intents"].append(intent)
        session["role"] = intent.get("role", "unknown")

    guard_events = [e for e in graph_result.get("events", [])
                    if e.get("event_type") == "guard_checked" and e.get("triggered")]
    session["guard_hits"].extend(guard_events)

    mem = get_mem(session_id)
    if intent.get("area"):
        mem.store("preferred_area", intent["area"], MemoryCategory.DURABLE)
    if intent.get("budget"):
        mem.store("budget", str(intent["budget"]), MemoryCategory.SESSION)

    _record_message(session, req.message, graph_result.get("response"),
                    latency.tier, graph_result.get("guard_passed", True), intent)
    return {
        "session_id":    session_id,
        "response":      graph_result.get("response"),
        "latency_tier":  latency.tier,
        "guard_passed":  graph_result.get("guard_passed", True),
        "intent":        intent,
        "events":        graph_result.get("events", []),
        "error":         graph_result.get("error"),
        "memory":        mem.summary(),
    }

def _record_message(session, user_msg, homey_msg, tier, guard, intent):
    ts = now_iso()
    session["messages"].append({"role": "user",  "content": user_msg, "ts": ts})
    session["messages"].append({"role": "homey", "content": homey_msg,
                                "latency_tier": tier, "guard_passed": guard,
                                "intent_role": intent.get("role") if intent else None,
                                "confidence": intent.get("confidence") if intent else None,
                                "ts": ts})

@app.post("/api/memory/store")
def store_memory(req: MemReq):
    mem = get_mem(req.session_id)
    cat = {"durable": MemoryCategory.DURABLE, "session": MemoryCategory.SESSION,
           "readiness": MemoryCategory.READINESS, "correction": MemoryCategory.CORRECTION
           }.get(req.category.lower(), MemoryCategory.DURABLE)
    ok = mem.store(req.key, req.value, cat)
    return {"stored": ok, "key": req.key, "blocked": not ok,
            "reason": "field in NEVER_STORE list" if not ok else None}

@app.get("/api/memory/{session_id}")
def get_memory_summary(session_id: str):
    return {"session_id": session_id, "memory": get_mem(session_id).summary()}

@app.get("/api/dashboard/live")
def dashboard_live(session_id: Optional[str] = Query(None)):
    all_events = read_jsonl(STREAM_PATH)
    failures   = read_jsonl(NOTEBOOK_PATH)

    event_counts = defaultdict(int)
    role_counts  = defaultdict(int)
    fit_labels   = defaultdict(int)
    guard_phrases= defaultdict(int)
    latency_tiers= defaultdict(int)
    squad_conf   = defaultdict(int)
    camp_hooks   = defaultdict(int)
    blocked_flds = defaultdict(int)
    ev_ok = ev_fail = 0

    for ev in all_events:
        et = ev.get("event_type", "")
        event_counts[et] += 1
        if et == "intent_classified":
            role_counts[ev.get("role","unknown")] += 1
        elif et == "soft_fit_scored":
            fit_labels[ev.get("fit_label","unknown")] += 1
        elif et == "guard_checked" and ev.get("triggered"):
            guard_phrases[ev.get("reason","unknown")] += 1
        elif et == "latency_route_selected":
            latency_tiers[ev.get("tier","unknown")] += 1
        elif et == "squad_profile_built":
            for c in ev.get("conflict_categories",[]): squad_conf[c] += 1
        elif et == "campaign_entry_routed":
            camp_hooks[ev.get("detected_hook") or "unknown"] += 1
        elif et == "blocked_memory_attempt":
            blocked_flds[ev.get("key","unknown")] += 1
        elif et == "retrieval_governed":
            if ev.get("evidence_sufficient"): ev_ok += 1
            else: ev_fail += 1

    total_msg   = event_counts.get("intent_classified", 0)
    guard_total = sum(guard_phrases.values())
    safe_rate   = round((total_msg - guard_total) / total_msg * 100, 1) if total_msg else 100
    ev_total    = ev_ok + ev_fail
    ev_rate     = round(ev_ok / ev_total * 100, 1) if ev_total else 100

    session_data = None
    if session_id and session_id in _sessions:
        s = _sessions[session_id]
        session_data = {
            "session_id":    session_id,
            "role":          s.get("role","unknown"),
            "started_at":    s["started_at"],
            "message_count": len(s["messages"]),
            "event_count":   len(s["events"]),
            "guard_hits":    len(s["guard_hits"]),
            "fit_scores":    s["fit_scores"],
            "squads":        s["squads"],
            "messages":      s["messages"][-30:],
            "intents":       s["intents"][-10:],
            "memory":        _memory_stores.get(session_id, MemoryStore()).summary(),
            "recent_events": s["events"][-20:],
        }

    all_listings = []
    for b in _brokers.values():
        all_listings.extend(b.get("listings", []))

    return {
        "ts": now_iso(),
        "total_events":    len(all_events),
        "total_messages":  total_msg,
        "guard_triggers":  guard_total,
        "safe_rate":       safe_rate,
        "evidence_rate":   ev_rate,
        "total_failures":  len(failures),
        "total_sessions":  len(_sessions),
        "total_renters":   len(_renters),
        "total_brokers":   len(_brokers),
        "total_listings":  len(all_listings),
        "total_fits":      len(_fit_results),
        "role_counts":     dict(role_counts),
        "fit_labels":      dict(fit_labels),
        "guard_phrases":   dict(guard_phrases),
        "latency_tiers":   dict(latency_tiers),
        "squad_conflicts": dict(squad_conf),
        "campaign_hooks":  dict(camp_hooks),
        "blocked_fields":  dict(blocked_flds),
        "event_counts":    dict(event_counts),
        "recent_events":   all_events[-50:][::-1],
        "renters":         list(_renters.values()),
        "brokers":         list(_brokers.values()),
        "listings":        all_listings,
        "fit_results":     _fit_results[-20:],
        "squad_results":   _squad_results[-10:],
        "failures":        failures[-5:][::-1],
        "session":         session_data,
    }

@app.get("/api/events/stream")
def events_stream():
    last = [0]
    def gen():
        yield "data: {\"type\":\"connected\"}\n\n"
        while True:
            evs = read_jsonl(STREAM_PATH)
            if len(evs) > last[0]:
                for ev in evs[last[0]:]:
                    yield f"data: {json.dumps(ev)}\n\n"
                last[0] = len(evs)
            time.sleep(1)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.get("/api/sessions")
def list_sessions():
    return {"sessions": [{"session_id":s,"started_at":d["started_at"],
            "message_count":len(d["messages"]),"role":d.get("role","unknown")}
            for s,d in _sessions.items()]}

@app.post("/api/run-eval")
def run_eval():
    from eval.harness import run_harness
    return run_harness()

@app.get("/health")
def health():
    return {"status":"ok","renters":len(_renters),"brokers":len(_brokers),
            "sessions":len(_sessions),"fit_results":len(_fit_results)}