from pathlib import PurePath
import re
from typing import Any

import httpx

from app.models import ReadList
from app.services.gap_detection import parse_tags


def build_komga_summary(read_list: ReadList) -> str:
    parts: list[str] = []
    if read_list.description:
        parts.append(read_list.description.strip())

    tags = parse_tags(read_list.tags)
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")

    note_lines: list[str] = []
    for item in sorted(read_list.items, key=lambda i: i.sort_order):
        if item.notes and item.notes.strip():
            label = f"{item.series} #{item.issue_number}"
            note_lines.append(f"- {label}: {item.notes.strip()}")

    if note_lines:
        parts.append("Issue notes:\n" + "\n".join(note_lines))

    return "\n\n".join(parts).strip()
from app.services.app_settings import SettingsStore
from app.services.cbl_export import generate_cbl


def _normalize_issue_number(value: str | None) -> str:
    if not value:
        return ""
    cleaned = str(value).strip().replace("½", ".5").lstrip("0")
    return cleaned or "0"


def _book_filename(book: dict) -> str:
    name = book.get("name") or ""
    if name:
        return name
    url = book.get("url") or ""
    if not url:
        return ""
    path = url.split("?", 1)[0].rstrip("/")
    return path.rsplit("/", 1)[-1]


def _extract_issue_candidates_from_filename(filename: str) -> list[str]:
    if not filename:
        return []

    stem = PurePath(filename).stem
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        normalized = _normalize_issue_number(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append(value)

    for match in re.finditer(r"#\s*(\d+(?:\.\d+)?(?:½)?)", stem, re.I):
        add(match.group(1))

    for match in re.finditer(
        r"(?:issue|iss(?:ue)?|no\.?)\s*(\d+(?:\.\d+)?(?:½)?)", stem, re.I
    ):
        add(match.group(1))

    for match in re.finditer(r"[\s_\-](\d+(?:\.\d+)?(?:½)?)\s*\(\d{4}\)", stem):
        add(match.group(1))

    for match in re.finditer(
        r"(?:^|[\s_\-])(\d{1,4}(?:\.\d+)?(?:½)?)(?:[\s_\-]|$|\.)", stem
    ):
        value = match.group(1)
        if len(value) == 4 and value.isdigit() and value.startswith(("19", "20")):
            continue
        add(value)

    return candidates


def _find_book_by_issue_number(books: list[dict], issue_number: str) -> dict | None:
    target = _normalize_issue_number(issue_number)
    if not target:
        return None

    for book in books:
        if _normalize_issue_number(book.get("number")) == target:
            return book

    for book in books:
        filename = book.get("filename") or _book_filename(book)
        for candidate in _extract_issue_candidates_from_filename(filename):
            if _normalize_issue_number(candidate) == target:
                return book

    return None


class KomgaClient:
    def _config(self) -> tuple[str, str]:
        s = SettingsStore.cached()
        return s.komga_url.rstrip("/"), s.komga_api_key

    def _configured(self) -> bool:
        base_url, api_key = self._config()
        return bool(base_url and api_key)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        if not self._configured():
            raise ValueError("Komga is not configured (KOMGA_URL / KOMGA_API_KEY)")

        base_url, api_key = self._config()
        url = f"{base_url}{path}"
        headers = {"X-API-Key": api_key}

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.request(
                method, url, params=params, json=json, headers=headers
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return None
            return response.json()

    async def match_cbl(self, cbl_content: str) -> dict:
        if not self._configured():
            raise ValueError("Komga is not configured (KOMGA_URL / KOMGA_API_KEY)")

        base_url, api_key = self._config()
        url = f"{base_url}/api/v1/readlists/match/comicrack"
        headers = {"X-API-Key": api_key}
        files = {
            "file": ("readlist.cbl", cbl_content.encode("utf-8"), "application/xml")
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, files=files, headers=headers)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _extract_candidates(match_entry: dict) -> list[dict]:
        candidates: list[dict] = []
        seen: set[tuple[str | None, str | None]] = set()

        for match in match_entry.get("matches") or []:
            series = match.get("series") or {}
            series_id = series.get("seriesId")
            series_title = series.get("title")
            books = match.get("books") or []

            if books:
                for book in books:
                    book_id = book.get("bookId")
                    key = (series_id, book_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(
                        {
                            "series_id": series_id,
                            "series_title": series_title,
                            "book_id": book_id,
                            "book_number": book.get("number"),
                            "book_title": book.get("title"),
                        }
                    )
            elif series_id:
                key = (series_id, None)
                if key not in seen:
                    seen.add(key)
                    candidates.append(
                        {
                            "series_id": series_id,
                            "series_title": series_title,
                            "book_id": None,
                            "book_number": None,
                            "book_title": None,
                        }
                    )

        return candidates

    @staticmethod
    def _first_book_id(match_entry: dict) -> str | None:
        for candidate in KomgaClient._extract_candidates(match_entry):
            if candidate.get("book_id"):
                return candidate["book_id"]
        return None

    @staticmethod
    def _match_message(match_entry: dict, book_id: str | None) -> str:
        if book_id:
            for candidate in KomgaClient._extract_candidates(match_entry):
                if candidate.get("book_id") == book_id:
                    title = candidate.get("book_title") or candidate.get("series_title")
                    if title:
                        return f"Matched: {title}"
            return "Matched in Komga library"
        request = match_entry.get("request") or {}
        series = request.get("series") or []
        number = request.get("number") or "?"
        label = series[0] if series else "Unknown series"
        candidates = KomgaClient._extract_candidates(match_entry)
        if candidates:
            return f"No exact match for {label} #{number} — pick a candidate below"
        return f"No match for {label} #{number}"

    def classify_list(self, read_list: ReadList, match_response: dict) -> dict:
        requests = match_response.get("requests") or []
        items = sorted(read_list.items, key=lambda i: i.sort_order)
        read_list_match = match_response.get("readListMatch") or {}

        preview_items = []
        matched_book_ids: list[str] = []

        for idx, item in enumerate(items):
            match_entry = requests[idx] if idx < len(requests) else {}
            book_id = self._first_book_id(match_entry)
            candidates = self._extract_candidates(match_entry)
            if book_id:
                matched_book_ids.append(book_id)

            preview_items.append(
                {
                    "list_item_id": item.id,
                    "cv_volume_id": item.cv_volume_id,
                    "series": item.series,
                    "issue_number": item.issue_number,
                    "volume_year": item.volume_year,
                    "status": "matched" if book_id else "unmatched",
                    "komga_book_id": book_id,
                    "message": self._match_message(match_entry, book_id),
                    "candidates": candidates,
                }
            )

        list_name = read_list_match.get("name") or read_list.name
        list_error = read_list_match.get("errorCode") or match_response.get("errorCode")

        return {
            "list_name": list_name,
            "list_error_code": list_error or None,
            "items": preview_items,
            "matched_count": len(matched_book_ids),
            "unmatched_count": len(preview_items) - len(matched_book_ids),
            "matched_book_ids": matched_book_ids,
        }

    @staticmethod
    def _page_content(data: Any) -> list[dict]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("content") or []
        return []

    async def search_series(self, query: str, *, limit: int = 20) -> list[dict]:
        data = await self._request(
            "POST",
            "/api/v1/series/list",
            params={"size": limit},
            json={"fullTextSearch": query},
        )
        results = []
        for series in self._page_content(data):
            metadata = series.get("metadata") or {}
            release_date = metadata.get("releaseDate") or ""
            year = int(release_date[:4]) if len(release_date) >= 4 else None
            results.append(
                {
                    "id": series["id"],
                    "name": series.get("name") or metadata.get("title") or "Unknown",
                    "books_count": series.get("booksCount", 0),
                    "year": year,
                }
            )
        return results

    async def get_series_books(self, series_id: str) -> list[dict]:
        data = await self._request(
            "POST",
            "/api/v1/books/list",
            params={"unpaged": "true", "sort": ["metadata.numberSort,asc"]},
            json={
                "condition": {
                    "seriesId": {"operator": "is", "value": series_id},
                }
            },
        )
        results = []
        for book in self._page_content(data):
            metadata = book.get("metadata") or {}
            filename = _book_filename(book)
            results.append(
                {
                    "id": book["id"],
                    "number": metadata.get("number") or str(book.get("number", "")),
                    "title": metadata.get("title") or book.get("name") or "",
                    "series_title": book.get("seriesTitle"),
                    "filename": filename,
                }
            )
        return results

    async def match_issues_to_books(
        self, series_id: str, items: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        books = await self.get_series_books(series_id)

        matched: list[dict] = []
        unmatched: list[dict] = []
        used_book_ids: set[str] = set()

        for item in items:
            list_item_id = item["list_item_id"]
            issue_number = item["issue_number"]
            book = _find_book_by_issue_number(
                [b for b in books if b["id"] not in used_book_ids],
                issue_number,
            )
            if book:
                used_book_ids.add(book["id"])
                series_title = book.get("series_title") or ""
                label = (
                    f"{series_title} #{book['number']}".strip()
                    if series_title
                    else f"#{book['number']}"
                )
                matched.append(
                    {
                        "list_item_id": list_item_id,
                        "komga_book_id": book["id"],
                        "label": label,
                        "issue_number": issue_number,
                    }
                )
            else:
                unmatched.append(
                    {
                        "list_item_id": list_item_id,
                        "issue_number": issue_number,
                    }
                )
        return matched, unmatched

    async def find_read_list_by_name(self, name: str) -> dict | None:
        data = await self._request(
            "GET",
            "/api/v1/readlists",
            params={"search": name, "unpaged": "true"},
        )
        content = self._page_content(data)
        exact = [rl for rl in content if rl.get("name") == name]
        return exact[0] if exact else None

    async def create_read_list(
        self,
        name: str,
        summary: str,
        book_ids: list[str],
        *,
        ordered: bool = True,
    ) -> dict:
        return await self._request(
            "POST",
            "/api/v1/readlists",
            json={
                "name": name,
                "summary": summary,
                "ordered": ordered,
                "bookIds": book_ids,
            },
        )

    async def update_read_list(
        self,
        read_list_id: str,
        *,
        name: str | None = None,
        summary: str | None = None,
        book_ids: list[str] | None = None,
        ordered: bool | None = None,
    ) -> None:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if summary is not None:
            payload["summary"] = summary
        if book_ids is not None:
            payload["bookIds"] = book_ids
        if ordered is not None:
            payload["ordered"] = ordered
        await self._request("PATCH", f"/api/v1/readlists/{read_list_id}", json=payload)

    @staticmethod
    def resolve_items(
        preview_items: list[dict],
        manual_mappings: dict[int, str] | None = None,
        manual_labels: dict[int, str] | None = None,
    ) -> tuple[list[str], list[dict]]:
        manual_mappings = manual_mappings or {}
        manual_labels = manual_labels or {}
        book_ids: list[str] = []
        resolved_items: list[dict] = []

        for item in preview_items:
            list_item_id = item["list_item_id"]
            book_id = manual_mappings.get(list_item_id) or item.get("komga_book_id")
            resolved = dict(item)

            if list_item_id in manual_mappings:
                resolved["status"] = "manual"
                resolved["komga_book_id"] = book_id
                resolved["message"] = manual_labels.get(
                    list_item_id, "Manually matched"
                )
            elif book_id:
                resolved["status"] = "matched"
                resolved["komga_book_id"] = book_id
            else:
                resolved["status"] = "unmatched"
                resolved["komga_book_id"] = None

            resolved_items.append(resolved)
            if book_id:
                book_ids.append(book_id)

        return book_ids, resolved_items

    async def preview(self, read_list: ReadList) -> dict:
        if not read_list.items:
            raise ValueError("List has no items")
        cbl = generate_cbl(read_list)
        match_response = await self.match_cbl(cbl)
        result = self.classify_list(read_list, match_response)
        existing = await self.find_read_list_by_name(result["list_name"])
        result["existing_komga_read_list_id"] = existing.get("id") if existing else None
        result["existing_komga_read_list_name"] = existing.get("name") if existing else None
        return result

    async def push(
        self,
        read_list: ReadList,
        *,
        allow_partial: bool = True,
        manual_mappings: dict[int, str] | None = None,
        manual_labels: dict[int, str] | None = None,
    ) -> dict:
        preview = await self.preview(read_list)
        book_ids, resolved_items = self.resolve_items(
            preview["items"], manual_mappings, manual_labels
        )
        unmatched_count = sum(1 for i in resolved_items if not i.get("komga_book_id"))

        if not book_ids:
            raise ValueError("No books matched in Komga — match unmatched items or check metadata")

        if unmatched_count and not allow_partial:
            raise ValueError(
                f"{unmatched_count} issue(s) did not match — "
                "match them manually or enable partial push"
            )

        name = preview["list_name"]
        summary = build_komga_summary(read_list)
        existing_id = preview.get("existing_komga_read_list_id")

        if existing_id:
            await self.update_read_list(
                existing_id,
                name=name,
                summary=summary,
                book_ids=book_ids,
                ordered=True,
            )
            action = "updated"
            read_list_id = existing_id
        else:
            created = await self.create_read_list(name, summary, book_ids, ordered=True)
            action = "created"
            read_list_id = created.get("id")

        return {
            "action": action,
            "komga_read_list_id": read_list_id,
            "komga_read_list_name": name,
            "books_pushed": len(book_ids),
            "books_skipped": unmatched_count,
            "items": resolved_items,
        }


komga_client = KomgaClient()
