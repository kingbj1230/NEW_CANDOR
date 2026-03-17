from routes_bootstrap import bind_core, build_pledge_patch_payload, runtime_error_response

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


@app.route("/api/admin/candidates/<candidate_id>", methods=["PATCH", "DELETE"])
@api_admin_required
def api_admin_candidate(candidate_id):
    candidate_id = str(candidate_id or "").strip()
    if not candidate_id:
        return jsonify({"error": "invalid candidate_id"}), 400

    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        patch_payload = {
            "updated_at": _now_iso(),
            "updated_by": None,
        }
        if "name" in payload:
            patch_payload["name"] = payload.get("name")
        if "image" in payload:
            patch_payload["image"] = payload.get("image")
        if "birth_date" in payload:
            try:
                patch_payload["birth_date"] = _normalize_date_only(
                    payload.get("birth_date"),
                    field_name="birth_date",
                    allow_null=True,
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

        _supabase_patch_with_optional_fields(
            "candidates",
            query_params={"id": f"eq.{candidate_id}"},
            payload=patch_payload,
            optional_fields={"updated_by"},
        )
        return jsonify({"ok": True})

    candidate_rows = _supabase_request(
        "GET",
        "candidates",
        query_params={"select": "id", "id": f"eq.{candidate_id}", "limit": "1"},
    ) or []
    if not candidate_rows:
        return jsonify({"error": "not found"}), 404

    def _delete_relation_rows_if_exists(table_name, query_params):
        try:
            _supabase_request("DELETE", table_name, query_params=query_params)
        except RuntimeError as exc:
            if _is_missing_relation_runtime_error(exc):
                return
            raise

    candidate_elections = _supabase_get_with_select_fallback(
        "candidate_elections",
        query_params={"candidate_id": f"eq.{candidate_id}", "limit": "5000"},
        select_candidates=[
            "id,candidate_id,election_id",
            "id,candidate_id",
            "id",
            "*",
        ],
    )
    candidate_election_ids = [row.get("id") for row in candidate_elections if row.get("id") is not None]
    candidate_election_filter = _to_in_filter(candidate_election_ids)

    pledge_ids = []
    if candidate_election_filter:
        pledges = _supabase_get_with_select_fallback(
            "pledges",
            query_params={"candidate_election_id": candidate_election_filter, "limit": "5000"},
            select_candidates=[
                "id,candidate_election_id",
                "id",
                "*",
            ],
        )
        pledge_ids = [row.get("id") for row in pledges if row.get("id") is not None]

    pledge_filter = _to_in_filter(pledge_ids)
    if pledge_filter:
        _delete_relation_rows_if_exists("reports", {"pledge_id": pledge_filter})

    _delete_relation_rows_if_exists("reports", {"candidate_id": f"eq.{candidate_id}"})

    for pledge_id in pledge_ids:
        _delete_pledge_tree(pledge_id)

    if candidate_election_filter:
        _delete_relation_rows_if_exists("pledges", {"candidate_election_id": candidate_election_filter})

    _delete_relation_rows_if_exists("terms", {"candidate_id": f"eq.{candidate_id}"})
    _delete_relation_rows_if_exists("candidate_elections", {"candidate_id": f"eq.{candidate_id}"})
    _supabase_request("DELETE", "candidates", query_params={"id": f"eq.{candidate_id}"})
    return jsonify({"ok": True})


@app.route("/api/admin/pledges/<pledge_id>", methods=["PATCH", "DELETE"])
@api_admin_required
def api_admin_pledge(pledge_id):
    pledge_id = str(pledge_id or "").strip()
    if not pledge_id:
        return jsonify({"error": "invalid pledge_id"}), 400

    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        uid = _session_user_id()

        if "raw_text" in payload or "candidate_election_id" in payload:
            try:
                current_pledge = _get_pledge_row(pledge_id)
            except RuntimeError as exc:
                app.logger.exception("Failed to load pledge %s before patch: %s", pledge_id, exc)
                return runtime_error_response(
                    exc,
                    default_message="failed to load pledge",
                    network_message="database connection issue while loading pledge",
                )

            if not current_pledge:
                return jsonify({"error": "not found"}), 404

            try:
                validated = _validate_pledge_payload(payload, current_pledge=current_pledge)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            try:
                _supabase_patch_with_optional_fields(
                    "pledges",
                    query_params={"id": f"eq.{pledge_id}"},
                    payload=build_pledge_patch_payload(validated, _now_iso()),
                    optional_fields={"updated_by"},
                )
            except RuntimeError as exc:
                app.logger.exception("Failed to patch pledge %s: %s", pledge_id, exc)
                return runtime_error_response(
                    exc,
                    default_message="failed to update pledge",
                    network_message="database connection issue while updating pledge",
                )

            try:
                _delete_pledge_tree(pledge_id)
                _insert_pledge_tree(pledge_id, validated["raw_text"], uid)
            except RuntimeError as exc:
                app.logger.exception("Pledge tree rebuild failed after admin patch (pledge_id=%s): %s", pledge_id, exc)
                if _is_missing_schema_runtime_error(exc):
                    return jsonify({"ok": True, "warning": "pledge_tree_unavailable"}), 200
                if _is_network_runtime_error(exc):
                    return jsonify({"ok": True, "warning": "pledge_tree_sync_network_error"}), 200
                if _is_foreign_key_runtime_error(exc):
                    return jsonify({"ok": True, "warning": "pledge_tree_sync_foreign_key"}), 200
                return jsonify({"ok": True, "warning": "pledge_tree_sync_failed"}), 200

            return jsonify({"ok": True})

        try:
            _supabase_patch_with_optional_fields(
                "pledges",
                query_params={"id": f"eq.{pledge_id}"},
                payload=payload,
                optional_fields={"updated_by"},
            )
        except RuntimeError as exc:
            app.logger.exception("Failed to patch pledge %s (simple payload): %s", pledge_id, exc)
            return runtime_error_response(
                exc,
                default_message="failed to update pledge",
                network_message="database connection issue while updating pledge",
            )
        return jsonify({"ok": True})

    try:
        current_pledge = _get_pledge_row(pledge_id)
    except RuntimeError as exc:
        app.logger.exception("Failed to load pledge %s before deletion: %s", pledge_id, exc)
        return runtime_error_response(
            exc,
            default_message="failed to load pledge",
            network_message="database connection issue while loading pledge",
        )

    if not current_pledge:
        return jsonify({"error": "not found"}), 404

    delete_error = None
    try:
        _unlink_reports_from_pledge(pledge_id)
        _safe_delete_rows("reports", {"pledge_id": f"eq.{pledge_id}"})
        _delete_pledge_tree(pledge_id)
        _supabase_request("DELETE", "pledges", query_params={"id": f"eq.{pledge_id}"})
        return jsonify({"ok": True})
    except RuntimeError as exc:
        delete_error = exc
        app.logger.exception("Failed to delete pledge %s: %s", pledge_id, exc)

    # Fallback 1: direct delete without relationship cleanup.
    try:
        _supabase_request("DELETE", "pledges", query_params={"id": f"eq.{pledge_id}"})
        return jsonify({"ok": True, "warning": "cleanup_partial"}), 200
    except RuntimeError as delete_exc:
        if not _is_foreign_key_runtime_error(delete_error):
            delete_error = delete_exc
        app.logger.exception("Fallback direct delete failed for pledge %s: %s", pledge_id, delete_exc)

    return runtime_error_response(
        delete_error,
        default_message="failed to delete pledge",
        network_message=NETWORK_DELETE_ERROR,
        foreign_key_message=FOREIGN_KEY_DELETE_ERROR,
        schema_message="schema mismatch blocked pledge deletion",
        debug_prefix="pledge delete failed",
    )
