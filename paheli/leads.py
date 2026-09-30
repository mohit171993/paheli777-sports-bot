"""Start-parameter campaigns for the Paheli777 lead funnel."""

from __future__ import annotations

import re

_CLEAN = re.compile(r"[^a-zA-Z0-9_-]")
_INTERNAL = {"reminder", "predict", "alerts", "website"}


def clean_start_arg(arg: str) -> str:
    return _CLEAN.sub("", str(arg or ""))[:64]


def campaign_from_start_arg(arg: str) -> str:
    value = clean_start_arg(arg)
    if not value:
        return "direct"
    lowered = value.lower()
    if lowered.startswith("ad_"):
        return lowered
    if lowered in _INTERNAL:
        return "internal"
    return f"ref_{lowered}"[:64]
