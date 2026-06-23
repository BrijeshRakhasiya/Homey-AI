"""Generate an operational SLO report from Homey's JSONL flight recorder."""

import json
import math
import statistics
from pathlib import Path

TRACE_PATH = Path(__file__).parent.parent / "observability" / "traces" / "stream.jsonl"
SLO_TARGETS = {
    "static": {"p50_ms": 10, "p95_ms": 50},
    "cache": {"p50_ms": 50, "p95_ms": 200},
    "retrieval_only": {"p50_ms": 300, "p95_ms": 1000},
    "full_llm": {"p50_ms": 1500, "p95_ms": 4000},
}


def load_events(path: Path = TRACE_PATH) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def generate_slo_report(path: Path = TRACE_PATH) -> dict:
    events = load_events(path)
    latency_events = [e for e in events if e.get("event_type") == "latency_route_selected"]
    guard_events = [e for e in events if e.get("event_type") == "guard_checked"]
    fallback_events = [e for e in events if e.get("event_type") == "fallback_returned"]
    tiers: dict[str, list[float]] = {}
    for event in latency_events:
        latency = event.get("latency_ms")
        if isinstance(latency, (int, float)):
            tiers.setdefault(event.get("tier", "unknown"), []).append(float(latency))

    tier_report = {}
    for tier, values in tiers.items():
        ordered = sorted(values)
        p50 = statistics.median(ordered)
        p95 = ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)]
        target = SLO_TARGETS.get(tier, {})
        tier_report[tier] = {
            "count": len(values),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "p50_ok": p50 <= target.get("p50_ms", float("inf")),
            "p95_ok": p95 <= target.get("p95_ms", float("inf")),
        }

    llm_calls = sum(bool(e.get("model_called")) for e in latency_events)
    return {
        "total_events": len(events),
        "latency_events": len(latency_events),
        "tiers": tier_report,
        "model_call_percentage": round(llm_calls / max(len(latency_events), 1) * 100, 2),
        "fallback_rate": round(len(fallback_events) / max(len(events), 1) * 100, 2),
        "guard_trigger_rate": round(
            sum(bool(e.get("triggered")) for e in guard_events)
            / max(len(guard_events), 1)
            * 100,
            2,
        ),
        "estimated_llm_calls_per_1000_requests": round(
            llm_calls / max(len(latency_events), 1) * 1000, 1
        ),
        "estimated_cost_per_1000_requests_usd": round(
            (llm_calls / max(len(latency_events), 1) * 1000)
            * 500 / 1_000_000 * 0.27,
            4,
        ),
    }


if __name__ == "__main__":
    print(json.dumps(generate_slo_report(), indent=2))
