import re

from fastapi import APIRouter, HTTPException, Query

from app.schemas import IssueResult, IssuesPage, VolumeSearchResult
from app.services.comicvine import comicvine_client

router = APIRouter(prefix="/api/comicvine", tags=["comicvine"])


def _parse_issue_id(raw: str) -> int:
    cleaned = raw.strip()
    match = re.match(r"^(?:4000-)?(\d+)$", cleaned, re.IGNORECASE)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid ComicVine issue ID format")
    return int(match.group(1))


@router.get("/volumes/search", response_model=list[VolumeSearchResult])
async def search_volumes(q: str = Query(min_length=1)):
    try:
        results = await comicvine_client.search_volumes(q)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return results


@router.get("/volumes/{volume_id}/issues", response_model=IssuesPage)
async def get_volume_issues(
    volume_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    try:
        page = await comicvine_client.get_issues(volume_id, offset=offset, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return IssuesPage(
        volume_id=page["volume_id"],
        issues=[IssueResult(**i) for i in page["issues"]],
        offset=page["offset"],
        limit=page["limit"],
        total=page["total"],
        has_more=page["has_more"],
    )


@router.get("/issues/{issue_id}", response_model=IssueResult)
async def get_issue(issue_id: str):
    parsed_id = _parse_issue_id(issue_id)
    try:
        issue = await comicvine_client.get_issue(parsed_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return IssueResult(
        id=issue["id"],
        issue_number=issue["issue_number"],
        name=issue.get("name"),
        cover_date=issue.get("cover_date"),
        volume_id=issue["volume_id"],
        volume_name=issue.get("volume_name"),
        volume_start_year=issue.get("volume_start_year"),
        publisher=issue.get("publisher"),
        image_url=issue.get("image_url"),
    )
