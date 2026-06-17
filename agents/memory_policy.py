"""
agents/memory_policy.py  — Task 15: Memory Policy
What Homey remembers, what expires, and what must NEVER be stored.

Categories:
  DURABLE    → preferences, name, area (no expiry)
  SESSION    → current search context (expires at session end)
  READINESS  → move-in timing (expires after 30 days)
  CORRECTION → user says "no, I meant X" (always overrides older data)
  BLOCKED    → credit_score, eviction, ssn — NEVER stored
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from schemas.memory import MemoryCategory, MemoryEntry, NEVER_STORE, EXPIRY_DAYS
from observability.stream import emit_memory_event, emit_blocked_memory_event


class MemoryStore:
    """
    In-memory session store. Replace _store with Redis in production.
    """

    def __init__(self):
        self._store: dict[str, MemoryEntry] = {}

    # ── Write ─────────────────────────────────────────────────────────────────

    def store(self, key: str, value: Any,
              category: MemoryCategory) -> bool:
        """
        Store a memory entry.
        Returns False (silently) if key matches a NEVER_STORE field.

        Failure case: store("credit_score", 720, DURABLE)
        → returns False, emits blocked_memory_attempt event.
        → value is NEVER written anywhere.
        """
        if any(blocked in key.lower() for blocked in NEVER_STORE):
            emit_blocked_memory_event(key)
            return False

        expiry: Optional[datetime] = None
        days = EXPIRY_DAYS.get(category)
        if days is not None and days > 0:
            expiry = datetime.now(timezone.utc) + timedelta(days=days)

        entry = MemoryEntry(
            key=key,
            value=value,
            category=category,
            stored_at=datetime.now(timezone.utc),
            expires_at=expiry,
        )
        self._store[key] = entry
        emit_memory_event(key, category.value, expiry is not None)
        return True

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value. Returns None if expired or not found.
        Expired entries are deleted on access.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at and datetime.now(timezone.utc) > entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    # ── Correction (user says "no, I meant X") ────────────────────────────────

    def correct(self, key: str, new_value: Any) -> bool:
        """
        User correction always wins over any existing value.
        Stored under CORRECTION category — no expiry.
        """
        return self.store(key, new_value, MemoryCategory.CORRECTION)

    # ── Session expiry ────────────────────────────────────────────────────────

    def expire_session(self):
        """Remove all SESSION-category entries. Call at conversation end."""
        keys_to_delete = [
            k for k, v in self._store.items()
            if v.category == MemoryCategory.SESSION
        ]
        for k in keys_to_delete:
            del self._store[k]

    # ── Debug view (no sensitive values) ──────────────────────────────────────

    def summary(self) -> dict:
        now = datetime.now(timezone.utc)
        return {
            k: {
                "category":   v.category.value,
                "will_expire": v.expires_at is not None,
                "expired":    bool(v.expires_at and now > v.expires_at),
            }
            for k, v in self._store.items()
        }


# ─── Module-level singleton (one per session in production) ───────────────────
memory = MemoryStore()
