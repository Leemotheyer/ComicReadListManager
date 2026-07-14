import re
from dataclasses import dataclass

from collections.abc import Awaitable, Callable

from app.services.comicvine import ComicVineClient, _issue_sort_key, comicvine_client
from app.services.locg import LocgIssue, LocgSource

PUBLISHER_ALIASES = {
    "marvel": "marvel",
    "marvel comics": "marvel",
    "dc": "dc",
    "dc comics": "dc",
    "image": "image",
    "image comics": "image",
    "dark horse": "dark horse",
    "dark horse comics": "dark horse",
    "idw": "idw",
    "idw publishing": "idw",
    "boom": "boom",
    "boom! studios": "boom",
    "viz media": "viz",
    "viz": "viz",
}


@dataclass
class ComicVineMatch:
    cv_volume_id: int
    cv_issue_id: int
    series: str
    issue_number: str
    volume_year: int | None
    cover_year: int | None
    issue_title: str | None
    publisher: str | None
    cover_image_url: str | None
    score: float


def _normalize_issue_number(value: str) -> str:
    cleaned = value.strip().replace("½", ".5")
    cleaned = re.sub(r"^0+(?=\d)", "", cleaned)
    return cleaned or "0"


def _normalize_publisher(value: str | None) -> str:
    if not value:
        return ""
    key = value.strip().lower()
    return PUBLISHER_ALIASES.get(key, key)


def _clean_series_name(value: str) -> str:
    cleaned = re.sub(r"[^\w\s'-]", " ", value.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned.startswith("the "):
        cleaned = cleaned[4:]
    return cleaned


def _year_from_store_date(store_date: str | None) -> int | None:
    if not store_date:
        return None
    match = re.search(r"(19|20)\d{2}", store_date)
    if not match:
        return None
    return int(match.group(0))


def _issue_numbers_match(left: str, right: str) -> bool:
    return _normalize_issue_number(left) == _normalize_issue_number(right)


def _volume_score(
    volume: dict,
    issue: LocgIssue,
    cover_year: int | None,
) -> float:
    score = 0.0
    expected_publisher = _normalize_publisher(issue.publisher)
    actual_publisher = _normalize_publisher(volume.get("publisher"))
    if expected_publisher and actual_publisher:
        if expected_publisher == actual_publisher:
            score += 40
        elif expected_publisher in actual_publisher or actual_publisher in expected_publisher:
            score += 25

    vol_name = _clean_series_name(volume.get("name") or "")
    target_name = _clean_series_name(issue.series)
    if vol_name == target_name:
        score += 35
    elif vol_name.startswith(target_name) or target_name.startswith(vol_name):
        score += 20

    start_year = volume.get("start_year")
    if cover_year and start_year:
        try:
            delta = abs(int(start_year) - cover_year)
        except (TypeError, ValueError):
            delta = None
        if delta is None:
            pass
        elif delta <= 1:
            score += 20
        elif delta <= 3:
            score += 10
        elif delta <= 8:
            score += 4

    return score


def _match_to_payload(match: ComicVineMatch) -> dict:
    return {
        "cv_volume_id": match.cv_volume_id,
        "cv_issue_id": match.cv_issue_id,
        "series": match.series,
        "issue_number": match.issue_number,
        "volume_year": match.volume_year,
        "cover_year": match.cover_year,
        "issue_title": match.issue_title,
        "publisher": match.publisher,
        "cover_image_url": match.cover_image_url,
    }


async def _find_issue_in_volume(
    client: ComicVineClient,
    volume: dict,
    issue: LocgIssue,
    cover_year: int | None,
    get_volume_issues: Callable[[int], Awaitable[list[dict]]] | None = None,
) -> ComicVineMatch | None:
    if get_volume_issues:
        issue_rows = await get_volume_issues(volume["id"])
    else:
        # Fetch the volume's complete issue list: long-running series (e.g.
        # Detective Comics) have far more than one page of issues, and the
        # target number may fall outside the first page.
        issue_rows = await client.get_all_issues(volume["id"])
    matched_row = None
    for row in issue_rows:
        if _issue_numbers_match(row["issue_number"], issue.issue_number):
            matched_row = row
            break
    if not matched_row:
        return None

    return ComicVineMatch(
        cv_volume_id=volume["id"],
        cv_issue_id=matched_row["id"],
        series=matched_row.get("volume_name") or volume["name"],
        issue_number=str(matched_row.get("issue_number") or issue.issue_number),
        volume_year=matched_row.get("volume_start_year") or volume.get("start_year"),
        cover_year=cover_year,
        issue_title=matched_row.get("name"),
        publisher=matched_row.get("publisher") or volume.get("publisher"),
        cover_image_url=matched_row.get("image_url"),
        score=_volume_score(volume, issue, cover_year) + 50,
    )


async def match_locg_issue(
    client: ComicVineClient,
    issue: LocgIssue,
    search_volumes: Callable[[str], Awaitable[list[dict]]] | None = None,
    get_volume_issues: Callable[[int], Awaitable[list[dict]]] | None = None,
) -> tuple[str, ComicVineMatch | None, list[ComicVineMatch], str | None]:
    if issue.parse_error:
        return "failed", None, [], issue.parse_error
    if not issue.issue_number:
        return (
            "failed",
            None,
            [],
            f"Could not determine issue number for {issue.title}",
        )

    cover_year = _year_from_store_date(issue.store_date)
    try:
        volumes = (
            await search_volumes(issue.series)
            if search_volumes
            else await client.search_volumes(issue.series)
        )
    except ValueError as exc:
        return "failed", None, [], str(exc)

    if not volumes:
        return "failed", None, [], f"No ComicVine volume found for {issue.series}"

    ranked_volumes = sorted(
        volumes,
        key=lambda volume: _volume_score(volume, issue, cover_year),
        reverse=True,
    )

    candidates: list[ComicVineMatch] = []
    for volume in ranked_volumes[:5]:
        match = await _find_issue_in_volume(
            client, volume, issue, cover_year, get_volume_issues=get_volume_issues
        )
        if match:
            candidates.append(match)

    if not candidates:
        return (
            "failed",
            None,
            [],
            f"No ComicVine issue #{issue.issue_number} found for {issue.series}",
        )

    candidates.sort(
        key=lambda item: (item.score, _issue_sort_key(item.issue_number)),
        reverse=True,
    )
    best = candidates[0]
    strong = [c for c in candidates if c.score >= best.score - 5]
    unique_issue_ids = {c.cv_issue_id for c in strong}

    if len(unique_issue_ids) == 1:
        return "matched", best, candidates[:5], None

    return (
        "ambiguous",
        None,
        candidates[:5],
        "Multiple ComicVine matches — pick the correct issue below",
    )


async def preview_locg_import(
    locg_source: LocgSource,
    existing_issue_ids: set[int] | None = None,
) -> dict:
    # Reuse the shared client so its response cache persists across previews;
    # fetching a long volume's full issue list is many rate-limited requests.
    client = comicvine_client
    volume_search_cache: dict[str, list[dict]] = {}
    volume_issues_cache: dict[int, list[dict]] = {}
    items: list[dict] = []
    matched_count = 0
    ambiguous_count = 0
    failed_count = 0
    duplicate_count = 0
    existing_issue_ids = existing_issue_ids or set()

    async def cached_search_volumes(series: str) -> list[dict]:
        key = series.strip().lower()
        if key not in volume_search_cache:
            volume_search_cache[key] = await client.search_volumes(series)
        return volume_search_cache[key]

    async def cached_volume_issues(volume_id: int) -> list[dict]:
        if volume_id not in volume_issues_cache:
            volume_issues_cache[volume_id] = await client.get_all_issues(volume_id)
        return volume_issues_cache[volume_id]

    for index, issue in enumerate(locg_source.items):
        status, best, candidates, message = await match_locg_issue(
            client,
            issue,
            search_volumes=cached_search_volumes,
            get_volume_issues=cached_volume_issues,
        )
        if status == "matched":
            matched_count += 1
        elif status == "ambiguous":
            ambiguous_count += 1
        else:
            failed_count += 1

        cv_issue_id = best.cv_issue_id if best else None
        already_in_list = bool(cv_issue_id and cv_issue_id in existing_issue_ids)
        if already_in_list:
            duplicate_count += 1

        item_payload = {
            "index": index,
            "locg_id": issue.locg_id,
            "title": issue.title,
            "series": issue.series,
            "issue_number": issue.issue_number,
            "publisher": issue.publisher,
            "store_date": issue.store_date,
            "notes": issue.notes,
            "status": status,
            "message": message,
            "cv_volume_id": best.cv_volume_id if best else None,
            "cv_issue_id": cv_issue_id,
            "volume_year": best.volume_year if best else None,
            "cover_year": best.cover_year if best else None,
            "issue_title": best.issue_title if best else None,
            "cover_image_url": best.cover_image_url if best else None,
            "already_in_list": already_in_list,
            "candidates": [_match_to_payload(candidate) for candidate in candidates],
        }
        items.append(item_payload)

    return {
        "source_url": locg_source.source_url,
        "source_type": locg_source.source_type,
        "list_name": locg_source.name,
        "list_description": locg_source.description,
        "item_count": len(items),
        "matched_count": matched_count,
        "ambiguous_count": ambiguous_count,
        "failed_count": failed_count,
        "duplicate_count": duplicate_count,
        "items": items,
    }
