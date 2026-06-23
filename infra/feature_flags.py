"""Conservative runtime feature-flag registry."""

import os
from typing import Any


_DEFAULTS: dict[str, Any] = {
    "HOMEY_INTENT_V2": True,
    "HOMEY_RETRIEVAL": False,
    "HOMEY_SEMANTIC_GUARD": False,
    "HOMEY_MEMORY": "limited",
    "HOMEY_SQUAD": True,
    "HOMEY_BROKER_CARDS": False,
    "HOMEY_FIT": False,
    "HOMEY_CAMPAIGN_ROUTER": True,
    "HOMEY_TRUST_RECEIPTS": "internal_only",
    "HOMEY_FLIGHT_RECORDER": True,
}


def get_flag(flag: str) -> Any:
    value = os.environ.get(flag, _DEFAULTS.get(flag))
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def is_enabled(flag: str) -> bool:
    value = get_flag(flag)
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "on", "limited", "internal_only"}


def flags_used_in_response(flags: list[str]) -> list[str]:
    return [f"{flag}={get_flag(flag)}" for flag in flags]


def all_flags() -> dict[str, Any]:
    return {flag: get_flag(flag) for flag in _DEFAULTS}
