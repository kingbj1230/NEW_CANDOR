from routes_bootstrap import bind_core, build_pledge_patch_payload, runtime_error_response

bind_core(globals())


@app.route("/api/mypage/reports/<report_id>", methods=["PATCH"])
@api_admin_required
def api_mypage_report_update(report_id):
    uid = _session_user_id()
    report_rows = _supabase_request(
        "GET",
        "reports",
        query_params={"select": "id,pledge_id,report_type,status", "id": f"eq.{report_id}", "limit": "1"},
    ) or []
    if not report_rows:
        return jsonify({"error": "not found"}), 404
    report_row = report_rows[0]

    payload = request.get_json(silent=True) or {}
    patch_payload = {"updated_at": _now_iso()}

    if "status" in payload:
        try:
            patch_payload["status"] = _normalize_report_status_for_admin(
                payload.get("status"),
                default="\uc811\uc218",
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if _is_resolved_report_status(patch_payload["status"]):
            patch_payload["resolved_at"] = patch_payload["updated_at"]
            patch_payload["resolved_by"] = uid
        else:
            patch_payload["resolved_at"] = None
            patch_payload["resolved_by"] = None

    if "admin_note" in payload:
        admin_note = (payload.get("admin_note") or "").strip()
        patch_payload["admin_note"] = admin_note or None

    if len(patch_payload) == 1:
        return jsonify({"error": "status or admin_note is required"}), 400

    _supabase_request(
        "PATCH",
        "reports",
        query_params={"id": f"eq.{report_id}"},
        payload=patch_payload,
    )
    _audit_log(
        "report_updated",
        admin_user_id=uid,
        report_id=report_id,
        status=patch_payload.get("status"),
        has_admin_note=("admin_note" in patch_payload),
    )

    # Reflect pledge visibility only for actual report items.
    if "status" in patch_payload and str(report_row.get("report_type") or "") == "\uc2e0\uace0":
        pledge_id = report_row.get("pledge_id")
        if pledge_id:
            if _is_resolved_report_status(patch_payload["status"]):
                _supabase_request("PATCH", "pledges", query_params={"id": f"eq.{pledge_id}"}, payload={"status": "hidden"})
                _audit_log("pledge_hidden_by_report_resolution", admin_user_id=uid, report_id=report_id, pledge_id=pledge_id)
            elif _is_rejected_report_status(patch_payload["status"]):
                _supabase_request("PATCH", "pledges", query_params={"id": f"eq.{pledge_id}"}, payload={"status": "active"})
                _audit_log("pledge_restored_by_report_rejection", admin_user_id=uid, report_id=report_id, pledge_id=pledge_id)

    return jsonify({"ok": True})


@app.route("/api/mypage/candidates/<candidate_id>", methods=["PATCH"])
@api_login_required
def api_mypage_candidate_update(candidate_id):
    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}
    now = _now_iso()
    patch_payload = {
        "updated_at": now,
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

    try:
        _supabase_patch_with_optional_fields(
            "candidates",
            query_params={"id": f"eq.{candidate_id}", "created_by": f"eq.{uid}"},
            payload=patch_payload,
            optional_fields={"updated_by"},
        )
    except RuntimeError as exc:
        app.logger.exception("Failed to update candidate %s: %s", candidate_id, exc)
        return runtime_error_response(
            exc,
            default_message="failed to update candidate",
            network_message="database connection issue while updating candidate",
        )
    return jsonify({"ok": True})


@app.route("/api/mypage/pledges/<pledge_id>", methods=["PATCH"])
@api_login_required
def api_mypage_pledge_update(pledge_id):
    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}

    try:
        current_pledge = _get_pledge_row(pledge_id)
    except RuntimeError as exc:
        app.logger.exception("Failed to load pledge %s before update: %s", pledge_id, exc)
        return runtime_error_response(
            exc,
            default_message="failed to load pledge",
            network_message="database connection issue while loading pledge",
        )

    if not current_pledge:
        return jsonify({"error": "not found"}), 404
    if str(current_pledge.get("created_by") or "") != str(uid):
        return jsonify({"error": "forbidden"}), 403

    try:
        validated = _validate_pledge_payload(payload, current_pledge=current_pledge)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    now = _now_iso()
    try:
        _supabase_patch_with_optional_fields(
            "pledges",
            query_params={"id": f"eq.{pledge_id}", "created_by": f"eq.{uid}"},
            payload=build_pledge_patch_payload(validated, now),
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
        app.logger.exception("Pledge tree rebuild failed after update (pledge_id=%s): %s", pledge_id, exc)
        if _is_missing_schema_runtime_error(exc):
            return jsonify({"ok": True, "warning": "pledge_tree_unavailable"}), 200
        if _is_network_runtime_error(exc):
            return jsonify({"ok": True, "warning": "pledge_tree_sync_network_error"}), 200
        if _is_foreign_key_runtime_error(exc):
            return jsonify({"ok": True, "warning": "pledge_tree_sync_foreign_key"}), 200
        return jsonify({"ok": True, "warning": "pledge_tree_sync_failed"}), 200

    return jsonify({"ok": True})
