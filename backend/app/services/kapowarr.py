import asyncio
import time
from typing import Any

import httpx

from app.services.app_settings import SettingsStore

AUTO_SEARCH_GAP_SECONDS = 2.0
DOWNLOAD_POLL_SECONDS = 3.0
NO_DOWNLOAD_GRACE_SECONDS = 5.0
DOWNLOAD_SETTLE_TIMEOUT_SECONDS = 3600.0
_TERMINAL_DOWNLOAD_STATUSES = frozenset({"failed", "canceled", "shutting down"})


def _normalize_issue_number(value: str | None) -> str:
    if not value:
        return ""
    cleaned = str(value).strip().lstrip("0")
    return cleaned or "0"


class KapowarrClient:
    def _config(self):
        s = SettingsStore.cached()
        return s.kapowarr_url.rstrip("/"), s.kapowarr_api_key, s.kapowarr_root_folder_id

    def _configured(self) -> bool:
        base_url, api_key, _ = self._config()
        return bool(base_url and api_key)

    @staticmethod
    def _parse_response(data: Any) -> Any:
        if isinstance(data, dict):
            error = data.get("error")
            if error:
                raise ValueError(str(error))
            if "result" in data:
                return data["result"]
        return data

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        if not self._configured():
            raise ValueError("Kapowarr is not configured (KAPOWARR_URL / KAPOWARR_API_KEY)")

        base_url, api_key, _ = self._config()
        url = f"{base_url}/api{path}"
        query = {"api_key": api_key}
        if params:
            query.update(params)

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.request(method, url, params=query, json=json)
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return None
            return self._parse_response(response.json())

    @staticmethod
    def _volume_id(volume: dict) -> int:
        vol_id = volume.get("id")
        if vol_id is None:
            raise ValueError("Unexpected Kapowarr volume response (missing id)")
        return vol_id

    @staticmethod
    def _find_issue(
        issues: list[dict], issue_number: str | None, cv_issue_id: int | None = None
    ) -> dict | None:
        if cv_issue_id is not None:
            for issue in issues:
                if issue.get("comicvine_id") == cv_issue_id:
                    return issue
        if issue_number:
            target = _normalize_issue_number(issue_number)
            for issue in issues:
                if _normalize_issue_number(str(issue.get("issue_number", ""))) == target:
                    return issue
        return None

    @staticmethod
    def _issues_resolved(issues: list[dict], needed: list[dict]) -> bool:
        if not issues:
            return False
        return all(
            KapowarrClient._find_issue(
                issues, ref.get("issue_number"), ref.get("cv_issue_id")
            )
            for ref in needed
        )

    async def find_volume_by_cv_id(self, cv_volume_id: int) -> dict | None:
        data = await self._request(
            "GET",
            "/volumes",
            params={"query": f"cv:4050-{cv_volume_id}"},
        )
        volumes = data if isinstance(data, list) else []
        for vol in volumes:
            if vol.get("comicvine_id") == cv_volume_id:
                return vol
        return volumes[0] if volumes else None

    async def get_volume(self, volume_id: int) -> dict:
        data = await self._request("GET", f"/volumes/{volume_id}")
        if not isinstance(data, dict):
            raise ValueError(f"Unexpected Kapowarr volume response for id {volume_id}")
        return data

    async def ensure_volume(self, cv_volume_id: int) -> dict:
        existing = await self.find_volume_by_cv_id(cv_volume_id)
        if existing:
            return existing
        return await self.add_volume(cv_volume_id)

    async def add_volume(self, cv_volume_id: int) -> dict:
        _, _, root_folder_id = self._config()
        data = await self._request(
            "POST",
            "/volumes",
            json={
                "comicvine_id": cv_volume_id,
                "root_folder_id": root_folder_id,
                "monitor": True,
                "monitoring_scheme": "none",
                "monitor_new_issues": False,
                "auto_search": False,
            },
        )
        if not isinstance(data, dict):
            raise ValueError("Unexpected Kapowarr response when adding volume")
        return data

    async def refresh_volume(self, kapowarr_volume_id: int) -> int:
        data = await self._request(
            "POST",
            "/system/tasks",
            json={"cmd": "refresh_and_scan", "volume_id": kapowarr_volume_id},
        )
        return self._task_id(data)

    async def _resolve_issue_metadata(
        self,
        kapowarr_volume_id: int,
        needed: list[dict],
        timeout: float = 120.0,
        poll_interval: float = 2.0,
    ) -> dict:
        deadline = time.monotonic() + timeout
        last_detail: dict = {}
        while time.monotonic() < deadline:
            last_detail = await self.get_volume(kapowarr_volume_id)
            if self._issues_resolved(last_detail.get("issues") or [], needed):
                return last_detail
            await asyncio.sleep(poll_interval)
        return last_detail

    async def wait_for_issues(
        self,
        kapowarr_volume_id: int,
        needed: list[dict],
        timeout: float = 120.0,
        poll_interval: float = 2.0,
    ) -> dict:
        return await self._resolve_issue_metadata(
            kapowarr_volume_id, needed, timeout, poll_interval
        )

    async def monitor_issue(self, issue_id: int, monitored: bool = True) -> None:
        await self._request(
            "PUT",
            f"/issues/{issue_id}",
            json={"monitored": monitored},
        )

    @staticmethod
    def _task_id(data: Any) -> int:
        if isinstance(data, dict) and "id" in data:
            return int(data["id"])
        raise ValueError("Unexpected Kapowarr task response (missing id)")

    async def get_tasks(self) -> list[dict]:
        data = await self._request("GET", "/system/tasks")
        return data if isinstance(data, list) else []

    async def wait_for_task(
        self,
        task_id: int,
        timeout: float = 600.0,
        poll_interval: float = 1.0,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            tasks = await self.get_tasks()
            if not any(t.get("id") == task_id for t in tasks):
                return
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"Kapowarr task {task_id} did not complete within {timeout}s")

    async def run_auto_search_issue(self, volume_id: int, issue_id: int) -> int:
        """Kapowarr built-in per-issue auto search (same as UI Auto Search on one issue)."""
        data = await self._request(
            "POST",
            "/system/tasks",
            json={
                "cmd": "auto_search_issue",
                "volume_id": volume_id,
                "issue_id": issue_id,
            },
        )
        return self._task_id(data)

    async def configure_volume_for_searches(self, kap_volume_id: int) -> None:
        """Kapowarr requires the volume to be monitored for auto_search_issue to run."""
        await self._request(
            "PUT",
            f"/volumes/{kap_volume_id}",
            json={
                "monitored": True,
                "monitoring_scheme": "none",
                "monitor_new_issues": False,
            },
        )

    async def _prepare_monitored_issues(
        self, detail: dict, refs: list[dict]
    ) -> dict[tuple[int, int], dict]:
        """Monitor only read-list issues; unmonitor everything else in the volume."""
        issues = detail.get("issues") or []
        target_by_ref: dict[tuple[int, int], dict] = {}

        for ref in refs:
            key = (ref["cv_volume_id"], ref["cv_issue_id"])
            matched = self._find_issue(
                issues, ref.get("issue_number"), ref["cv_issue_id"]
            )
            if matched:
                target_by_ref[key] = matched

        target_kap_ids = {m["id"] for m in target_by_ref.values()}

        for issue in issues:
            kap_issue_id = issue.get("id")
            if kap_issue_id is None:
                continue
            should_monitor = kap_issue_id in target_kap_ids
            if issue.get("monitored") != should_monitor:
                await self.monitor_issue(kap_issue_id, monitored=should_monitor)

        return target_by_ref

    @staticmethod
    def _downloads_for_issue(
        queue: list[dict], kap_volume_id: int, kap_issue_id: int
    ) -> list[dict]:
        return [
            entry
            for entry in queue
            if entry.get("volume_id") == kap_volume_id
            and entry.get("issue_id") == kap_issue_id
        ]

    async def _issue_has_file_by_id(
        self, kap_volume_id: int, kap_issue_id: int
    ) -> bool:
        detail = await self.get_volume(kap_volume_id)
        for issue in detail.get("issues") or []:
            if issue.get("id") == kap_issue_id:
                return self._issue_has_file(issue)
        return False

    async def wait_for_volume_queue_idle(
        self,
        kap_volume_id: int,
        timeout: float = DOWNLOAD_SETTLE_TIMEOUT_SECONDS,
        poll_interval: float = DOWNLOAD_POLL_SECONDS,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            queue = await self.get_queue()
            if not any(entry.get("volume_id") == kap_volume_id for entry in queue):
                return
            await asyncio.sleep(poll_interval)
        raise TimeoutError(
            f"Timed out waiting for Kapowarr downloads on volume {kap_volume_id}"
        )

    async def wait_after_auto_search(
        self,
        kap_volume_id: int,
        kap_issue_id: int,
        timeout: float = DOWNLOAD_SETTLE_TIMEOUT_SECONDS,
    ) -> None:
        """Wait for a queued download to finish, or move on if none was grabbed."""
        deadline = time.monotonic() + timeout
        no_download_deadline = time.monotonic() + NO_DOWNLOAD_GRACE_SECONDS
        saw_download = False

        while time.monotonic() < deadline:
            if await self._issue_has_file_by_id(kap_volume_id, kap_issue_id):
                return

            queue = await self.get_queue()
            active = self._downloads_for_issue(queue, kap_volume_id, kap_issue_id)

            if active:
                saw_download = True
                if all(
                    entry.get("status") in _TERMINAL_DOWNLOAD_STATUSES
                    for entry in active
                ):
                    return
            elif saw_download:
                return
            elif time.monotonic() >= no_download_deadline:
                return

            await asyncio.sleep(DOWNLOAD_POLL_SECONDS)

        raise TimeoutError(
            f"Timed out waiting for Kapowarr issue {kap_issue_id} to settle"
        )

    async def get_queue(self) -> list:
        data = await self._request("GET", "/activity/queue")
        return data if isinstance(data, list) else []

    async def get_download_history(self, offset: int = 0) -> list[dict]:
        data = await self._request(
            "GET", "/activity/history", params={"offset": offset}
        )
        return data if isinstance(data, list) else []

    async def get_task_history(self, offset: int = 0) -> list[dict]:
        data = await self._request(
            "GET", "/system/tasks/history", params={"offset": offset}
        )
        return data if isinstance(data, list) else []

    @staticmethod
    def _issue_has_file(issue: dict) -> bool:
        return bool(
            issue.get("files")
            or issue.get("file")
            or str(issue.get("status", "")).lower() == "downloaded"
        )

    async def _resolve_volume(self, cv_volume_id: int, cache: dict[int, dict]) -> dict | None:
        if cv_volume_id in cache:
            return cache[cv_volume_id]
        vol = await self.find_volume_by_cv_id(cv_volume_id)
        if vol:
            cache[cv_volume_id] = vol
        return vol

    @staticmethod
    def _issue_sort_key(issue_number: str | None) -> tuple:
        if not issue_number:
            return (1, 0.0, "")
        cleaned = issue_number.strip().replace("½", ".5")
        try:
            return (0, float(cleaned), issue_number)
        except ValueError:
            return (1, 0.0, issue_number.lower())

    async def _ensure_issue_monitored(self, kap_issue_id: int) -> None:
        await self.monitor_issue(kap_issue_id, monitored=True)

    async def queue_downloads_for_volume(
        self,
        cv_volume_id: int,
        refs: list[dict],
        volume_cache: dict[int, dict],
        search_queue_idx: list[int] | None = None,
        reporter: Any | None = None,
    ) -> list[dict]:
        results: list[dict] = []
        kap_vol = await self._resolve_volume(cv_volume_id, volume_cache)
        if not kap_vol:
            for ref in refs:
                step_key = f"auto_search:{cv_volume_id}:{ref['cv_issue_id']}"
                msg = f"Volume {cv_volume_id} not in Kapowarr"
                if reporter:
                    await reporter.step_done(step_key, success=False, message=msg)
                results.append(
                    {
                        "cv_volume_id": cv_volume_id,
                        "cv_issue_id": ref["cv_issue_id"],
                        "action": "auto_search_issue",
                        "success": False,
                        "message": msg,
                    }
                )
            return results

        kap_vol_id = self._volume_id(kap_vol)
        detail = await self._resolve_issue_metadata(kap_vol_id, refs, timeout=60.0)
        await self.configure_volume_for_searches(kap_vol_id)
        sorted_refs = sorted(
            refs,
            key=lambda r: self._issue_sort_key(r.get("issue_number")),
        )

        try:
            matched_by_ref = await self._prepare_monitored_issues(detail, sorted_refs)
        except Exception as exc:
            for ref in sorted_refs:
                step_key = f"auto_search:{cv_volume_id}:{ref['cv_issue_id']}"
                if reporter:
                    await reporter.step_done(step_key, success=False, message=str(exc))
                results.append(
                    {
                        "cv_volume_id": cv_volume_id,
                        "cv_issue_id": ref["cv_issue_id"],
                        "action": "auto_search_issue",
                        "success": False,
                        "message": str(exc),
                    }
                )
            return results

        for ref in sorted_refs:
            issue_number = ref.get("issue_number")
            cv_issue_id = ref["cv_issue_id"]
            label = f"#{issue_number}" if issue_number else str(cv_issue_id)
            key = (cv_volume_id, cv_issue_id)
            step_key = f"auto_search:{cv_volume_id}:{cv_issue_id}"
            matched = matched_by_ref.get(key)

            if not matched:
                detail = await self.get_volume(kap_vol_id)
                matched = self._find_issue(
                    detail.get("issues") or [],
                    issue_number,
                    cv_issue_id,
                )

            if not matched:
                if reporter:
                    await reporter.step_done(
                        step_key,
                        success=False,
                        message=f"Issue {label} not found in volume metadata",
                    )
                results.append(
                    {
                        "cv_volume_id": cv_volume_id,
                        "cv_issue_id": cv_issue_id,
                        "action": "auto_search_issue",
                        "success": False,
                        "message": f"Issue {label} not found in volume metadata",
                    }
                )
                continue

            has_file = self._issue_has_file(matched)
            if has_file:
                if reporter:
                    await reporter.step_skipped(
                        step_key, message=f"Issue {label} already downloaded"
                    )
                results.append(
                    {
                        "cv_volume_id": cv_volume_id,
                        "cv_issue_id": cv_issue_id,
                        "action": "auto_search_issue",
                        "success": True,
                        "message": f"Issue {label} already downloaded",
                    }
                )
                continue

            try:
                if reporter:
                    await reporter.step_running(
                        step_key, message=f"Searching for issue {label}…"
                    )
                if search_queue_idx is not None and search_queue_idx[0] > 0:
                    await self.wait_for_volume_queue_idle(kap_vol_id)
                    await asyncio.sleep(AUTO_SEARCH_GAP_SECONDS)
                await self._ensure_issue_monitored(matched["id"])
                task_id = await self.run_auto_search_issue(kap_vol_id, matched["id"])
                if reporter:
                    await reporter.step_running(
                        step_key, message=f"Waiting for Kapowarr search on {label}…"
                    )
                await self.wait_for_task(task_id, timeout=300.0)
                if reporter:
                    await reporter.step_running(
                        step_key, message=f"Waiting for download on {label}…"
                    )
                await self.wait_after_auto_search(kap_vol_id, matched["id"])
                if search_queue_idx is not None:
                    search_queue_idx[0] += 1
                if reporter:
                    await reporter.step_done(
                        step_key,
                        success=True,
                        message=f"Completed auto search for issue {label}",
                    )
                results.append(
                    {
                        "cv_volume_id": cv_volume_id,
                        "cv_issue_id": cv_issue_id,
                        "action": "auto_search_issue",
                        "success": True,
                        "message": f"Completed auto search for issue {label}",
                    }
                )
            except Exception as exc:
                if reporter:
                    await reporter.step_done(step_key, success=False, message=str(exc))
                results.append(
                    {
                        "cv_volume_id": cv_volume_id,
                        "cv_issue_id": cv_issue_id,
                        "action": "auto_search_issue",
                        "success": False,
                        "message": str(exc),
                    }
                )

        return results

    @staticmethod
    def _series_for_volume(list_items: list | None, cv_volume_id: int) -> tuple[str | None, int | None, str | None]:
        if not list_items:
            return None, None, None
        for item in list_items:
            if item.cv_volume_id == cv_volume_id:
                series = getattr(item, "series", None)
                list_id = getattr(item, "list_id", None)
                list_name = getattr(item, "list_name", None)
                return series, list_id, list_name
        return None, None, None

    async def classify_list_items(self, items: list) -> list[dict]:
        volume_cache: dict[int, dict | None] = {}
        detail_cache: dict[int, dict] = {}
        results = []

        for item in items:
            cv_vol = item.cv_volume_id
            cv_issue = item.cv_issue_id

            if cv_vol not in volume_cache:
                volume_cache[cv_vol] = await self.find_volume_by_cv_id(cv_vol)

            kap_vol = volume_cache[cv_vol]
            if not kap_vol:
                results.append(
                    {
                        "list_item_id": item.id,
                        "cv_volume_id": cv_vol,
                        "cv_issue_id": cv_issue,
                        "series": item.series,
                        "issue_number": item.issue_number,
                        "volume_year": item.volume_year,
                        "status": "volume_not_in_library",
                        "kapowarr_volume_id": None,
                        "kapowarr_issue_id": None,
                        "message": "Volume not in Kapowarr library",
                    }
                )
                continue

            kap_vol_id = self._volume_id(kap_vol)
            if kap_vol_id not in detail_cache:
                detail_cache[kap_vol_id] = await self.get_volume(kap_vol_id)

            detail = detail_cache[kap_vol_id]
            issues = detail.get("issues") or []
            matched = self._find_issue(issues, item.issue_number, cv_issue)

            if not matched:
                if not issues:
                    message = (
                        "Issue metadata not loaded yet — add the volume and sync "
                        "to refresh and download"
                    )
                else:
                    message = f"Issue #{item.issue_number} not found in Kapowarr metadata"
                results.append(
                    {
                        "list_item_id": item.id,
                        "cv_volume_id": cv_vol,
                        "cv_issue_id": cv_issue,
                        "series": item.series,
                        "issue_number": item.issue_number,
                        "volume_year": item.volume_year,
                        "status": "issue_not_found",
                        "kapowarr_volume_id": kap_vol_id,
                        "kapowarr_issue_id": None,
                        "message": message,
                    }
                )
                continue

            has_file = self._issue_has_file(matched)
            if has_file:
                status = "in_library"
                message = "Issue already downloaded"
            else:
                status = "missing_file"
                message = f"Issue #{item.issue_number} missing — can trigger download"

            results.append(
                {
                    "list_item_id": item.id,
                    "cv_volume_id": cv_vol,
                    "cv_issue_id": cv_issue,
                    "series": item.series,
                    "issue_number": item.issue_number,
                    "volume_year": item.volume_year,
                    "status": status,
                    "kapowarr_volume_id": kap_vol_id,
                    "kapowarr_issue_id": matched["id"],
                    "message": message,
                }
            )

        return results

    async def sync(
        self,
        add_volume_ids: list[int],
        download_issues: list[dict],
        list_items: list | None = None,
        reporter: Any | None = None,
    ) -> tuple[list[dict], int | None]:
        results: list[dict] = []
        volume_cache: dict[int, dict] = {}

        download_map: dict[tuple[int, int], dict] = {
            (d["cv_volume_id"], d["cv_issue_id"]): d for d in download_issues
        }
        if list_items:
            for item in list_items:
                if item.cv_volume_id in add_volume_ids:
                    key = (item.cv_volume_id, item.cv_issue_id)
                    if key not in download_map:
                        download_map[key] = {
                            "cv_volume_id": item.cv_volume_id,
                            "cv_issue_id": item.cv_issue_id,
                            "issue_number": item.issue_number,
                        }

        for cv_vol_id in add_volume_ids:
            step_key = f"add_volume:{cv_vol_id}"
            if reporter:
                await reporter.step_running(step_key, "Adding volume to Kapowarr…")
            try:
                volume = await self.ensure_volume(cv_vol_id)
                volume_cache[cv_vol_id] = volume
                kap_id = self._volume_id(volume)
                msg = f"Volume ready in Kapowarr (id {kap_id})"
                if reporter:
                    await reporter.step_done(step_key, success=True, message=msg)
                results.append(
                    {
                        "cv_volume_id": cv_vol_id,
                        "cv_issue_id": None,
                        "action": "add_volume",
                        "success": True,
                        "message": msg,
                    }
                )
            except Exception as exc:
                if reporter:
                    await reporter.step_done(step_key, success=False, message=str(exc))
                results.append(
                    {
                        "cv_volume_id": cv_vol_id,
                        "cv_issue_id": None,
                        "action": "add_volume",
                        "success": False,
                        "message": str(exc),
                    }
                )

        refs_by_volume: dict[int, list[dict]] = {}
        for ref in download_map.values():
            refs_by_volume.setdefault(ref["cv_volume_id"], []).append(ref)

        for cv_vol_id, needed in refs_by_volume.items():
            kap_vol = await self._resolve_volume(cv_vol_id, volume_cache)
            if not kap_vol:
                continue

            kap_vol_id = self._volume_id(kap_vol)
            detail = await self.get_volume(kap_vol_id)
            if self._issues_resolved(detail.get("issues") or [], needed):
                continue

            series, list_id, list_name = self._series_for_volume(list_items, cv_vol_id)
            refresh_key = f"refresh_volume:{cv_vol_id}"
            if reporter:
                refresh_key = await reporter.register_refresh_step(
                    cv_vol_id, series, list_id, list_name
                )
                await reporter.step_running(
                    refresh_key, "Refreshing issue metadata from ComicVine…"
                )
            try:
                refresh_task_id = await self.refresh_volume(kap_vol_id)
                results.append(
                    {
                        "cv_volume_id": cv_vol_id,
                        "cv_issue_id": None,
                        "action": "refresh_volume",
                        "success": True,
                        "message": "Refreshing issue metadata from ComicVine",
                    }
                )
                await self.wait_for_task(refresh_task_id, timeout=180.0)
                await self.wait_for_issues(kap_vol_id, needed, timeout=180.0)
                if reporter:
                    await reporter.step_done(
                        refresh_key,
                        success=True,
                        message="Issue metadata refreshed",
                    )
            except Exception as exc:
                if reporter:
                    await reporter.step_done(refresh_key, success=False, message=str(exc))
                results.append(
                    {
                        "cv_volume_id": cv_vol_id,
                        "cv_issue_id": None,
                        "action": "refresh_volume",
                        "success": False,
                        "message": str(exc),
                    }
                )

        downloads_by_volume: dict[int, list[dict]] = {}
        for ref in download_map.values():
            downloads_by_volume.setdefault(ref["cv_volume_id"], []).append(ref)

        search_queue_idx = [0]
        for cv_vol_id, refs in downloads_by_volume.items():
            batch_results = await self.queue_downloads_for_volume(
                cv_vol_id, refs, volume_cache, search_queue_idx, reporter
            )
            results.extend(batch_results)

        queue = await self.get_queue()
        return results, len(queue)


kapowarr_client = KapowarrClient()
