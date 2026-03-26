from routes_bootstrap import bind_core, runtime_error_response

bind_core(globals())


def _db_progress_rate_to_score(rate_value):
    try:
        rate = float(rate_value)
    except (TypeError, ValueError):
        return None
    if rate < 0:
        return None
    score = (rate / 20.0) if rate > 5 else rate
    if score < 0 or score > 5:
        return None
    return round(score, 2)


PROGRESS_OVERVIEW_DEFAULT_LIMIT = 200
PROGRESS_OVERVIEW_MAX_LIMIT = 500
PROGRESS_OVERVIEW_IN_CHUNK_SIZE = 180


def _unique_string_values(values):
    seen = set()
    ordered = []
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _chunk_values(values, chunk_size):
    rows = list(values or [])
    size = max(1, int(chunk_size or 1))
    for idx in range(0, len(rows), size):
        yield rows[idx: idx + size]


def _supabase_fetch_in_chunks(table, in_column, ids, *, select, limit_per_chunk="5000", order=None):
    deduped_ids = _unique_string_values(ids)
    if not deduped_ids:
        return []

    rows = []
    for chunk in _chunk_values(deduped_ids, PROGRESS_OVERVIEW_IN_CHUNK_SIZE):
        in_filter = _to_in_filter(chunk)
        if not in_filter:
            continue
        query_params = {
            "select": select,
            in_column: in_filter,
            "limit": str(limit_per_chunk),
        }
        if order:
            query_params["order"] = order
        rows.extend(_supabase_request("GET", table, query_params=query_params) or [])
    return rows


def _build_overview_base_rows(candidate_elections, candidate_map, election_map, election_type_filter):
    rows = []
    for candidate_election in candidate_elections or []:
        election = election_map.get(str(candidate_election.get("election_id"))) or {}
        election_type = election.get("election_type")
        if election_type_filter and election_type_filter != _normalize_compact_text(election_type):
            continue

        candidate = candidate_map.get(str(candidate_election.get("candidate_id"))) or {}
        rows.append(
            {
                "candidate_election_id": candidate_election.get("id"),
                "candidate_id": candidate_election.get("candidate_id"),
                "candidate_name": candidate.get("name"),
                "candidate_image": candidate.get("image"),
                "election_id": candidate_election.get("election_id"),
                "election_type": election_type,
                "election_title": _format_presidential_election_title(election.get("title")),
                "election_date": election.get("election_date"),
                "party": candidate_election.get("party"),
                "result": candidate_election.get("result"),
                "candidate_number": candidate_election.get("candidate_number"),
                "target_count": 0,
                "evaluated_count": 0,
                "avg_progress": None,
            }
        )

    return sorted(
        rows,
        key=lambda x: (str(x.get("election_date") or ""), str(x.get("election_title") or ""), str(x.get("candidate_name") or "")),
        reverse=True,
    )


def _build_progress_stats_for_candidate_elections(candidate_election_ids, *, is_admin):
    stats_by_candidate_election = {}
    ce_ids = _unique_string_values(candidate_election_ids)
    if not ce_ids:
        return stats_by_candidate_election

    pledges = _supabase_fetch_in_chunks(
        "pledges",
        "candidate_election_id",
        ce_ids,
        select="id,candidate_election_id,status,created_at",
        limit_per_chunk="10000",
        order="created_at.desc",
    )
    pledges = [row for row in pledges if str(row.get("status") or "active") != "deleted"]
    if not is_admin:
        pledges = [row for row in pledges if str(row.get("status") or "active") != "hidden"]

    pledge_ids = _unique_string_values([row.get("id") for row in pledges if row.get("id") is not None])
    if not pledge_ids:
        return stats_by_candidate_election

    node_rows = _supabase_fetch_in_chunks(
        "pledge_nodes",
        "pledge_id",
        pledge_ids,
        select="id,pledge_id,node_type,name,content,level,sort_order,parent_id,is_leaf,created_at",
        limit_per_chunk="50000",
    )
    node_ids = _unique_string_values([row.get("id") for row in node_rows if row.get("id") is not None])

    progress_rows = []
    if node_ids:
        progress_rows = _supabase_fetch_in_chunks(
            "pledge_node_progress",
            "pledge_node_id",
            node_ids,
            select="id,pledge_node_id,progress_rate,evaluation_date,created_at",
            limit_per_chunk="100000",
        )
    latest_progress_by_node = _latest_progress_row_map(progress_rows)

    nodes_by_pledge = {}
    for row in node_rows:
        key = str(row.get("pledge_id"))
        if not key:
            continue
        nodes_by_pledge.setdefault(key, []).append(row)

    for pledge in pledges:
        ce_key = str(pledge.get("candidate_election_id"))
        if not ce_key:
            continue
        context = _build_progress_node_context(nodes_by_pledge.get(str(pledge.get("id")), []))
        targets = context.get("progress_targets") or []
        stat = stats_by_candidate_election.setdefault(
            ce_key,
            {"target_count": 0, "evaluated_count": 0, "rate_sum": 0.0, "rate_count": 0},
        )
        for target in targets:
            node_id = target.get("id")
            if node_id is None:
                continue
            stat["target_count"] += 1
            latest = latest_progress_by_node.get(str(node_id))
            if not latest:
                continue
            score = _db_progress_rate_to_score(latest.get("progress_rate"))
            if score is None:
                continue
            stat["evaluated_count"] += 1
            stat["rate_sum"] += score
            stat["rate_count"] += 1

    return stats_by_candidate_election


@app.route("/progress")
def progress_page():
    return render_template("progress.html")

@app.route("/api/progress-overview", methods=["GET"])
def api_progress_overview():
    limit, offset = _pagination_params(default_limit=PROGRESS_OVERVIEW_DEFAULT_LIMIT, max_limit=PROGRESS_OVERVIEW_MAX_LIMIT)
    election_type_filter = _normalize_compact_text(request.args.get("election_type"))
    is_admin = _is_admin(_session_user_id())
    cache_key = f"api_progress_overview:{'admin' if is_admin else 'public'}:{election_type_filter or '-'}:{limit}:{offset}"
    cached = _cache_get(cache_key)
    if cached:
        return jsonify(
            {
                "rows": cached.get("rows") or [],
                "total": int(cached.get("total") or 0),
                "limit": limit,
                "offset": offset,
            }
        )

    try:
        candidates = _supabase_request(
            "GET",
            "candidates",
            query_params={
                "select": "id,name,image",
                "order": "name.asc",
                "limit": "2000",
            },
        ) or []
        candidate_map = {str(row.get("id")): row for row in candidates if row.get("id") is not None}

        candidate_elections = _supabase_request(
            "GET",
            "candidate_elections",
            query_params={
                "select": "id,candidate_id,election_id,party,result,is_elect,candidate_number,created_at",
                "order": "created_at.desc",
                "limit": "10000",
            },
        ) or []
        if not candidate_elections:
            return jsonify({"rows": [], "total": 0, "limit": limit, "offset": offset})

        election_ids = _unique_string_values([row.get("election_id") for row in candidate_elections if row.get("election_id") is not None])
        election_rows = _supabase_fetch_in_chunks(
            "elections",
            "id",
            election_ids,
            select="id,election_type,title,election_date",
            limit_per_chunk="5000",
        )
        election_map = {str(row.get("id")): row for row in election_rows if row.get("id") is not None}

        base_rows = _build_overview_base_rows(candidate_elections, candidate_map, election_map, election_type_filter)
        total = len(base_rows)
        if total == 0:
            return jsonify({"rows": [], "total": 0, "limit": limit, "offset": offset})

        paged_rows, _ = _slice_rows(base_rows, limit, offset)
        if not paged_rows:
            return jsonify({"rows": [], "total": total, "limit": limit, "offset": offset})

        stats_by_candidate_election = _build_progress_stats_for_candidate_elections(
            [row.get("candidate_election_id") for row in paged_rows if row.get("candidate_election_id") is not None],
            is_admin=is_admin,
        )

        for row in paged_rows:
            stat = stats_by_candidate_election.get(str(row.get("candidate_election_id"))) or {}
            rate_count = int(stat.get("rate_count") or 0)
            avg_progress = None
            if rate_count > 0:
                avg_progress = round(float(stat.get("rate_sum") or 0) / rate_count, 2)

            row["target_count"] = int(stat.get("target_count") or 0)
            row["evaluated_count"] = int(stat.get("evaluated_count") or 0)
            row["avg_progress"] = avg_progress

        _cache_set(cache_key, {"rows": paged_rows, "total": total})
        return jsonify({"rows": paged_rows, "total": total, "limit": limit, "offset": offset})
    except RuntimeError as exc:
        app.logger.exception("progress overview fetch failed: %s", exc)
        return runtime_error_response(
            exc,
            default_message="failed to load progress overview",
            network_message="이행현황 데이터를 불러오는 중 연결 문제가 발생했습니다.",
            schema_message="progress overview schema mismatch",
            debug_prefix="progress overview failed",
        )
    except Exception as exc:
        app.logger.exception("unexpected progress overview error: %s", exc)
        return jsonify({"error": "failed to load progress overview"}), 500

@app.route("/api/progress-admin/record", methods=["POST"])
@api_login_required
def api_progress_admin_record():
    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}

    pledge_node_id = str(payload.get("pledge_node_id") or "").strip()
    evaluation_date = str(payload.get("evaluation_date") or "").strip()
    reason = str(payload.get("reason") or "").strip() or None
    evaluator = str(payload.get("evaluator") or "").strip() or None

    source_id = str(payload.get("source_id") or "").strip() or None
    source_title = str(payload.get("source_title") or "").strip()
    source_url = str(payload.get("source_url") or "").strip() or None
    source_type = _normalize_source_type(payload.get("source_type"))
    source_publisher = str(payload.get("source_publisher") or "").strip() or None
    source_published_at = str(payload.get("source_published_at") or "").strip() or None
    source_summary = str(payload.get("source_summary") or "").strip() or None
    source_role = str(payload.get("source_role") or "").strip() or "primary"
    quoted_text = str(payload.get("quoted_text") or "").strip() or None
    page_no = str(payload.get("page_no") or "").strip() or None
    link_note = str(payload.get("note") or "").strip() or None

    if not pledge_node_id:
        return jsonify({"error": "pledge_node_id is required"}), 400
    if not evaluation_date:
        return jsonify({"error": "evaluation_date is required"}), 400
    try:
        datetime.strptime(evaluation_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "evaluation_date must be in YYYY-MM-DD format"}), 400

    if source_published_at:
        try:
            datetime.strptime(source_published_at, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "source_published_at must be in YYYY-MM-DD format"}), 400

    if source_url:
        try:
            parsed_source_url = parse.urlparse(source_url)
        except Exception:
            return jsonify({"error": "source_url is invalid"}), 400
        if str(parsed_source_url.scheme or "").lower() not in {"http", "https"}:
            return jsonify({"error": "source_url must be http(s)"}), 400

    try:
        progress_rate = _normalize_progress_rate(payload.get("progress_rate"))
        status = _normalize_progress_status(payload.get("status"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        pledge_node = _get_pledge_node(pledge_node_id)
        if not pledge_node:
            return jsonify({"error": "pledge_node not found"}), 404

        pledge_id = pledge_node.get("pledge_id")
        node_rows = _fetch_pledge_nodes(pledge_id)
        node_context = _build_progress_node_context(node_rows)
        target_ids = {str(row.get("id")) for row in (node_context.get("progress_targets") or []) if row.get("id") is not None}
        if str(pledge_node_id) not in target_ids:
            return jsonify({"error": "progress target must be an item or an item-less promise under an execution-method goal"}), 400
    except RuntimeError as exc:
        app.logger.exception("progress target lookup failed: pledge_node_id=%s error=%s", pledge_node_id, exc)
        return runtime_error_response(
            exc,
            default_message="failed to load progress target",
            network_message="database connection issue while loading progress target",
            schema_message="progress node schema mismatch",
        )
    except Exception as exc:
        app.logger.exception("unexpected progress target lookup error: pledge_node_id=%s error=%s", pledge_node_id, exc)
        return jsonify({"error": "failed to resolve progress target"}), 500

    now = _now_iso()
    try:
        latest_progress = _fetch_latest_progress_row(pledge_node_id)
        if latest_progress and latest_progress.get("id") is not None:
            progress_id = latest_progress.get("id")
            patched = _supabase_patch_with_optional_fields(
                "pledge_node_progress",
                query_params={"id": f"eq.{progress_id}"},
                payload={
                    "progress_rate": progress_rate,
                    "status": status,
                    "reason": reason,
                    "evaluator": evaluator,
                    "evaluation_date": evaluation_date,
                    "updated_at": now,
                    "updated_by": uid,
                },
                optional_fields={"status", "reason", "evaluator", "evaluation_date", "updated_at", "updated_by"},
            )
            progress_row = dict(latest_progress)
            progress_row.update(patched)
            progress_row["id"] = progress_id
        else:
            progress_row = _supabase_insert_with_optional_fields(
                "pledge_node_progress",
                payload={
                    "pledge_node_id": pledge_node_id,
                    "progress_rate": progress_rate,
                    "status": status,
                    "reason": reason,
                    "evaluator": evaluator,
                    "evaluation_date": evaluation_date,
                    "created_at": now,
                    "created_by": uid,
                    "updated_at": now,
                    "updated_by": uid,
                },
                optional_fields={
                    "status",
                    "reason",
                    "evaluator",
                    "evaluation_date",
                    "created_at",
                    "created_by",
                    "updated_at",
                    "updated_by",
                },
            )
    except RuntimeError as exc:
        app.logger.exception("progress save failed: pledge_node_id=%s error=%s", pledge_node_id, exc)
        return runtime_error_response(
            exc,
            default_message="failed to save progress record",
            network_message="database connection issue while saving progress",
            schema_message="progress-related table schema mismatch",
        )

    progress_id = progress_row.get("id")
    if not progress_id:
        return jsonify({"error": "progress save failed"}), 500

    warning_code = None
    saved_source_id = source_id
    source_row = None
    progress_source_row = None

    try:
        if saved_source_id:
            if not _ensure_source_exists(saved_source_id):
                return jsonify({"error": "source not found"}), 404
        elif source_title:
            source_row = _supabase_insert_with_optional_fields(
                "sources",
                payload={
                    "title": source_title,
                    "url": source_url,
                    "source_type": source_type,
                    "publisher": source_publisher,
                    "published_at": source_published_at,
                    "summary": source_summary,
                    "created_at": now,
                    "created_by": uid,
                    "updated_at": now,
                    "updated_by": uid,
                },
                optional_fields={
                    "url",
                    "source_type",
                    "publisher",
                    "published_at",
                    "summary",
                    "created_at",
                    "created_by",
                    "updated_at",
                    "updated_by",
                },
            )
            saved_source_id = source_row.get("id")
            if not saved_source_id:
                warning_code = "source_insert_failed"

        if saved_source_id:
            existing_progress_source = _fetch_latest_progress_source_link(progress_id)
            if existing_progress_source and existing_progress_source.get("id") is not None:
                progress_source_id = existing_progress_source.get("id")
                patched_link = _supabase_patch_with_optional_fields(
                    "pledge_node_progress_sources",
                    query_params={"id": f"eq.{progress_source_id}"},
                    payload={
                        "source_id": saved_source_id,
                        "source_role": source_role,
                        "quoted_text": quoted_text,
                        "page_no": page_no,
                        "note": link_note,
                        "updated_at": now,
                        "updated_by": uid,
                    },
                    optional_fields={"source_role", "quoted_text", "page_no", "note", "updated_at", "updated_by"},
                )
                progress_source_row = dict(existing_progress_source)
                progress_source_row.update(patched_link)
                progress_source_row["id"] = progress_source_id
            else:
                progress_source_row = _supabase_insert_with_optional_fields(
                    "pledge_node_progress_sources",
                    payload={
                        "pledge_node_progress_id": progress_id,
                        "source_id": saved_source_id,
                        "source_role": source_role,
                        "quoted_text": quoted_text,
                        "page_no": page_no,
                        "note": link_note,
                        "created_at": now,
                        "created_by": uid,
                        "updated_at": now,
                        "updated_by": uid,
                    },
                    optional_fields={
                        "source_role",
                        "quoted_text",
                        "page_no",
                        "note",
                        "created_at",
                        "created_by",
                        "updated_at",
                        "updated_by",
                    },
                )
        elif source_title:
            warning_code = warning_code or "source_link_skipped"
    except RuntimeError as exc:
        app.logger.exception("progress source save failed: progress_id=%s error=%s", progress_id, exc)
        warning_code = "source_save_failed"

    response_payload = {
        "ok": True,
        "progress": progress_row,
        "source_id": saved_source_id,
        "source": source_row,
        "progress_source": progress_source_row,
    }
    if warning_code:
        response_payload["warning"] = warning_code
    return jsonify(response_payload), 201


def _source_has_any_reference(source_id):
    source_id = str(source_id or "").strip()
    if not source_id:
        return False
    source_filter = f"eq.{source_id}"

    node_refs = _supabase_get_with_select_fallback(
        "pledge_node_sources",
        query_params={"source_id": source_filter, "limit": "1"},
        select_candidates=[
            "id,source_id",
            "id",
            "*",
        ],
    )
    if node_refs:
        return True

    progress_refs = _supabase_get_with_select_fallback(
        "pledge_node_progress_sources",
        query_params={"source_id": source_filter, "limit": "1"},
        select_candidates=[
            "id,source_id",
            "id",
            "*",
        ],
    )
    return bool(progress_refs)


@app.route("/api/admin/progress-records/<progress_id>", methods=["DELETE"])
@api_admin_required
def api_admin_progress_record_delete(progress_id):
    progress_id = str(progress_id or "").strip()
    if not progress_id:
        return jsonify({"error": "invalid progress_id"}), 400

    try:
        progress_rows = _supabase_get_with_select_fallback(
            "pledge_node_progress",
            query_params={"id": f"eq.{progress_id}", "limit": "1"},
            select_candidates=[
                "id,pledge_node_id",
                "id",
                "*",
            ],
        )
    except RuntimeError as exc:
        app.logger.exception("progress lookup failed: progress_id=%s error=%s", progress_id, exc)
        return runtime_error_response(
            exc,
            default_message="failed to load progress record",
            network_message="database connection issue while loading progress record",
            schema_message="progress-related table schema mismatch",
            debug_prefix="progress lookup failed",
        )

    if not progress_rows:
        return jsonify({"error": "not found"}), 404

    deleted_orphan_source_ids = []
    try:
        progress_source_rows = _supabase_get_with_select_fallback(
            "pledge_node_progress_sources",
            query_params={"pledge_node_progress_id": f"eq.{progress_id}", "limit": "5000"},
            select_candidates=[
                "id,source_id,pledge_node_progress_id",
                "id,source_id",
                "id",
                "*",
            ],
        )
        source_ids = []
        for row in progress_source_rows:
            source_id = str(row.get("source_id") or "").strip()
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)

        _supabase_request(
            "DELETE",
            "pledge_node_progress_sources",
            query_params={"pledge_node_progress_id": f"eq.{progress_id}"},
        )
        _supabase_request(
            "DELETE",
            "pledge_node_progress",
            query_params={"id": f"eq.{progress_id}"},
        )

        for source_id in source_ids:
            if _source_has_any_reference(source_id):
                continue
            _supabase_request(
                "DELETE",
                "sources",
                query_params={"id": f"eq.{source_id}"},
            )
            deleted_orphan_source_ids.append(source_id)

        _invalidate_api_cache()
    except RuntimeError as exc:
        app.logger.exception("progress delete failed: progress_id=%s error=%s", progress_id, exc)
        return runtime_error_response(
            exc,
            default_message="failed to delete progress record",
            network_message="database connection issue while deleting progress record",
            foreign_key_message="관련된 데이터가 남아 있어 평가를 삭제할 수 없습니다.",
            schema_message="progress-related table schema mismatch",
            debug_prefix="progress delete failed",
        )

    return jsonify(
        {
            "ok": True,
            "deleted_progress_id": progress_id,
            "deleted_orphan_source_ids": deleted_orphan_source_ids,
        }
    )
