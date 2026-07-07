import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.kapowarr import kapowarr_client


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SyncStep:
    id: str
    action: str
    status: str = "pending"
    cv_volume_id: int | None = None
    cv_issue_id: int | None = None
    series: str | None = None
    issue_number: str | None = None
    list_id: int | None = None
    list_name: str | None = None
    message: str | None = None


@dataclass
class SyncJob:
    id: str
    source: str
    source_label: str
    status: str = "running"
    created_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None
    steps: list[SyncStep] = field(default_factory=list)
    results: list[dict] | None = None
    queue_count: int | None = None
    error: str | None = None
    list_items: list[Any] = field(default_factory=list, repr=False)

    def step_by_key(self, key: str) -> SyncStep | None:
        for step in self.steps:
            if step.id == key:
                return step
        return None

    def to_dict(self) -> dict:
        running = [s for s in self.steps if s.status == "running"]
        pending = [s for s in self.steps if s.status == "pending"]
        current = running[0] if running else (pending[0] if pending else None)
        return {
            "id": self.id,
            "source": self.source,
            "source_label": self.source_label,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "steps": [
                {
                    "id": s.id,
                    "action": s.action,
                    "status": s.status,
                    "cv_volume_id": s.cv_volume_id,
                    "cv_issue_id": s.cv_issue_id,
                    "series": s.series,
                    "issue_number": s.issue_number,
                    "list_id": s.list_id,
                    "list_name": s.list_name,
                    "message": s.message,
                }
                for s in self.steps
            ],
            "completed_count": sum(
                1 for s in self.steps if s.status in ("completed", "failed", "skipped")
            ),
            "total_count": len(self.steps),
            "current_message": current.message if current else None,
            "results": self.results,
            "queue_count": self.queue_count,
            "error": self.error,
        }


class _ListItemRef:
    def __init__(
        self,
        *,
        cv_volume_id: int,
        cv_issue_id: int,
        issue_number: str,
        series: str | None = None,
        list_id: int | None = None,
        list_name: str | None = None,
    ) -> None:
        self.cv_volume_id = cv_volume_id
        self.cv_issue_id = cv_issue_id
        self.issue_number = issue_number
        self.series = series
        self.list_id = list_id
        self.list_name = list_name


class JobSyncReporter:
    def __init__(self, job: SyncJob) -> None:
        self.job = job

    async def step_running(self, step_key: str, message: str | None = None) -> None:
        step = self.job.step_by_key(step_key)
        if not step:
            return
        step.status = "running"
        if message:
            step.message = message

    async def step_done(
        self, step_key: str, *, success: bool, message: str | None = None
    ) -> None:
        step = self.job.step_by_key(step_key)
        if not step:
            return
        step.status = "completed" if success else "failed"
        if message:
            step.message = message

    async def step_skipped(self, step_key: str, message: str | None = None) -> None:
        step = self.job.step_by_key(step_key)
        if not step:
            return
        step.status = "skipped"
        if message:
            step.message = message

    async def register_refresh_step(
        self, cv_volume_id: int, series: str | None, list_id: int | None, list_name: str | None
    ) -> str:
        step_key = f"refresh_volume:{cv_volume_id}"
        if self.job.step_by_key(step_key):
            return step_key
        insert_at = 0
        for i, step in enumerate(self.job.steps):
            if step.cv_volume_id == cv_volume_id and step.action == "add_volume":
                insert_at = i + 1
                break
        self.job.steps.insert(
            insert_at,
            SyncStep(
                id=step_key,
                action="refresh_volume",
                cv_volume_id=cv_volume_id,
                series=series,
                list_id=list_id,
                list_name=list_name,
            ),
        )
        return step_key


def _lookup_item(
    items: list[Any], meta: dict[int, tuple[int, str]], cv_volume_id: int, cv_issue_id: int | None
) -> tuple[str | None, str | None, int | None, str | None]:
    series = None
    issue_number = None
    list_id = None
    list_name = None
    for item in items:
        if item.cv_volume_id != cv_volume_id:
            continue
        if cv_issue_id is not None and item.cv_issue_id != cv_issue_id:
            continue
        series = getattr(item, "series", None)
        issue_number = getattr(item, "issue_number", None)
        list_id = getattr(item, "list_id", None)
        if list_id is not None:
            list_name = meta.get(list_id, (None, None))[1]
        break
    if series is None:
        for item in items:
            if item.cv_volume_id == cv_volume_id:
                series = getattr(item, "series", None)
                list_id = getattr(item, "list_id", None)
                if list_id is not None:
                    list_name = meta.get(list_id, (None, None))[1]
                break
    return series, issue_number, list_id, list_name


def _build_steps(
    add_volume_ids: list[int],
    download_issues: list[dict],
    items: list[Any],
    meta: dict[int, tuple[int, str]],
) -> list[SyncStep]:
    steps: list[SyncStep] = []
    seen_volumes: set[int] = set()

    for cv_vol_id in add_volume_ids:
        series, _, list_id, list_name = _lookup_item(items, meta, cv_vol_id, None)
        steps.append(
            SyncStep(
                id=f"add_volume:{cv_vol_id}",
                action="add_volume",
                cv_volume_id=cv_vol_id,
                series=series,
                list_id=list_id,
                list_name=list_name,
            )
        )
        seen_volumes.add(cv_vol_id)

    for ref in download_issues:
        cv_vol_id = ref["cv_volume_id"]
        cv_issue_id = ref["cv_issue_id"]
        series, issue_number, list_id, list_name = _lookup_item(
            items, meta, cv_vol_id, cv_issue_id
        )
        if not issue_number:
            issue_number = ref.get("issue_number")
        steps.append(
            SyncStep(
                id=f"auto_search:{cv_vol_id}:{cv_issue_id}",
                action="auto_search_issue",
                cv_volume_id=cv_vol_id,
                cv_issue_id=cv_issue_id,
                series=series,
                issue_number=issue_number,
                list_id=list_id,
                list_name=list_name,
            )
        )

    return steps


class SyncJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, SyncJob] = {}
        self._lock = asyncio.Lock()
        self._running_task: asyncio.Task | None = None

    def get_visible_jobs(self) -> list[dict]:
        now = _utcnow()
        visible: list[SyncJob] = []
        for job in self._jobs.values():
            if job.status == "running":
                visible.append(job)
            elif job.completed_at and (now - job.completed_at).total_seconds() < 600:
                visible.append(job)
        visible.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in visible]

    def get_job(self, job_id: str) -> SyncJob | None:
        return self._jobs.get(job_id)

    def has_running_job(self) -> bool:
        return any(j.status == "running" for j in self._jobs.values())

    def _prune_old(self) -> None:
        now = _utcnow()
        stale = [
            jid
            for jid, job in self._jobs.items()
            if job.status != "running"
            and job.completed_at
            and (now - job.completed_at).total_seconds() > 3600
        ]
        for jid in stale:
            del self._jobs[jid]

    def create_job(
        self,
        *,
        source: str,
        source_label: str,
        add_volume_ids: list[int],
        download_issues: list[dict],
        items: list[Any],
        meta: dict[int, tuple[int, str]],
    ) -> SyncJob:
        self._prune_old()
        job_id = str(uuid.uuid4())
        list_refs = [
            _ListItemRef(
                cv_volume_id=item.cv_volume_id,
                cv_issue_id=item.cv_issue_id,
                issue_number=item.issue_number,
                series=getattr(item, "series", None),
                list_id=getattr(item, "list_id", None),
                list_name=meta.get(getattr(item, "list_id", -1), (None, None))[1]
                if getattr(item, "list_id", None) is not None
                else None,
            )
            for item in items
        ]
        job = SyncJob(
            id=job_id,
            source=source,
            source_label=source_label,
            steps=_build_steps(add_volume_ids, download_issues, items, meta),
            list_items=list_refs,
        )
        self._jobs[job_id] = job
        return job

    async def run_job(
        self,
        job_id: str,
        *,
        add_volume_ids: list[int],
        download_issues: list[dict],
    ) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return

        reporter = JobSyncReporter(job)
        try:
            results, queue_count = await kapowarr_client.sync(
                add_volume_ids=add_volume_ids,
                download_issues=download_issues,
                list_items=job.list_items,
                reporter=reporter,
            )
            job.results = results
            job.queue_count = queue_count
            job.status = "completed"
            for step in job.steps:
                if step.status == "pending":
                    step.status = "skipped"
                    step.message = step.message or "Not reached"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            for step in job.steps:
                if step.status in ("pending", "running"):
                    step.status = "failed"
                    step.message = str(exc)
        finally:
            job.completed_at = _utcnow()

    async def enqueue(
        self,
        *,
        source: str,
        source_label: str,
        add_volume_ids: list[int],
        download_issues: list[dict],
        items: list[Any],
        meta: dict[int, tuple[int, str]],
    ) -> SyncJob:
        async with self._lock:
            job = self.create_job(
                source=source,
                source_label=source_label,
                add_volume_ids=add_volume_ids,
                download_issues=download_issues,
                items=items,
                meta=meta,
            )

            async def _run_when_ready() -> None:
                if self._running_task and not self._running_task.done():
                    await self._running_task
                self._running_task = asyncio.create_task(
                    self.run_job(
                        job.id,
                        add_volume_ids=add_volume_ids,
                        download_issues=download_issues,
                    )
                )
                await self._running_task

            asyncio.create_task(_run_when_ready())
            return job


sync_job_manager = SyncJobManager()
