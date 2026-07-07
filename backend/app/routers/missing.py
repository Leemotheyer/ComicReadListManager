from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ReadList, ReadListItem
from app.schemas import (
    KapowarrSyncRequest,
    MissingActivityResponse,
    MissingIssuesPreviewResponse,
    SyncJobCreatedResponse,
)
from app.services.app_settings import SettingsStore
from app.services.kapowarr import kapowarr_client
from app.services.kapowarr_activity import fetch_activity
from app.services.kapowarr_preview import enrich_kapowarr_items
from app.services.sync_jobs import sync_job_manager

router = APIRouter(prefix="/api/missing", tags=["missing"])

_ACTIONABLE = frozenset(
    {"missing_file", "volume_not_in_library", "issue_not_found"}
)


def _collect_items(db: Session) -> tuple[list[ReadListItem], dict[int, tuple[int, str]]]:
    lists = (
        db.query(ReadList)
        .options(joinedload(ReadList.items))
        .order_by(ReadList.id)
        .all()
    )
    items: list[ReadListItem] = []
    meta: dict[int, tuple[int, str]] = {}
    for read_list in lists:
        for item in read_list.items:
            items.append(item)
            meta[item.id] = (read_list.id, read_list.name)
    return items, meta


@router.get("/preview", response_model=MissingIssuesPreviewResponse)
async def missing_preview(db: Session = Depends(get_db)):
    items, meta = _collect_items(db)
    if not items:
        return MissingIssuesPreviewResponse(
            items=[],
            kapowarr_url=SettingsStore.cached().kapowarr_url.rstrip("/"),
        )

    try:
        classified = await kapowarr_client.classify_list_items(items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for row in classified:
        list_id, list_name = meta.get(row["list_item_id"], (None, None))
        row["list_id"] = list_id
        row["list_name"] = list_name

    filtered = [i for i in classified if i["status"] in _ACTIONABLE]
    enriched = enrich_kapowarr_items(filtered)

    return MissingIssuesPreviewResponse(
        items=enriched,
        kapowarr_url=SettingsStore.cached().kapowarr_url.rstrip("/"),
    )


@router.get("/activity", response_model=MissingActivityResponse)
async def missing_activity(
    history_offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, meta = _collect_items(db)
    try:
        data = await fetch_activity(items, meta, history_offset=history_offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MissingActivityResponse(**data)


@router.post("/sync", response_model=SyncJobCreatedResponse)
async def missing_sync(payload: KapowarrSyncRequest, db: Session = Depends(get_db)):
    items, meta = _collect_items(db)
    try:
        job = await sync_job_manager.enqueue(
            source="missing",
            source_label="Missing issues",
            add_volume_ids=payload.add_volume_ids,
            download_issues=[r.model_dump() for r in payload.download_issues],
            items=items,
            meta=meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SyncJobCreatedResponse(job_id=job.id, status=job.status)


@router.get("/sync/jobs/{job_id}")
async def missing_sync_job(job_id: str):
    job = sync_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")
    return job.to_dict()
