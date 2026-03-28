from datetime import datetime
from urllib import parse


def normalize_pledge_sources_payload(
    raw_sources,
    *,
    normalize_source_link_scope_fn,
    normalize_source_target_path_fn,
    normalize_node_source_role_fn,
    normalize_source_type_fn,
):
    if raw_sources is None:
        return []
    if not isinstance(raw_sources, list):
        raise ValueError("sources must be an array")
    if not raw_sources:
        raise ValueError("sources must contain at least one row")

    normalized = []
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise ValueError("source row must be an object")

        source_id = str(raw.get("source_id") or "").strip() or None
        title = str(raw.get("title") or "").strip()
        if not title and not source_id:
            raise ValueError("source title is required")

        inferred_scope = "goal"
        link_scope = normalize_source_link_scope_fn(raw.get("link_scope") or inferred_scope)

        source_url = str(raw.get("url") or "").strip() or None
        if source_url:
            try:
                parsed_source_url = parse.urlparse(source_url)
            except Exception:
                raise ValueError("source url is invalid")
            if str(parsed_source_url.scheme or "").lower() not in {"http", "https"}:
                raise ValueError("source url must be http(s)")

        published_at = str(raw.get("published_at") or "").strip() or None
        if published_at:
            try:
                datetime.strptime(published_at, "%Y-%m-%d")
            except ValueError:
                raise ValueError("source published_at must be in YYYY-MM-DD format")

        normalized_target_path = normalize_source_target_path_fn(raw.get("target_path")) if link_scope == "goal" else None
        if link_scope == "goal" and normalized_target_path and "/" in normalized_target_path:
            raise ValueError("goal target_path must use g:<순번> 형식입니다.")

        normalized.append(
            {
                "source_id": source_id,
                "link_scope": link_scope,
                "pledge_node_id": str(raw.get("pledge_node_id") or "").strip() or None if link_scope == "goal" else None,
                "target_path": normalized_target_path,
                "source_role": normalize_node_source_role_fn(raw.get("source_role") or "reference"),
                "title": title or None,
                "url": source_url,
                "source_type": normalize_source_type_fn(raw.get("source_type")),
                "publisher": str(raw.get("publisher") or "").strip() or None,
                "published_at": published_at,
                "summary": str(raw.get("summary") or "").strip() or None,
                "note": str(raw.get("note") or "").strip() or None,
            }
        )

    return normalized


def save_pledge_source_rows(
    pledge_id,
    source_rows,
    created_nodes,
    uid,
    *,
    now_iso_fn,
    build_pledge_goal_target_map_fn,
    validate_goal_source_coverage_fn,
    ensure_source_exists_fn,
    find_existing_source_by_url_fn,
    supabase_insert_with_optional_fields_fn,
    upsert_pledge_source_link_fn,
    upsert_pledge_node_source_link_fn,
    first_goal_node_id_fn,
    is_foreign_key_runtime_error_fn,
    is_not_null_constraint_error_fn,
):
    if not source_rows:
        return [], []

    now_iso = now_iso_fn()
    goal_map = build_pledge_goal_target_map_fn(created_nodes)
    validate_goal_source_coverage_fn(source_rows, goal_map)

    saved_source_rows = []
    saved_link_rows = []

    for source_row in source_rows:
        link_scope = source_row.get("link_scope") or "pledge"
        source_id = source_row.get("source_id")
        source_db_row = None
        if source_id:
            if not ensure_source_exists_fn(source_id):
                raise ValueError("source_id not found")
        else:
            source_db_row = find_existing_source_by_url_fn(source_row.get("url"))
            source_id = (source_db_row or {}).get("id")

        if not source_id:
            source_db_row = supabase_insert_with_optional_fields_fn(
                "sources",
                payload={
                    "title": source_row.get("title"),
                    "url": source_row.get("url"),
                    "source_type": source_row.get("source_type"),
                    "publisher": source_row.get("publisher"),
                    "published_at": source_row.get("published_at"),
                    "summary": source_row.get("summary"),
                    "note": source_row.get("note"),
                    "created_at": now_iso,
                    "created_by": uid,
                    "updated_at": now_iso,
                    "updated_by": uid,
                },
                optional_fields={
                    "url",
                    "source_type",
                    "publisher",
                    "published_at",
                    "summary",
                    "note",
                    "created_at",
                    "created_by",
                    "updated_at",
                    "updated_by",
                },
            )
            source_id = source_db_row.get("id")

        if not source_id:
            raise RuntimeError("source insert failed")

        if link_scope == "pledge":
            try:
                link_row = upsert_pledge_source_link_fn(
                    pledge_id=pledge_id,
                    source_id=source_id,
                    source_role=source_row.get("source_role"),
                    note=source_row.get("note"),
                    uid=uid,
                    now_iso=now_iso,
                )
            except RuntimeError as exc:
                fallback_goal_node_id = first_goal_node_id_fn(goal_map)
                can_fallback_to_goal_node = (
                    fallback_goal_node_id
                    and (
                        is_foreign_key_runtime_error_fn(exc)
                        or is_not_null_constraint_error_fn(exc, "pledge_node_id")
                    )
                )
                if not can_fallback_to_goal_node:
                    raise
                link_row = upsert_pledge_node_source_link_fn(
                    pledge_node_id=fallback_goal_node_id,
                    pledge_id=pledge_id,
                    source_id=source_id,
                    source_role=source_row.get("source_role"),
                    note=source_row.get("note"),
                    uid=uid,
                    now_iso=now_iso,
                )
        else:
            target_node_id = None
            target_path = str(source_row.get("target_path") or "").strip()
            if target_path:
                target_node_id = str((goal_map.get(target_path) or {}).get("node_id") or "").strip() or None
            if not target_node_id:
                pledge_node_id = str(source_row.get("pledge_node_id") or "").strip()
                if pledge_node_id:
                    target_node_id = pledge_node_id
            if not target_node_id:
                raise ValueError("goal 연결에 사용할 대항목을 찾을 수 없습니다.")
            link_row = upsert_pledge_node_source_link_fn(
                pledge_node_id=target_node_id,
                pledge_id=pledge_id,
                source_id=source_id,
                source_role=source_row.get("source_role"),
                note=source_row.get("note"),
                uid=uid,
                now_iso=now_iso,
            )

        if source_db_row:
            saved_source_rows.append(source_db_row)
        saved_link_rows.append(link_row)

    return saved_source_rows, saved_link_rows


def build_candidate_election_source_library(
    candidate_election_id,
    *,
    supabase_get_with_select_fallback_fn,
    node_source_table,
    to_in_filter_fn,
):
    pledge_rows = supabase_get_with_select_fallback_fn(
        "pledges",
        query_params={
            "candidate_election_id": f"eq.{candidate_election_id}",
            "limit": "5000",
        },
        select_candidates=[
            "id,status,created_at",
            "id,status",
            "id",
            "*",
        ],
    ) or []

    pledge_ids = []
    for pledge_row in pledge_rows:
        pledge_id = pledge_row.get("id")
        if pledge_id is None:
            continue
        status = str(pledge_row.get("status") or "active").strip().lower()
        if status == "deleted":
            continue
        pledge_ids.append(str(pledge_id))

    pledge_filter = to_in_filter_fn(pledge_ids)
    if not pledge_filter:
        return []

    source_link_rows = supabase_get_with_select_fallback_fn(
        node_source_table,
        query_params={
            "pledge_id": pledge_filter,
            "order": "created_at.desc,id.desc",
            "limit": "100000",
        },
        select_candidates=[
            "id,pledge_id,source_id,created_at",
            "id,pledge_id,source_id",
            "pledge_id,source_id",
            "source_id",
            "*",
        ],
    ) or []

    source_ids = []
    source_stats = {}
    for link_row in source_link_rows:
        source_id = str(link_row.get("source_id") or "").strip()
        if not source_id:
            continue
        stats = source_stats.setdefault(source_id, {"usage_count": 0, "last_used_at": None})
        stats["usage_count"] += 1
        created_at = str(link_row.get("created_at") or "").strip() or None
        if created_at and (stats["last_used_at"] is None or created_at > stats["last_used_at"]):
            stats["last_used_at"] = created_at
        if source_id not in source_ids:
            source_ids.append(source_id)

    source_filter = to_in_filter_fn(source_ids)
    if not source_filter:
        return []

    source_rows = supabase_get_with_select_fallback_fn(
        "sources",
        query_params={
            "id": source_filter,
            "limit": "50000",
        },
        select_candidates=[
            "id,title,url,source_type,publisher,published_at,summary,note",
            "id,title,url,source_type,publisher,published_at,summary",
            "id,title,url,source_type,publisher,published_at",
            "id,title,url,source_type,publisher",
            "id,title,url,source_type",
            "id,title,url",
            "id,title",
            "id",
            "*",
        ],
    ) or []

    source_map = {
        str(row.get("id")): row
        for row in source_rows
        if row.get("id") is not None
    }

    library_rows = []
    for source_id in source_ids:
        source_row = source_map.get(source_id) or {}
        source_stats_row = source_stats.get(source_id) or {}
        library_rows.append(
            {
                "id": source_id,
                "title": source_row.get("title"),
                "url": source_row.get("url"),
                "source_type": source_row.get("source_type"),
                "publisher": source_row.get("publisher"),
                "published_at": source_row.get("published_at"),
                "summary": source_row.get("summary"),
                "note": source_row.get("note"),
                "usage_count": source_stats_row.get("usage_count") or 0,
                "last_used_at": source_stats_row.get("last_used_at"),
            }
        )

    return library_rows
