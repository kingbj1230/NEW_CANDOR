import json
from datetime import datetime, timezone


def parse_env_bool(raw, default=False):
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def parse_env_int(raw, default):
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def now_iso_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def cache_clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def normalize_report_type(value, *, default, choices):
    raw = str(value or "").strip() or str(default or "").strip()
    if raw not in set(choices or []):
        raise ValueError(f"report_type must be one of: {', '.join(sorted(choices or []))}")
    return raw


def normalize_report_status_for_admin(value, *, default, allowed):
    raw = str(value or "").strip() or str(default or "").strip()
    if raw not in set(allowed or []):
        raise ValueError(f"status must be one of: {', '.join(sorted(allowed or []))}")
    return raw


def is_status_in_markers(value, markers):
    normalized = str(value or "").replace(" ", "").lower()
    return normalized in set(markers or [])


def pagination_params(limit_raw, offset_raw, *, default_limit=None, max_limit=500):
    limit_text = str(limit_raw or "").strip()
    offset_text = str(offset_raw or "").strip()

    offset = 0
    if offset_text:
        try:
            offset = max(0, int(offset_text))
        except (TypeError, ValueError):
            offset = 0

    if not limit_text:
        return default_limit, offset

    try:
        parsed_limit = int(limit_text)
    except (TypeError, ValueError):
        return default_limit, offset
    parsed_limit = max(1, parsed_limit)
    if max_limit > 0:
        parsed_limit = min(parsed_limit, max_limit)
    return parsed_limit, offset


def slice_rows(rows, limit, offset):
    total = len(rows or [])
    if limit is None:
        return rows, total
    sliced = (rows or [])[offset: offset + limit]
    return sliced, total
