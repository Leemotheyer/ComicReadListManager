import re
from typing import Any

from app.models import ReadListItem
from app.services.app_settings import SettingsStore
from app.services.kapowarr import kapowarr_client
from app.services.kapowarr_urls import kapowarr_issue_url, kapowarr_volume_url
from app.services.sync_jobs import sync_job_manager


def _normalize_issue_number(value: str | None) -> str:
    if not value:
        return ""
    cleaned = str(value).strip().replace("½", ".5").lstrip("0")
    return cleaned or "0"


def _parse_issue_number_from_message(message: str | None) -> str | None:
    if not message:
        return None
    match = re.search(r"#(\S+)\s*$", message.strip())
    return match.group(1) if match else None


def _format_progress(entry: dict) -> str | None:
    size = entry.get("size")
    progress = entry.get("progress")
    if progress is None:
        return None
    if size == -1:
        return _format_bytes(progress)
    try:
        pct = float(progress) * 100
        return f"{pct:.1f}%"
    except (TypeError, ValueError):
        return str(progress)


def _format_bytes(value: Any) -> str | None:
    if value is None or value == -1:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num < 1024:
        return f"{num:.0f} B"
    if num < 1024**2:
        return f"{num / 1024:.1f} KB"
    if num < 1024**3:
        return f"{num / 1024**2:.1f} MB"
    return f"{num / 1024**3:.2f} GB"


def _format_speed(value: Any) -> str | None:
    if value is None:
        return None
    try:
        bps = float(value)
    except (TypeError, ValueError):
        return None
    if bps <= 0:
        return None
    mbps = bps / 1_000_000
    if mbps >= 1:
        return f"{mbps:.1f} MB/s"
    return f"{bps / 1000:.0f} KB/s"


def _build_list_lookups(
    items: list[ReadListItem], meta: dict[int, tuple[int, str]]
) -> tuple[dict[tuple[int, int], dict], dict[tuple[int, str], list[dict]]]:
    by_cv_issue: dict[tuple[int, int], dict] = {}
    by_volume_number: dict[tuple[int, str], list[dict]] = {}

    for item in items:
        list_name = meta.get(item.list_id, (None, None))[1]
        ctx = {
            "list_id": item.list_id,
            "list_name": list_name,
            "series": item.series,
            "issue_number": item.issue_number,
            "cv_issue_id": item.cv_issue_id,
        }
        by_cv_issue[(item.cv_volume_id, item.cv_issue_id)] = ctx
        num_key = (item.cv_volume_id, _normalize_issue_number(item.issue_number))
        by_volume_number.setdefault(num_key, []).append(ctx)

    return by_cv_issue, by_volume_number


def _build_sync_step_lookup() -> dict[tuple[int, int], dict]:
    lookup: dict[tuple[int, int], dict] = {}
    for job in sync_job_manager.get_visible_jobs():
        if job.get("status") != "running":
            continue
        for step in job.get("steps") or []:
            cv_vol = step.get("cv_volume_id")
            cv_issue = step.get("cv_issue_id")
            if cv_vol is None or cv_issue is None:
                continue
            if step.get("status") not in ("pending", "running"):
                continue
            lookup[(cv_vol, cv_issue)] = {
                "list_id": step.get("list_id"),
                "list_name": step.get("list_name"),
                "series": step.get("series"),
                "issue_number": step.get("issue_number"),
                "cv_issue_id": cv_issue,
            }
    return lookup


async def _fetch_volume_cache(volume_ids: set[int]) -> dict[int, dict]:
    cache: dict[int, dict] = {}
    for volume_id in volume_ids:
        try:
            detail = await kapowarr_client.get_volume(volume_id)
        except Exception:
            continue
        issues_by_id: dict[int, dict] = {}
        for issue in detail.get("issues") or []:
            issue_id = issue.get("id")
            if issue_id is not None:
                issues_by_id[int(issue_id)] = issue
        cache[volume_id] = {
            "comicvine_id": detail.get("comicvine_id"),
            "title": detail.get("title") or detail.get("volume_folder"),
            "issues_by_id": issues_by_id,
        }
    return cache


def _resolve_kapowarr_issue(
    volume_cache: dict[int, dict],
    kap_volume_id: int | None,
    kap_issue_id: int | None,
    message: str | None,
) -> tuple[int | None, int | None, str | None, str | None]:
    """Returns cv_volume_id, cv_issue_id, issue_number, volume_title."""
    if kap_volume_id is None:
        return None, None, _parse_issue_number_from_message(message), None

    vol = volume_cache.get(int(kap_volume_id))
    if not vol:
        return None, None, _parse_issue_number_from_message(message), None

    cv_volume_id = vol.get("comicvine_id")
    volume_title = vol.get("title")
    issue_number: str | None = None
    cv_issue_id: int | None = None

    if kap_issue_id is not None:
        kap_issue = vol.get("issues_by_id", {}).get(int(kap_issue_id))
        if kap_issue:
            issue_number = kap_issue.get("issue_number")
            cv_issue_id = kap_issue.get("comicvine_id")

    if not issue_number:
        issue_number = _parse_issue_number_from_message(message)

    return cv_volume_id, cv_issue_id, issue_number, volume_title


def _match_list_context(
    cv_volume_id: int | None,
    cv_issue_id: int | None,
    issue_number: str | None,
    by_cv_issue: dict[tuple[int, int], dict],
    by_volume_number: dict[tuple[int, str], list[dict]],
    sync_step_lookup: dict[tuple[int, int], dict],
) -> dict | None:
    if cv_volume_id is None:
        return None

    if cv_issue_id is not None:
        sync_ctx = sync_step_lookup.get((cv_volume_id, cv_issue_id))
        if sync_ctx:
            return sync_ctx
        ctx = by_cv_issue.get((cv_volume_id, cv_issue_id))
        if ctx:
            return ctx

    if issue_number:
        norm = _normalize_issue_number(issue_number)
        sync_matches = [
            ctx
            for (vol, iss), ctx in sync_step_lookup.items()
            if vol == cv_volume_id and _normalize_issue_number(ctx.get("issue_number")) == norm
        ]
        if len(sync_matches) == 1:
            return sync_matches[0]

        matches = by_volume_number.get((cv_volume_id, norm), [])
        if len(matches) == 1:
            return matches[0]

    return None


def _enrich_entry(
    *,
    kap_volume_id: int | None,
    kap_issue_id: int | None,
    message: str | None,
    title: str | None,
    volume_cache: dict[int, dict],
    by_cv_issue: dict[tuple[int, int], dict],
    by_volume_number: dict[tuple[int, str], list[dict]],
    sync_step_lookup: dict[tuple[int, int], dict],
    issue_number_hint: str | None = None,
) -> tuple[dict | None, str | None, str | None]:
    cv_volume_id, cv_issue_id, issue_number, volume_title = _resolve_kapowarr_issue(
        volume_cache, kap_volume_id, kap_issue_id, message
    )
    if not issue_number and issue_number_hint:
        issue_number = issue_number_hint

    list_ctx = _match_list_context(
        cv_volume_id,
        cv_issue_id,
        issue_number,
        by_cv_issue,
        by_volume_number,
        sync_step_lookup,
    )

    series = list_ctx["series"] if list_ctx else volume_title or title
    display_issue = list_ctx["issue_number"] if list_ctx else issue_number
    return list_ctx, series, display_issue


async def fetch_activity(
    items: list[ReadListItem],
    meta: dict[int, tuple[int, str]],
    *,
    history_offset: int = 0,
) -> dict:
    base_url = SettingsStore.cached().kapowarr_url.rstrip("/")
    by_cv_issue, by_volume_number = _build_list_lookups(items, meta)
    sync_step_lookup = _build_sync_step_lookup()

    download_queue_raw = await kapowarr_client.get_queue()
    system_tasks_raw = await kapowarr_client.get_tasks()
    download_history_raw = await kapowarr_client.get_download_history(history_offset)
    task_history_raw = await kapowarr_client.get_task_history(history_offset)

    volume_ids: set[int] = set()
    for entry in download_queue_raw + download_history_raw + system_tasks_raw:
        vol_id = entry.get("volume_id")
        if vol_id is not None:
            volume_ids.add(int(vol_id))

    volume_cache = await _fetch_volume_cache(volume_ids)

    download_queue = [
        _normalize_queue_entry(
            entry, base_url, volume_cache, by_cv_issue, by_volume_number, sync_step_lookup
        )
        for entry in download_queue_raw
    ]
    system_tasks = [
        _normalize_system_task(
            entry, base_url, volume_cache, by_cv_issue, by_volume_number, sync_step_lookup
        )
        for entry in system_tasks_raw
    ]
    download_history = [
        _normalize_download_history(
            entry, base_url, volume_cache, by_cv_issue, by_volume_number, sync_step_lookup
        )
        for entry in download_history_raw
    ]
    task_history = [_normalize_task_history(entry) for entry in task_history_raw]
    app_sync_jobs = sync_job_manager.get_visible_jobs()

    has_app_work = any(j["status"] == "running" for j in app_sync_jobs)

    return {
        "kapowarr_url": base_url,
        "download_queue": download_queue,
        "system_tasks": system_tasks,
        "download_history": download_history,
        "task_history": task_history,
        "app_sync_jobs": app_sync_jobs,
        "history_offset": history_offset,
        "has_active_work": bool(download_queue or system_tasks or has_app_work),
    }


def _normalize_queue_entry(
    entry: dict,
    base_url: str,
    volume_cache: dict[int, dict],
    by_cv_issue: dict[tuple[int, int], dict],
    by_volume_number: dict[tuple[int, str], list[dict]],
    sync_step_lookup: dict[tuple[int, int], dict],
) -> dict:
    volume_id = entry.get("volume_id")
    issue_id = entry.get("issue_id")
    list_ctx, series, issue_number = _enrich_entry(
        kap_volume_id=volume_id,
        kap_issue_id=issue_id,
        message=entry.get("title"),
        title=entry.get("title") or entry.get("web_title"),
        volume_cache=volume_cache,
        by_cv_issue=by_cv_issue,
        by_volume_number=by_volume_number,
        sync_step_lookup=sync_step_lookup,
    )

    issue_url = None
    volume_url = None
    if volume_id is not None and issue_id is not None:
        issue_url = kapowarr_issue_url(base_url, int(volume_id), int(issue_id))
    if volume_id is not None:
        volume_url = kapowarr_volume_url(base_url, int(volume_id))

    return {
        "id": entry.get("id"),
        "status": entry.get("status") or "unknown",
        "title": entry.get("title") or entry.get("web_title"),
        "series": series,
        "issue_number": issue_number,
        "list_id": list_ctx["list_id"] if list_ctx else None,
        "list_name": list_ctx["list_name"] if list_ctx else None,
        "volume_id": volume_id,
        "issue_id": issue_id,
        "source": entry.get("source_name") or entry.get("source"),
        "size": _format_bytes(entry.get("size")),
        "speed": _format_speed(entry.get("speed")),
        "progress": _format_progress(entry),
        "web_link": entry.get("web_link"),
        "kapowarr_issue_url": issue_url,
        "kapowarr_volume_url": volume_url,
    }


def _normalize_system_task(
    entry: dict,
    base_url: str,
    volume_cache: dict[int, dict],
    by_cv_issue: dict[tuple[int, int], dict],
    by_volume_number: dict[tuple[int, str], list[dict]],
    sync_step_lookup: dict[tuple[int, int], dict],
) -> dict:
    volume_id = entry.get("volume_id")
    issue_id = entry.get("issue_id")
    message = entry.get("message")
    list_ctx, series, issue_number = _enrich_entry(
        kap_volume_id=volume_id,
        kap_issue_id=issue_id,
        message=message,
        title=None,
        volume_cache=volume_cache,
        by_cv_issue=by_cv_issue,
        by_volume_number=by_volume_number,
        sync_step_lookup=sync_step_lookup,
    )

    issue_url = None
    volume_url = None
    if volume_id is not None and issue_id is not None:
        issue_url = kapowarr_issue_url(base_url, int(volume_id), int(issue_id))
    elif volume_id is not None:
        volume_url = kapowarr_volume_url(base_url, int(volume_id))

    return {
        "id": entry.get("id"),
        "action": entry.get("action") or "",
        "display_title": entry.get("display_title") or entry.get("action") or "Task",
        "status": entry.get("status") or "unknown",
        "message": message,
        "series": series,
        "issue_number": issue_number,
        "list_id": list_ctx["list_id"] if list_ctx else None,
        "list_name": list_ctx["list_name"] if list_ctx else None,
        "volume_id": volume_id,
        "issue_id": issue_id,
        "kapowarr_issue_url": issue_url,
        "kapowarr_volume_url": volume_url,
    }


def _normalize_download_history(
    entry: dict,
    base_url: str,
    volume_cache: dict[int, dict],
    by_cv_issue: dict[tuple[int, int], dict],
    by_volume_number: dict[tuple[int, str], list[dict]],
    sync_step_lookup: dict[tuple[int, int], dict],
) -> dict:
    volume_id = entry.get("volume_id")
    issue_id = entry.get("issue_id")
    list_ctx, series, issue_number = _enrich_entry(
        kap_volume_id=volume_id,
        kap_issue_id=issue_id,
        message=entry.get("file_title"),
        title=entry.get("file_title"),
        volume_cache=volume_cache,
        by_cv_issue=by_cv_issue,
        by_volume_number=by_volume_number,
        sync_step_lookup=sync_step_lookup,
        issue_number_hint=entry.get("file_title"),
    )

    issue_url = None
    volume_url = None
    if volume_id is not None and issue_id is not None:
        issue_url = kapowarr_issue_url(base_url, int(volume_id), int(issue_id))
    elif volume_id is not None:
        volume_url = kapowarr_volume_url(base_url, int(volume_id))

    return {
        "web_title": entry.get("web_title"),
        "web_sub_title": entry.get("web_sub_title"),
        "file_title": entry.get("file_title"),
        "series": series,
        "issue_number": issue_number,
        "list_id": list_ctx["list_id"] if list_ctx else None,
        "list_name": list_ctx["list_name"] if list_ctx else None,
        "volume_id": volume_id,
        "issue_id": issue_id,
        "source": entry.get("source"),
        "downloaded_at": entry.get("downloaded_at"),
        "success": entry.get("success"),
        "web_link": entry.get("web_link"),
        "kapowarr_issue_url": issue_url,
        "kapowarr_volume_url": volume_url,
    }


def _normalize_task_history(entry: dict) -> dict:
    return {
        "task_name": entry.get("task_name") or "",
        "display_title": entry.get("display_title") or entry.get("task_name") or "Task",
        "run_at": entry.get("run_at"),
    }
