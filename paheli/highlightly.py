"""Highlightly All Sports API client."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx


logger = logging.getLogger(__name__)

API_BASE = "https://sports.highlightly.net"
TRANSIENT_STATUS = {502, 503, 504}


class HighlightlyError(Exception):
    def __init__(self, kind: str, status: int | None = None):
        super().__init__(kind)
        self.kind = kind
        self.status = status


class HighlightlyClient:
    def __init__(self, api_key: str, ttl_seconds: int = 30):
        self.api_key = api_key
        self.ttl_seconds = ttl_seconds
        self._cache: dict[tuple, tuple[float, Any]] = {}

    async def matches_for_date(self, sport: str, date_text: str, timezone_name: str) -> list:
        items: list = []
        offset = 0
        limit = 100
        total: int | None = None
        for _ in range(3):
            page, page_total = await self._get(
                f"/{sport}/matches",
                {
                    "date": date_text,
                    "timezone": timezone_name,
                    "limit": limit,
                    "offset": offset,
                },
            )
            if total is None:
                total = page_total
            items.extend(page)
            offset += limit
            if len(page) < limit:
                break
            if total is not None and offset >= total:
                break
        return items

    async def highlights(self, sport: str, date_text: str, timezone_name: str) -> list:
        items, _total = await self._get(
            f"/{sport}/highlights",
            {
                "date": date_text,
                "timezone": timezone_name,
                "limit": 10,
                "offset": 0,
            },
        )
        return items

    async def search_teams(self, sport: str, name: str) -> list:
        items, _total = await self._get(
            f"/{sport}/teams",
            {"name": name, "limit": 5, "offset": 0},
        )
        return items[:5]

    async def team(self, sport: str, team_id: str) -> dict:
        payload = await self._request(f"/{sport}/teams/{team_id}", None)
        if isinstance(payload, list):
            return payload[0] if payload else {}
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            return payload["data"]
        if isinstance(payload, dict) and "data" not in payload:
            return payload
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            return data[0] if data else {}
        return data if isinstance(data, dict) else {}

    async def team_matches(self, sport: str, team_id: str, timezone_name: str) -> list:
        home, away = await asyncio.gather(
            self._get(
                f"/{sport}/matches",
                {
                    "homeTeamId": team_id,
                    "timezone": timezone_name,
                    "limit": 40,
                    "offset": 0,
                },
            ),
            self._get(
                f"/{sport}/matches",
                {
                    "awayTeamId": team_id,
                    "timezone": timezone_name,
                    "limit": 40,
                    "offset": 0,
                },
            ),
        )
        combined = list(home[0]) + list(away[0])
        return combined

    async def _get(self, path: str, params: dict | None) -> tuple[list, int | None]:
        payload = await self._request(path, params)
        if isinstance(payload, list):
            return payload, None
        if isinstance(payload, dict):
            data = payload.get("data", [])
            pagination = payload.get("pagination") or {}
            total = pagination.get("totalCount") if isinstance(pagination, dict) else None
            if isinstance(data, list):
                return data, total if isinstance(total, int) else None
        return [], None

    async def _request(self, path: str, params: dict | None) -> Any:
        if not self.api_key:
            raise HighlightlyError("not_configured")
        key = (path, tuple(sorted((params or {}).items())))
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < self.ttl_seconds:
            return cached[1]
        try:
            payload = await self._fetch(path, params)
        except HighlightlyError:
            raise
        except Exception as exc:
            logger.warning("Highlightly request failed for %s: %s", path, exc)
            raise HighlightlyError("unavailable") from exc
        self._cache[key] = (now, payload)
        return payload

    async def _fetch(self, path: str, params: dict | None) -> Any:
        headers = {"x-rapidapi-key": self.api_key}
        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(
                    f"{API_BASE}{path}", headers=headers, params=params
                )
            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                logger.warning("Highlightly timeout on %s; retrying once", path)
                await asyncio.sleep(1)
                response = await client.get(
                    f"{API_BASE}{path}", headers=headers, params=params
                )
            if response.status_code in TRANSIENT_STATUS:
                logger.warning("Highlightly HTTP %s on %s; retrying once", response.status_code, path)
                await asyncio.sleep(1)
                response = await client.get(
                    f"{API_BASE}{path}", headers=headers, params=params
                )
        return _raise_for_status(response)


def _raise_for_status(response: httpx.Response) -> Any:
    remaining = response.headers.get("x-ratelimit-requests-remaining")
    if remaining is not None:
        logger.info("Highlightly requests remaining: %s", remaining)
    if response.status_code in {401, 403}:
        raise HighlightlyError("auth", response.status_code)
    if response.status_code == 429:
        raise HighlightlyError("rate_limit", 429)
    if response.status_code >= 400:
        raise HighlightlyError("http", response.status_code)
    return response.json()
