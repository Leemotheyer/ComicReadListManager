import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import AppSettings, ReadList, ReadListItem
from app.services.app_settings import SettingsStore


BACKUP_VERSION = 1


def export_backup(db: Session) -> dict[str, Any]:
    settings_row = db.get(AppSettings, 1)
    lists = (
        db.query(ReadList)
        .options(joinedload(ReadList.items))
        .order_by(ReadList.id)
        .all()
    )

    settings_data = None
    if settings_row:
        settings_data = {
            "comicvine_api_key": settings_row.comicvine_api_key,
            "kapowarr_url": settings_row.kapowarr_url,
            "kapowarr_api_key": settings_row.kapowarr_api_key,
            "kapowarr_root_folder_id": settings_row.kapowarr_root_folder_id,
            "komga_url": settings_row.komga_url,
            "komga_api_key": settings_row.komga_api_key,
        }

    return {
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "settings": settings_data,
        "lists": [
            {
                "name": rl.name,
                "description": rl.description,
                "tags": rl.tags,
                "items": [
                    {
                        "sort_order": item.sort_order,
                        "cv_volume_id": item.cv_volume_id,
                        "cv_issue_id": item.cv_issue_id,
                        "series": item.series,
                        "issue_number": item.issue_number,
                        "volume_year": item.volume_year,
                        "cover_year": item.cover_year,
                        "issue_title": item.issue_title,
                        "publisher": item.publisher,
                        "cover_image_url": item.cover_image_url,
                        "notes": item.notes,
                    }
                    for item in sorted(rl.items, key=lambda i: i.sort_order)
                ],
            }
            for rl in lists
        ],
    }


def import_backup(db: Session, payload: dict[str, Any], *, replace: bool = False) -> dict[str, int]:
    if payload.get("version") != BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version: {payload.get('version')}")

    if replace:
        db.query(ReadListItem).delete()
        db.query(ReadList).delete()

    settings_data = payload.get("settings")
    if settings_data and isinstance(settings_data, dict):
        row = SettingsStore.get(db)
        for key in (
            "comicvine_api_key",
            "kapowarr_url",
            "kapowarr_api_key",
            "kapowarr_root_folder_id",
            "komga_url",
            "komga_api_key",
        ):
            if key in settings_data and settings_data[key] is not None:
                setattr(row, key, settings_data[key])
        db.add(row)

    lists_imported = 0
    items_imported = 0
    for list_data in payload.get("lists") or []:
        if not isinstance(list_data, dict) or not list_data.get("name"):
            continue
        read_list = ReadList(
            name=list_data["name"],
            description=list_data.get("description"),
            tags=list_data.get("tags"),
        )
        db.add(read_list)
        db.flush()

        for item_data in list_data.get("items") or []:
            if not isinstance(item_data, dict):
                continue
            item = ReadListItem(
                list_id=read_list.id,
                sort_order=item_data.get("sort_order", items_imported),
                cv_volume_id=item_data["cv_volume_id"],
                cv_issue_id=item_data["cv_issue_id"],
                series=item_data["series"],
                issue_number=item_data["issue_number"],
                volume_year=item_data.get("volume_year"),
                cover_year=item_data.get("cover_year"),
                issue_title=item_data.get("issue_title"),
                publisher=item_data.get("publisher"),
                cover_image_url=item_data.get("cover_image_url"),
                notes=item_data.get("notes"),
            )
            db.add(item)
            items_imported += 1
        lists_imported += 1

    db.commit()
    SettingsStore.invalidate()
    return {"lists_imported": lists_imported, "items_imported": items_imported}
