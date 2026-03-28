import copy
import time


def embedded_single_row(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return first
    return {}


def sortable_date_key(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def latest_election_sort_key(row):
    row = row or {}
    election_info = embedded_single_row(row.get("election"))
    return (
        sortable_date_key(election_info.get("election_date")),
        str(row.get("created_at") or ""),
        str(row.get("id") or ""),
    )


def latest_term_sort_key(row):
    row = row or {}
    return (
        sortable_date_key(row.get("term_start")),
        str(row.get("created_at") or ""),
        str(row.get("id") or ""),
    )


def apply_candidate_latest_fields(
    candidate,
    election_links,
    terms,
    *,
    format_presidential_election_title_fn,
    year_from_date_fn,
):
    candidate_row = dict(candidate or {})
    sorted_links = sorted(election_links or [], key=latest_election_sort_key, reverse=True)
    sorted_terms = sorted(terms or [], key=latest_term_sort_key, reverse=True)
    latest_link = sorted_links[0] if sorted_links else {}
    latest_term = sorted_terms[0] if sorted_terms else {}

    election_by_id = {}
    for row in election_links or []:
        election_id = row.get("election_id")
        if election_id is None:
            continue
        election_by_id[str(election_id)] = embedded_single_row(row.get("election"))

    election_info = embedded_single_row((latest_link or {}).get("election"))
    if not election_info:
        election_id = (latest_link or {}).get("election_id") or (latest_term or {}).get("election_id")
        if election_id is not None:
            election_info = election_by_id.get(str(election_id), {})

    candidate_row["party"] = (latest_link or {}).get("party")
    candidate_row["position"] = (latest_term or {}).get("position")
    candidate_row["term_start"] = (latest_term or {}).get("term_start")
    candidate_row["term_end"] = (latest_term or {}).get("term_end")
    candidate_row["election_title"] = format_presidential_election_title_fn((election_info or {}).get("title"))
    candidate_row["election_year"] = year_from_date_fn((election_info or {}).get("election_date"))
    return candidate_row


def is_join_embed_runtime_error(exc, *, is_missing_schema_runtime_error_fn):
    if is_missing_schema_runtime_error_fn(exc):
        return True
    message = str(exc or "").lower()
    markers = (
        "relationship",
        "embed",
        "schema cache",
        "failed to parse select",
        "not found in schema",
        "could not find",
        "could not embed",
        "select parameter",
        "pgrst200",
        "pgrst201",
        "pgrst204",
    )
    return any(marker in message for marker in markers)


def fetch_candidate_elections_joined(
    candidate_id,
    *,
    supabase_request_fn,
    supabase_get_with_select_fallback_fn,
    is_join_embed_runtime_error_fn,
    debug_join_fallback_fn,
):
    base_query = {
        "candidate_id": f"eq.{candidate_id}",
        "order": "created_at.desc",
        "limit": "1000",
    }
    joined_select_candidates = [
        (
            "id,candidate_id,election_id,party,result,is_elect,candidate_number,created_at,"
            "election:elections(id,election_type,title,election_date),"
            "pledges:pledges(id,candidate_election_id,sort_order,title,raw_text,category,timeline_text,finance_text,parse_type,structure_version,fulfillment_rate,status,created_at)",
            True,
            True,
        ),
        (
            "id,candidate_id,election_id,party,result,is_elect,candidate_number,created_at,"
            "election:elections(id,election_type,title,election_date)",
            False,
            True,
        ),
    ]

    for include_order in (True, False):
        for index, (select_text, has_pledges_embed, has_election_embed) in enumerate(joined_select_candidates, start=1):
            query_params = dict(base_query)
            if not include_order:
                query_params.pop("order", None)
            query_params["select"] = select_text
            try:
                rows = supabase_request_fn("GET", "candidate_elections", query_params=query_params) or []
                return rows, has_pledges_embed, has_election_embed, "fast_path"
            except RuntimeError as exc:
                if is_join_embed_runtime_error_fn(exc):
                    stage = f"joined_variant_{index}_{'with_order' if include_order else 'without_order'}"
                    debug_join_fallback_fn(candidate_id, stage, exc)
                    continue
                raise

    debug_join_fallback_fn(candidate_id, "legacy_candidate_elections", "all_join_variants_failed")
    rows = supabase_get_with_select_fallback_fn(
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
    return rows, False, False, "fallback"


def flatten_joined_pledges(candidate_election_rows, candidate_id):
    rows = []
    for link in candidate_election_rows or []:
        link_id = link.get("id")
        nested_pledges = link.pop("pledges", None)
        if not isinstance(nested_pledges, list):
            continue
        for pledge in nested_pledges:
            if not isinstance(pledge, dict):
                continue
            pledge_row = dict(pledge)
            if pledge_row.get("candidate_election_id") in (None, "", "null"):
                pledge_row["candidate_election_id"] = link_id
            pledge_row["candidate_id"] = candidate_id
            rows.append(pledge_row)
    return rows


def normalize_election_payload(link_row, *, format_presidential_election_title_fn):
    election_info = embedded_single_row((link_row or {}).get("election"))
    return {
        "id": election_info.get("id"),
        "election_type": election_info.get("election_type"),
        "title": format_presidential_election_title_fn(election_info.get("title")),
        "election_date": election_info.get("election_date"),
    }


def filter_visible_pledges(pledges, is_admin):
    rows = [row for row in (pledges or []) if str(row.get("status") or "active") != "deleted"]
    if not is_admin:
        rows = [row for row in rows if str(row.get("status") or "active") != "hidden"]
    return rows


def detail_tree_cache_key(candidate_id, is_admin):
    return f"{candidate_id}:{'admin' if is_admin else 'public'}"


def detail_tree_cache_get(cache_store, cache_lock, candidate_id, is_admin, *, ttl_seconds):
    key = detail_tree_cache_key(candidate_id, is_admin)
    now_ts = time.time()
    with cache_lock:
        cached_entry = cache_store.get(key)
        if not cached_entry:
            return None, 0, "miss"
        cached_at = float(cached_entry.get("cached_at") or 0.0)
        if now_ts - cached_at > max(1, int(ttl_seconds)):
            cache_store.pop(key, None)
            return None, 0, "stale"
        return (
            copy.deepcopy(cached_entry.get("pledges") or []),
            int(cached_entry.get("fallback_goal_count") or 0),
            "hit",
        )


def detail_tree_cache_set(cache_store, cache_lock, candidate_id, is_admin, pledges, fallback_goal_count):
    key = detail_tree_cache_key(candidate_id, is_admin)
    with cache_lock:
        cache_store[key] = {
            "cached_at": time.time(),
            "pledges": copy.deepcopy(pledges or []),
            "fallback_goal_count": int(fallback_goal_count or 0),
        }
