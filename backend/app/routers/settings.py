from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import SettingsResponse, SettingsUpdate
from app.services.app_settings import SettingsStore

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_response(row) -> SettingsResponse:
    return SettingsResponse(
        kapowarr_url=row.kapowarr_url,
        kapowarr_root_folder_id=row.kapowarr_root_folder_id,
        komga_url=row.komga_url,
        comicvine_api_key_set=bool(row.comicvine_api_key),
        kapowarr_api_key_set=bool(row.kapowarr_api_key),
        komga_api_key_set=bool(row.komga_api_key),
        updated_at=row.updated_at,
    )


@router.get("", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    row = SettingsStore.get(db)
    return _to_response(row)


@router.put("", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    updates = {}
    if payload.kapowarr_url is not None:
        updates["kapowarr_url"] = payload.kapowarr_url.rstrip("/")
    if payload.kapowarr_root_folder_id is not None:
        updates["kapowarr_root_folder_id"] = payload.kapowarr_root_folder_id
    if payload.comicvine_api_key is not None and payload.comicvine_api_key.strip():
        updates["comicvine_api_key"] = payload.comicvine_api_key.strip()
    if payload.kapowarr_api_key is not None and payload.kapowarr_api_key.strip():
        updates["kapowarr_api_key"] = payload.kapowarr_api_key.strip()
    if payload.komga_url is not None:
        updates["komga_url"] = payload.komga_url.rstrip("/")
    if payload.komga_api_key is not None and payload.komga_api_key.strip():
        updates["komga_api_key"] = payload.komga_api_key.strip()

    row = SettingsStore.update(db, **updates)
    return _to_response(row)
