from routes_bootstrap import bind_core, runtime_error_response
from routes.admin_common import FOREIGN_KEY_DELETE_ERROR, NETWORK_DELETE_ERROR, _unlink_reports_from_pledge

bind_core(globals())

@app.route("/election")
@login_required
def election_page():
    return render_template("election.html")

@app.route("/api/admin/candidate-elections/<candidate_election_id>", methods=["PATCH", "DELETE"])
@api_admin_required
def api_admin_candidate_election(candidate_election_id):
    candidate_election_id = str(candidate_election_id or "").strip()
    if not candidate_election_id:
        return jsonify({"error": "invalid candidate_election_id"}), 400

    current_rows = _supabase_get_with_select_fallback(
        "candidate_elections",
        query_params={"id": f"eq.{candidate_election_id}", "limit": "1"},
        select_candidates=[
            "id,candidate_id,election_id,party,result,is_elect,candidate_number,created_at,created_by",
            "id,candidate_id,election_id,party,result,is_elect,candidate_number",
            "id,candidate_id,election_id",
            "id",
            "*",
        ],
    )
    if not current_rows:
        return jsonify({"error": "not found"}), 404
    current_row = current_rows[0]

    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        patch_payload = {"updated_at": _now_iso(), "updated_by": _session_user_id()}
        has_candidate_election_update = False

        if "candidate_id" in payload:
            candidate_id = str(payload.get("candidate_id") or "").strip()
            if not candidate_id:
                return jsonify({"error": "candidate_id must not be empty"}), 400
            patch_payload["candidate_id"] = candidate_id
            has_candidate_election_update = True

        if "election_id" in payload:
            election_id = str(payload.get("election_id") or "").strip()
            if not election_id:
                return jsonify({"error": "election_id must not be empty"}), 400
            patch_payload["election_id"] = election_id
            has_candidate_election_update = True

        if "party" in payload:
            party = str(payload.get("party") or "").strip()
            if not party:
                return jsonify({"error": "party must not be empty"}), 400
            patch_payload["party"] = party
            has_candidate_election_update = True

        if "result" in payload:
            result = str(payload.get("result") or "").strip()
            if not result:
                return jsonify({"error": "result must not be empty"}), 400
            patch_payload["result"] = result
            patch_payload["is_elect"] = 1 if _is_elected_result(result) else 0
            has_candidate_election_update = True

        if "candidate_number" in payload:
            try:
                candidate_number = int(payload.get("candidate_number"))
            except (TypeError, ValueError):
                return jsonify({"error": "candidate_number must be a number"}), 400
            if candidate_number < 1:
                return jsonify({"error": "candidate_number must be greater than or equal to 1"}), 400
            patch_payload["candidate_number"] = candidate_number
            has_candidate_election_update = True

        term_position = str(payload.get("term_position") or "").strip()
        term_start = None
        term_end = None
        try:
            term_start = _normalize_date_only(
                payload.get("term_start"),
                field_name="term_start",
                allow_null=True,
            )
            term_end = _normalize_date_only(
                payload.get("term_end"),
                field_name="term_end",
                allow_null=True,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        has_term_values = bool(term_position or term_start or term_end)
        if term_end and not term_start:
            return jsonify({"error": "term_start is required when term_end is provided"}), 400
        if term_end and term_start and term_end < term_start:
            return jsonify({"error": "term_end must be greater than or equal to term_start"}), 400

        if not has_candidate_election_update and not has_term_values:
            return jsonify({"error": "no editable fields provided"}), 400

        next_candidate_id = str(patch_payload.get("candidate_id") or current_row.get("candidate_id") or "").strip()
        next_election_id = str(patch_payload.get("election_id") or current_row.get("election_id") or "").strip()
        if not next_candidate_id or not next_election_id:
            return jsonify({"error": "candidate_id and election_id are required"}), 400

        duplicate_rows = _supabase_get_with_select_fallback(
            "candidate_elections",
            query_params={
                "candidate_id": f"eq.{next_candidate_id}",
                "election_id": f"eq.{next_election_id}",
                "limit": "2",
            },
            select_candidates=[
                "id,candidate_id,election_id",
                "id",
                "*",
            ],
        )
        for row in duplicate_rows:
            if str(row.get("id")) != candidate_election_id:
                return jsonify({"error": "duplicate candidate-election relation"}), 409

        next_result = patch_payload.get("result")
        if next_result is None:
            next_result = current_row.get("result")
        next_is_elect = _is_elected_result(next_result)

        if has_term_values:
            if not next_is_elect:
                return jsonify({"error": "term fields can be saved only when result is elected"}), 400
            if not term_position or not term_start:
                return jsonify({"error": "term_position and term_start are required to save term details"}), 400

        if has_candidate_election_update:
            _supabase_patch_with_optional_fields(
                "candidate_elections",
                query_params={"id": f"eq.{candidate_election_id}"},
                payload=patch_payload,
                optional_fields={"updated_by"},
            )

        if has_term_values:
            _upsert_term_for_candidate_election(
                candidate_id=next_candidate_id,
                election_id=next_election_id,
                position=term_position,
                term_start=term_start,
                term_end=term_end,
                user_id=_session_user_id(),
            )
        return jsonify({"ok": True})

    delete_error = None
    try:
        pledge_rows = _supabase_get_with_select_fallback(
            "pledges",
            query_params={
                "candidate_election_id": f"eq.{candidate_election_id}",
                "limit": "5000",
            },
            select_candidates=[
                "id,candidate_election_id",
                "id",
                "*",
            ],
        )
        pledge_ids = [row.get("id") for row in pledge_rows if row.get("id") is not None]
        for pledge_id in pledge_ids:
            _unlink_reports_from_pledge(pledge_id)
            _safe_delete_rows("reports", {"pledge_id": f"eq.{pledge_id}"})
            _delete_pledge_tree(pledge_id)
            _supabase_request("DELETE", "pledges", query_params={"id": f"eq.{pledge_id}"})

        _supabase_request("DELETE", "candidate_elections", query_params={"id": f"eq.{candidate_election_id}"})
        return jsonify({"ok": True})
    except RuntimeError as exc:
        delete_error = exc
        app.logger.exception("Failed to delete candidate_election %s: %s", candidate_election_id, exc)

    return runtime_error_response(
        delete_error,
        default_message="failed to delete candidate_election",
        network_message=NETWORK_DELETE_ERROR,
        foreign_key_message="연결된 데이터가 남아 있어 선거 후보를 삭제할 수 없습니다. 관리자에게 문의해 주세요.",
        schema_message="schema mismatch blocked candidate election deletion",
        debug_prefix="candidate election delete failed",
    )

@app.route("/api/admin/elections/<election_id>", methods=["PATCH", "DELETE"])
@api_admin_required
def api_admin_election(election_id):
    election_id = str(election_id or "").strip()
    if not election_id:
        return jsonify({"error": "invalid election_id"}), 400

    current_rows = _supabase_get_with_select_fallback(
        "elections",
        query_params={"id": f"eq.{election_id}", "limit": "1"},
        select_candidates=[
            "id,election_type,title,election_date,created_at,created_by",
            "id,election_type,title,election_date",
            "id,title,election_date",
            "id",
            "*",
        ],
    )
    if not current_rows:
        return jsonify({"error": "not found"}), 404

    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        patch_payload = {
            "updated_at": _now_iso(),
            "updated_by": _session_user_id(),
            "election_type": "\ub300\ud1b5\ub839",
        }
        has_editable_field = False

        if "title" in payload:
            try:
                title_number = _normalize_election_round_title(payload.get("title"), field_name="title")
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            patch_payload["title"] = title_number
            has_editable_field = True

        if "election_date" in payload:
            try:
                patch_payload["election_date"] = _normalize_date_only(
                    payload.get("election_date"),
                    field_name="election_date",
                    allow_null=False,
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            has_editable_field = True

        if not has_editable_field:
            return jsonify({"error": "title or election_date is required"}), 400

        _supabase_patch_with_optional_fields(
            "elections",
            query_params={"id": f"eq.{election_id}"},
            payload=patch_payload,
            optional_fields={"updated_by"},
        )
        return jsonify({"ok": True})

    delete_error = None
    try:
        candidate_election_rows = _supabase_get_with_select_fallback(
            "candidate_elections",
            query_params={"election_id": f"eq.{election_id}", "limit": "10000"},
            select_candidates=[
                "id,election_id",
                "id",
                "*",
            ],
        )

        for candidate_election_row in candidate_election_rows:
            candidate_election_id = str(candidate_election_row.get("id") or "").strip()
            if not candidate_election_id:
                continue

            pledge_rows = _supabase_get_with_select_fallback(
                "pledges",
                query_params={
                    "candidate_election_id": f"eq.{candidate_election_id}",
                    "limit": "5000",
                },
                select_candidates=[
                    "id,candidate_election_id",
                    "id",
                    "*",
                ],
            )
            pledge_ids = [row.get("id") for row in pledge_rows if row.get("id") is not None]

            for pledge_id in pledge_ids:
                _unlink_reports_from_pledge(pledge_id)
                _safe_delete_rows("reports", {"pledge_id": f"eq.{pledge_id}"})
                _delete_pledge_tree(pledge_id)
                _supabase_request("DELETE", "pledges", query_params={"id": f"eq.{pledge_id}"})

            _supabase_request("DELETE", "candidate_elections", query_params={"id": f"eq.{candidate_election_id}"})

        _supabase_request("DELETE", "elections", query_params={"id": f"eq.{election_id}"})
        return jsonify({"ok": True})
    except RuntimeError as exc:
        delete_error = exc
        app.logger.exception("Failed to delete election %s: %s", election_id, exc)

    return runtime_error_response(
        delete_error,
        default_message="failed to delete election",
        network_message=NETWORK_DELETE_ERROR,
        foreign_key_message="related rows still exist; delete blocked",
        schema_message="schema mismatch blocked election deletion",
        debug_prefix="election delete failed",
    )
