import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ReadListItem
from app.routers.lists import _get_list_or_404, _to_response
from app.schemas import (
    LocgImportRequest,
    LocgImportResponse,
    LocgPreviewRequest,
    LocgPreviewResponse,
)
from app.services.locg import LocgError, LocgSource, fetch_locg_source
from app.services.locg_match import preview_locg_import

router = APIRouter(prefix="/api/lists", tags=["locg"])


@router.post("/{list_id}/locg/preview", response_model=LocgPreviewResponse)
async def locg_preview(
    list_id: int,
    payload: LocgPreviewRequest,
    db: Session = Depends(get_db),
):
    read_list = _get_list_or_404(db, list_id)
    try:
        locg_source = await asyncio.to_thread(fetch_locg_source, payload.url)
        existing_issue_ids = {item.cv_issue_id for item in read_list.items}
        preview = await preview_locg_import(
            locg_source,
            existing_issue_ids=existing_issue_ids,
        )
    except LocgError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not load League of Comic Geeks list: {exc}",
        ) from exc

    preview["existing_item_count"] = len(read_list.items)
    return LocgPreviewResponse(**preview)


@router.post("/{list_id}/locg/import", response_model=LocgImportResponse)
async def locg_import(
    list_id: int,
    payload: LocgImportRequest,
    db: Session = Depends(get_db),
):
    read_list = _get_list_or_404(db, list_id)
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items selected for import")

    if payload.update_list_meta:
        if payload.list_name:
            read_list.name = payload.list_name
        if payload.list_description is not None:
            read_list.description = payload.list_description or None

    existing_ids = {item.cv_issue_id for item in read_list.items}
    max_order = max((item.sort_order for item in read_list.items), default=-1)

    ordered_items = sorted(payload.items, key=lambda item: item.index)
    added = 0
    skipped = 0

    for item_data in ordered_items:
        if item_data.cv_issue_id in existing_ids:
            skipped += 1
            continue
        max_order += 1
        db.add(
            ReadListItem(
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
                notes=item_data.notes if payload.include_notes else None,
            )
        )
        existing_ids.add(item_data.cv_issue_id)
        added += 1

    if added or payload.update_list_meta:
        db.commit()

    return LocgImportResponse(
        added_count=added,
        skipped_count=skipped,
        read_list=_to_response(_get_list_or_404(db, list_id)),
    )
