"""Start-link campaign names for the Paheli777 lead funnel."""

from __future__ import annotations

import re


_INTERNAL = {"reminder", "predict", "website", "start", "alerts"}


def clean_start_arg(arg: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", str(arg or ""))[:64]


def campaign_from_start_arg(arg: str) -> str:
    cleaned = clean_start_arg(arg)
    if not cleaned:
        return "direct"
    lowered = cleaned.lower()
    if lowered.startswith("ad_"):
        return lowered
    if lowered in _INTERNAL:
        return "internal"
    return f"ref_{lowered}"[:64]
