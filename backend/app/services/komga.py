from pathlib import PurePath
import re
from typing import Any

import httpx

from app.models import ReadList
from app.services.app_settings import SettingsStore
from app.services.cbl_export import generate_cbl
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


def _names_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return left.casefold() == right.casefold()


def _dedupe_book_ids(book_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for book_id in book_ids:
        if book_id not in seen:
            seen.add(book_id)
            unique.append(book_id)
    return unique


def format_komga_error(exc: httpx.HTTPStatusError) -> str:
    status = exc.response.status_code
    try:
        body = exc.response.json()
    except Exception:
        body = None

    if isinstance(body, dict):
        if message := body.get("message"):
            return f"Komga API error ({status}): {message}"
        if violations := body.get("violations"):
            parts = [
                f"{v.get('fieldName', '?')}: {v.get('message', '?')}"
                for v in violations
            ]
            return f"Komga API error ({status}): {'; '.join(parts)}"
        if detail := body.get("detail"):
            return f"Komga API error ({status}): {detail}"

    text = exc.response.text.strip()
    if text:
        return f"Komga API error ({status}): {text[:500]}"
    return f"Komga API error ({status})"


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


def _parse_year(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def _year_from_series_title(title: str | None) -> int | None:
    if not title:
        return None
    match = re.search(r"\((\d{4})\)\s*$", title.strip())
    if match:
        return int(match.group(1))
    return None


def _series_year_from_komga(series: dict) -> int | None:
    year = _parse_year(series.get("releaseDate"))
    if year is not None:
        return year
    return _year_from_series_title(series.get("title"))


def _issue_numbers_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return _normalize_issue_number(left) == _normalize_issue_number(right)


def _request_series_hints(match_entry: dict) -> set[str]:
    request = match_entry.get("request") or {}
    series = request.get("series") or []
    hints: set[str] = set()
    for value in series:
        if isinstance(value, str) and value.strip():
            hints.add(value.strip())
    return hints


def _score_book_candidate(
    candidate: dict,
    *,
    issue_number: str,
    volume_year: int | None,
    cover_year: int | None,
    request_series: set[str],
) -> int:
    book_number = candidate.get("book_number")
    if not book_number or not _issue_numbers_match(book_number, issue_number):
        return -1

    score = 10
    series_year = candidate.get("series_year")
    series_title = candidate.get("series_title") or ""

    if volume_year is not None:
        if series_year is None:
            return -1
        if series_year != volume_year:
            return -1
        score += 200
    elif series_year is not None:
        score += 20

    if cover_year is not None and series_year is not None and cover_year == series_year:
        score += 15

    title_cf = series_title.casefold()
    for hint in request_series:
        hint_cf = hint.casefold()
        if hint_cf == title_cf:
            score += 40
        elif volume_year is not None and hint_cf == f"{series_title.split('(')[0].strip().casefold()} ({volume_year})":
            score += 60

    if volume_year is not None and f"({volume_year})" in series_title:
        score += 30

    return score


def _pick_best_book_id(
    match_entry: dict,
    *,
    issue_number: str,
    volume_year: int | None,
    cover_year: int | None,
    preferred_series_id: str | None = None,
    used_book_ids: set[str] | None = None,
) -> str | None:
    candidates = KomgaClient._extract_candidates(match_entry)
    if not candidates:
        return None

    used_book_ids = used_book_ids or set()
    request_series = _request_series_hints(match_entry)
    scored: list[tuple[int, dict]] = []

    for candidate in candidates:
        book_id = candidate.get("book_id")
        if not book_id or book_id in used_book_ids:
            continue
        if preferred_series_id and candidate.get("series_id") != preferred_series_id:
            continue
        score = _score_book_candidate(
            candidate,
            issue_number=issue_number,
            volume_year=volume_year,
            cover_year=cover_year,
            request_series=request_series,
        )
        if score >= 0:
            scored.append((score, candidate))

    if not scored:
        return None

    scored.sort(key=lambda pair: pair[0], reverse=True)
    for best_score in sorted({score for score, _ in scored}, reverse=True):
        tier = [candidate for score, candidate in scored if score == best_score]
        available = [
            candidate
            for candidate in tier
            if candidate.get("book_id") and candidate["book_id"] not in used_book_ids
        ]
        unique_books = {candidate["book_id"] for candidate in available}
        if len(unique_books) == 1:
            return available[0]["book_id"]
        if len(unique_books) > 1:
            continue

    return None


def _book_id_blocked_as_duplicate(
    match_entry: dict,
    *,
    issue_number: str,
    volume_year: int | None,
    cover_year: int | None,
    used_book_ids: set[str],
) -> bool:
    if not used_book_ids:
        return False
    best_without_reserve = _pick_best_book_id(
        match_entry,
        issue_number=issue_number,
        volume_year=volume_year,
        cover_year=cover_year,
        used_book_ids=set(),
    )
    return bool(best_without_reserve and best_without_reserve in used_book_ids)


def _sort_candidates_for_display(
    candidates: list[dict],
    *,
    issue_number: str,
    volume_year: int | None,
    cover_year: int | None,
    request_series: set[str],
) -> list[dict]:
    scored: list[tuple[int, dict]] = []
    for candidate in candidates:
        if candidate.get("book_id"):
            score = _score_book_candidate(
                candidate,
                issue_number=issue_number,
                volume_year=volume_year,
                cover_year=cover_year,
                request_series=request_series,
            )
        else:
            score = 0
            if volume_year is not None and candidate.get("series_year") == volume_year:
                score = 100
        scored.append((score, candidate))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in scored]


def _apply_volume_series_consistency(
    preview_items: list[dict],
    match_entries: list[dict],
    used_book_ids: set[str],
) -> None:
    groups: dict[int, list[tuple[dict, dict]]] = {}
    for item, match_entry in zip(preview_items, match_entries):
        groups.setdefault(item["cv_volume_id"], []).append((item, match_entry))

    for pairs in groups.values():
        series_counts: dict[str, int] = {}
        for item, _ in pairs:
            book_id = item.get("komga_book_id")
            if not book_id:
                continue
            for candidate in item.get("candidates") or []:
                if candidate.get("book_id") == book_id and candidate.get("series_id"):
                    series_id = candidate["series_id"]
                    series_counts[series_id] = series_counts.get(series_id, 0) + 1
                    break

        if not series_counts:
            continue

        preferred_series_id = max(series_counts, key=series_counts.get)

        for item, match_entry in pairs:
            if item.get("komga_book_id"):
                continue
            book_id = _pick_best_book_id(
                match_entry,
                issue_number=item["issue_number"],
                volume_year=item.get("volume_year"),
                cover_year=item.get("cover_year"),
                preferred_series_id=preferred_series_id,
                used_book_ids=used_book_ids,
            )
            if book_id:
                item["komga_book_id"] = book_id
                item["status"] = "matched"
                item["message"] = KomgaClient._match_message(
                    match_entry,
                    book_id,
                    volume_year=item.get("volume_year"),
                )
                used_book_ids.add(book_id)


def _resolve_duplicate_matches(
    preview_items: list[dict],
    match_entries: list[dict],
) -> None:
    used_book_ids: set[str] = set()

    for item, match_entry in zip(preview_items, match_entries):
        book_id = item.get("komga_book_id")
        if not book_id:
            continue

        if book_id in used_book_ids:
            alternate = _pick_best_book_id(
                match_entry,
                issue_number=item["issue_number"],
                volume_year=item.get("volume_year"),
                cover_year=item.get("cover_year"),
                used_book_ids=used_book_ids,
            )
            if alternate:
                item["komga_book_id"] = alternate
                item["status"] = "matched"
                item["message"] = KomgaClient._match_message(
                    match_entry,
                    alternate,
                    volume_year=item.get("volume_year"),
                )
                used_book_ids.add(alternate)
            else:
                item["komga_book_id"] = None
                item["status"] = "unmatched"
                item["message"] = (
                    "Komga book already matched to another issue in this list"
                )
        else:
            used_book_ids.add(book_id)


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
                            "series_year": _series_year_from_komga(series),
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
                            "series_year": _series_year_from_komga(series),
                            "book_id": None,
                            "book_number": None,
                            "book_title": None,
                        }
                    )

        return candidates

    @staticmethod
    def _match_message(
        match_entry: dict,
        book_id: str | None,
        *,
        volume_year: int | None = None,
    ) -> str:
        if book_id:
            for candidate in KomgaClient._extract_candidates(match_entry):
                if candidate.get("book_id") == book_id:
                    title = candidate.get("book_title") or candidate.get("series_title")
                    series_year = candidate.get("series_year")
                    if title:
                        if series_year is not None:
                            return f"Matched: {title} ({series_year})"
                        return f"Matched: {title}"
            return "Matched in Komga library"
        request = match_entry.get("request") or {}
        series = request.get("series") or []
        number = request.get("number") or "?"
        label = series[0] if series else "Unknown series"
        candidates = [
            c for c in KomgaClient._extract_candidates(match_entry) if c.get("book_id")
        ]
        if candidates:
            if volume_year is not None:
                return (
                    f"No confident match for {label} ({volume_year}) #{number} "
                    "— multiple similar series found; pick a candidate below"
                )
            return f"No exact match for {label} #{number} — pick a candidate below"
        return f"No match for {label} #{number}"

    def classify_list(self, read_list: ReadList, match_response: dict) -> dict:
        requests = match_response.get("requests") or []
        items = sorted(read_list.items, key=lambda i: i.sort_order)
        read_list_match = match_response.get("readListMatch") or {}

        preview_items: list[dict] = []
        match_entries: list[dict] = []
        used_book_ids: set[str] = set()

        for idx, item in enumerate(items):
            match_entry = requests[idx] if idx < len(requests) else {}
            request_series = _request_series_hints(match_entry)
            candidates = _sort_candidates_for_display(
                self._extract_candidates(match_entry),
                issue_number=item.issue_number,
                volume_year=item.volume_year,
                cover_year=item.cover_year,
                request_series=request_series,
            )
            book_id = _pick_best_book_id(
                match_entry,
                issue_number=item.issue_number,
                volume_year=item.volume_year,
                cover_year=item.cover_year,
                used_book_ids=used_book_ids,
            )
            if book_id:
                used_book_ids.add(book_id)

            if book_id:
                message = self._match_message(
                    match_entry,
                    book_id,
                    volume_year=item.volume_year,
                )
            elif _book_id_blocked_as_duplicate(
                match_entry,
                issue_number=item.issue_number,
                volume_year=item.volume_year,
                cover_year=item.cover_year,
                used_book_ids=used_book_ids,
            ):
                message = "Komga book already matched to another issue in this list"
            else:
                message = self._match_message(
                    match_entry,
                    None,
                    volume_year=item.volume_year,
                )

            preview_items.append(
                {
                    "list_item_id": item.id,
                    "cv_volume_id": item.cv_volume_id,
                    "series": item.series,
                    "issue_number": item.issue_number,
                    "volume_year": item.volume_year,
                    "cover_year": item.cover_year,
                    "status": "matched" if book_id else "unmatched",
                    "komga_book_id": book_id,
                    "message": message,
                    "candidates": candidates,
                }
            )
            match_entries.append(match_entry)

        _apply_volume_series_consistency(preview_items, match_entries, used_book_ids)
        _resolve_duplicate_matches(preview_items, match_entries)

        matched_book_ids = [
            item["komga_book_id"]
            for item in preview_items
            if item.get("komga_book_id")
        ]

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
        exact = [rl for rl in content if _names_match(rl.get("name"), name)]
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
        excluded_ids: set[int] | None = None,
    ) -> tuple[list[str], list[dict]]:
        manual_mappings = manual_mappings or {}
        manual_labels = manual_labels or {}
        excluded_ids = excluded_ids or set()
        book_ids: list[str] = []
        resolved_items: list[dict] = []

        for item in preview_items:
            list_item_id = item["list_item_id"]
            resolved = dict(item)

            if list_item_id in manual_mappings:
                book_id = manual_mappings[list_item_id]
                resolved["status"] = "manual"
                resolved["komga_book_id"] = book_id
                resolved["message"] = manual_labels.get(
                    list_item_id, "Manually matched"
                )
            elif list_item_id in excluded_ids:
                book_id = None
                resolved["status"] = "unmatched"
                resolved["komga_book_id"] = None
                resolved["message"] = "Auto-match rejected"
            elif item.get("komga_book_id"):
                book_id = item["komga_book_id"]
                resolved["status"] = "matched"
                resolved["komga_book_id"] = book_id
            else:
                book_id = None
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
        excluded_ids: set[int] | None = None,
    ) -> dict:
        preview = await self.preview(read_list)
        book_ids, resolved_items = self.resolve_items(
            preview["items"],
            manual_mappings,
            manual_labels,
            excluded_ids,
        )
        unmatched_count = sum(1 for i in resolved_items if not i.get("komga_book_id"))
        original_book_count = len(book_ids)
        book_ids = _dedupe_book_ids(book_ids)
        duplicate_count = original_book_count - len(book_ids)

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
            action = "updated"
            read_list_id = existing_id
            await self.update_read_list(
                existing_id,
                name=name,
                summary=summary,
                book_ids=book_ids,
                ordered=True,
            )
        else:
            action, read_list_id = await self._create_or_update_read_list(
                name, summary, book_ids
            )

        return {
            "action": action,
            "komga_read_list_id": read_list_id,
            "komga_read_list_name": name,
            "books_pushed": len(book_ids),
            "books_skipped": unmatched_count + duplicate_count,
            "items": resolved_items,
        }

    async def _create_or_update_read_list(
        self,
        name: str,
        summary: str,
        book_ids: list[str],
    ) -> tuple[str, str | None]:
        try:
            created = await self.create_read_list(name, summary, book_ids, ordered=True)
            return "created", created.get("id")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400:
                raise
            existing = await self.find_read_list_by_name(name)
            if not existing:
                raise
            await self.update_read_list(
                existing["id"],
                name=name,
                summary=summary,
                book_ids=book_ids,
                ordered=True,
            )
            return "updated", existing.get("id")


komga_client = KomgaClient()
