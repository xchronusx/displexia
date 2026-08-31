"""Tiny async client for the Overseerr/Jellyseerr/Seerr API."""

import logging

import aiohttp

log = logging.getLogger("displexia.seerr")

# Overseerr media status codes
STATUS_LABEL = {
    2: "⏳ Already requested",
    3: "⏳ Requested — processing",
    4: "🟡 Partially on Plex",
    5: "✅ Already on Plex",
}


class SeerrClient:
    def __init__(self, base_url: str, api_key: str):
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(self, query: str, limit: int = 8) -> list[dict]:
        """Returns simplified results: title, year, media_type, tmdb_id, status."""
        s = await self._sess()
        async with s.get(f"{self.base}/api/v1/search",
                         params={"query": query, "page": "1"}) as r:
            r.raise_for_status()
            data = await r.json()
        out = []
        for item in data.get("results", []):
            mtype = item.get("mediaType")
            if mtype not in ("movie", "tv"):
                continue
            title = item.get("title") or item.get("name") or "?"
            date = item.get("releaseDate") or item.get("firstAirDate") or ""
            media_info = item.get("mediaInfo") or {}
            poster = item.get("posterPath")
            overview = (item.get("overview") or "").strip()
            if len(overview) > 350:
                overview = overview[:347].rstrip() + "…"
            out.append({
                "tmdb_id": item.get("id"),
                "media_type": mtype,
                "title": title,
                "year": date[:4] if date else "",
                "status": media_info.get("status") or 1,
                "poster": f"https://image.tmdb.org/t/p/w342{poster}" if poster else None,
                "overview": overview,
            })
            if len(out) >= limit:
                break
        return out

    async def request(self, media_type: str, tmdb_id: int) -> tuple[bool, str]:
        """Submit a request. Returns (ok, message)."""
        payload: dict = {"mediaType": media_type, "mediaId": int(tmdb_id)}
        if media_type == "tv":
            # Explicit season list works on every Overseerr/Jellyseerr version;
            # "all" is the fallback if the season lookup fails.
            seasons = await self._season_numbers(tmdb_id)
            payload["seasons"] = seasons or "all"

        status, body = await self._post_request(payload)
        if status in (200, 201):
            return (True, "requested")

        if media_type == "tv":
            # Retry once with the other seasons form (API differences between versions)
            alt = "all" if isinstance(payload["seasons"], list) \
                else await self._season_numbers(tmdb_id)
            if alt and alt != payload["seasons"]:
                payload["seasons"] = alt
                status, body = await self._post_request(payload)
                if status in (200, 201):
                    return (True, "requested")

        log.warning("Seerr request failed: %s %s -> HTTP %s: %s",
                    media_type, tmdb_id, status, body)
        if status == 409:
            return (False, "already exists")
        return (False, f"{body} (HTTP {status})")

    async def _post_request(self, payload: dict) -> tuple[int, str]:
        s = await self._sess()
        async with s.post(f"{self.base}/api/v1/request", json=payload) as r:
            if r.status in (200, 201):
                return (r.status, "")
            return (r.status, await self._safe_message(r))

    async def _season_numbers(self, tmdb_id: int) -> list[int]:
        try:
            s = await self._sess()
            async with s.get(f"{self.base}/api/v1/tv/{tmdb_id}") as r:
                if r.status != 200:
                    return []
                data = await r.json()
            return [x["seasonNumber"] for x in data.get("seasons", [])
                    if x.get("seasonNumber", 0) > 0]
        except Exception:
            return []

    @staticmethod
    async def _safe_message(resp) -> str:
        try:
            data = await resp.json()
            return str(data.get("message") or data)[:200]
        except Exception:
            return f"HTTP {resp.status}"
