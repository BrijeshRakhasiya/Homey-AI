"""Safe, user-facing fallbacks for unavailable dependencies."""

from observability.stream import emit_event


class DegradedModeHandler:
    @staticmethod
    def _fallback(reason: str, response: str, missing_fields=None, **extra) -> dict:
        emit_event("fallback_returned", {"reason": reason, **extra})
        return {
            "response": response,
            "response_type": "fallback",
            "confidence": 0.0,
            "missing_fields": missing_fields or [],
            "feature_flags_used": extra.get("feature_flags_used", []),
        }

    @classmethod
    def no_llm_key(cls) -> dict:
        return cls._fallback(
            "no_llm_key",
            "I can still help with your search. Tell me your area, budget, and move-in timing.",
            ["area", "budget", "timing"],
            tier="static",
            feature_flags_used=["LLM=unavailable"],
        )

    @classmethod
    def no_corpus(cls) -> dict:
        return cls._fallback(
            "no_corpus",
            "I don't have enough verified listing information right now. What area and budget are you working with?",
            ["area", "budget"],
            tier="static",
            feature_flags_used=["HOMEY_RETRIEVAL=False"],
        )

    @classmethod
    def schema_drift(cls, missing_field: str) -> dict:
        emit_event("schema_failed", {"missing_field": missing_field, "reason": "schema_drift"})
        return {
            "response": "Something looks off with that request. Could you rephrase it?",
            "response_type": "fallback",
            "confidence": 0.0,
            "missing_fields": [missing_field],
            "feature_flags_used": [],
        }

    @classmethod
    def backend_timeout(cls) -> dict:
        return cls._fallback(
            "backend_timeout",
            "I'm waiting on verified information. What's most important right now—area, budget, or timing?",
            tier="static",
        )

    @staticmethod
    def dashboard_outage() -> dict:
        return {"events_written": False, "fallback": "stderr_only"}

    @classmethod
    def low_confidence(cls, confidence: float) -> dict:
        result = cls._fallback(
            "low_confidence",
            "I want to make sure I understand. Could you share a little more detail?",
            confidence=confidence,
        )
        result["response_type"] = "clarification"
        result["confidence"] = confidence
        return result
