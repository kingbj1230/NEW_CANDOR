from routes_bootstrap import bind_core, build_pledge_patch_payload, runtime_error_response
from routes.admin_common import FOREIGN_KEY_DELETE_ERROR, NETWORK_DELETE_ERROR, _unlink_reports_from_pledge
from services import pledge_source_service as _pledge_source_service

bind_core(globals())

def _normalize_source_target_path(value):
    text = str(value or "").strip().lower().replace(" ", "")
    if not text or text in {"__auto__", "auto", "default", "root"}:
        return None

    parts = [part for part in text.split("/") if part]
    if not parts:
        return None
    if len(parts) > 3:
        raise ValueError("source target_path is invalid")

    expected = ["g", "p", "i"]
    normalized_parts = []
    for idx, part in enumerate(parts):
        if ":" not in part:
            raise ValueError("source target_path is invalid")
        kind, order_text = part.split(":", 1)
        if idx >= len(expected) or kind != expected[idx]:
            raise ValueError("source target_path is invalid")
        try:
            order = int(order_text)
        except (TypeError, ValueError):
            raise ValueError("source target_path is invalid")
        if order < 1:
            raise ValueError("source target_path is invalid")
        normalized_parts.append(f"{kind}:{order}")

    return "/".join(normalized_parts)

def _normalize_source_link_scope(value):
    raw = str(value or "").strip()
    if not raw:
        return "pledge"
    compact = raw.lower().replace(" ", "").replace("_", "").replace("-", "")
    if compact in {"pledge", "pledges", "pledgeid", "공약"}:
        return "pledge"
    if compact in {"goal", "goals", "대항목"}:
        return "goal"
    if compact in {"node", "pledgenode", "pledgenodeid", "노드"}:
        # Backward compatibility: old node scope is treated as goal scope.
        return "goal"
    raise ValueError("source link_scope must be pledge or goal")

def _build_pledge_goal_target_map(node_rows):
    goal_map = {}
    rows = _sorted_node_rows(node_rows or [])
    if not rows:
        return goal_map

    root_rows = [
        row
        for row in rows
        if row.get("parent_id") is None
        and (
            str(row.get("node_type") or "").strip().lower() == "goal"
            or str(row.get("name") or "").strip().lower() == "goal"
        )
    ]
    goal_rows = _sorted_node_rows(root_rows)
    for goal_idx, goal_row in enumerate(goal_rows, start=1):
        goal_id = goal_row.get("id")
        if goal_id is None:
            continue
        goal_path = f"g:{goal_idx}"
        goal_map[goal_path] = {
            "node_id": str(goal_id),
            "title": str(goal_row.get("content") or "").strip(),
        }
    return goal_map

def _validate_goal_source_coverage(source_rows, goal_map):
    if not source_rows:
        return

    uses_goal_scope = any(str(row.get("link_scope") or "") == "goal" for row in source_rows)
    if not uses_goal_scope:
        return
    if not goal_map:
        raise ValueError("goal 연결 대상을 찾을 수 없습니다.")

    covered_paths = set()
    for row in source_rows:
        if str(row.get("link_scope") or "") != "goal":
            continue
        target_path = str(row.get("target_path") or "").strip()
        pledge_node_id = str(row.get("pledge_node_id") or "").strip()

        if target_path:
            if target_path not in goal_map:
                raise ValueError(f"goal target_path not found: {target_path}")
            covered_paths.add(target_path)
            continue

        if pledge_node_id:
            matched = None
            for path, info in goal_map.items():
                if str(info.get("node_id") or "") == pledge_node_id:
                    matched = path
                    break
            if not matched:
                raise ValueError("goal pledge_node_id is invalid")
            covered_paths.add(matched)
            continue

        raise ValueError("goal 연결 시 target_path가 필요합니다.")

    missing_paths = [path for path in goal_map.keys() if path not in covered_paths]
    if missing_paths:
        missing_labels = [str((goal_map.get(path) or {}).get("title") or path) for path in missing_paths]
        raise ValueError(f"goal 연결을 선택한 경우 모든 대항목(goal)에 출처가 필요합니다: {', '.join(missing_labels)}")

def _first_goal_node_id(goal_map):
    for info in (goal_map or {}).values():
        node_id = str((info or {}).get("node_id") or "").strip()
        if node_id:
            return node_id
    return None

def _is_not_null_constraint_error(exc, column_name=None):
    message = str(exc or "").lower()
    if "23502" not in message and "not-null constraint" not in message and "null value in column" not in message:
        return False
    if not column_name:
        return True
    return str(column_name or "").lower() in message

def _find_existing_source_by_url(url):
    source_url = str(url or "").strip()
    if not source_url:
        return None

    rows = _supabase_get_with_select_fallback(
        "sources",
        query_params={
            "url": f"eq.{source_url}",
            "limit": "5",
        },
        select_candidates=[
            "id,title,url,source_type,publisher,published_at,summary,note",
            "id,title,url,source_type,publisher,published_at,summary",
            "id,title,url,source_type,publisher,published_at",
            "id,title,url,source_type,publisher",
            "id,title,url,source_type",
            "id,title,url",
            "id,url",
            "*",
        ],
    ) or []

    for row in rows:
        if str(row.get("url") or "").strip() == source_url and row.get("id") is not None:
            return row
    return None

def _upsert_pledge_node_source_link(
    *,
    pledge_node_id,
    pledge_id,
    source_id,
    source_role,
    note,
    uid,
    now_iso,
):
    existing_rows = _supabase_get_with_select_fallback(
        NODE_SOURCE_TABLE,
        query_params={
            "pledge_node_id": f"eq.{pledge_node_id}",
            "source_id": f"eq.{source_id}",
            "limit": "1",
            "order": "id.desc",
        },
        select_candidates=[
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at,created_by,updated_at,updated_by",
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at,updated_at",
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at",
            "id,pledge_node_id,pledge_id,source_id,source_role,note",
            "id,pledge_node_id,source_id,source_role,note",
            "id,pledge_node_id,source_id",
            "*",
        ],
    )
    existing = existing_rows[0] if existing_rows else None
    if existing and existing.get("id") is not None:
        link_id = existing.get("id")
        patched = _supabase_patch_with_optional_fields(
            NODE_SOURCE_TABLE,
            query_params={"id": f"eq.{link_id}"},
            payload={
                "pledge_id": pledge_id,
                "source_role": source_role,
                "note": note,
                "updated_at": now_iso,
                "updated_by": uid,
            },
            optional_fields={"pledge_id", "source_role", "note", "updated_at", "updated_by"},
        )
        merged = dict(existing)
        merged.update(patched)
        merged["id"] = link_id
        return merged

    return _insert_node_source_row(
        payload={
            "pledge_node_id": pledge_node_id,
            "pledge_id": pledge_id,
            "source_id": source_id,
            "source_role": source_role,
            "note": note,
            "created_at": now_iso,
            "created_by": uid,
            "updated_at": now_iso,
            "updated_by": uid,
        }
    )

def _upsert_pledge_source_link(
    *,
    pledge_id,
    source_id,
    source_role,
    note,
    uid,
    now_iso,
):
    existing_rows = _supabase_get_with_select_fallback(
        NODE_SOURCE_TABLE,
        query_params={
            "pledge_id": f"eq.{pledge_id}",
            "pledge_node_id": "is.null",
            "source_id": f"eq.{source_id}",
            "limit": "1",
            "order": "id.desc",
        },
        select_candidates=[
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at,created_by,updated_at,updated_by",
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at,updated_at",
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at",
            "id,pledge_node_id,pledge_id,source_id,source_role,note",
            "id,pledge_node_id,pledge_id,source_id",
            "id,pledge_id,source_id",
            "*",
        ],
    )
    existing = existing_rows[0] if existing_rows else None
    if existing and existing.get("id") is not None:
        link_id = existing.get("id")
        patched = _supabase_patch_with_optional_fields(
            NODE_SOURCE_TABLE,
            query_params={"id": f"eq.{link_id}"},
            payload={
                "source_role": source_role,
                "note": note,
                "updated_at": now_iso,
                "updated_by": uid,
            },
            optional_fields={"source_role", "note", "updated_at", "updated_by"},
        )
        merged = dict(existing)
        merged.update(patched)
        merged["id"] = link_id
        return merged

    return _insert_node_source_row(
        payload={
            "pledge_node_id": None,
            "pledge_id": pledge_id,
            "source_id": source_id,
            "source_role": source_role,
            "note": note,
            "created_at": now_iso,
            "created_by": uid,
            "updated_at": now_iso,
            "updated_by": uid,
        }
    )

def _normalize_pledge_sources_payload(raw_sources):
    return _pledge_source_service.normalize_pledge_sources_payload(
        raw_sources,
        normalize_source_link_scope_fn=_normalize_source_link_scope,
        normalize_source_target_path_fn=_normalize_source_target_path,
        normalize_node_source_role_fn=_normalize_node_source_role,
        normalize_source_type_fn=_normalize_source_type,
    )

def _save_pledge_source_rows(pledge_id, source_rows, created_nodes, uid):
    return _pledge_source_service.save_pledge_source_rows(
        pledge_id,
        source_rows,
        created_nodes,
        uid,
        now_iso_fn=_now_iso,
        build_pledge_goal_target_map_fn=_build_pledge_goal_target_map,
        validate_goal_source_coverage_fn=_validate_goal_source_coverage,
        ensure_source_exists_fn=_ensure_source_exists,
        find_existing_source_by_url_fn=_find_existing_source_by_url,
        supabase_insert_with_optional_fields_fn=_supabase_insert_with_optional_fields,
        upsert_pledge_source_link_fn=_upsert_pledge_source_link,
        upsert_pledge_node_source_link_fn=_upsert_pledge_node_source_link,
        first_goal_node_id_fn=_first_goal_node_id,
        is_foreign_key_runtime_error_fn=_is_foreign_key_runtime_error,
        is_not_null_constraint_error_fn=_is_not_null_constraint_error,
    )

def _build_candidate_election_source_library(candidate_election_id):
    return _pledge_source_service.build_candidate_election_source_library(
        candidate_election_id,
        supabase_get_with_select_fallback_fn=_supabase_get_with_select_fallback,
        node_source_table=NODE_SOURCE_TABLE,
        to_in_filter_fn=_to_in_filter,
    )

@app.route("/api/pledges/source-library", methods=["GET"])
@api_login_required
def api_pledge_source_library():
    candidate_election_id = str(request.args.get("candidate_election_id") or "").strip()
    if not candidate_election_id:
        return jsonify({"error": "candidate_election_id is required"}), 400

    try:
        rows = _build_candidate_election_source_library(candidate_election_id)
    except RuntimeError as exc:
        if _is_missing_schema_runtime_error(exc):
            return jsonify({"candidate_election_id": candidate_election_id, "rows": [], "total": 0})
        app.logger.exception("Failed to load pledge source library (candidate_election_id=%s): %s", candidate_election_id, exc)
        return runtime_error_response(
            exc,
            default_message="출처 목록 조회에 실패했습니다.",
            network_message="데이터베이스 연결 문제로 출처 목록 조회에 실패했습니다.",
            schema_message="출처 관련 테이블 스키마를 확인해 주세요.",
            debug_prefix="source library fetch failed",
        )

    return jsonify(
        {
            "candidate_election_id": candidate_election_id,
            "rows": rows,
            "total": len(rows),
        }
    )

@app.route("/api/pledges", methods=["POST"])
def api_pledges():
    uid = _session_user_id()
    if not uid:
        return jsonify({"error": "login required"}), 401
    save_uid = uid

    payload = request.get_json(silent=True) or {}
    try:
        validated = _validate_pledge_payload(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        source_rows = _normalize_pledge_sources_payload(payload.get("sources"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    def _rollback_new_pledge(target_pledge_id):
        try:
            _delete_pledge_tree(target_pledge_id)
        except Exception as rollback_exc:
            app.logger.warning("Failed to rollback pledge tree %s: %s", target_pledge_id, rollback_exc)
        try:
            _supabase_request("DELETE", "pledges", query_params={"id": f"eq.{target_pledge_id}"})
        except Exception as rollback_exc:
            app.logger.warning("Failed to rollback pledge row %s: %s", target_pledge_id, rollback_exc)

    now = _now_iso()
    try:
        inserted = _supabase_insert_with_optional_fields(
            "pledges",
            payload={
                "candidate_election_id": validated["candidate_election_id"],
                "sort_order": validated["sort_order"],
                "title": validated["title"],
                "raw_text": validated["raw_text"],
                "category": validated["category"],
                "parse_type": validated["parse_type"],
                "structure_version": validated["structure_version"],
                "fulfillment_rate": validated["fulfillment_rate"],
                "status": validated["status"],
                "created_at": now,
                "created_by": save_uid,
                "updated_at": now,
                "updated_by": None,
            },
            optional_fields={"parse_type", "structure_version", "fulfillment_rate", "updated_by"},
        )
    except RuntimeError as exc:
        app.logger.exception("Pledge insert failed: %s", exc)
        return runtime_error_response(
            exc,
            default_message="공약 저장 중 오류가 발생했습니다.",
            network_message="데이터베이스 연결 문제로 공약 저장에 실패했습니다.",
            schema_message="pledges 테이블 스키마를 확인해 주세요.",
            debug_prefix="pledge insert failed",
        )
    pledge_id = inserted.get("id")
    if not pledge_id:
        return jsonify({"error": "pledge insert failed"}), 500

    try:
        _insert_pledge_tree(pledge_id, validated["raw_text"], save_uid)
    except ValueError as exc:
        _rollback_new_pledge(pledge_id)
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        _rollback_new_pledge(pledge_id)
        app.logger.exception("Pledge tree insert failed for pledge_id=%s: %s", pledge_id, exc)
        return runtime_error_response(
            exc,
            default_message="공약 구조 저장 중 오류가 발생했습니다.",
            network_message="데이터베이스 연결 문제로 공약 구조 저장에 실패했습니다.",
            schema_message="pledge_nodes 테이블 스키마를 확인해 주세요.",
            debug_prefix="pledge tree insert failed",
        )
    except Exception:
        _rollback_new_pledge(pledge_id)
        raise

    try:
        created_nodes = _fetch_pledge_nodes(pledge_id)
    except RuntimeError as exc:
        _rollback_new_pledge(pledge_id)
        app.logger.exception("Pledge node fetch failed for pledge_id=%s: %s", pledge_id, exc)
        return runtime_error_response(
            exc,
            default_message="공약 구조 조회 중 오류가 발생했습니다.",
            network_message="데이터베이스 연결 문제로 공약 구조 조회에 실패했습니다.",
            schema_message="pledge_nodes 테이블 스키마를 확인해 주세요.",
            debug_prefix="pledge node fetch failed",
        )
    saved_source_rows = []
    saved_source_links = []
    if source_rows:
        try:
            saved_source_rows, saved_source_links = _save_pledge_source_rows(
                pledge_id,
                source_rows,
                created_nodes,
                save_uid,
            )
        except ValueError as exc:
            _rollback_new_pledge(pledge_id)
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            app.logger.exception("Pledge source save failed for pledge_id=%s: %s", pledge_id, exc)
            _rollback_new_pledge(pledge_id)
            return runtime_error_response(
                exc,
                default_message="공약 출처 저장 중 오류가 발생했습니다.",
                network_message="데이터베이스 연결 문제로 공약 출처 저장에 실패했습니다.",
                foreign_key_message="공약 출처 연결 관계가 유효하지 않습니다. pledge_node_sources의 FK를 확인해 주세요.",
                schema_message="공약 출처 테이블 스키마를 확인해 주세요.",
                debug_prefix="pledge source save failed",
            )
        except Exception as exc:
            _rollback_new_pledge(pledge_id)
            app.logger.exception("Unexpected pledge source save error for pledge_id=%s: %s", pledge_id, exc)
            return jsonify({"error": str(exc) if not IS_PRODUCTION else "공약 출처 저장 중 알 수 없는 오류가 발생했습니다."}), 500

    return jsonify(
        {
            "ok": True,
            "pledge_id": pledge_id,
            "nodes": created_nodes,
            "sources": saved_source_rows,
            "source_links": saved_source_links,
        }
    ), 201

@app.route("/pledge")
@login_required
def pledge_page():
    return render_template("pledge.html")

@app.route("/promises")
def promises_page():
    return render_template("promises.html")

@app.route("/api/promises", methods=["GET"])
def api_promises():
    limit, offset = _pagination_params(default_limit=None, max_limit=500)
    is_admin = _session_is_admin()
    cache_key = f"api_promises:{'admin' if is_admin else 'public'}"
    cached = _cache_get(cache_key)
    candidates = []
    cards = []
    if cached:
        candidates = cached.get("candidates") or []
        cards = cached.get("cards") or []
    else:
        try:
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
                    "select": "id,candidate_election_id,sort_order,title,category,status,created_at,fulfillment_rate",
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
                pledge["election_title"] = _format_presidential_election_title(election.get("title"))
                pledge["election_date"] = election.get("election_date")

            pledges = [p for p in pledges if str(p.get("status") or "active") != "deleted"]
            if not is_admin:
                pledges = [p for p in pledges if str(p.get("status") or "active") != "hidden"]

            def _progress_from_fulfillment(value):
                try:
                    rate = float(value)
                except (TypeError, ValueError):
                    return None
                if rate < 0 or rate > 100:
                    return None
                return round(rate / 20.0, 2)

            cards = []
            for pledge in pledges:
                pledge_title = str(pledge.get("title") or "").strip()
                if not pledge_title:
                    continue

                category = str(pledge.get("category") or "").strip() or "미분류"
                content = f"{category} 분야 공약입니다. 상세 내용은 후보 상세 페이지에서 확인할 수 있습니다."

                cards.append(
                    {
                        "id": str(pledge.get("id") or ""),
                        "candidate_id": pledge.get("candidate_id"),
                        "candidate_election_id": pledge.get("candidate_election_id"),
                        "pledge_id": pledge.get("id"),
                        "promise_node_id": None,
                        "promise_title": pledge_title,
                        "content": content,
                        "progress_rate": _progress_from_fulfillment(pledge.get("fulfillment_rate")),
                        "category": pledge.get("category"),
                        "election_id": pledge.get("election_id"),
                        "election_type": pledge.get("election_type"),
                        "election_title": pledge.get("election_title"),
                        "election_date": pledge.get("election_date"),
                        "party": pledge.get("party"),
                        "result": pledge.get("result"),
                        "candidate_number": pledge.get("candidate_number"),
                        "pledge_sort_order": pledge.get("sort_order"),
                        "promise_sort_order": 0,
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
        except RuntimeError as exc:
            app.logger.exception("api_promises lightweight load failed: %s", exc)
            candidates = []
            cards = []

    rows, total = _slice_rows(cards, limit, offset)
    return jsonify({"candidates": candidates, "promises": rows, "total": total, "limit": limit, "offset": offset})

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

        simple_payload = dict(payload or {})
        simple_payload.pop("timeline_text", None)
        simple_payload.pop("finance_text", None)

        try:
            _supabase_patch_with_optional_fields(
                "pledges",
                query_params={"id": f"eq.{pledge_id}"},
                payload=simple_payload,
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
