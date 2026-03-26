import re


def attach_pledge_tree_rows(
    pledges,
    *,
    to_in_filter,
    supabase_request,
    fetch_node_source_rows,
    fetch_pledge_source_rows=None,
    safe_int,
    is_leaf_node,
    is_missing_schema_runtime_error=None,
):
    if not pledges:
        return pledges

    pledge_ids = [row.get("id") for row in pledges if row.get("id") is not None]
    pledge_filter = to_in_filter(pledge_ids)
    if not pledge_filter:
        for pledge in pledges:
            pledge["goals"] = []
            pledge["sources"] = []
        return pledges

    def _can_skip_missing_schema(exc):
        checker = is_missing_schema_runtime_error
        if not callable(checker):
            return False
        try:
            return bool(checker(exc))
        except Exception:
            return False

    def _fetch_rows_with_select_candidates(table_name, base_query, select_candidates, *, allow_missing_schema=False):
        last_schema_error = None
        for select_clause in select_candidates:
            query_params = dict(base_query or {})
            query_params["select"] = select_clause
            try:
                return supabase_request(
                    "GET",
                    table_name,
                    query_params=query_params,
                ) or []
            except RuntimeError as exc:
                if allow_missing_schema and _can_skip_missing_schema(exc):
                    last_schema_error = exc
                    continue
                raise
        if allow_missing_schema and last_schema_error is not None:
            return []
        return []

    node_rows = _fetch_rows_with_select_candidates(
        "pledge_nodes",
        {
            "pledge_id": pledge_filter,
            "limit": "50000",
        },
        [
            "id,pledge_id,node_type,name,content,level,sort_order,parent_id,is_leaf,created_at",
            "id,pledge_id,node_type,name,content,level,sort_order,parent_id,created_at",
            "id,pledge_id,node_type,name,content,level,sort_order,parent_id",
            "id,pledge_id,node_type,name,content,level,parent_id",
            "*",
        ],
        allow_missing_schema=True,
    )
    node_ids = [row.get("id") for row in node_rows if row.get("id") is not None]
    node_filter = to_in_filter(node_ids)

    progress_rows = []
    node_source_rows = []
    pledge_source_rows = []
    progress_source_rows = []
    source_rows = []

    if fetch_pledge_source_rows:
        pledge_source_rows = fetch_pledge_source_rows(pledge_filter) or []

    if node_filter:
        progress_rows = _fetch_rows_with_select_candidates(
            "pledge_node_progress",
            {
                "pledge_node_id": node_filter,
                "limit": "100000",
            },
            [
                "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date,created_at,created_by,updated_at,updated_by",
                "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date,created_at,updated_at",
                "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date,created_at",
                "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date",
                "id,pledge_node_id,progress_rate,status,reason",
                "id,pledge_node_id,progress_rate,status",
                "*",
            ],
            allow_missing_schema=True,
        )

        node_source_rows = fetch_node_source_rows(node_filter)

        progress_ids = [row.get("id") for row in progress_rows if row.get("id") is not None]
        progress_filter = to_in_filter(progress_ids)
        if progress_filter:
            progress_source_rows = _fetch_rows_with_select_candidates(
                "pledge_node_progress_sources",
                {
                    "pledge_node_progress_id": progress_filter,
                    "limit": "100000",
                },
                [
                    "id,pledge_node_progress_id,source_id,source_role,quoted_text,page_no,note,created_at",
                    "id,pledge_node_progress_id,source_id,source_role,quoted_text,page_no,note",
                    "id,pledge_node_progress_id,source_id,source_role,quoted_text",
                    "id,pledge_node_progress_id,source_id,source_role",
                    "id,pledge_node_progress_id,source_id",
                    "*",
                ],
                allow_missing_schema=True,
            )

    source_ids = []
    for row in node_source_rows:
        sid = row.get("source_id")
        if sid is None:
            continue
        sid_str = str(sid)
        if sid_str not in source_ids:
            source_ids.append(sid_str)
    for row in progress_source_rows:
        sid = row.get("source_id")
        if sid is None:
            continue
        sid_str = str(sid)
        if sid_str not in source_ids:
            source_ids.append(sid_str)
    for row in pledge_source_rows:
        sid = row.get("source_id")
        if sid is None:
            continue
        sid_str = str(sid)
        if sid_str not in source_ids:
            source_ids.append(sid_str)

    source_filter = to_in_filter(source_ids)
    if source_filter:
        source_rows = _fetch_rows_with_select_candidates(
            "sources",
            {
                "id": source_filter,
                "limit": "50000",
            },
            [
                "id,title,url,source_type,publisher,published_at,summary,note",
                "id,title,url,source_type,publisher,published_at,summary",
                "id,title,url,source_type,publisher,published_at",
                "id,title,url,source_type,publisher",
                "id,title,url,source_type",
                "id,title,url",
                "*",
            ],
            allow_missing_schema=True,
        )

    children_by_parent = {}
    for row in node_rows:
        parent_key = str(row.get("parent_id")) if row.get("parent_id") is not None else "__root__"
        children_by_parent.setdefault(parent_key, []).append(row)

    source_map = {str(row.get("id")): row for row in source_rows if row.get("id") is not None}

    def _source_link_payload(link_row):
        source_id = link_row.get("source_id")
        source = source_map.get(str(source_id)) if source_id is not None else None
        return {
            "id": link_row.get("id"),
            "source_id": source_id,
            "source_role": link_row.get("source_role"),
            "note": link_row.get("note"),
            "quoted_text": link_row.get("quoted_text"),
            "page_no": link_row.get("page_no"),
            "created_at": link_row.get("created_at"),
            "source": source,
        }

    node_sources_by_node = {}
    for row in node_source_rows:
        node_key = str(row.get("pledge_node_id"))
        if not node_key:
            continue
        node_sources_by_node.setdefault(node_key, []).append(_source_link_payload(row))

    progress_sources_by_progress = {}
    for row in progress_source_rows:
        progress_key = str(row.get("pledge_node_progress_id"))
        if not progress_key:
            continue
        progress_sources_by_progress.setdefault(progress_key, []).append(_source_link_payload(row))

    pledge_sources_by_pledge = {}
    for row in pledge_source_rows:
        pledge_node_id = row.get("pledge_node_id")
        if pledge_node_id not in (None, "", "null"):
            continue
        pledge_key = str(row.get("pledge_id") or "")
        if not pledge_key:
            continue
        pledge_sources_by_pledge.setdefault(pledge_key, []).append(_source_link_payload(row))

    def _progress_sort_key(row):
        return (
            str(row.get("evaluation_date") or ""),
            str(row.get("created_at") or ""),
            str(row.get("id") or ""),
        )

    progress_by_node = {}
    for row in progress_rows:
        node_key = str(row.get("pledge_node_id"))
        if not node_key:
            continue
        progress_by_node.setdefault(node_key, []).append(row)

    for node_key in progress_by_node:
        progress_by_node[node_key] = sorted(progress_by_node[node_key], key=_progress_sort_key, reverse=True)

    def _sorted_nodes(rows):
        return sorted(
            rows,
            key=lambda x: (safe_int(x.get("sort_order"), 999999), str(x.get("created_at") or ""), str(x.get("id") or "")),
        )

    def _node_payload(node_row):
        node_id = node_row.get("id")
        node_key = str(node_id)
        history_rows = progress_by_node.get(node_key, [])
        latest = history_rows[0] if history_rows else None
        latest_progress_id = latest.get("id") if latest else None
        latest_sources = progress_sources_by_progress.get(str(latest_progress_id), []) if latest_progress_id else []
        history_payload = []
        for progress_row in history_rows:
            progress_id = progress_row.get("id")
            history_payload.append(
                {
                    "id": progress_id,
                    "progress_rate": progress_row.get("progress_rate"),
                    "status": progress_row.get("status"),
                    "reason": progress_row.get("reason"),
                    "evaluator": progress_row.get("evaluator"),
                    "evaluation_date": progress_row.get("evaluation_date"),
                    "created_at": progress_row.get("created_at"),
                    "sources": progress_sources_by_progress.get(str(progress_id), []),
                }
            )

        return {
            "id": node_id,
            "text": node_row.get("content"),
            "level": safe_int(node_row.get("level"), 0),
            "sort_order": node_row.get("sort_order"),
            "node_type": node_row.get("node_type"),
            "name": node_row.get("name"),
            "progress_rate": (latest or {}).get("progress_rate"),
            "progress_status": (latest or {}).get("status"),
            "progress_reason": (latest or {}).get("reason"),
            "progress_evaluator": (latest or {}).get("evaluator"),
            "progress_evaluation_date": (latest or {}).get("evaluation_date"),
            "progress_updated_at": (latest or {}).get("updated_at"),
            "progress_sources": latest_sources,
            "sources": node_sources_by_node.get(node_key, []),
            "progress_history": history_payload,
        }

    def _build_tree_node(node_row):
        node_id = node_row.get("id")
        payload = _node_payload(node_row)
        child_rows = _sorted_nodes(children_by_parent.get(str(node_id), []))
        child_payloads = [_build_tree_node(child_row) for child_row in child_rows]
        payload["children"] = child_payloads

        # Backward compatibility for endpoints still reading 3-level keys.
        node_level = safe_int(node_row.get("level"), 0)
        node_type = str(node_row.get("node_type") or "").strip().lower()
        node_name = str(node_row.get("name") or "").strip().lower()
        if node_level <= 1 or node_type == "goal" or node_name == "goal":
            payload["promises"] = child_payloads
        elif node_level == 2 or node_type in {"strategy", "promise"} or node_name == "promise":
            payload["items"] = child_payloads
        return payload

    goals_by_pledge = {}
    root_rows = _sorted_nodes(children_by_parent.get("__root__", []))
    for root in root_rows:
        pledge_id = str(root.get("pledge_id"))
        if not pledge_id:
            continue
        goals_by_pledge.setdefault(pledge_id, []).append(_build_tree_node(root))

    for pledge in pledges:
        pledge_key = str(pledge.get("id"))
        pledge["goals"] = goals_by_pledge.get(pledge_key, [])
        pledge["sources"] = pledge_sources_by_pledge.get(pledge_key, [])

    return pledges


def normalize_compact_text(value):
    return re.sub(r"\s+", "", str(value or ""))


def is_execution_method_goal_text(text):
    normalized = normalize_compact_text(text)
    return (
        "이행방법" in normalized
        or "이행방안" in normalized
        or "실천방안" in normalized
        or "추진전략" in normalized
    )

def sorted_node_rows(rows, *, safe_int):
    return sorted(
        rows,
        key=lambda x: (safe_int(x.get("sort_order"), 999999), str(x.get("created_at") or ""), str(x.get("id") or "")),
    )


def fetch_pledge_nodes(pledge_id, *, supabase_request):
    return supabase_request(
        "GET",
        "pledge_nodes",
        query_params={
            "select": "id,pledge_id,node_type,name,content,level,sort_order,parent_id,is_leaf,created_at",
            "pledge_id": f"eq.{pledge_id}",
            "limit": "50000",
        },
    ) or []


def build_progress_node_context(
    node_rows,
    *,
    sorted_node_rows_fn,
    is_leaf_node,
    is_execution_method_goal_text_fn,
):
    def _safe_level(value, fallback=1):
        try:
            level = int(value)
        except (TypeError, ValueError):
            return fallback
        return max(1, level)

    children_by_parent = {}
    for row in node_rows:
        parent_key = str(row.get("parent_id")) if row.get("parent_id") is not None else "__root__"
        children_by_parent.setdefault(parent_key, []).append(row)
    for key in list(children_by_parent.keys()):
        children_by_parent[key] = sorted_node_rows_fn(children_by_parent[key])

    def _node_name(row):
        node_type = str(row.get("node_type") or "").strip().lower()
        if node_type == "goal":
            return "goal"
        if node_type in {"strategy", "promise"}:
            return "promise"
        if node_type in {"action", "item"}:
            return "item"
        raw = str(row.get("name") or "").strip().lower()
        if raw in {"goal", "promise", "item"}:
            return raw
        return "item" if is_leaf_node(row.get("is_leaf")) else "promise"

    def _node_title(row):
        return str(row.get("content") or "").strip() or "(?댁슜 ?놁쓬)"

    all_nodes = []
    node_meta_by_id = {}

    def _walk(node_row, path_parts, active_ids=None):
        active_ids = active_ids or set()
        node_id = node_row.get("id")
        if node_id is None:
            return
        node_key = str(node_id)
        if node_key in active_ids:
            return
        next_active = set(active_ids)
        next_active.add(node_key)
        title = _node_title(node_row)
        full_path_parts = [*path_parts, title]
        payload = {
            "id": node_id,
            "name": _node_name(node_row),
            "text": title,
            "path": " > ".join(full_path_parts),
            "sort_order": node_row.get("sort_order"),
            "parent_id": node_row.get("parent_id"),
            "is_leaf": is_leaf_node(node_row.get("is_leaf")),
            "level": _safe_level(node_row.get("level"), len(full_path_parts)),
        }
        all_nodes.append(payload)
        node_meta_by_id[node_key] = payload
        for child in children_by_parent.get(node_key, []):
            _walk(child, full_path_parts, next_active)

    def _collect_leaf_descendants(node_row, active_ids=None):
        active_ids = active_ids or set()
        node_id = node_row.get("id")
        if node_id is None:
            return []
        node_key = str(node_id)
        if node_key in active_ids:
            return [node_row]
        next_active = set(active_ids)
        next_active.add(node_key)
        child_rows = children_by_parent.get(node_key, [])
        if not child_rows:
            return [node_row]
        leaves = []
        for child in child_rows:
            leaves.extend(_collect_leaf_descendants(child, next_active))
        return leaves or [node_row]

    root_rows = children_by_parent.get("__root__", [])
    for root in root_rows:
        _walk(root, [], set())

    progress_targets = []
    appended_ids = set()
    for goal_row in root_rows:
        goal_id = goal_row.get("id")
        if goal_id is None:
            continue
        goal_title = _node_title(goal_row)
        if not is_execution_method_goal_text_fn(goal_title):
            continue

        promise_rows = children_by_parent.get(str(goal_id), [])
        for promise_row in promise_rows:
            promise_id = promise_row.get("id")
            if promise_id is None:
                continue
            promise_title = _node_title(promise_row)
            leaf_rows = _collect_leaf_descendants(promise_row)
            if not leaf_rows:
                promise_meta = node_meta_by_id.get(str(promise_id), {})
                promise_key = str(promise_id)
                if promise_key in appended_ids:
                    continue
                appended_ids.add(promise_key)
                progress_targets.append(
                    {
                        "id": promise_id,
                        "name": promise_meta.get("name") or "promise",
                        "text": promise_title,
                        "goal_text": goal_title,
                        "promise_text": promise_title,
                        "path": promise_meta.get("path") or " > ".join([goal_title, promise_title]),
                        "is_leaf": bool(promise_meta.get("is_leaf")),
                    }
                )
                continue

            for leaf_row in leaf_rows:
                leaf_id = leaf_row.get("id")
                if leaf_id is None:
                    continue
                leaf_key = str(leaf_id)
                if leaf_key in appended_ids:
                    continue
                leaf_meta = node_meta_by_id.get(leaf_key, {})
                appended_ids.add(leaf_key)
                progress_targets.append(
                    {
                        "id": leaf_id,
                        "name": leaf_meta.get("name") or "item",
                        "text": leaf_meta.get("text") or _node_title(leaf_row),
                        "goal_text": goal_title,
                        "promise_text": promise_title,
                        "path": leaf_meta.get("path") or " > ".join([goal_title, promise_title, _node_title(leaf_row)]),
                        "is_leaf": bool(leaf_meta.get("is_leaf", True)),
                    }
                )

    return {
        "all_nodes": all_nodes,
        "progress_targets": progress_targets,
    }

