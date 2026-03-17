from routes_bootstrap import bind_core

bind_core(globals())

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "time": _now_iso()}), 200


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/candidate")
@login_required
def candidate_page():
    return render_template("candidate.html")


@app.route("/election")
@login_required
def election_page():
    return render_template("election.html")


@app.route("/pledge")
@login_required
def pledge_page():
    return render_template("pledge.html")


@app.route("/progress")
def progress_page():
    return render_template("progress.html")


@app.route("/promises")
def promises_page():
    return render_template("promises.html")


@app.route("/politicians")
def politicians_page():
    return render_template("politicians.html")


@app.route("/politicians/<candidate_id>")
def politician_detail_page(candidate_id):
    normalized = str(candidate_id or "").strip().lower()
    if not normalized or normalized in {"undefined", "null", "none", "nan"}:
        return redirect(url_for("politicians_page"))
    return render_template("politician_detail.html", candidate_id=candidate_id)


@app.route("/mypage")
@login_required
def mypage():
    return render_template("mypage.html")


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


@app.route("/api/promises", methods=["GET"])
def api_promises():
    limit, offset = _pagination_params(default_limit=None, max_limit=500)
    is_admin = _is_admin(_session_user_id())
    cache_key = f"api_promises:{'admin' if is_admin else 'public'}"
    cached = _cache_get(cache_key)
    if cached:
        candidates = cached.get("candidates") or []
        cards = cached.get("cards") or []
    else:
        candidates = _supabase_request(
            "GET",
            "candidates",
            query_params={"select": "id,name", "order": "name.asc", "limit": "500"},
        ) or []

        candidate_elections = _supabase_request(
            "GET",
            "candidate_elections",
            query_params={"select": "id,candidate_id,election_id,party,result,candidate_number", "limit": "5000"},
        ) or []
        candidate_election_map = {
            str(row.get("id")): row
            for row in candidate_elections
            if row.get("id") is not None
        }

        election_ids = []
        for row in candidate_elections:
            election_id = row.get("election_id")
            if election_id is None:
                continue
            election_id_str = str(election_id)
            if election_id_str not in election_ids:
                election_ids.append(election_id_str)

        election_map = {}
        election_filter = _to_in_filter(election_ids)
        if election_filter:
            elections = _supabase_request(
                "GET",
                "elections",
                query_params={
                    "select": "id,election_type,title,election_date",
                    "id": election_filter,
                    "limit": "5000",
                },
            ) or []
            election_map = {str(row.get("id")): row for row in elections if row.get("id") is not None}

        pledges = _supabase_request(
            "GET",
            "pledges",
            query_params={
                "select": "id,candidate_election_id,sort_order,title,raw_text,category,status,created_at,created_by,updated_at,updated_by",
                "order": "sort_order.asc.nullslast,created_at.desc",
                "limit": "1000",
            },
        ) or []

        for pledge in pledges:
            candidate_election = candidate_election_map.get(str(pledge.get("candidate_election_id"))) or {}
            election = election_map.get(str(candidate_election.get("election_id"))) or {}
            pledge["candidate_id"] = candidate_election.get("candidate_id")
            pledge["election_id"] = candidate_election.get("election_id")
            pledge["party"] = candidate_election.get("party")
            pledge["result"] = candidate_election.get("result")
            pledge["candidate_number"] = candidate_election.get("candidate_number")
            pledge["election_type"] = election.get("election_type")
            pledge["election_title"] = election.get("title")
            pledge["election_date"] = election.get("election_date")

        pledges = [p for p in pledges if str(p.get("status") or "active") != "deleted"]
        if not is_admin:
            pledges = [p for p in pledges if str(p.get("status") or "active") != "hidden"]

        pledges = _attach_pledge_tree_rows(pledges)
        cards = []

        for pledge in pledges:
            goals = pledge.get("goals") or []
            for goal in goals:
                goal_text = str(goal.get("text") or "").strip()
                if not _is_execution_method_goal_text(goal_text):
                    continue

                promises = goal.get("promises") or []
                for promise in promises:
                    promise_text = str(promise.get("text") or "").strip()
                    items = promise.get("items") or []

                    item_texts = []
                    item_rates = []
                    for item in items:
                        item_text = str(item.get("text") or "").strip()
                        if item_text:
                            item_texts.append(item_text)
                        rate_raw = item.get("progress_rate")
                        try:
                            rate = float(rate_raw)
                        except (TypeError, ValueError):
                            continue
                        if 0 <= rate <= 5:
                            item_rates.append(rate)

                    if item_texts:
                        content = " / ".join(item_texts)
                        progress_rate = round(sum(item_rates) / len(item_rates), 2) if item_rates else None
                    else:
                        content = ""
                        progress_rate = None
                        rate_raw = promise.get("progress_rate")
                        try:
                            rate = float(rate_raw)
                        except (TypeError, ValueError):
                            rate = None
                        if rate is not None and 0 <= rate <= 5:
                            progress_rate = round(rate, 2)

                    if not promise_text and not content:
                        continue

                    cards.append(
                        {
                            "id": f"{pledge.get('id')}:{promise.get('id')}",
                            "candidate_id": pledge.get("candidate_id"),
                            "candidate_election_id": pledge.get("candidate_election_id"),
                            "pledge_id": pledge.get("id"),
                            "promise_node_id": promise.get("id"),
                            "promise_title": promise_text,
                            "content": content,
                            "progress_rate": progress_rate,
                            "category": pledge.get("category"),
                            "election_id": pledge.get("election_id"),
                            "election_type": pledge.get("election_type"),
                            "election_title": pledge.get("election_title"),
                            "election_date": pledge.get("election_date"),
                            "party": pledge.get("party"),
                            "result": pledge.get("result"),
                            "candidate_number": pledge.get("candidate_number"),
                            "pledge_sort_order": pledge.get("sort_order"),
                            "promise_sort_order": promise.get("sort_order"),
                        }
                    )

        cards = sorted(
            cards,
            key=lambda row: (
                str(row.get("election_date") or ""),
                str(row.get("candidate_id") or ""),
                _safe_int(row.get("pledge_sort_order"), 999999),
                _safe_int(row.get("promise_sort_order"), 999999),
            ),
            reverse=True,
        )
        _cache_set(cache_key, {"candidates": candidates, "cards": cards})

    rows, total = _slice_rows(cards, limit, offset)
    return jsonify({"candidates": candidates, "promises": rows, "total": total, "limit": limit, "offset": offset})


@app.route("/api/progress-overview", methods=["GET"])
def api_progress_overview():
    limit, offset = _pagination_params(default_limit=None, max_limit=2000)
    election_type_filter = _normalize_compact_text(request.args.get("election_type"))
    is_admin = _is_admin(_session_user_id())
    cache_key = f"api_progress_overview:{'admin' if is_admin else 'public'}:{election_type_filter or '-'}"
    cached = _cache_get(cache_key)
    if cached:
        cached_rows = cached.get("rows") or []
        rows, total = _slice_rows(cached_rows, limit, offset)
        return jsonify({"rows": rows, "total": total, "limit": limit, "offset": offset})

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

    election_ids = []
    for row in candidate_elections:
        eid = row.get("election_id")
        if eid is None:
            continue
        eid_str = str(eid)
        if eid_str not in election_ids:
            election_ids.append(eid_str)
    election_map = {}
    if election_ids:
        election_filter = _to_in_filter(election_ids)
        election_rows = _supabase_request(
            "GET",
            "elections",
            query_params={
                "select": "id,election_type,title,election_date",
                "id": election_filter,
                "limit": "10000",
            },
        ) or []
        election_map = {str(row.get("id")): row for row in election_rows if row.get("id") is not None}

    candidate_election_ids = [row.get("id") for row in candidate_elections if row.get("id") is not None]
    ce_filter = _to_in_filter(candidate_election_ids)
    pledges = []
    if ce_filter:
        pledges = _supabase_request(
            "GET",
            "pledges",
            query_params={
                "select": "id,candidate_election_id,sort_order,title,status,created_at",
                "candidate_election_id": ce_filter,
                "order": "sort_order.asc.nullslast,created_at.desc",
                "limit": "50000",
            },
        ) or []
        pledges = [row for row in pledges if str(row.get("status") or "active") != "deleted"]
        if not is_admin:
            pledges = [row for row in pledges if str(row.get("status") or "active") != "hidden"]

    pledge_ids = [row.get("id") for row in pledges if row.get("id") is not None]
    pledge_filter = _to_in_filter(pledge_ids)
    node_rows = []
    if pledge_filter:
        node_rows = _supabase_request(
            "GET",
            "pledge_nodes",
            query_params={
                "select": "id,pledge_id,name,content,sort_order,parent_id,is_leaf,created_at",
                "pledge_id": pledge_filter,
                "limit": "100000",
            },
        ) or []

    node_ids = [row.get("id") for row in node_rows if row.get("id") is not None]
    node_filter = _to_in_filter(node_ids)
    progress_rows = []
    if node_filter:
        progress_rows = _supabase_request(
            "GET",
            "pledge_node_progress",
            query_params={
                "select": "id,pledge_node_id,progress_rate,evaluation_date,created_at",
                "pledge_node_id": node_filter,
                "limit": "200000",
            },
        ) or []
    latest_progress_by_node = _latest_progress_row_map(progress_rows)

    nodes_by_pledge = {}
    for row in node_rows:
        key = str(row.get("pledge_id"))
        if not key:
            continue
        nodes_by_pledge.setdefault(key, []).append(row)

    stats_by_candidate_election = {}
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
            rate_raw = latest.get("progress_rate")
            try:
                rate = float(rate_raw)
            except (TypeError, ValueError):
                continue
            if rate < 0 or rate > 5:
                continue
            stat["evaluated_count"] += 1
            stat["rate_sum"] += rate
            stat["rate_count"] += 1

    rows = []
    for row in candidate_elections:
        election = election_map.get(str(row.get("election_id"))) or {}
        election_type = election.get("election_type")
        if election_type_filter and election_type_filter != _normalize_compact_text(election_type):
            continue

        candidate = candidate_map.get(str(row.get("candidate_id"))) or {}
        stat = stats_by_candidate_election.get(str(row.get("id"))) or {}
        rate_count = int(stat.get("rate_count") or 0)
        avg_progress = None
        if rate_count > 0:
            avg_progress = round(float(stat.get("rate_sum") or 0) / rate_count, 2)

        rows.append(
            {
                "candidate_election_id": row.get("id"),
                "candidate_id": row.get("candidate_id"),
                "candidate_name": candidate.get("name"),
                "candidate_image": candidate.get("image"),
                "election_id": row.get("election_id"),
                "election_type": election_type,
                "election_title": election.get("title"),
                "election_date": election.get("election_date"),
                "party": row.get("party"),
                "result": row.get("result"),
                "candidate_number": row.get("candidate_number"),
                "target_count": int(stat.get("target_count") or 0),
                "evaluated_count": int(stat.get("evaluated_count") or 0),
                "avg_progress": avg_progress,
            }
        )

    rows = sorted(
        rows,
        key=lambda x: (str(x.get("election_date") or ""), str(x.get("election_title") or ""), str(x.get("candidate_name") or "")),
        reverse=True,
    )
    _cache_set(cache_key, {"rows": rows})
    sliced_rows, total = _slice_rows(rows, limit, offset)
    return jsonify({"rows": sliced_rows, "total": total, "limit": limit, "offset": offset})


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
        for pledge in pledges:
            pledge["goals"] = []

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
            "title": election_info.get("title"),
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
