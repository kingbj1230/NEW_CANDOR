from routes_bootstrap import bind_core, runtime_error_response

bind_core(globals())

@app.route("/api/report", methods=["POST"])
@api_login_required
def api_report():
    if _is_rate_limited("api_report", REPORT_RATE_LIMIT_PER_MINUTE, window_seconds=60):
        return jsonify({"error": "too many report requests"}), 429

    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}
    candidate_id = payload.get("candidate_id") or None
    pledge_id = payload.get("pledge_id") or None
    reason = (payload.get("reason") or "").strip()
    try:
        report_type = _normalize_report_type(payload.get("report_type"), default="?좉퀬")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    reason_category = (payload.get("reason_category") or "").strip() or None
    status = "?묒닔"
    target_url = _sanitize_target_url(payload.get("target_url")) or _sanitize_target_url(request.headers.get("Referer"))
    now = _now_iso()

    if not reason:
        return jsonify({"error": "reason is required"}), 400
    if len(reason) > 2000:
        return jsonify({"error": "reason is too long (max 2000 chars)"}), 400
    if candidate_id and pledge_id:
        return jsonify({"error": "candidate_id and pledge_id cannot both be set"}), 400
    if report_type == "?좉퀬" and not (candidate_id or pledge_id):
        return jsonify({"error": "?좉퀬???꾨낫???먮뒗 怨듭빟 ??곸쓣 吏?뺥빐???⑸땲??"}), 400

    if candidate_id:
        candidate_rows = _supabase_request(
            "GET",
            "candidates",
            query_params={"select": "id", "id": f"eq.{candidate_id}", "limit": "1"},
        ) or []
        if not candidate_rows:
            return jsonify({"error": "candidate not found"}), 404
    if pledge_id:
        pledge_rows = _supabase_request(
            "GET",
            "pledges",
            query_params={"select": "id", "id": f"eq.{pledge_id}", "limit": "1"},
        ) or []
        if not pledge_rows:
            return jsonify({"error": "pledge not found"}), 404

    if report_type == "?좉퀬":
        duplicate_query = {
            "select": "id,status",
            "user_id": f"eq.{uid}",
            "report_type": "eq.?좉퀬",
            "limit": "50",
            "order": "created_at.desc",
        }
        if candidate_id:
            duplicate_query["candidate_id"] = f"eq.{candidate_id}"
        if pledge_id:
            duplicate_query["pledge_id"] = f"eq.{pledge_id}"
        duplicates = _supabase_request("GET", "reports", query_params=duplicate_query) or []
        if any(str(row.get("status") or "").strip() in OPEN_REPORT_STATUS_CHOICES for row in duplicates):
            return jsonify({"error": "?대? ?묒닔/寃?좎쨷???좉퀬媛 ?덉뒿?덈떎."}), 409

    _supabase_request(
        "POST",
        "reports",
        payload={
            "user_id": uid,
            "candidate_id": candidate_id,
            "pledge_id": pledge_id,
            "reason": reason,
            "status": status,
            "report_type": report_type,
            "reason_category": reason_category,
            "target_url": target_url,
            "created_at": now,
            "updated_at": now,
        },
    )
    _audit_log(
        "report_created",
        user_id=uid,
        report_type=report_type,
        candidate_id=candidate_id,
        pledge_id=pledge_id,
        status=status,
        reason_category=reason_category,
    )
    return jsonify({"ok": True, "status": status})

@app.route("/api/mypage/reports", methods=["GET"])
@api_admin_required
def api_mypage_reports():
    rows = _supabase_request(
        "GET",
        "reports",
        query_params={
            "select": "id,user_id,candidate_id,pledge_id,created_at,updated_at,reason,status,report_type,admin_note,resolved_at,resolved_by,target_url,reason_category",
            "order": "created_at.desc",
            "limit": "500",
        },
    ) or []

    candidate_ids = [row.get("candidate_id") for row in rows if row.get("candidate_id")]
    pledge_ids = [row.get("pledge_id") for row in rows if row.get("pledge_id")]
    candidate_filter = _to_in_filter(candidate_ids)
    pledge_filter = _to_in_filter(pledge_ids)

    candidate_map = {}
    pledge_map = {}

    if candidate_filter:
        candidates = _supabase_request(
            "GET",
            "candidates",
            query_params={"select": "id,name", "id": candidate_filter, "limit": "1000"},
        ) or []
        candidate_map = {str(row.get("id")): row for row in candidates if row.get("id")}

    if pledge_filter:
        pledges = _supabase_request(
            "GET",
            "pledges",
            query_params={"select": "id,title,status", "id": pledge_filter, "limit": "1000"},
        ) or []
        pledge_map = {str(row.get("id")): row for row in pledges if row.get("id")}

    enriched = []
    for row in rows:
        candidate_id = row.get("candidate_id")
        pledge_id = row.get("pledge_id")
        candidate = candidate_map.get(str(candidate_id)) if candidate_id else None
        pledge = pledge_map.get(str(pledge_id)) if pledge_id else None

        if candidate_id:
            target_type = "정치인"
            target_name = (candidate or {}).get("name") or f"정치인({candidate_id})"
        elif pledge_id:
            target_type = "공약"
            target_name = (pledge or {}).get("title") or f"공약({pledge_id})"
        else:
            target_type = "의견"
            target_name = "일반 의견"

        enriched.append(
            {
                **row,
                "target_type": target_type,
                "target_name": target_name,
                "pledge_status": (pledge or {}).get("status"),
            }
        )

    return jsonify({"reports": enriched})

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

