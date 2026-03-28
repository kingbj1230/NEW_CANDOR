import copy
import time
from threading import Lock

from services import candidate_detail_service as _candidate_detail_service
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


def _embedded_single_row(value):
    return _candidate_detail_service.embedded_single_row(value)


def _sortable_date_key(value):
    return _candidate_detail_service.sortable_date_key(value)


def _latest_election_sort_key(row):
    return _candidate_detail_service.latest_election_sort_key(row)


def _latest_term_sort_key(row):
    return _candidate_detail_service.latest_term_sort_key(row)


def _apply_candidate_latest_fields(candidate, election_links, terms):
    return _candidate_detail_service.apply_candidate_latest_fields(
        candidate,
        election_links,
        terms,
        format_presidential_election_title_fn=_format_presidential_election_title,
        year_from_date_fn=_year_from_date,
    )


def _is_join_embed_runtime_error(exc):
    return _candidate_detail_service.is_join_embed_runtime_error(
        exc,
        is_missing_schema_runtime_error_fn=_is_missing_schema_runtime_error,
    )


def _debug_join_fallback(candidate_id, stage, exc):
    if not DEBUG_MODE:
        return
    app.logger.debug(
        "api_politician_detail join fallback candidate_id=%s stage=%s reason=%s",
        candidate_id,
        stage,
        exc,
    )


def _fetch_candidate_elections_joined(candidate_id):
    return _candidate_detail_service.fetch_candidate_elections_joined(
        candidate_id,
        supabase_request_fn=_supabase_request,
        supabase_get_with_select_fallback_fn=_supabase_get_with_select_fallback,
        is_join_embed_runtime_error_fn=_is_join_embed_runtime_error,
        debug_join_fallback_fn=_debug_join_fallback,
    )


def _flatten_joined_pledges(candidate_election_rows, candidate_id):
    return _candidate_detail_service.flatten_joined_pledges(candidate_election_rows, candidate_id)


def _normalize_election_payload(link_row):
    return _candidate_detail_service.normalize_election_payload(
        link_row,
        format_presidential_election_title_fn=_format_presidential_election_title,
    )


def _filter_visible_pledges(pledges, is_admin):
    return _candidate_detail_service.filter_visible_pledges(pledges, is_admin)


DETAIL_INITIAL_CANDIDATE_FIELDS = (
    "id",
    "name",
    "image",
    "birth_date",
    "party",
    "election_year",
    "position",
    "term_start",
    "term_end",
)

DETAIL_INITIAL_PLEDGE_FIELDS = (
    "id",
    "candidate_election_id",
    "sort_order",
    "title",
    "category",
    "created_at",
    "status",
)

DETAIL_FULL_PLEDGE_FIELDS = (
    "id",
    "candidate_election_id",
    "sort_order",
    "title",
    "raw_text",
    "category",
    "timeline_text",
    "finance_text",
    "parse_type",
    "structure_version",
    "fulfillment_rate",
    "created_at",
    "status",
    "sources",
    "goals",
    "tree_fallback",
)


def _is_initial_detail_view():
    return str(request.args.get("view") or "").strip().lower() == "initial"


def _pick_row_fields(row, field_names):
    source = dict(row or {})
    return {field_name: source.get(field_name) for field_name in field_names}


def _build_candidate_initial_payload(candidate):
    return _pick_row_fields(candidate, DETAIL_INITIAL_CANDIDATE_FIELDS)


def _build_pledge_summary_rows(pledges):
    rows = []
    for pledge in pledges or []:
        rows.append(_pick_row_fields(pledge, DETAIL_INITIAL_PLEDGE_FIELDS))
    return rows


def _build_pledge_detail_payload(pledge):
    payload = _pick_row_fields(pledge, DETAIL_FULL_PLEDGE_FIELDS)
    if not isinstance(payload.get("goals"), list):
        payload["goals"] = []
    if not isinstance(payload.get("sources"), list):
        payload["sources"] = []
    return payload


def _group_pledges_by_candidate_election(pledges):
    grouped = {}
    for pledge in pledges or []:
        key = str(pledge.get("candidate_election_id") or "").strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(pledge)
    return grouped


def _sorted_pledges(rows):
    return sorted(
        rows or [],
        key=lambda p: (_safe_int(p.get("sort_order"), 999999), str(p.get("created_at") or "")),
    )


def _build_election_sections(election_links, pledges_by_candidate_election, *, include_pledges):
    sections = []
    for row in election_links or []:
        candidate_election_key = str(row.get("id"))
        election_info = row.get("election") or {}
        linked_pledges = _sorted_pledges(pledges_by_candidate_election.get(candidate_election_key, []))
        section_payload = {
            "candidate_election_id": row.get("id"),
            "party": row.get("party"),
            "result": row.get("result"),
            "is_elect": row.get("is_elect"),
            "candidate_number": row.get("candidate_number"),
            "created_at": row.get("created_at"),
            "election": election_info,
            "pledge_count": len(linked_pledges),
        }
        section_payload["pledges"] = linked_pledges if include_pledges else []
        sections.append(section_payload)
    return sorted(
        sections,
        key=lambda x: (str((x.get("election") or {}).get("election_date") or ""), str(x.get("created_at") or "")),
        reverse=True,
    )


DETAIL_TREE_CACHE_TTL_SECONDS = max(1, _env_int("DETAIL_TREE_CACHE_TTL_SECONDS", 60))
_DETAIL_TREE_POSTPROCESS_CACHE = {}
_DETAIL_TREE_POSTPROCESS_CACHE_LOCK = Lock()
_DETAIL_JOIN_PATH_STATS = {"fast_path": 0, "fallback": 0, "error": 0}
_DETAIL_JOIN_PATH_STATS_LOCK = Lock()


def _detail_perf_now():
    return time.perf_counter()


def _detail_perf_ms(started_at):
    return (time.perf_counter() - started_at) * 1000.0


def _detail_perf_log(candidate_id, stage, elapsed_ms, **fields):
    if not DEBUG_MODE:
        return
    details = " ".join(f"{key}={fields[key]}" for key in sorted(fields))
    app.logger.info(
        "detail_perf candidate_id=%s stage=%s ms=%.2f %s",
        candidate_id,
        stage,
        elapsed_ms,
        details,
    )


def _detail_tree_cache_key(candidate_id, is_admin):
    return _candidate_detail_service.detail_tree_cache_key(candidate_id, is_admin)


def _detail_tree_cache_get(candidate_id, is_admin):
    return _candidate_detail_service.detail_tree_cache_get(
        _DETAIL_TREE_POSTPROCESS_CACHE,
        _DETAIL_TREE_POSTPROCESS_CACHE_LOCK,
        candidate_id,
        is_admin,
        ttl_seconds=DETAIL_TREE_CACHE_TTL_SECONDS,
    )


def _detail_tree_cache_set(candidate_id, is_admin, pledges, fallback_goal_count):
    _candidate_detail_service.detail_tree_cache_set(
        _DETAIL_TREE_POSTPROCESS_CACHE,
        _DETAIL_TREE_POSTPROCESS_CACHE_LOCK,
        candidate_id,
        is_admin,
        pledges,
        fallback_goal_count,
    )


def _record_join_path(candidate_id, join_mode):
    mode = str(join_mode or "error").strip() or "error"
    if mode not in {"fast_path", "fallback", "error"}:
        mode = "error"
    with _DETAIL_JOIN_PATH_STATS_LOCK:
        _DETAIL_JOIN_PATH_STATS[mode] = int(_DETAIL_JOIN_PATH_STATS.get(mode, 0)) + 1
        snapshot = dict(_DETAIL_JOIN_PATH_STATS)
    _detail_perf_log(
        candidate_id,
        "join_path",
        0.0,
        mode=mode,
        fast_path=snapshot.get("fast_path", 0),
        fallback=snapshot.get("fallback", 0),
        error=snapshot.get("error", 0),
    )


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
        is_admin = _session_is_admin()
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
        is_admin = _session_is_admin()
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
    is_initial_view = _is_initial_detail_view()
    view_mode = "initial" if is_initial_view else "full"

    total_started_at = _detail_perf_now()

    try:
        is_admin = _session_is_admin()
    except Exception as exc:
        app.logger.exception("api_politician_detail admin check failed: candidate_id=%s error=%s", candidate_id, exc)
        is_admin = False
    detail_warnings = []
    candidate_fetch_failed = False
    candidate_fetch_started_at = _detail_perf_now()
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
    candidate_fetch_ms = _detail_perf_ms(candidate_fetch_started_at)
    _detail_perf_log(
        candidate_id,
        "candidate_fetch",
        candidate_fetch_ms,
        rows=len(candidates),
        failed=candidate_fetch_failed,
        view=view_mode,
    )

    if not candidates and not candidate_fetch_failed:
        _detail_perf_log(candidate_id, "total", _detail_perf_ms(total_started_at), result="not_found")
        return jsonify({"error": "not found"}), 404

    candidate = (dict(candidates[0]) if candidates else {"id": candidate_id, "name": f"정치인 {candidate_id}", "image": None})

    election_links_fetch_started_at = _detail_perf_now()
    join_mode = "error"
    try:
        candidate_elections_for_candidate, has_pledges_embed, has_election_embed, join_mode = _fetch_candidate_elections_joined(candidate_id)
    except Exception as exc:
        app.logger.exception("api_politician_detail candidate_elections fetch failed: candidate_id=%s error=%s", candidate_id, exc)
        candidate_elections_for_candidate = []
        has_pledges_embed = False
        has_election_embed = False
        join_mode = "error"
        detail_warnings.append("candidate_elections")
    _record_join_path(candidate_id, join_mode)
    election_links_fetch_ms = _detail_perf_ms(election_links_fetch_started_at)
    _detail_perf_log(
        candidate_id,
        "election_links_fetch",
        election_links_fetch_ms,
        rows=len(candidate_elections_for_candidate),
        has_pledges_embed=has_pledges_embed,
        has_election_embed=has_election_embed,
        join_mode=join_mode,
        view=view_mode,
    )

    pledges_fetch_started_at = _detail_perf_now()
    candidate_election_ids = [row.get("id") for row in candidate_elections_for_candidate if row.get("id") is not None]
    pledges = _flatten_joined_pledges(candidate_elections_for_candidate, candidate_id) if has_pledges_embed else []
    if not has_pledges_embed:
        pledge_filter = _to_in_filter(candidate_election_ids)
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
                        "id,candidate_election_id,sort_order,title,raw_text,category,timeline_text,finance_text,parse_type,structure_version,fulfillment_rate,status,created_at,created_by,updated_at,updated_by",
                        "id,candidate_election_id,sort_order,title,raw_text,category,timeline_text,finance_text,parse_type,structure_version,fulfillment_rate,status,created_at,updated_at",
                        "id,candidate_election_id,sort_order,title,raw_text,category,timeline_text,finance_text,parse_type,structure_version,fulfillment_rate,status,created_at",
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
    pledges_fetch_ms = _detail_perf_ms(pledges_fetch_started_at)
    _detail_perf_log(
        candidate_id,
        "pledges_fetch",
        pledges_fetch_ms,
        mode="embedded" if has_pledges_embed else "direct",
        candidate_elections=len(candidate_election_ids),
        rows=len(pledges),
        view=view_mode,
    )

    pledges = _filter_visible_pledges(pledges, is_admin)
    pledge_tree_postprocess_started_at = _detail_perf_now()
    if is_initial_view:
        fallback_goal_count = 0
        tree_cache_state = "skipped_initial_view"
    else:
        cached_pledges, cached_fallback_goal_count, tree_cache_state = _detail_tree_cache_get(candidate_id, is_admin)
        _detail_perf_log(
            candidate_id,
            "pledge_tree_cache",
            0.0,
            state=tree_cache_state,
            ttl_seconds=DETAIL_TREE_CACHE_TTL_SECONDS,
            join_mode=join_mode,
            view=view_mode,
        )
        if tree_cache_state == "hit":
            pledges = cached_pledges
            fallback_goal_count = cached_fallback_goal_count
        else:
            tree_attach_failed = False
            try:
                pledges = _attach_pledge_tree_rows(pledges)
            except Exception as exc:
                tree_attach_failed = True
                app.logger.exception("api_politician_detail pledge tree attach failed: candidate_id=%s error=%s", candidate_id, exc)
                detail_warnings.append("pledge_tree")
            fallback_goal_count = _hydrate_missing_pledge_goals(pledges)
            if not tree_attach_failed:
                _detail_tree_cache_set(candidate_id, is_admin, pledges, fallback_goal_count)
        if fallback_goal_count:
            detail_warnings.append("pledge_tree_fallback")
    pledge_tree_postprocess_ms = _detail_perf_ms(pledge_tree_postprocess_started_at)
    _detail_perf_log(
        candidate_id,
        "pledge_tree_postprocess",
        pledge_tree_postprocess_ms,
        rows=len(pledges),
        fallback_goals=fallback_goal_count,
        cache_state=tree_cache_state,
        view=view_mode,
    )

    election_links = candidate_elections_for_candidate

    for row in election_links:
        row["election"] = _normalize_election_payload(row)

    election_ids = []
    for row in election_links:
        existing = row.get("election") or {}
        if existing.get("id") is not None and has_election_embed:
            continue
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
        election_info = row.get("election") or {}
        if election_info.get("id") is not None:
            continue
        fallback_info = election_map.get(str(row.get("election_id"))) or {}
        row["election"] = {
            "id": fallback_info.get("id"),
            "election_type": fallback_info.get("election_type"),
            "title": _format_presidential_election_title(fallback_info.get("title")),
            "election_date": fallback_info.get("election_date"),
        }

    pledges_for_response = _build_pledge_summary_rows(pledges) if is_initial_view else pledges
    pledges_by_candidate_election = _group_pledges_by_candidate_election(pledges_for_response)
    election_sections = _build_election_sections(
        election_links,
        pledges_by_candidate_election,
        include_pledges=not is_initial_view,
    )

    terms_fetch_started_at = _detail_perf_now()
    try:
        terms = _fetch_terms_rows(candidate_id=candidate_id, limit="200")
    except Exception as exc:
        app.logger.exception("api_politician_detail terms fetch failed: candidate_id=%s error=%s", candidate_id, exc)
        terms = []
        detail_warnings.append("terms")
    terms_fetch_ms = _detail_perf_ms(terms_fetch_started_at)
    _detail_perf_log(candidate_id, "terms_fetch", terms_fetch_ms, rows=len(terms), view=view_mode)
    _detail_perf_log(
        candidate_id,
        "election_links_terms_fetch",
        election_links_fetch_ms + terms_fetch_ms,
        election_links_ms=round(election_links_fetch_ms, 2),
        terms_ms=round(terms_fetch_ms, 2),
        view=view_mode,
    )

    candidate = _apply_candidate_latest_fields(candidate, election_links, terms)

    payload = {
        "candidate": _build_candidate_initial_payload(candidate) if is_initial_view else candidate,
        "pledges": pledges_for_response,
        "election_history": [] if is_initial_view else election_links,
        "election_sections": election_sections,
        "terms": [] if is_initial_view else terms,
        "is_admin": is_admin,
    }
    if detail_warnings:
        payload["warning"] = f"partial_data:{','.join(detail_warnings)}"
    response = jsonify(payload)
    payload_bytes = None
    if DEBUG_MODE:
        payload_bytes = len(response.get_data(as_text=False) or b"")
    _detail_perf_log(
        candidate_id,
        "response_payload",
        0.0,
        bytes=payload_bytes,
        has_warning=bool(detail_warnings),
        join_mode=join_mode,
        tree_cache_state=tree_cache_state,
        view=view_mode,
    )
    _detail_perf_log(
        candidate_id,
        "total",
        _detail_perf_ms(total_started_at),
        payload_bytes=payload_bytes,
        pledge_count=len(pledges_for_response),
        election_sections=len(election_sections),
        join_mode=join_mode,
        tree_cache_state=tree_cache_state,
        view=view_mode,
    )
    return response


def _fetch_single_visible_pledge_for_candidate(candidate_id, pledge_id, is_admin):
    candidate_election_rows = _supabase_get_with_select_fallback(
        "candidate_elections",
        query_params={
            "candidate_id": f"eq.{candidate_id}",
            "limit": "1000",
        },
        select_candidates=[
            "id",
            "id,candidate_id",
            "*",
        ],
    )
    candidate_election_ids = [row.get("id") for row in candidate_election_rows if row.get("id") is not None]
    candidate_election_filter = _to_in_filter(candidate_election_ids)
    if not candidate_election_filter:
        return None

    pledge_rows = _supabase_get_with_select_fallback(
        "pledges",
        query_params={
            "id": f"eq.{pledge_id}",
            "candidate_election_id": candidate_election_filter,
            "limit": "1",
        },
        select_candidates=[
            "id,candidate_election_id,sort_order,title,raw_text,category,timeline_text,finance_text,parse_type,structure_version,fulfillment_rate,status,created_at,created_by,updated_at,updated_by",
            "id,candidate_election_id,sort_order,title,raw_text,category,timeline_text,finance_text,parse_type,structure_version,fulfillment_rate,status,created_at,updated_at",
            "id,candidate_election_id,sort_order,title,raw_text,category,timeline_text,finance_text,parse_type,structure_version,fulfillment_rate,status,created_at",
            "id,candidate_election_id,sort_order,title,raw_text,category,status,created_at",
            "id,candidate_election_id,sort_order,title,raw_text,category,status",
            "id,candidate_election_id,title,raw_text,category,status",
            "id,candidate_election_id,title,raw_text",
            "*",
        ],
    )
    if not pledge_rows:
        return None

    pledge = dict(pledge_rows[0])
    status = str(pledge.get("status") or "active").strip()
    if status == "deleted":
        return None
    if status == "hidden" and not is_admin:
        return None
    pledge["candidate_id"] = candidate_id
    return pledge


@app.route("/api/politicians/<candidate_id>/pledges/<pledge_id>/detail", methods=["GET"])
def api_politician_pledge_detail(candidate_id, pledge_id):
    candidate_id = str(candidate_id or "").strip()
    pledge_id = str(pledge_id or "").strip()
    if not candidate_id or candidate_id.lower() in {"undefined", "null", "none", "nan"}:
        return jsonify({"error": "invalid candidate_id"}), 400
    if not pledge_id or pledge_id.lower() in {"undefined", "null", "none", "nan"}:
        return jsonify({"error": "invalid pledge_id"}), 400

    started_at = _detail_perf_now()
    try:
        is_admin = _session_is_admin()
    except Exception as exc:
        app.logger.exception("api_politician_pledge_detail admin check failed: candidate_id=%s pledge_id=%s error=%s", candidate_id, pledge_id, exc)
        is_admin = False

    warning = None
    tree_cache_state = "miss"
    payload_pledge = None
    fetch_started_at = _detail_perf_now()
    try:
        cached_pledges, _cached_fallback_goal_count, tree_cache_state = _detail_tree_cache_get(candidate_id, is_admin)
        _detail_perf_log(
            candidate_id,
            "pledge_detail_cache",
            0.0,
            pledge_id=pledge_id,
            cache_state=tree_cache_state,
        )
        if tree_cache_state == "hit":
            for cached in cached_pledges:
                if str(cached.get("id") or "").strip() == pledge_id:
                    payload_pledge = dict(cached)
                    break

        if payload_pledge is None:
            tree_cache_state = "miss"
            pledge = _fetch_single_visible_pledge_for_candidate(candidate_id, pledge_id, is_admin)
            if pledge is None:
                return jsonify({"error": "not found"}), 404
            try:
                processed_rows = _attach_pledge_tree_rows([pledge])
            except Exception as exc:
                app.logger.exception("api_politician_pledge_detail tree attach failed: candidate_id=%s pledge_id=%s error=%s", candidate_id, pledge_id, exc)
                processed_rows = [pledge]
                warning = "pledge_tree"
            fallback_goal_count = _hydrate_missing_pledge_goals(processed_rows)
            if fallback_goal_count:
                warning = "pledge_tree_fallback"
            payload_pledge = dict(processed_rows[0]) if processed_rows else pledge
        _detail_perf_log(
            candidate_id,
            "pledge_detail_fetch",
            _detail_perf_ms(fetch_started_at),
            pledge_id=pledge_id,
            cache_state=tree_cache_state,
            has_warning=bool(warning),
        )
    except RuntimeError as exc:
        app.logger.exception("api_politician_pledge_detail runtime error: candidate_id=%s pledge_id=%s error=%s", candidate_id, pledge_id, exc)
        return runtime_error_response(
            exc,
            default_message="failed to load pledge detail",
            network_message="pledge detail fetch failed due to network issue",
            schema_message="pledge detail schema mismatch",
        )
    except Exception as exc:
        app.logger.exception("api_politician_pledge_detail unexpected error: candidate_id=%s pledge_id=%s error=%s", candidate_id, pledge_id, exc)
        return jsonify({"error": "failed to load pledge detail"}), 500

    payload = {
        "candidate_id": candidate_id,
        "is_admin": is_admin,
        "pledge": _build_pledge_detail_payload(payload_pledge),
    }
    if warning:
        payload["warning"] = warning

    response = jsonify(payload)
    payload_bytes = None
    if DEBUG_MODE:
        payload_bytes = len(response.get_data(as_text=False) or b"")
    _detail_perf_log(
        candidate_id,
        "pledge_detail_total",
        _detail_perf_ms(started_at),
        pledge_id=pledge_id,
        cache_state=tree_cache_state,
        payload_bytes=payload_bytes,
        has_warning=bool(warning),
    )
    return response


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


