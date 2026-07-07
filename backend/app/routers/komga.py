import httpx
from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    KomgaBookResult,
    KomgaSeriesResult,
    KomgaVolumeMatchRequest,
    KomgaVolumeMatchResponse,
)
from app.services.komga import komga_client

router = APIRouter(prefix="/api/komga", tags=["komga"])


def _handle_komga_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(
            status_code=502,
            detail=f"Komga API error: {exc.response.status_code}",
        )
    raise exc


@router.get("/series/search", response_model=list[KomgaSeriesResult])
async def search_series(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
):
    try:
        return await komga_client.search_series(q, limit=limit)
    except Exception as exc:
        raise _handle_komga_error(exc) from exc


@router.get("/series/{series_id}/books", response_model=list[KomgaBookResult])
async def series_books(series_id: str):
    try:
        return await komga_client.get_series_books(series_id)
    except Exception as exc:
        raise _handle_komga_error(exc) from exc


@router.post("/series/{series_id}/match-issues", response_model=KomgaVolumeMatchResponse)
async def match_volume_issues(series_id: str, payload: KomgaVolumeMatchRequest):
    try:
        matched, unmatched = await komga_client.match_issues_to_books(
            series_id,
            [item.model_dump() for item in payload.items],
        )
        return KomgaVolumeMatchResponse(mappings=matched, unmatched=unmatched)
    except Exception as exc:
        raise _handle_komga_error(exc) from exc
