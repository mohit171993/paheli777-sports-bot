"""Highlightly All Sports client. Same host and header the paid key expects."""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

TRANSIENT_STATUS_CODES = {429, 502, 503, 504}


class HighlightlyError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class HighlightlyClient:
    def __init__(self, api_key: str, base_url: str = "https://sports.highlightly.net"):
        self.api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")

    async def get(self, path: str, params: dict | None = None):
        if not self.api_key:
            raise HighlightlyError("HIGHLIGHTLY_API_KEY is not configured")
        try:
            return await self._get_once(path, params)
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in TRANSIENT_STATUS_CODES:
                logger.warning("Highlightly HTTP %s from %s; retrying once", code, path)
                await asyncio.sleep(1)
                try:
                    return await self._get_once(path, params)
                except httpx.HTTPStatusError as retry_exc:
                    raise HighlightlyError(
                        f"Highlightly HTTP {retry_exc.response.status_code}",
                        retry_exc.response.status_code,
                    ) from retry_exc
            raise HighlightlyError(f"Highlightly HTTP {code}", code) from exc
        except (httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            logger.warning("Highlightly timeout from %s; retrying once", path)
            await asyncio.sleep(1)
            try:
                return await self._get_once(path, params)
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as retry_exc:
                raise HighlightlyError("Highlightly timed out") from retry_exc

    async def _get_once(self, path: str, params: dict | None):
        headers = {"x-rapidapi-key": self.api_key}
        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{self.base_url}{path}",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            remaining = response.headers.get("x-ratelimit-requests-remaining")
            if remaining is not None:
                logger.info("Highlightly requests remaining: %s", remaining)
            payload = response.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    async def matches(self, sport: str, date_text: str, limit: int = 100) -> list:
        data = await self.get(
            f"/{sport}/matches",
            {"date": date_text, "timezone": "Asia/Kolkata", "limit": limit},
        )
        return data if isinstance(data, list) else []

    async def match(self, sport: str, match_id: str) -> dict:
        data = await self.get(f"/{sport}/matches/{match_id}")
        if isinstance(data, list):
            return data[0] if data else {}
        return data if isinstance(data, dict) else {}

    async def highlights(self, sport: str, date_text: str, limit: int = 8) -> list:
        data = await self.get(
            f"/{sport}/highlights",
            {"date": date_text, "timezone": "Asia/Kolkata", "limit": limit},
        )
        return data if isinstance(data, list) else []

    async def search_teams(self, sport: str, name: str) -> list:
        data = await self.get(
            f"/{sport}/teams",
            {"name": name, "limit": 5, "offset": 0},
        )
        if isinstance(data, list):
            return data[:5]
        return []

    async def team(self, sport: str, team_id: str) -> dict:
        data = await self.get(f"/{sport}/teams/{team_id}")
        if isinstance(data, list):
            return data[0] if data else {}
        return data if isinstance(data, dict) else {}

    async def team_matches(self, sport: str, team_id: str) -> list:
        home_call = self.get(
            f"/{sport}/matches",
            {"homeTeamId": team_id, "timezone": "Asia/Kolkata", "limit": 40, "offset": 0},
        )
        away_call = self.get(
            f"/{sport}/matches",
            {"awayTeamId": team_id, "timezone": "Asia/Kolkata", "limit": 40, "offset": 0},
        )
        home_data, away_data = await asyncio.gather(home_call, away_call)
        combined = []
        seen = set()
        for item in list(home_data or []) + list(away_data or []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("id") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            combined.append(item)
        return combined
