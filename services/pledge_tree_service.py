import re


_SECTION_GOAL = "goal"
_SECTION_METHOD = "method"
_SECTION_TIMELINE = "timeline"
_SECTION_FINANCE = "finance"

_TYPE1_RE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]")
_CIRCLED_NUMBER_RE = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]")

_SECTION_LABELS = {
    _SECTION_GOAL: ("목표", "비전", "핵심 목표", "핵심목표", "추진 목표", "추진목표"),
    _SECTION_METHOD: ("이행방법", "이행 방법", "이행방안", "실천방안", "추진전략", "추진 전략", "세부실천", "세부 실행"),
    _SECTION_TIMELINE: ("이행기간", "이행 기간", "추진일정", "추진 일정"),
    _SECTION_FINANCE: ("재원조달방안", "재원 조달 방안", "재원조달", "재원 대책", "재원대책"),
}

_GOAL_SECTION_TITLE = "목표"
_METHOD_SECTION_TITLE = "이행 방법"


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _collapse_spaces(value):
    return re.sub(r"\s+", "", str(value or "")).strip()


def _leading_spaces(line):
    match = re.match(r"^\s*", str(line or ""))
    return len(match.group(0)) if match else 0


def _starts_with_circled_number(line):
    return bool(_CIRCLED_NUMBER_RE.match(str(line or "").strip()))


def _detect_marker(trimmed_line):
    line = str(trimmed_line or "").strip()
    if not line:
        return "plain"
    if re.match(r"^(?:□|○|◯)\s+", line):
        return "circle"
    if _starts_with_circled_number(line):
        return "circled"
    if re.match(r"^\d+[.)]\s+", line):
        return "number"
    if re.match(r"^[-·•▪◦*]\s+", line):
        return "bullet"
    return "plain"


def _strip_marker(trimmed_line):
    line = str(trimmed_line or "").strip()
    line = re.sub(r"^(?:□|○|◯)\s+", "", line)
    line = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*", "", line)
    line = re.sub(r"^\d+[.)]\s+", "", line)
    line = re.sub(r"^[-·•▪◦*]\s+", "", line)
    return _clean_text(line)


def _normalize_section_header(line):
    compact = _collapse_spaces(line)
    return re.sub(r"[\[\]\(\):：\-]", "", compact)


def _detect_section(line):
    compact = _normalize_section_header(line)
    if not compact:
        return None

    for section_name, labels in _SECTION_LABELS.items():
        for label in labels:
            normalized = _collapse_spaces(label)
            if compact == normalized or compact.startswith(normalized):
                return section_name
    return None


def _detect_parse_type(text):
    raw = str(text or "")
    if _TYPE1_RE.search(raw):
        return "type1"
    if re.search(r"(^|\n)\s*[□○◯]", raw):
        return "type2"
    return "type3"


def _parse_pledge_text(text):
    raw = str(text or "").replace("\r\n", "\n")
    parse_type = _detect_parse_type(raw)
    result = {
        "parse_type": parse_type,
        "goals": [],
        "strategies": [],
        "timeline": [],
        "finance": [],
        "warnings": [],
    }

    current_section = None
    current_strategy = None
    current_strategy_indent = 0

    for raw_line in raw.split("\n"):
        trimmed = str(raw_line or "").strip()
        if not trimmed:
            continue

        section = _detect_section(trimmed)
        if section:
            current_section = section
            if section != _SECTION_METHOD:
                current_strategy = None
                current_strategy_indent = 0
            continue

        if not current_section:
            current_section = _SECTION_METHOD

        if current_section == _SECTION_GOAL:
            value = _strip_marker(trimmed)
            if value:
                result["goals"].append(value)
            continue

        if current_section == _SECTION_TIMELINE:
            value = _strip_marker(trimmed)
            if value:
                result["timeline"].append(value)
            continue

        if current_section == _SECTION_FINANCE:
            value = _strip_marker(trimmed)
            if value:
                result["finance"].append(value)
            continue

        indent = _leading_spaces(raw_line)
        marker = _detect_marker(trimmed)
        content = _strip_marker(trimmed)
        if not content:
            continue

        is_strategy_by_marker = marker in {"circle", "circled", "number"}
        is_action_by_marker = marker == "bullet"

        if not current_strategy:
            current_strategy = {"title": content, "actions": []}
            current_strategy_indent = indent
            result["strategies"].append(current_strategy)
            continue

        if is_strategy_by_marker:
            current_strategy = {"title": content, "actions": []}
            current_strategy_indent = indent
            result["strategies"].append(current_strategy)
            continue

        if is_action_by_marker or indent > current_strategy_indent:
            current_strategy["actions"].append(content)
            continue

        if parse_type == "type3":
            current_strategy = {"title": content, "actions": []}
            current_strategy_indent = indent
            result["strategies"].append(current_strategy)
            continue

        current_strategy["actions"].append(content)

    if not result["goals"]:
        result["warnings"].append("목표 섹션이 비어 있습니다.")
    if not result["strategies"]:
        result["warnings"].append("이행 방법(strategy) 섹션이 비어 있습니다.")

    return result


def _build_tree_nodes(parsed):
    nodes = []

    def _append_node(*, node_type, level, content, parent_index):
        text = _clean_text(content)
        if not text:
            return None
        node = {
            "node_type": node_type,
            "level": level,
            "content": text,
            "name": text[:120],
            "parent_index": parent_index,
            "has_child": False,
        }
        index = len(nodes)
        nodes.append(node)
        if parent_index is not None and 0 <= parent_index < len(nodes):
            nodes[parent_index]["has_child"] = True
        return index

    goals = parsed.get("goals") or []
    strategies = parsed.get("strategies") or []

    if goals:
        goal_root_index = _append_node(
            node_type="goal",
            level=1,
            content=_GOAL_SECTION_TITLE,
            parent_index=None,
        )
        for goal_line in goals:
            _append_node(
                node_type="strategy",
                level=2,
                content=goal_line,
                parent_index=goal_root_index,
            )

    if strategies:
        method_root_index = _append_node(
            node_type="goal",
            level=1,
            content=_METHOD_SECTION_TITLE,
            parent_index=None,
        )
        for strategy in strategies:
            strategy_index = _append_node(
                node_type="strategy",
                level=2,
                content=strategy.get("title"),
                parent_index=method_root_index,
            )
            for action in strategy.get("actions") or []:
                _append_node(
                    node_type="action",
                    level=3,
                    content=action,
                    parent_index=strategy_index,
                )

    return nodes


def _parse_pledges_text(text):
    parsed = _parse_pledge_text(text)
    goals = []

    if parsed.get("goals"):
        goals.append(
            {
                "title": _GOAL_SECTION_TITLE,
                "promises": [{"title": item, "items": []} for item in parsed["goals"]],
            }
        )
    if parsed.get("strategies"):
        goals.append(
            {
                "title": _METHOD_SECTION_TITLE,
                "promises": [
                    {
                        "title": strategy.get("title"),
                        "items": [{"detail": action} for action in (strategy.get("actions") or [])],
                    }
                    for strategy in parsed["strategies"]
                ],
            }
        )
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
    parsed = _parse_pledge_text(raw_text or "")
    parsed_nodes = _build_tree_nodes(parsed)
    now = now_iso_fn()

    inserted_ids = []
    order_by_parent = {}

    for node in parsed_nodes:
        parent_index = node.get("parent_index")
        parent_id = inserted_ids[parent_index] if parent_index is not None and parent_index < len(inserted_ids) else None
        parent_key = str(parent_id) if parent_id is not None else "__root__"
        next_sort_order = order_by_parent.get(parent_key, 0) + 1
        order_by_parent[parent_key] = next_sort_order

        level = max(1, min(int(node.get("level") or 1), 3))
        node_type = str(node.get("node_type") or "").strip().lower() or (
            "goal" if level == 1 else ("strategy" if level == 2 else "action")
        )
        node_name = _clean_text(node.get("name") or node.get("content") or "")
        node_content = _clean_text(node.get("content") or node_name)
        if not node_content:
            continue

        inserted_row = supabase_insert_returning(
            "pledge_nodes",
            payload={
                "pledge_id": pledge_id,
                "name": node_name,
                "node_type": node_type,
                "level": level,
                "content": node_content,
                "sort_order": next_sort_order,
                "parent_id": parent_id,
                "is_leaf": not bool(node.get("has_child")),
                "created_at": now,
                "created_by": created_by,
                "updated_at": now,
                "updated_by": None,
            },
        )
        inserted_ids.append(inserted_row.get("id"))


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

