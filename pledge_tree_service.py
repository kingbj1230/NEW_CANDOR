import re


def _parse_pledges_text(text):
    goals = []
    current_goal = None
    current_promise = None
    current_item = None

    parts = [p for p in re.split(r"(□ |○ |- )", text or "") if (p or "").strip()]
    i = 0
    while i < len(parts):
        part = parts[i]

        if part == "□ ":
            if i + 1 >= len(parts):
                break
            title = parts[i + 1].strip()
            current_goal = {"title": title, "promises": []}
            goals.append(current_goal)
            current_promise = None
            current_item = None
            i += 2
            continue

        if part == "○ ":
            if not current_goal:
                i += 2
                continue
            if i + 1 >= len(parts):
                break
            title = parts[i + 1].strip()
            current_promise = {"title": title, "items": []}
            current_goal["promises"].append(current_promise)
            current_item = None
            i += 2
            continue

        if part == "- ":
            if not current_promise:
                i += 2
                continue
            if i + 1 >= len(parts):
                break
            detail = parts[i + 1].strip()
            current_item = {"detail": detail}
            current_promise["items"].append(current_item)
            i += 2
            continue

        content = part.strip()
        if content:
            if current_item:
                current_item["detail"] = f"{current_item['detail']} {content}".strip()
            elif current_promise:
                current_promise["title"] = f"{current_promise['title']} {content}".strip()
            elif current_goal:
                current_goal["title"] = f"{current_goal['title']} {content}".strip()
        i += 1

    return goals


def _source_has_any_reference(
    source_id,
    *,
    supabase_request,
    is_missing_schema_runtime_error,
    node_source_table,
    progress_source_table,
):
    sid = str(source_id or "").strip()
    if not sid:
        return False

    query = {"select": "id", "source_id": f"eq.{sid}", "limit": "1"}
    for table_name in (node_source_table, progress_source_table):
        try:
            rows = supabase_request("GET", table_name, query_params=query) or []
        except RuntimeError as exc:
            if is_missing_schema_runtime_error(exc):
                continue
            raise
        if rows:
            return True
    return False


def _delete_orphan_sources(
    source_ids,
    *,
    supabase_request,
    safe_delete_rows,
    is_missing_schema_runtime_error,
    node_source_table,
    progress_source_table,
    logger,
):
    unique_ids = {str(value).strip() for value in (source_ids or set()) if str(value).strip()}
    if not unique_ids:
        return

    for source_id in unique_ids:
        try:
            if _source_has_any_reference(
                source_id,
                supabase_request=supabase_request,
                is_missing_schema_runtime_error=is_missing_schema_runtime_error,
                node_source_table=node_source_table,
                progress_source_table=progress_source_table,
            ):
                continue
            safe_delete_rows("sources", {"id": f"eq.{source_id}"})
        except RuntimeError as exc:
            logger.warning("Source cleanup skipped for %s: %s", source_id, exc)


def _delete_pledge_nodes_bottom_up(
    node_rows,
    *,
    safe_delete_rows,
    to_in_filter,
    logger,
):
    remaining = {
        str(row.get("id")): str(row.get("parent_id")) if row.get("parent_id") is not None else None
        for row in (node_rows or [])
        if row.get("id") is not None
    }
    if not remaining:
        return

    while remaining:
        current_ids = set(remaining.keys())
        parent_ids = {
            parent_id
            for parent_id in remaining.values()
            if parent_id and parent_id in current_ids
        }
        leaf_ids = sorted([node_id for node_id in current_ids if node_id not in parent_ids])

        # Defensive fallback for unexpected cyclic/inconsistent trees.
        if not leaf_ids:
            leaf_ids = sorted(current_ids)

        leaf_filter = to_in_filter(leaf_ids)
        if not leaf_filter:
            break
        safe_delete_rows("pledge_nodes", {"id": leaf_filter}, ignore_missing_schema=False)
        for node_id in leaf_ids:
            remaining.pop(node_id, None)


def _detach_external_child_nodes(
    node_filter,
    *,
    node_ids,
    supabase_request,
    to_in_filter,
    is_missing_schema_runtime_error,
    logger,
):
    if not node_filter:
        return

    known_ids = {str(value) for value in (node_ids or []) if value is not None}
    try:
        child_rows = supabase_request(
            "GET",
            "pledge_nodes",
            query_params={
                "select": "id",
                "parent_id": node_filter,
                "limit": "100000",
            },
        ) or []
    except RuntimeError as exc:
        if is_missing_schema_runtime_error(exc):
            return
        logger.warning("Failed to inspect child pledge_nodes for detach: %s", exc)
        return

    detach_ids = [
        str(row.get("id"))
        for row in child_rows
        if row.get("id") is not None and str(row.get("id")) not in known_ids
    ]
    detach_filter = to_in_filter(detach_ids)
    if not detach_filter:
        return

    try:
        supabase_request(
            "PATCH",
            "pledge_nodes",
            query_params={"id": detach_filter},
            payload={"parent_id": None},
        )
    except RuntimeError as exc:
        if is_missing_schema_runtime_error(exc):
            return
        logger.warning("Failed to detach external child pledge_nodes: %s", exc)


def delete_pledge_tree(
    pledge_id,
    *,
    supabase_request,
    safe_delete_rows,
    to_in_filter,
    is_missing_schema_runtime_error,
    node_source_table,
    progress_source_table,
    logger,
):
    # Deletion order by FK dependency (explicit schema):
    # 1) pledge_nodes by pledge_id lookup
    # 2) pledge_node_sources by pledge_node_id
    # 3) pledge_node_progress_sources by pledge_node_progress_id
    # 4) pledge_node_progress by pledge_node_id
    # 5) orphan sources
    # 6) pledge_nodes (pledges is deleted by caller)
    try:
        node_rows = supabase_request(
            "GET",
            "pledge_nodes",
            query_params={
                "select": "id,parent_id",
                "pledge_id": f"eq.{pledge_id}",
                "limit": "50000",
            },
        ) or []
    except RuntimeError as exc:
        if is_missing_schema_runtime_error(exc):
            return
        raise
    node_ids = [row.get("id") for row in node_rows if row.get("id") is not None]
    source_ids_to_cleanup = set()
    node_filter = to_in_filter(node_ids)

    if node_filter:
        try:
            node_source_rows = supabase_request(
                "GET",
                node_source_table,
                query_params={
                    "select": "id,source_id",
                    "pledge_node_id": node_filter,
                    "limit": "100000",
                },
            ) or []
        except RuntimeError as exc:
            if is_missing_schema_runtime_error(exc):
                node_source_rows = []
            else:
                raise
        for row in node_source_rows:
            source_id = row.get("source_id")
            if source_id is not None:
                source_ids_to_cleanup.add(str(source_id))
        safe_delete_rows(node_source_table, {"pledge_node_id": node_filter}, ignore_missing_schema=False)

    # Also remove pledge-scoped source links where pledge_node_id may be NULL.
    try:
        pledge_source_rows = supabase_request(
            "GET",
            node_source_table,
            query_params={
                "select": "id,source_id",
                "pledge_id": f"eq.{pledge_id}",
                "limit": "100000",
            },
        ) or []
    except RuntimeError as exc:
        if is_missing_schema_runtime_error(exc):
            pledge_source_rows = []
        else:
            raise
    for row in pledge_source_rows:
        source_id = row.get("source_id")
        if source_id is not None:
            source_ids_to_cleanup.add(str(source_id))
    safe_delete_rows(node_source_table, {"pledge_id": f"eq.{pledge_id}"})

    if node_filter:
        try:
            progress_rows = supabase_request(
                "GET",
                "pledge_node_progress",
                query_params={
                    "select": "id",
                    "pledge_node_id": node_filter,
                    "limit": "100000",
                },
            ) or []
        except RuntimeError as exc:
            if is_missing_schema_runtime_error(exc):
                progress_rows = []
            else:
                raise
        progress_ids = [row.get("id") for row in progress_rows if row.get("id") is not None]
        progress_filter = to_in_filter(progress_ids)
        if progress_filter:
            try:
                progress_source_rows = supabase_request(
                    "GET",
                    progress_source_table,
                    query_params={
                        "select": "id,source_id",
                        "pledge_node_progress_id": progress_filter,
                        "limit": "100000",
                    },
                ) or []
            except RuntimeError as exc:
                if is_missing_schema_runtime_error(exc):
                    progress_source_rows = []
                else:
                    raise
            for row in progress_source_rows:
                source_id = row.get("source_id")
                if source_id is not None:
                    source_ids_to_cleanup.add(str(source_id))
            safe_delete_rows(progress_source_table, {"pledge_node_progress_id": progress_filter})
        safe_delete_rows("pledge_node_progress", {"pledge_node_id": node_filter})

        try:
            _delete_pledge_nodes_bottom_up(
                node_rows,
                safe_delete_rows=safe_delete_rows,
                to_in_filter=to_in_filter,
                logger=logger,
            )
        except RuntimeError as exc:
            # If corrupted links remain (for example cross-pledge parent refs),
            # detach parent links and retry a direct pledge_id sweep.
            logger.warning("Bottom-up pledge_nodes delete failed for %s: %s", pledge_id, exc)
            _detach_external_child_nodes(
                node_filter,
                node_ids=node_ids,
                supabase_request=supabase_request,
                to_in_filter=to_in_filter,
                is_missing_schema_runtime_error=is_missing_schema_runtime_error,
                logger=logger,
            )
            try:
                supabase_request(
                    "PATCH",
                    "pledge_nodes",
                    query_params={"pledge_id": f"eq.{pledge_id}"},
                    payload={"parent_id": None},
                )
            except RuntimeError as patch_exc:
                if not is_missing_schema_runtime_error(patch_exc):
                    logger.warning("Failed to clear parent links before fallback delete: %s", patch_exc)
            safe_delete_rows("pledge_nodes", {"pledge_id": f"eq.{pledge_id}"}, ignore_missing_schema=False)

    # Optional table in schema list: remove pledge-scoped votes before deleting pledge row.
    safe_delete_rows("pledge_votes", {"pledge_id": f"eq.{pledge_id}"})
    _delete_orphan_sources(
        source_ids_to_cleanup,
        supabase_request=supabase_request,
        safe_delete_rows=safe_delete_rows,
        is_missing_schema_runtime_error=is_missing_schema_runtime_error,
        node_source_table=node_source_table,
        progress_source_table=progress_source_table,
        logger=logger,
    )


def insert_pledge_tree(
    pledge_id,
    raw_text,
    created_by,
    *,
    now_iso_fn,
    supabase_insert_returning,
    supabase_request,
):
    goals = _parse_pledges_text(raw_text or "")
    now = now_iso_fn()

    for goal_idx, goal in enumerate(goals, start=1):
        goal_text = str(goal.get("title") or "").strip()
        if not goal_text:
            continue

        inserted_goal = supabase_insert_returning(
            "pledge_nodes",
            payload={
                "pledge_id": pledge_id,
                "name": "goal",
                "level": 1,
                "content": goal_text,
                "sort_order": goal_idx,
                "parent_id": None,
                "is_leaf": False,
                "created_at": now,
                "created_by": created_by,
                "updated_at": now,
                "updated_by": None,
            },
        )
        goal_id = inserted_goal.get("id")
        if not goal_id:
            continue

        for promise_idx, promise in enumerate(goal.get("promises", []), start=1):
            promise_text = str(promise.get("title") or "").strip()
            if not promise_text:
                continue

            inserted_promise = supabase_insert_returning(
                "pledge_nodes",
                payload={
                    "pledge_id": pledge_id,
                    "name": "promise",
                    "level": 2,
                    "content": promise_text,
                    "sort_order": promise_idx,
                    "parent_id": goal_id,
                    "is_leaf": False,
                    "created_at": now,
                    "created_by": created_by,
                    "updated_at": now,
                    "updated_by": None,
                },
            )
            promise_id = inserted_promise.get("id")
            if not promise_id:
                continue

            for item_idx, item in enumerate(promise.get("items", []), start=1):
                item_text = str(item.get("detail") or "").strip()
                if not item_text:
                    continue
                supabase_request(
                    "POST",
                    "pledge_nodes",
                    payload={
                        "pledge_id": pledge_id,
                        "name": "item",
                        "level": 3,
                        "content": item_text,
                        "sort_order": item_idx,
                        "parent_id": promise_id,
                        "is_leaf": True,
                        "created_at": now,
                        "created_by": created_by,
                        "updated_at": now,
                        "updated_by": None,
                    },
                )


def fetch_node_source_rows(node_filter, *, supabase_request, is_missing_schema_runtime_error, node_source_table):
    try:
        return supabase_request(
            "GET",
            node_source_table,
            query_params={
                "select": "id,pledge_node_id,source_id,source_role,note,created_at",
                "pledge_node_id": node_filter,
                "limit": "100000",
            },
        ) or []
    except RuntimeError as exc:
        if is_missing_schema_runtime_error(exc):
            return []
        raise


def insert_node_source_row(
    payload,
    *,
    supabase_insert_with_optional_fields,
    node_source_table,
    optional_fields=None,
):
    return supabase_insert_with_optional_fields(
        node_source_table,
        payload=payload,
        optional_fields=optional_fields or {"created_at", "created_by", "updated_at", "updated_by"},
    )
