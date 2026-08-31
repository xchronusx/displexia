"""Tiny async client for the Overseerr/Jellyseerr/Seerr API."""

import aiohttp

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
                timeout=aiohttp.ClientTimeout(total=20),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(self, query: str, limit: int = 8) -> list[dict]:
        """Returns simplified results: title, year, media_type, tmdb_id, status."""
        s = await self._sess()
        async with s.get(f"{self.base}/api/v1/search", params={"query": query, "page": 1}) as r:
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
            out.append({
                "tmdb_id": item.get("id"),
                "media_type": mtype,
                "title": title,
                "year": date[:4] if date else "",
                "status": media_info.get("status") or 1,
            })
            if len(out) >= limit:
                break
        return out

    async def request(self, media_type: str, tmdb_id: int) -> tuple[bool, str]:
        """Submit a request. Returns (ok, message)."""
        s = await self._sess()
        payload: dict = {"mediaType": media_type, "mediaId": tmdb_id}
        if media_type == "tv":
            payload["seasons"] = "all"
        async with s.post(f"{self.base}/api/v1/request", json=payload) as r:
            if r.status in (200, 201):
                return (True, "requested")
            body = await self._safe_message(r)
            # Some versions want an explicit season list for TV
            if media_type == "tv" and r.status in (400, 500):
                seasons = await self._season_numbers(tmdb_id)
                if seasons:
                    payload["seasons"] = seasons
                    async with s.post(f"{self.base}/api/v1/request", json=payload) as r2:
                        if r2.status in (200, 201):
                            return (True, "requested")
                        body = await self._safe_message(r2)
            return (False, body)

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
