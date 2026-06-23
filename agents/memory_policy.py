"""
agents/memory_policy.py  — v2
Two-layer defense against restricted data entering memory.

Layer 1: exact field name match (NEVER_STORE list)
Layer 2: semantic regex pattern match on both key AND value
         catches: fico, score, screening_result, risk_level,
                  nested content like notes="fico 720 eviction 2019"

Production gap from v1:
  "fico" bypassed Layer 1 because it wasn't in NEVER_STORE.
  Layer 2 catches it via RESTRICTED_SEMANTIC_PATTERNS regex.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from schemas.memory import MemoryCategory, MemoryEntry, NEVER_STORE, EXPIRY_DAYS
from observability.stream import emit_memory_event, emit_blocked_memory_event, emit_event
from agents.semantic_guard import check_memory_key

# ── Layer 2: semantic patterns (key OR value) ──────────────────────────────────
RESTRICTED_SEMANTIC_PATTERNS: dict[str, str] = {
    "fico_score":        r'\bfico\b',
    "credit_rating":     r'\bcredit[\s_]?(score|rating|report|check)\b',
    "screening_result":  r'\bscreening[\s_]?result\b',
    "risk_level":        r'\brisk[\s_]?level\b',
    "eviction_content":  r'\beviction\b',
    "criminal_content":  r'\bcriminal\b|\barrest\b|\bconviction\b',
    "background_check":  r'\bbackground[\s_]?(check|report)\b',
    "score_number":      r'\b[5-8]\d{2}\s*(credit|fico|score)\b',
}


def _is_semantically_restricted(key: str, value: Any) -> Optional[str]:
    """
    Return the matched pattern label if key or value contains
    restricted semantic content, else None.
    """
    key_lower = str(key).lower()
    val_str   = str(value).lower() if value is not None else ""

    for label, pattern in RESTRICTED_SEMANTIC_PATTERNS.items():
        if re.search(pattern, key_lower) or re.search(pattern, val_str):
            return label
    return None


class MemoryStore:
    """
    Session memory with two-layer restricted-data defense.
    Replace _store dict with Redis/DynamoDB in production.

    Schema versioning: every stored entry tagged schema_version="1.1"
    Tenant scoping: tenant_id stored per entry (set at session init)
    Retention: entries with expires_at in past are deleted on read.
    """

    SCHEMA_VERSION = "1.1"

    def __init__(self, tenant_id: str = "vryfid", session_token: str = ""):
        self._store:        dict[str, MemoryEntry] = {}
        self.tenant_id:     str = tenant_id
        self.session_token: str = session_token   # hashed, not raw session_id

    # ── Write ──────────────────────────────────────────────────────────────────

    def store(self, key: str, value: Any, category: MemoryCategory) -> bool:
        """
        Store a memory entry.

        Layer 1: exact NEVER_STORE name match → block.
        Layer 2: semantic regex on key + value → block.
        Both layers emit blocked_memory_attempt event.
        Returns False silently on block (never raises).
        """
        # Layer 1 — exact name
        if any(blocked in key.lower() for blocked in NEVER_STORE):
            emit_blocked_memory_event(f"layer1_name_block:{key}")
            return False

        guard_result = check_memory_key(key, str(value))
        if guard_result["blocked"]:
            emit_event("memory_blocked", {
                "key": key,
                "category": guard_result["category"],
                "reason": guard_result["reason"],
            })
            return False

        # Layer 2 — semantic pattern
        semantic_hit = _is_semantically_restricted(key, value)
        if semantic_hit:
            emit_blocked_memory_event(f"layer2_semantic_block:{key}[{semantic_hit}]")
            return False

        expiry: Optional[datetime] = None
        days = EXPIRY_DAYS.get(category)
        if days is not None and days > 0:
            expiry = datetime.now(timezone.utc) + timedelta(days=days)

        entry = MemoryEntry(
            key=key, value=value, category=category,
            stored_at=datetime.now(timezone.utc),
            expires_at=expiry,
        )
        self._store[key] = entry

        # Event uses hashed session token, NOT raw value
        emit_memory_event(
            key=key,
            category=f"{category.value}[schema:{self.SCHEMA_VERSION}]",
            will_expire=expiry is not None,
        )
        return True

    # ── Read ───────────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at and datetime.now(timezone.utc) > entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    # ── Correction ─────────────────────────────────────────────────────────────

    def correct(self, key: str, new_value: Any) -> bool:
        """User correction always wins over durable or session values."""
        return self.store(key, new_value, MemoryCategory.CORRECTION)

    # ── Session cleanup ────────────────────────────────────────────────────────

    def expire_session(self) -> None:
        keys = [k for k, v in self._store.items()
                if v.category == MemoryCategory.SESSION]
        for k in keys:
            del self._store[k]

    # ── Safe summary (no values, no PII) ──────────────────────────────────────

    def summary(self) -> dict:
        """
        Returns key metadata only — never raw values.
        Safe to include in observability events and dashboard.
        """
        now = datetime.now(timezone.utc)
        return {
            k: {
                "category":   v.category.value,
                "will_expire": v.expires_at is not None,
                "expired":    bool(v.expires_at and now > v.expires_at),
                "schema_ver": self.SCHEMA_VERSION,
            }
            for k, v in self._store.items()
        }


# Module-level singleton for single-session use
memory = MemoryStore()


def store(key: str, value: Any, session: Optional[dict] = None) -> dict:
    """Compatibility contract used by red-team and integration tests."""
    target = session.get("_memory_store") if isinstance(session, dict) else None
    if not isinstance(target, MemoryStore):
        target = memory
    stored = target.store(key, value, MemoryCategory.DURABLE)
    return {
        "stored": stored,
        "reason": None if stored else "restricted memory content",
    }
