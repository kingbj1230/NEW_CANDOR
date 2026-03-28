def clear_admin_session_cache(session_obj, session_keys):
    for key in session_keys or []:
        session_obj.pop(key, None)


def normalize_session_admin_flag(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return None


def normalize_session_admin_checked_at(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def normalize_session_admin_uid(value):
    text = str(value or "").strip()
    return text or None


def set_admin_session_cache(
    session_obj,
    session_keys,
    *,
    uid,
    is_admin,
    checked_at=None,
    now_ts_fn=None,
):
    uid_text = normalize_session_admin_uid(uid)
    if not uid_text:
        clear_admin_session_cache(session_obj, session_keys)
        return
    normalized_checked_at = normalize_session_admin_checked_at(checked_at)
    if normalized_checked_at is None:
        normalized_checked_at = int(now_ts_fn()) if callable(now_ts_fn) else 0
    session_obj["is_admin"] = bool(is_admin)
    session_obj["is_admin_checked_at"] = normalized_checked_at
    session_obj["is_admin_uid"] = uid_text
