import json
from urllib import error as urlerror
from urllib import parse, request as urlrequest


def build_supabase_headers(service_role_key, extra_headers=None):
    if not service_role_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_KEY) is not configured.")

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def supabase_request(
    method,
    table,
    *,
    rest_base,
    service_role_key,
    query_params=None,
    payload=None,
    extra_headers=None,
    invalidate_cache_cb=None,
):
    if str(method or "").upper() in {"POST", "PATCH", "DELETE"} and callable(invalidate_cache_cb):
        invalidate_cache_cb()
    query = f"?{parse.urlencode(query_params)}" if query_params else ""
    url = f"{str(rest_base or '').rstrip('/')}/{table}{query}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")

    req = urlrequest.Request(
        url=url,
        data=body,
        headers=build_supabase_headers(service_role_key, extra_headers),
        method=method,
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Supabase request failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Supabase request failed (network): {exc}") from exc


def supabase_insert_returning(table, payload, *, supabase_request_fn):
    rows = supabase_request_fn(
        "POST",
        table,
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    ) or []
    if isinstance(rows, list) and rows:
        return rows[0]
    if isinstance(rows, dict):
        return rows
    raise RuntimeError(f"Failed to insert row in {table}")


def upload_to_supabase_storage(
    bucket,
    object_path,
    content_bytes,
    content_type,
    *,
    storage_base,
    service_role_key,
):
    encoded_path = parse.quote(object_path, safe="/")
    storage_root = str(storage_base or "").rstrip("/")
    url = f"{storage_root}/object/{bucket}/{encoded_path}"
    req = urlrequest.Request(
        url=url,
        data=content_bytes,
        headers=build_supabase_headers(
            service_role_key,
            {
                "Content-Type": content_type or "application/octet-stream",
                "x-upsert": "true",
            },
        ),
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=20):
            pass
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Supabase storage upload failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Supabase storage upload failed (network): {exc}") from exc

    return f"{storage_root}/object/public/{bucket}/{encoded_path}"


def supabase_get_with_select_fallback(
    table,
    query_params,
    select_candidates,
    *,
    supabase_request_fn,
    is_missing_relation_runtime_error_fn,
    is_missing_column_runtime_error_fn,
):
    base_query = dict(query_params or {})
    last_missing_column_error = None
    include_order_options = [True]
    if "order" in base_query:
        include_order_options.append(False)

    for include_order in include_order_options:
        for select_text in select_candidates or []:
            current_query = dict(base_query)
            if not include_order:
                current_query.pop("order", None)
            current_query["select"] = select_text
            try:
                return supabase_request_fn("GET", table, query_params=current_query) or []
            except RuntimeError as exc:
                if callable(is_missing_relation_runtime_error_fn) and is_missing_relation_runtime_error_fn(exc):
                    return []
                if callable(is_missing_column_runtime_error_fn) and is_missing_column_runtime_error_fn(exc):
                    last_missing_column_error = exc
                    continue
                raise

    if last_missing_column_error:
        raise last_missing_column_error
    return []
