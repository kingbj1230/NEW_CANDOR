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

    node_rows = supabase_request(
        "GET",
        "pledge_nodes",
        query_params={
            "select": "id,pledge_id,name,content,sort_order,parent_id,is_leaf,created_at",
            "pledge_id": pledge_filter,
            "limit": "50000",
        },
    ) or []
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
        progress_rows = supabase_request(
            "GET",
            "pledge_node_progress",
            query_params={
                "select": "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date,created_at,created_by,updated_at,updated_by",
                "pledge_node_id": node_filter,
                "limit": "100000",
            },
        ) or []

        node_source_rows = fetch_node_source_rows(node_filter)

        progress_ids = [row.get("id") for row in progress_rows if row.get("id") is not None]
        progress_filter = to_in_filter(progress_ids)
        if progress_filter:
            progress_source_rows = supabase_request(
                "GET",
                "pledge_node_progress_sources",
                query_params={
                    "select": "id,pledge_node_progress_id,source_id,source_role,quoted_text,page_no,note,created_at",
                    "pledge_node_progress_id": progress_filter,
                    "limit": "100000",
                },
            ) or []

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
        source_rows = supabase_request(
            "GET",
            "sources",
            query_params={
                "select": "id,title,url,source_type,publisher,published_at,summary,note",
                "id": source_filter,
                "limit": "50000",
            },
        ) or []

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
            "sort_order": node_row.get("sort_order"),
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

    goals_by_pledge = {}
    root_rows = _sorted_nodes(children_by_parent.get("__root__", []))
    for goal in root_rows:
        goal_id = goal.get("id")
        pledge_id = str(goal.get("pledge_id"))
        if not pledge_id or not goal_id:
            continue
        if is_leaf_node(goal.get("is_leaf")):
            continue

        promise_rows = _sorted_nodes(children_by_parent.get(str(goal_id), []))
        promise_list = []
        for promise in promise_rows:
            promise_id = promise.get("id")
            if not promise_id or is_leaf_node(promise.get("is_leaf")):
                continue
            item_rows = _sorted_nodes(children_by_parent.get(str(promise_id), []))
            item_list = []
            for item in item_rows:
                if not is_leaf_node(item.get("is_leaf")):
                    continue
                item_list.append(_node_payload(item))
            promise_payload = _node_payload(promise)
            promise_payload["items"] = item_list
            promise_list.append(promise_payload)

        goal_payload = _node_payload(goal)
        goal_payload["promises"] = promise_list
        goals_by_pledge.setdefault(pledge_id, []).append(goal_payload)

    for pledge in pledges:
        pledge_key = str(pledge.get("id"))
        pledge["goals"] = goals_by_pledge.get(pledge_key, [])
        pledge["sources"] = pledge_sources_by_pledge.get(pledge_key, [])

    return pledges


def normalize_compact_text(value):
    return re.sub(r"\s+", "", str(value or ""))


def is_execution_method_goal_text(text):
    normalized = normalize_compact_text(text)
    return ("이행방법" in normalized) or ("실행방법" in normalized)


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
            "select": "id,pledge_id,name,content,sort_order,parent_id,is_leaf,created_at",
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
    children_by_parent = {}
    for row in node_rows:
        parent_key = str(row.get("parent_id")) if row.get("parent_id") is not None else "__root__"
        children_by_parent.setdefault(parent_key, []).append(row)
    for key in list(children_by_parent.keys()):
        children_by_parent[key] = sorted_node_rows_fn(children_by_parent[key])

    def _node_name(row):
        raw = str(row.get("name") or "").strip().lower()
        if raw in {"goal", "promise", "item"}:
            return raw
        return "item" if is_leaf_node(row.get("is_leaf")) else "promise"

    def _node_title(row):
        return str(row.get("content") or "").strip() or "(내용 없음)"

    all_nodes = []

    def _walk(node_row, path_parts):
        node_id = node_row.get("id")
        if node_id is None:
            return
        title = _node_title(node_row)
        full_path_parts = [*path_parts, title]
        all_nodes.append(
            {
                "id": node_id,
                "name": _node_name(node_row),
                "text": title,
                "path": " > ".join(full_path_parts),
                "sort_order": node_row.get("sort_order"),
                "parent_id": node_row.get("parent_id"),
                "is_leaf": is_leaf_node(node_row.get("is_leaf")),
            }
        )
        for child in children_by_parent.get(str(node_id), []):
            _walk(child, full_path_parts)

    root_rows = children_by_parent.get("__root__", [])
    for root in root_rows:
        _walk(root, [])

    progress_targets = []
    for goal_row in root_rows:
        goal_id = goal_row.get("id")
        if goal_id is None:
            continue
        goal_title = _node_title(goal_row)
        if not is_execution_method_goal_text_fn(goal_title):
            continue

        # Legacy rows may not preserve canonical `name` values.
        # For execution-method goals, treat non-leaf children as promise-level targets.
        promise_rows = [row for row in children_by_parent.get(str(goal_id), []) if not is_leaf_node(row.get("is_leaf"))]
        for promise_row in promise_rows:
            promise_id = promise_row.get("id")
            if promise_id is None:
                continue
            promise_title = _node_title(promise_row)
            item_rows = [row for row in children_by_parent.get(str(promise_id), []) if _node_name(row) == "item"]

            if item_rows:
                for item_row in item_rows:
                    item_title = _node_title(item_row)
                    progress_targets.append(
                        {
                            "id": item_row.get("id"),
                            "name": "item",
                            "text": item_title,
                            "goal_text": goal_title,
                            "promise_text": promise_title,
                            "path": " > ".join([goal_title, promise_title, item_title]),
                            "is_leaf": True,
                        }
                    )
            else:
                progress_targets.append(
                    {
                        "id": promise_id,
                        "name": "promise",
                        "text": promise_title,
                        "goal_text": goal_title,
                        "promise_text": promise_title,
                        "path": " > ".join([goal_title, promise_title]),
                        "is_leaf": False,
                    }
                )

    return {
        "all_nodes": all_nodes,
        "progress_targets": progress_targets,
    }
