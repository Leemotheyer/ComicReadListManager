import re
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BASE_URL = "https://leagueofcomicgeeks.com"

LIST_URL_RE = re.compile(
    r"^https?://(?:www\.)?leagueofcomicgeeks\.com/profile/"
    r"(?P<username>[^/]+)/lists/(?P<list_id>\d+)(?:/[^/?#]*)?$",
    re.IGNORECASE,
)
COMIC_URL_RE = re.compile(
    r"^https?://(?:www\.)?leagueofcomicgeeks\.com/comic/(?P<comic_id>\d+)(?:/[^/?#]*)?$",
    re.IGNORECASE,
)
THREAD_ID_RE = re.compile(r"DashboardFeed\.loadThread\((\d+)")


@dataclass
class LocgIssue:
    locg_id: int
    sort_order: int
    title: str
    series: str
    issue_number: str
    publisher: str | None
    store_date: str | None
    notes: str | None
    href: str | None
    parse_error: str | None = None


@dataclass
class LocgSource:
    source_url: str
    source_type: str
    name: str
    description: str | None
    items: list[LocgIssue]
    username: str | None = None
    list_id: int | None = None
    activity_id: int | None = None
    locg_comic_id: int | None = None


class LocgError(ValueError):
    pass


def _normalize_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned.startswith("http"):
        cleaned = f"{BASE_URL}/{cleaned.lstrip('/')}"
    parsed = urlparse(cleaned)
    if parsed.netloc and "leagueofcomicgeeks.com" not in parsed.netloc.lower():
        raise LocgError("URL must be on leagueofcomicgeeks.com")
    return cleaned.split("?")[0].rstrip("/")


def _parse_title_with_hash(title: str) -> tuple[str, str] | None:
    match = re.match(
        r"^(.*?)\s+#\s*(\d+(?:\.\d+)?(?:½)?)\s*$", title.strip(), re.IGNORECASE
    )
    if match:
        return match.group(1).strip(), match.group(2).replace("½", ".5")
    return None


def _parse_title_trailing_number(title: str) -> tuple[str, str] | None:
    match = re.match(r"^(.*?)\s+(\d+(?:\.\d+)?(?:½)?)\s*$", title.strip())
    if match:
        return match.group(1).strip(), match.group(2).replace("½", ".5")
    return None


def _resolve_series_and_number(
    title: str,
    reference_titles: list[str],
) -> tuple[str, str] | None:
    """Determine series name and issue number for a row.

    Prefers explicit ``Series #N`` formats. Story titles on collected edition
    pages (e.g. "The Tower, Part 1" or "The Tower, Finale") often don't carry
    the real issue number, so the linked issue reference (e.g. "Detective
    Comics #1058") takes precedence over a bare trailing number in the title.
    References are only trusted with an explicit ``#`` since their text can
    contain other digits (dates, page counts).
    """
    parsed = _parse_title_with_hash(title)
    if parsed:
        return parsed
    for reference in reference_titles:
        parsed = _parse_title_with_hash(reference)
        if parsed:
            return parsed
    return _parse_title_trailing_number(title)


def _session() -> requests.Session:
    session = requests.Session(impersonate="chrome120")
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _extract_activity_id(page_html: str) -> int:
    match = THREAD_ID_RE.search(page_html)
    if not match:
        raise LocgError(
            "Could not find community list data on the page. "
            "Check that the URL points to a public community list."
        )
    return int(match.group(1))


def _page_metadata(soup: BeautifulSoup) -> tuple[str, str | None]:
    title_tag = soup.find("meta", property="og:title")
    desc_tag = soup.find("meta", property="og:description")
    raw_title = title_tag.get("content", "").strip() if title_tag else ""
    description = desc_tag.get("content", "").strip() if desc_tag else None

    name = raw_title
    by_match = re.search(r"\s+by\s+", raw_title, re.IGNORECASE)
    if by_match:
        name = raw_title[: by_match.start()].strip()
    reviews_match = re.search(r"\s+reviews\s*$", name, re.IGNORECASE)
    if reviews_match:
        name = name[: reviews_match.start()].strip()
    if not name:
        name = "Imported LoCG list"
    return name, description or None


def _edition_publisher(soup: BeautifulSoup) -> str | None:
    header = soup.select_one(".header-intro")
    if not header:
        return None
    link = header.find("a", href=True)
    if link and link.get("href", "").startswith("/comics/"):
        return link.get_text(strip=True) or None
    return None


def _story_store_date(copy_el) -> str | None:
    if not copy_el:
        return None
    text = copy_el.get_text(" ", strip=True)
    match = re.match(
        r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{4})",
        text,
    )
    if match:
        return match.group(1)
    # The metadata line may lead with the linked issue (e.g.
    # "Detective Comics #1058 · Mar 2022 · Story"), so also look for a
    # date anywhere in the text. Avoid matching digits that belong to an
    # issue number like "#1058".
    match = re.search(
        r"([A-Za-z]{3,9}\.?\s+\d{1,2},?\s+(?:19|20)\d{2}"
        r"|[A-Za-z]{3,9}\.?\s+(?:19|20)\d{2}"
        r"|(?<![#\d])(?:19|20)\d{2}(?!\d))",
        text,
    )
    return match.group(1) if match else None


def _reference_titles(li) -> list[str]:
    """Collect linked issue references inside a row (e.g. "Detective Comics #1058")."""
    references: list[str] = []
    for link in li.select("a[href*='/comic/']"):
        text = link.get_text(" ", strip=True)
        if text and text not in references:
            references.append(text)
        img = link.find("img")
        if img:
            alt = (img.get("alt") or "").strip()
            if alt and alt not in references:
                references.append(alt)
    return references


def _issue_from_list_row(
    li,
    *,
    default_publisher: str | None = None,
) -> LocgIssue | None:
    locg_raw = li.get("data-comic")
    if not locg_raw:
        link = li.select_one("a[href*='/comic/']")
        if link and link.get("href"):
            parts = link["href"].strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "comic" and parts[1].isdigit():
                locg_raw = parts[1]
    if not locg_raw:
        return None

    title_el = li.select_one(".title") or li.select_one(".story-title")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    parsed = _resolve_series_and_number(title, _reference_titles(li))
    parse_error: str | None = None
    if parsed:
        series, issue_number = parsed
    else:
        series, issue_number = title, ""
        parse_error = f"Could not parse issue number from title: {title}"
    publisher_el = li.select_one(".publisher")
    publisher = (
        publisher_el.get_text(strip=True)
        if publisher_el
        else default_publisher
    )
    date_el = li.select_one(".date")
    store_date = date_el.get_text(strip=True) if date_el else None
    if not store_date:
        store_date = _story_store_date(li.select_one(".copy-really-small"))
    note_el = li.select_one(".comic-description")
    notes = note_el.get_text(" ", strip=True) if note_el else None
    href_el = li.select_one("a[href*='/comic/']")
    href_val = href_el.get("href") if href_el else None
    sort_raw = li.get("data-row")
    if sort_raw:
        sort_order = int(sort_raw)
    else:
        num_el = li.select_one(".story-num .number") or li.select_one(".story-num")
        sort_order = int(num_el.get_text(strip=True)) if num_el else None

    return LocgIssue(
        locg_id=int(locg_raw),
        sort_order=sort_order or 0,
        title=title,
        series=series,
        issue_number=issue_number,
        publisher=publisher or None,
        store_date=store_date,
        notes=notes or None,
        href=href_val,
        parse_error=parse_error,
    )


def _finalize_issue_order(items: list[LocgIssue]) -> list[LocgIssue]:
    if not items:
        return items
    if all(item.sort_order > 0 for item in items):
        items.sort(key=lambda item: item.sort_order)
    else:
        for index, item in enumerate(items, start=1):
            item.sort_order = index
    return items


def _parse_issue_rows(html: str, default_publisher: str | None = None) -> list[LocgIssue]:
    soup = BeautifulSoup(html, "lxml")
    rows = soup.find_all("li", class_="issue")
    items: list[LocgIssue] = []
    for li in rows:
        issue = _issue_from_list_row(li, default_publisher=default_publisher)
        if issue:
            if not issue.sort_order:
                issue.sort_order = len(items) + 1
            items.append(issue)
    return _finalize_issue_order(items)


def _parse_collected_edition_page(html: str) -> list[LocgIssue]:
    soup = BeautifulSoup(html, "lxml")
    default_publisher = _edition_publisher(soup)
    items: list[LocgIssue] = []

    legacy = soup.find("section", id="collected-issues-list")
    if legacy:
        for li in legacy.find_all("li"):
            issue = _issue_from_list_row(li, default_publisher=default_publisher)
            if issue:
                if not issue.sort_order:
                    issue.sort_order = len(items) + 1
                items.append(issue)
        if items:
            return _finalize_issue_order(items)

    stories = soup.find("section", id="stories")
    if stories:
        for el in stories.find_all("details", class_="story-item"):
            classes = el.get("class") or []
            if "story-item-overview" in classes:
                continue
            issue = _issue_from_list_row(el, default_publisher=default_publisher)
            if issue:
                if not issue.sort_order:
                    issue.sort_order = len(items) + 1
                items.append(issue)

    return _finalize_issue_order(items)


def fetch_community_list(url: str) -> LocgSource:
    source_url = _normalize_url(url)
    match = LIST_URL_RE.match(source_url)
    if not match:
        raise LocgError(
            "Invalid LoCG community list URL. Expected format: "
            "https://leagueofcomicgeeks.com/profile/{user}/lists/{id}/..."
        )
    username = match.group("username")
    list_id = int(match.group("list_id"))
    session = _session()

    page = session.get(source_url, timeout=60)
    if page.status_code == 403:
        raise LocgError(
            "League of Comic Geeks blocked the request. Try again later or from another network."
        )
    page.raise_for_status()

    activity_id = _extract_activity_id(page.text)
    name, description = _page_metadata(BeautifulSoup(page.text, "lxml"))

    thread = session.get(f"{BASE_URL}/member/load_thread/{activity_id}", timeout=60)
    thread.raise_for_status()
    payload = thread.json()
    if payload.get("type") != "success":
        raise LocgError("LoCG did not return community list contents")

    data = payload.get("data") or {}
    expected_path = data.get("path")
    if expected_path and f"/lists/{list_id}" not in expected_path:
        raise LocgError(
            "The LoCG list ID in the URL does not match the loaded community list."
        )

    items = _parse_issue_rows(payload.get("html") or "")
    if not items:
        raise LocgError("The community list contains no issues")

    if data.get("type") == "Community List" and data.get("comments", {}).get("model_id"):
        list_id = int(data["comments"]["model_id"])

    return LocgSource(
        source_url=source_url,
        source_type="community_list",
        name=name,
        description=description,
        items=items,
        username=username,
        list_id=list_id,
        activity_id=activity_id,
    )


def fetch_collected_edition(url: str) -> LocgSource:
    source_url = _normalize_url(url)
    match = COMIC_URL_RE.match(source_url)
    if not match:
        raise LocgError(
            "Invalid LoCG collected edition URL. Expected format: "
            "https://leagueofcomicgeeks.com/comic/{id}/{slug}"
        )

    locg_comic_id = int(match.group("comic_id"))
    session = _session()
    page = session.get(source_url, timeout=60)
    if page.status_code == 403:
        raise LocgError(
            "League of Comic Geeks blocked the request. Try again later or from another network."
        )
    page.raise_for_status()

    soup = BeautifulSoup(page.text, "lxml")
    name, description = _page_metadata(soup)
    items = _parse_collected_edition_page(page.text)
    if not items:
        raise LocgError(
            "No collected stories found on this page. "
            "Make sure the URL is for a trade paperback, omnibus, or other collected edition."
        )

    return LocgSource(
        source_url=source_url,
        source_type="collected_edition",
        name=name,
        description=description,
        items=items,
        locg_comic_id=locg_comic_id,
    )


def fetch_locg_source(url: str) -> LocgSource:
    normalized = _normalize_url(url)
    if LIST_URL_RE.match(normalized):
        return fetch_community_list(normalized)
    if COMIC_URL_RE.match(normalized):
        return fetch_collected_edition(normalized)
    raise LocgError(
        "Unsupported LoCG URL. Paste a community list URL "
        "(/profile/.../lists/...) or a collected edition URL (/comic/...)."
    )
