from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ReadList, ReadListItem
from app.schemas import (
    AddItemsRequest,
    AddItemsResult,
    CopyListRequest,
    ExportResponse,
    GapDetectionResponse,
    KapowarrPreviewResponse,
    KapowarrSyncRequest,
    SyncJobCreatedResponse,
    KapowarrVolumeToAdd,
    KomgaPreviewResponse,
    KomgaPushRequest,
    KomgaPushResponse,
    ReadListCreate,
    ReadListItemResponse,
    ReadListItemUpdate,
    ReadListResponse,
    ReadListSummary,
    ReadListUpdate,
    ReorderRequest,
    VolumeGapInfo,
)
from app.services.cbl_export import export_filename, generate_cbl
from app.services.gap_detection import detect_volume_gaps, serialize_tags
from app.services.kapowarr import kapowarr_client
from app.services.kapowarr_preview import enrich_kapowarr_items
from app.services.sync_jobs import sync_job_manager
from app.services.komga import komga_client
from app.config import settings as env_settings

router = APIRouter(prefix="/api/lists", tags=["lists"])


def _get_list_or_404(db: Session, list_id: int) -> ReadList:
    read_list = (
        db.query(ReadList)
        .options(joinedload(ReadList.items))
        .filter(ReadList.id == list_id)
        .first()
    )
    if not read_list:
        raise HTTPException(status_code=404, detail="Read list not found")
    return read_list


def _to_response(read_list: ReadList) -> ReadListResponse:
    return ReadListResponse(
        id=read_list.id,
        name=read_list.name,
        description=read_list.description,
        created_at=read_list.created_at,
        updated_at=read_list.updated_at,
        last_exported_at=read_list.last_exported_at,
        item_count=len(read_list.items),
        items=[ReadListItemResponse.model_validate(i) for i in read_list.items],
    )


def _to_summary(
    read_list: ReadList, item_count: int, thumbnail_url: str | None = None
) -> ReadListSummary:
    return ReadListSummary(
        id=read_list.id,
        name=read_list.name,
        description=read_list.description,
        created_at=read_list.created_at,
        updated_at=read_list.updated_at,
        last_exported_at=read_list.last_exported_at,
        item_count=item_count,
        thumbnail_url=thumbnail_url,
    )


@router.get("", response_model=list[ReadListSummary])
def list_read_lists(db: Session = Depends(get_db)):
    lists = db.query(ReadList).order_by(ReadList.updated_at.desc()).all()
    summaries = []
    for rl in lists:
        count = db.query(ReadListItem).filter(ReadListItem.list_id == rl.id).count()
        first_item = (
            db.query(ReadListItem.cover_image_url)
            .filter(ReadListItem.list_id == rl.id)
            .order_by(ReadListItem.sort_order)
            .first()
        )
        thumbnail_url = first_item[0] if first_item else None
        summaries.append(_to_summary(rl, count, thumbnail_url))
    return summaries


@router.post("", response_model=ReadListResponse, status_code=201)
def create_read_list(payload: ReadListCreate, db: Session = Depends(get_db)):
    read_list = ReadList(
        name=payload.name,
        description=payload.description,
        tags=serialize_tags(payload.tags),
    )
    db.add(read_list)
    db.commit()
    db.refresh(read_list)
    return _to_response(read_list)


@router.get("/{list_id}", response_model=ReadListResponse)
def get_read_list(list_id: int, db: Session = Depends(get_db)):
    return _to_response(_get_list_or_404(db, list_id))


@router.patch("/{list_id}", response_model=ReadListResponse)
def update_read_list(
    list_id: int, payload: ReadListUpdate, db: Session = Depends(get_db)
):
    read_list = _get_list_or_404(db, list_id)
    if payload.name is not None:
        read_list.name = payload.name
    if payload.description is not None:
        read_list.description = payload.description
    if payload.tags is not None:
        read_list.tags = serialize_tags(payload.tags)
    db.commit()
    db.refresh(read_list)
    return _to_response(read_list)


@router.delete("/{list_id}", status_code=204)
def delete_read_list(list_id: int, db: Session = Depends(get_db)):
    read_list = _get_list_or_404(db, list_id)
    db.delete(read_list)
    db.commit()


@router.post("/{list_id}/items", response_model=AddItemsResult)
def add_items(
    list_id: int, payload: AddItemsRequest, db: Session = Depends(get_db)
):
    read_list = _get_list_or_404(db, list_id)
    existing_ids = {i.cv_issue_id for i in read_list.items}
    max_order = max((i.sort_order for i in read_list.items), default=-1)

    added = 0
    skipped = 0
    added_items: list[ReadListItem] = []
    for item_data in payload.items:
        if item_data.cv_issue_id in existing_ids:
            skipped += 1
            continue
        max_order += 1
        item = ReadListItem(
            list_id=list_id,
            sort_order=max_order,
            cv_volume_id=item_data.cv_volume_id,
            cv_issue_id=item_data.cv_issue_id,
            series=item_data.series,
            issue_number=item_data.issue_number,
            volume_year=item_data.volume_year,
            cover_year=item_data.cover_year,
            issue_title=item_data.issue_title,
            publisher=item_data.publisher,
            cover_image_url=item_data.cover_image_url,
            notes=item_data.notes,
        )
        db.add(item)
        existing_ids.add(item_data.cv_issue_id)
        added_items.append(item)
        added += 1

    if added:
        db.commit()
        for item in added_items:
            db.refresh(item)
        read_list = _get_list_or_404(db, list_id)

    return AddItemsResult(
        read_list=_to_response(read_list),
        added_count=added,
        skipped_count=skipped,
        added_items=[ReadListItemResponse.model_validate(i) for i in added_items],
    )


@router.patch("/{list_id}/items/reorder", response_model=ReadListResponse)
def reorder_items(
    list_id: int, payload: ReorderRequest, db: Session = Depends(get_db)
):
    read_list = _get_list_or_404(db, list_id)
    item_map = {i.id: i for i in read_list.items}
    if set(payload.item_ids) != set(item_map.keys()):
        raise HTTPException(status_code=400, detail="item_ids must match all list items")

    for order, item_id in enumerate(payload.item_ids):
        item_map[item_id].sort_order = order

    db.commit()
    return _to_response(_get_list_or_404(db, list_id))


@router.delete("/{list_id}/items/{item_id}", response_model=ReadListResponse)
def remove_item(list_id: int, item_id: int, db: Session = Depends(get_db)):
    read_list = _get_list_or_404(db, list_id)
    item = next((i for i in read_list.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()

    read_list = _get_list_or_404(db, list_id)
    for order, i in enumerate(sorted(read_list.items, key=lambda x: x.sort_order)):
        i.sort_order = order
    db.commit()
    return _to_response(_get_list_or_404(db, list_id))


@router.post("/{list_id}/copy", response_model=ReadListResponse, status_code=201)
def copy_read_list(
    list_id: int, payload: CopyListRequest, db: Session = Depends(get_db)
):
    source = _get_list_or_404(db, list_id)
    copy_name = payload.name or f"{source.name} (copy)"
    read_list = ReadList(
        name=copy_name,
        description=source.description,
        tags=source.tags,
    )
    db.add(read_list)
    db.flush()

    for item in sorted(source.items, key=lambda i: i.sort_order):
        db.add(
            ReadListItem(
                list_id=read_list.id,
                sort_order=item.sort_order,
                cv_volume_id=item.cv_volume_id,
                cv_issue_id=item.cv_issue_id,
                series=item.series,
                issue_number=item.issue_number,
                volume_year=item.volume_year,
                cover_year=item.cover_year,
                issue_title=item.issue_title,
                publisher=item.publisher,
                cover_image_url=item.cover_image_url,
                notes=item.notes,
            )
        )

    db.commit()
    return _to_response(_get_list_or_404(db, read_list.id))


@router.get("/{list_id}/gaps", response_model=GapDetectionResponse)
def list_gaps(list_id: int, db: Session = Depends(get_db)):
    read_list = _get_list_or_404(db, list_id)
    volumes = detect_volume_gaps(read_list.items)
    return GapDetectionResponse(volumes=[VolumeGapInfo(**v) for v in volumes])


@router.patch("/{list_id}/items/{item_id}", response_model=ReadListItemResponse)
def update_item(
    list_id: int,
    item_id: int,
    payload: ReadListItemUpdate,
    db: Session = Depends(get_db),
):
    read_list = _get_list_or_404(db, list_id)
    item = next((i for i in read_list.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if payload.notes is not None:
        item.notes = payload.notes or None
    db.commit()
    db.refresh(item)
    return ReadListItemResponse.model_validate(item)


@router.get("/{list_id}/export.cbl")
def export_cbl(list_id: int, db: Session = Depends(get_db)):
    read_list = _get_list_or_404(db, list_id)
    if not read_list.items:
        raise HTTPException(status_code=400, detail="Cannot export an empty list")

    xml_content = generate_cbl(read_list)
    filename = export_filename(read_list)
    export_path = env_settings.exports_dir / filename
    export_path.write_text(xml_content, encoding="utf-8")

    read_list.last_exported_at = datetime.now(timezone.utc)
    db.commit()

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{list_id}/export-info", response_model=ExportResponse)
def export_info(list_id: int, db: Session = Depends(get_db)):
    read_list = _get_list_or_404(db, list_id)
    filename = export_filename(read_list)
    path = str(env_settings.exports_dir / filename)
    return ExportResponse(
        filename=filename,
        path=path,
        exported_at=read_list.last_exported_at or datetime.now(timezone.utc),
    )


@router.post("/{list_id}/kapowarr/preview", response_model=KapowarrPreviewResponse)
async def kapowarr_preview(list_id: int, db: Session = Depends(get_db)):
    read_list = _get_list_or_404(db, list_id)
    if not read_list.items:
        raise HTTPException(status_code=400, detail="List has no items")

    try:
        items = await kapowarr_client.classify_list_items(read_list.items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    volumes_to_add = sorted(
        {
            i["cv_volume_id"]: KapowarrVolumeToAdd(
                cv_volume_id=i["cv_volume_id"],
                series=i["series"],
                volume_year=i.get("volume_year"),
            )
            for i in items
            if i["status"] == "volume_not_in_library"
        }.values(),
        key=lambda v: (v.series.lower(), v.volume_year or 0),
    )
    issues_to_download = [i for i in items if i["status"] == "missing_file"]

    enriched = enrich_kapowarr_items(items)
    issues_to_download_enriched = enrich_kapowarr_items(issues_to_download)

    return KapowarrPreviewResponse(
        items=enriched,
        volumes_to_add=volumes_to_add,
        issues_to_download=issues_to_download_enriched,
    )


@router.post("/{list_id}/kapowarr/sync", response_model=SyncJobCreatedResponse)
async def kapowarr_sync(
    list_id: int, payload: KapowarrSyncRequest, db: Session = Depends(get_db)
):
    read_list = _get_list_or_404(db, list_id)
    meta = {read_list.id: (read_list.id, read_list.name)}
    try:
        job = await sync_job_manager.enqueue(
            source=f"list:{list_id}",
            source_label=read_list.name,
            add_volume_ids=payload.add_volume_ids,
            download_issues=[r.model_dump() for r in payload.download_issues],
            items=read_list.items,
            meta=meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SyncJobCreatedResponse(job_id=job.id, status=job.status)


@router.post("/{list_id}/komga/preview", response_model=KomgaPreviewResponse)
async def komga_preview(list_id: int, db: Session = Depends(get_db)):
    read_list = _get_list_or_404(db, list_id)
    if not read_list.items:
        raise HTTPException(status_code=400, detail="List has no items")

    try:
        preview = await komga_client.preview(read_list)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Komga API error: {exc.response.status_code}",
        ) from exc

    return KomgaPreviewResponse(**preview)


@router.post("/{list_id}/komga/push", response_model=KomgaPushResponse)
async def komga_push(
    list_id: int,
    payload: KomgaPushRequest,
    db: Session = Depends(get_db),
):
    read_list = _get_list_or_404(db, list_id)
    if not read_list.items:
        raise HTTPException(status_code=400, detail="List has no items")

    try:
        manual_mappings = {
            m.list_item_id: m.komga_book_id for m in payload.manual_mappings
        }
        manual_labels = {
            m.list_item_id: m.label
            for m in payload.manual_mappings
            if m.label
        }
        result = await komga_client.push(
            read_list,
            allow_partial=payload.allow_partial,
            manual_mappings=manual_mappings,
            manual_labels=manual_labels,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Komga API error: {exc.response.status_code}",
        ) from exc

    read_list.last_exported_at = datetime.now(timezone.utc)
    db.commit()

    return KomgaPushResponse(**result)
