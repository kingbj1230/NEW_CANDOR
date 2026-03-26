from routes_bootstrap import bind_core, runtime_error_response

bind_core(globals())


def _build_fallback_pledge_goals(pledge):
    pledge_id = str((pledge or {}).get("id") or "unknown").strip() or "unknown"
    raw_text = str((pledge or {}).get("raw_text") or "").replace("\r\n", "\n")
    if not raw_text.strip():
        return []

    lines = []
    for raw_line in raw_text.split("\n"):
        compact_line = " ".join(str(raw_line or "").split()).strip()
        if not compact_line:
            continue
        lines.append(compact_line)
        if len(lines) >= 40:
            break

    if not lines:
        return []

    children = []
    for index, line in enumerate(lines, start=1):
        children.append(
            {
                "id": f"fallback-node-{pledge_id}-{index}",
                "text": line,
                "level": 2,
                "sort_order": index - 1,
                "children": [],
                "sources": [],
                "progress_history": [],
            }
        )

    return [
        {
            "id": f"fallback-root-{pledge_id}",
            "text": "공약 내용",
            "level": 1,
            "sort_order": 0,
            "children": children,
            "sources": [],
            "progress_history": [],
        }
    ]


def _hydrate_missing_pledge_goals(pledges):
    fallback_count = 0
    for pledge in pledges or []:
        goals = pledge.get("goals")
        if isinstance(goals, list) and goals:
            continue
        fallback_goals = _build_fallback_pledge_goals(pledge)
        pledge["goals"] = fallback_goals
        if fallback_goals:
            pledge["tree_fallback"] = True
            fallback_count += 1
    return fallback_count


PROFILE_NICKNAME_MIN_LENGTH = 2
PROFILE_NICKNAME_MAX_LENGTH = 30


def _mypage_profile_payload(*, uid, email, profile_row=None):
    profile = dict(profile_row or {})
    fallback_nickname = (str(email or "").split("@")[0] or f"user_{str(uid)[:8]}").strip()
    return {
        "user_id": str(uid or "").strip() or None,
        "email": str(email or "").strip() or None,
        "nickname": str(profile.get("nickname") or "").strip() or fallback_nickname,
        "role": str(profile.get("role") or "").strip() or "user",
        "status": str(profile.get("status") or "").strip() or "active",
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
        "reputation_score": profile.get("reputation_score"),
    }


@app.route("/api/mypage/profile", methods=["GET"])
@api_login_required
def api_mypage_profile():
    uid = _session_user_id()
    email = str(session.get("email") or "").strip()

    try:
        ensure_user_profile(uid, email)
        profile_row = _try_fetch_user_profile(uid) or {}
        is_admin = bool(_is_admin(uid))
    except RuntimeError as exc:
        app.logger.exception("Failed to load mypage profile for %s: %s", uid, exc)
        return runtime_error_response(
            exc,
            default_message="failed to load profile",
            network_message="프로필 정보를 불러오는 중 연결 문제가 발생했습니다.",
            schema_message="profile schema mismatch",
        )
    except Exception as exc:
        app.logger.exception("Unexpected profile load error for %s: %s", uid, exc)
        return jsonify({"error": "failed to load profile"}), 500

    return jsonify(
        {
            "ok": True,
            "is_admin": is_admin,
            "profile": _mypage_profile_payload(uid=uid, email=email, profile_row=profile_row),
        }
    ), 200


@app.route("/api/mypage/profile", methods=["PATCH"])
@api_login_required
def api_mypage_profile_update():
    uid = _session_user_id()
    email = str(session.get("email") or "").strip()
    payload = request.get_json(silent=True) or {}
    nickname = str(payload.get("nickname") or "").strip()

    if not nickname:
        return jsonify({"error": "nickname is required"}), 400
    if len(nickname) < PROFILE_NICKNAME_MIN_LENGTH or len(nickname) > PROFILE_NICKNAME_MAX_LENGTH:
        return jsonify({"error": f"nickname must be between {PROFILE_NICKNAME_MIN_LENGTH} and {PROFILE_NICKNAME_MAX_LENGTH} characters"}), 400

    now = _now_iso()
    patch_error = None

    try:
        ensure_user_profile(uid, email)

        for id_column in ("user__id", "user_id"):
            try:
                _supabase_patch_with_optional_fields(
                    "user_profiles",
                    query_params={id_column: f"eq.{uid}"},
                    payload={
                        "nickname": nickname,
                        "update_at": now,
                        "updated_at": now,
                    },
                    optional_fields={"update_at", "updated_at"},
                )
                patch_error = None
                break
            except RuntimeError as exc:
                patch_error = exc
                missing_column = _extract_missing_column_from_runtime_message(str(exc))
                if missing_column and missing_column == id_column:
                    continue
        if patch_error:
            raise patch_error

        profile_row = _try_fetch_user_profile(uid) or {}
        is_admin = bool(_is_admin(uid))
    except RuntimeError as exc:
        app.logger.exception("Failed to update mypage profile for %s: %s", uid, exc)
        return runtime_error_response(
            exc,
            default_message="failed to update profile",
            network_message="프로필 저장 중 연결 문제가 발생했습니다.",
            schema_message="profile schema mismatch",
        )
    except Exception as exc:
        app.logger.exception("Unexpected profile update error for %s: %s", uid, exc)
        return jsonify({"error": "failed to update profile"}), 500

    return jsonify(
        {
            "ok": True,
            "is_admin": is_admin,
            "profile": _mypage_profile_payload(uid=uid, email=email, profile_row=profile_row),
        }
    ), 200


@app.route("/candidate")
@login_required
def candidate_page():
    return render_template("candidate.html")

@app.route("/politicians")
def politicians_page():
    return render_template("politicians.html")

@app.route("/politicians/<candidate_id>")
def politician_detail_page(candidate_id):
    normalized = str(candidate_id or "").strip().lower()
    if not normalized or normalized in {"undefined", "null", "none", "nan"}:
        return redirect(url_for("politicians_page"))
    return render_template("politician_detail.html", candidate_id=candidate_id)

@app.route("/api/politicians", methods=["GET"])
def api_politicians():
    rows = _supabase_request(
        "GET",
        "candidates",
        query_params={
            "select": "id,name,image",
            "order": "name.asc",
            "limit": "500",
        },
    ) or []
    rows = _enrich_candidates_with_latest(rows)

    return jsonify({"politicians": rows})

@app.route("/api/politicians/<candidate_id>", methods=["GET"])
def api_politician_detail(candidate_id):
    candidate_id = str(candidate_id or "").strip()
    if not candidate_id or candidate_id.lower() in {"undefined", "null", "none", "nan"}:
        return jsonify({"error": "invalid candidate_id"}), 400

    try:
        is_admin = bool(_is_admin(_session_user_id()))
    except Exception as exc:
        app.logger.exception("api_politician_detail admin check failed: candidate_id=%s error=%s", candidate_id, exc)
        is_admin = False
    detail_warnings = []
    candidate_fetch_failed = False
    try:
        candidates = _supabase_get_with_select_fallback(
            "candidates",
            query_params={
                "id": f"eq.{candidate_id}",
                "limit": "1",
            },
            select_candidates=[
                "id,name,image,birth_date,created_at,created_by,updated_at,updated_by",
                "id,name,image,birth_date,created_at,updated_at",
                "id,name,image,birth_date,created_at",
                "id,name,image,birth_date",
                "id,name,image",
                "*",
            ],
        )
    except Exception as exc:
        app.logger.exception("api_politician_detail candidate fetch failed: candidate_id=%s error=%s", candidate_id, exc)
        candidates = []
        candidate_fetch_failed = True
        detail_warnings.append("candidate")

    if not candidates and not candidate_fetch_failed:
        return jsonify({"error": "not found"}), 404

    if candidates:
        try:
            candidates = _enrich_candidates_with_latest(candidates)
        except Exception as exc:
            app.logger.exception("api_politician_detail candidate enrich failed: candidate_id=%s error=%s", candidate_id, exc)
            detail_warnings.append("candidate_enrich")
    candidate = (candidates[0] if candidates else {"id": candidate_id, "name": f"정치인 {candidate_id}", "image": None})

    try:
        candidate_elections_for_candidate = _supabase_get_with_select_fallback(
            "candidate_elections",
            query_params={
                "candidate_id": f"eq.{candidate_id}",
                "order": "created_at.desc",
                "limit": "1000",
            },
            select_candidates=[
                "id,candidate_id,election_id,party,result,is_elect,candidate_number,created_at,created_by",
                "id,candidate_id,election_id,party,result,is_elect,candidate_number,created_at",
                "id,candidate_id,election_id,party,result,candidate_number,created_at",
                "id,candidate_id,election_id,party,result,candidate_number",
                "id,candidate_id,election_id,party,result",
                "id,candidate_id,election_id",
                "*",
            ],
        )
    except Exception as exc:
        app.logger.exception("api_politician_detail candidate_elections fetch failed: candidate_id=%s error=%s", candidate_id, exc)
        candidate_elections_for_candidate = []
        detail_warnings.append("candidate_elections")

    candidate_election_ids = [row.get("id") for row in candidate_elections_for_candidate if row.get("id") is not None]
    pledge_filter = _to_in_filter(candidate_election_ids)
    pledges = []
    if pledge_filter:
        try:
            pledges = _supabase_get_with_select_fallback(
                "pledges",
                query_params={
                    "candidate_election_id": pledge_filter,
                    "order": "sort_order.asc.nullslast,created_at.desc",
                    "limit": "1000",
                },
                select_candidates=[
                    "id,candidate_election_id,sort_order,title,raw_text,category,status,created_at,created_by,updated_at,updated_by",
                    "id,candidate_election_id,sort_order,title,raw_text,category,status,created_at,updated_at",
                    "id,candidate_election_id,sort_order,title,raw_text,category,status,created_at",
                    "id,candidate_election_id,sort_order,title,raw_text,category,status",
                    "id,candidate_election_id,title,raw_text,category,status",
                    "id,candidate_election_id,title,raw_text",
                    "*",
                ],
            )
        except Exception as exc:
            app.logger.exception("api_politician_detail pledges fetch failed: candidate_id=%s error=%s", candidate_id, exc)
            pledges = []
            detail_warnings.append("pledges")
        for pledge in pledges:
            pledge["candidate_id"] = candidate_id

    pledges = [p for p in pledges if str(p.get("status") or "active") != "deleted"]
    if not is_admin:
        pledges = [p for p in pledges if str(p.get("status") or "active") != "hidden"]
    try:
        pledges = _attach_pledge_tree_rows(pledges)
    except Exception as exc:
        app.logger.exception("api_politician_detail pledge tree attach failed: candidate_id=%s error=%s", candidate_id, exc)
        detail_warnings.append("pledge_tree")
    fallback_goal_count = _hydrate_missing_pledge_goals(pledges)
    if fallback_goal_count:
        detail_warnings.append("pledge_tree_fallback")

    election_links = candidate_elections_for_candidate

    election_ids = []
    for row in election_links:
        eid = row.get("election_id")
        if eid is None:
            continue
        eid_str = str(eid)
        if eid_str not in election_ids:
            election_ids.append(eid_str)

    election_map = {}
    if election_ids:
        election_filter = _to_in_filter(election_ids)
        try:
            election_rows = _supabase_get_with_select_fallback(
                "elections",
                query_params={
                    "id": election_filter,
                    "limit": "5000",
                },
                select_candidates=[
                    "id,election_type,title,election_date",
                    "id,election_type,title",
                    "id,title,election_date",
                    "id,title",
                    "*",
                ],
            )
        except Exception as exc:
            app.logger.exception("api_politician_detail elections fetch failed: candidate_id=%s error=%s", candidate_id, exc)
            election_rows = []
            detail_warnings.append("elections")
        election_map = {str(row.get("id")): row for row in election_rows if row.get("id") is not None}

    for row in election_links:
        election_info = election_map.get(str(row.get("election_id"))) or {}
        row["election"] = {
            "id": election_info.get("id"),
            "election_type": election_info.get("election_type"),
            "title": _format_presidential_election_title(election_info.get("title")),
            "election_date": election_info.get("election_date"),
        }

    pledges_by_candidate_election = {}
    for pledge in pledges:
        key = str(pledge.get("candidate_election_id"))
        if not key:
            continue
        pledges_by_candidate_election.setdefault(key, []).append(pledge)

    election_sections = []
    for row in election_links:
        candidate_election_key = str(row.get("id"))
        election_info = row.get("election") or {}
        linked_pledges = sorted(
            pledges_by_candidate_election.get(candidate_election_key, []),
            key=lambda p: (_safe_int(p.get("sort_order"), 999999), str(p.get("created_at") or "")),
        )
        election_sections.append(
            {
                "candidate_election_id": row.get("id"),
                "party": row.get("party"),
                "result": row.get("result"),
                "is_elect": row.get("is_elect"),
                "candidate_number": row.get("candidate_number"),
                "created_at": row.get("created_at"),
                "election": election_info,
                "pledges": linked_pledges,
                "pledge_count": len(linked_pledges),
            }
        )

    election_sections = sorted(
        election_sections,
        key=lambda x: (str((x.get("election") or {}).get("election_date") or ""), str(x.get("created_at") or "")),
        reverse=True,
    )

    try:
        terms = _fetch_terms_rows(candidate_id=candidate_id, limit="200")
    except Exception as exc:
        app.logger.exception("api_politician_detail terms fetch failed: candidate_id=%s error=%s", candidate_id, exc)
        terms = []
        detail_warnings.append("terms")

    payload = {
        "candidate": candidate,
        "pledges": pledges,
        "election_history": election_links,
        "election_sections": election_sections,
        "terms": terms,
        "is_admin": is_admin,
    }
    if detail_warnings:
        payload["warning"] = f"partial_data:{','.join(detail_warnings)}"
    return jsonify(payload)

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
