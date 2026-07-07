from app.services.app_settings import SettingsStore
from app.services.kapowarr_urls import kapowarr_issue_url


def enrich_kapowarr_items(items: list[dict]) -> list[dict]:
    base_url = SettingsStore.cached().kapowarr_url.rstrip("/")
    enriched: list[dict] = []
    for item in items:
        row = dict(item)
        vol_id = row.get("kapowarr_volume_id")
        issue_id = row.get("kapowarr_issue_id")
        if vol_id and issue_id and base_url:
            row["kapowarr_issue_url"] = kapowarr_issue_url(base_url, vol_id, issue_id)
        else:
            row["kapowarr_issue_url"] = None
        enriched.append(row)
    return enriched
