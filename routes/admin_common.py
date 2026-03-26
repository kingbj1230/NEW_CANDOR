from routes_bootstrap import bind_core

bind_core(globals())

FOREIGN_KEY_DELETE_ERROR = (
    "\uc5f0\uacb0\ub41c \ub370\uc774\ud130\uac00 \ub0a8\uc544 \uc788\uc5b4 "
    "\uacf5\uc57d\uc744 \uc0ad\uc81c\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. "
    "\uad00\ub9ac\uc790\uc5d0\uac8c \ubb38\uc758\ud574 \uc8fc\uc138\uc694."
)
NETWORK_DELETE_ERROR = (
    "\ub370\uc774\ud130\ubca0\uc774\uc2a4 \uc5f0\uacb0 \ubb38\uc81c\ub85c "
    "\uc0ad\uc81c\uc5d0 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4. "
    "\uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694."
)

def _unlink_reports_from_pledge(pledge_id):
    pledge_id = str(pledge_id or "").strip()
    if not pledge_id:
        return
    try:
        _supabase_request(
            "PATCH",
            "reports",
            query_params={"pledge_id": f"eq.{pledge_id}"},
            payload={"pledge_id": None, "updated_at": _now_iso()},
        )
    except RuntimeError as exc:
        if _is_missing_schema_runtime_error(exc):
            return
        app.logger.warning("Failed to unlink reports from pledge %s: %s", pledge_id, exc)
