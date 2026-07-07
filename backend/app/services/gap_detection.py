import json
import re
from typing import Any


def _parse_issue_number(value: str) -> float | None:
    if not value:
        return None
    cleaned = value.strip().replace("½", ".5")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _format_gap_number(n: float) -> str:
    if n == int(n):
        return str(int(n))
    return str(n)


def detect_volume_gaps(items: list[Any]) -> list[dict]:
    """Find missing issue numbers within each volume's collected run."""
    by_volume: dict[int, list[Any]] = {}
    for item in items:
        by_volume.setdefault(item.cv_volume_id, []).append(item)

    results: list[dict] = []
    for cv_volume_id, vol_items in by_volume.items():
        parsed: list[tuple[float, str]] = []
        for item in vol_items:
            num = _parse_issue_number(item.issue_number)
            if num is not None:
                parsed.append((num, item.issue_number))

        if len(parsed) < 2:
            continue

        parsed.sort(key=lambda x: x[0])
        numbers = [p[0] for p in parsed]
        low, high = int(numbers[0]), int(numbers[-1])
        if high - low < 1:
            continue

        present = {int(n) if n == int(n) else n for n in numbers}
        gaps: list[str] = []
        for candidate in range(low, high + 1):
            if candidate not in present:
                gaps.append(str(candidate))

        if not gaps:
            continue

        sample = vol_items[0]
        results.append(
            {
                "cv_volume_id": cv_volume_id,
                "series": sample.series,
                "volume_year": sample.volume_year,
                "collected_count": len(vol_items),
                "collected_numbers": sorted({p[1] for p in parsed}, key=lambda s: _parse_issue_number(s) or 0),
                "gaps": gaps,
            }
        )

    results.sort(key=lambda r: (r["series"].lower(), r["volume_year"] or 0))
    return results


def parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(t).strip() for t in data if str(t).strip()]
        except json.JSONDecodeError:
            pass
    return [t.strip() for t in re.split(r"[,;]", raw) if t.strip()]


def serialize_tags(tags: list[str]) -> str | None:
    cleaned = [t.strip() for t in tags if t.strip()]
    if not cleaned:
        return None
    return json.dumps(cleaned)
