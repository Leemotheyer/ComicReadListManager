import asyncio
import re
import time
from typing import Any

import httpx

from app.services.app_settings import SettingsStore

BASE_URL = "https://comicvine.gamespot.com/api"
USER_AGENT = "ComicReadListManager/1.0 (https://github.com/comic-read-list-manager)"

VOLUME_SEARCH_FIELDS = "id,name,start_year,count_of_issues,deck,image,publisher"
VOLUME_DETAIL_FIELDS = "id,name,start_year,count_of_issues,publisher"
ISSUE_FIELDS = "id,issue_number,name,cover_date,volume,image"
ISSUE_DETAIL_FIELDS = "id,issue_number,name,cover_date,volume,publisher,image"


def _issue_sort_key(issue_number: str) -> tuple:
    cleaned = issue_number.strip().replace("½", ".5")
    match = re.match(r"^([\d.]+)", cleaned)
    if match:
        try:
            return (0, float(match.group(1)), issue_number.lower())
        except ValueError:
            pass
    return (1, 0.0, issue_number.lower())


class ComicVineClient:
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_ttl = 3600

    def _get_lock(self, resource: str) -> asyncio.Lock:
        if resource not in self._locks:
            self._locks[resource] = asyncio.Lock()
        return self._locks[resource]

    async def _rate_limit(self, resource: str):
        async with self._get_lock(resource):
            now = time.monotonic()
            last = self._last_request.get(resource, 0)
            wait = 1.0 - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request[resource] = time.monotonic()

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        ts, value = entry
        if time.monotonic() - ts > self._cache_ttl:
            del self._cache[key]
            return None
        return value

    def _cache_set(self, key: str, value: Any):
        self._cache[key] = (time.monotonic(), value)

    async def _request(self, resource: str, path: str, params: dict | None = None) -> dict:
        cache_key = f"{path}:{params}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if not SettingsStore.cached().comicvine_api_key:
            raise ValueError("ComicVine API key is not configured")

        await self._rate_limit(resource)
        query = {"api_key": SettingsStore.cached().comicvine_api_key, "format": "json"}
        if params:
            query.update(params)

        headers = {"User-Agent": USER_AGENT}

        try:
            async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                response = await client.get(f"{BASE_URL}{path}", params=query)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                raise ValueError(
                    "ComicVine rejected the request (403). Verify your API key in Settings."
                ) from exc
            raise ValueError(
                f"ComicVine request failed ({exc.response.status_code})"
            ) from exc
        except httpx.RequestError as exc:
            raise ValueError(f"Could not reach ComicVine: {exc}") from exc

        if data.get("status_code") != 1:
            error = data.get("error") or "ComicVine API error"
            raise ValueError(error)

        self._cache_set(cache_key, data)
        return data

    @staticmethod
    def _publisher_name(publisher: dict | None) -> str | None:
        if not publisher:
            return None
        return publisher.get("name")

    @staticmethod
    def _image_url(image: dict | None) -> str | None:
        if not image:
            return None
        return image.get("small_url") or image.get("thumb_url")

    @staticmethod
    def _cover_year(cover_date: str | None) -> int | None:
        if not cover_date or len(cover_date) < 4:
            return None
        try:
            return int(cover_date[:4])
        except ValueError:
            return None

    @staticmethod
    def _start_year(value) -> int | None:
        # ComicVine returns start_year as a string and marks uncertain
        # years with a trailing "?" (e.g. "1950?").
        if value is None:
            return None
        match = re.search(r"(?:19|20)\d{2}", str(value))
        return int(match.group(0)) if match else None

    async def search_volumes(self, query: str) -> list[dict]:
        data = await self._request(
            "search",
            "/search/",
            {
                "query": query,
                "resources": "volume",
                "limit": 10,
                "field_list": VOLUME_SEARCH_FIELDS,
            },
        )
        results = []
        for item in data.get("results", []):
            results.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "start_year": self._start_year(item.get("start_year")),
                    "publisher": self._publisher_name(item.get("publisher")),
                    "count_of_issues": item.get("count_of_issues"),
                    "deck": item.get("deck"),
                    "image_url": self._image_url(item.get("image")),
                }
            )
        return results

    @staticmethod
    def _parse_issue_row(item: dict, volume: dict, volume_id: int) -> dict:
        vol = item.get("volume") or {}
        return {
            "id": item["id"],
            "issue_number": str(item.get("issue_number", "")),
            "name": item.get("name"),
            "cover_date": item.get("cover_date"),
            "volume_id": vol.get("id") or volume_id,
            "volume_name": vol.get("name") or volume["name"],
            "volume_start_year": ComicVineClient._start_year(
                vol.get("start_year") or volume.get("start_year")
            ),
            "publisher": volume.get("publisher"),
            "image_url": ComicVineClient._image_url(item.get("image")),
        }

    async def _fetch_all_issues_sorted(self, volume_id: int) -> list[dict]:
        cache_key = f"volume_issues_sorted:{volume_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        volume = await self.get_volume(volume_id)
        all_issues: list[dict] = []
        offset = 0
        limit = 100
        total = None

        while True:
            data = await self._request(
                "issues",
                "/issues/",
                {
                    "filter": f"volume:{volume_id}",
                    "offset": offset,
                    "limit": limit,
                    "field_list": ISSUE_FIELDS,
                },
            )
            results = data.get("results", [])
            for item in results:
                all_issues.append(self._parse_issue_row(item, volume, volume_id))

            if total is None:
                total = data.get("number_of_total_results", len(results))
            if offset + len(results) >= total or not results:
                break
            offset += limit

        all_issues.sort(key=lambda i: _issue_sort_key(i["issue_number"]))
        self._cache_set(cache_key, all_issues)
        return all_issues

    async def get_volume(self, volume_id: int) -> dict:
        data = await self._request(
            "volume",
            f"/volume/4050-{volume_id}/",
            {"field_list": VOLUME_DETAIL_FIELDS},
        )
        item = data["results"]
        return {
            "id": item["id"],
            "name": item["name"],
            "start_year": self._start_year(item.get("start_year")),
            "publisher": self._publisher_name(item.get("publisher")),
            "count_of_issues": item.get("count_of_issues"),
        }

    async def get_issues(
        self, volume_id: int, offset: int = 0, limit: int = 100
    ) -> dict:
        all_issues = await self._fetch_all_issues_sorted(volume_id)
        page = all_issues[offset : offset + limit]
        total = len(all_issues)
        return {
            "volume_id": volume_id,
            "issues": page,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(page) < total,
        }

    async def get_issue(self, issue_id: int) -> dict:
        data = await self._request(
            "issue",
            f"/issue/4000-{issue_id}/",
            {"field_list": ISSUE_DETAIL_FIELDS},
        )
        item = data["results"]
        vol = item.get("volume") or {}
        publisher = self._publisher_name(item.get("publisher"))
        if not publisher and vol.get("id"):
            volume = await self.get_volume(vol["id"])
            publisher = volume.get("publisher")
        return {
            "id": item["id"],
            "issue_number": str(item.get("issue_number", "")),
            "name": item.get("name"),
            "cover_date": item.get("cover_date"),
            "volume_id": vol.get("id"),
            "volume_name": vol.get("name"),
            "volume_start_year": self._start_year(vol.get("start_year")),
            "publisher": publisher,
            "cover_year": self._cover_year(item.get("cover_date")),
            "image_url": self._image_url(item.get("image")),
        }


comicvine_client = ComicVineClient()
