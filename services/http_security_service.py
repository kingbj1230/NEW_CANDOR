from urllib import parse


def normalize_origin(raw_url):
    text = str(raw_url or "").strip()
    if not text:
        return ""
    parsed = parse.urlparse(text)
    scheme = str(parsed.scheme or "").lower()
    netloc = str(parsed.netloc or "").strip().lower()
    if scheme not in {"http", "https"} or not netloc:
        return ""
    return f"{scheme}://{netloc}"


def request_origin(host_url):
    origin = normalize_origin(host_url)
    return origin.rstrip("/")


def trusted_origins(host_url, configured_origins):
    trusted = {request_origin(host_url)}
    for origin in configured_origins or []:
        normalized = normalize_origin(origin)
        if normalized:
            trusted.add(normalized)
    return trusted


def request_is_https(*, request_is_secure, x_forwarded_proto):
    if request_is_secure:
        return True
    x_proto = str(x_forwarded_proto or "").split(",")[0].strip().lower()
    return x_proto == "https"


def should_check_origin(*, csrf_origin_check, method, path):
    if not csrf_origin_check:
        return False
    if str(method or "").upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    if str(path or "").startswith("/static/"):
        return False
    return True


def origin_allowed(value, trusted_origin_values):
    normalized = normalize_origin(value)
    if not normalized:
        return False
    return normalized in set(trusted_origin_values or [])


def append_vary(response, token):
    current = str(response.headers.get("Vary") or "").strip()
    parts = [part.strip() for part in current.split(",") if part.strip()] if current else []
    if token not in parts:
        parts.append(token)
    if parts:
        response.headers["Vary"] = ", ".join(parts)


def set_no_store_cache_headers(response):
    response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


def is_sensitive_cache_path(path, path_prefixes):
    text = str(path or "")
    return any(text.startswith(prefix) for prefix in (path_prefixes or []))


def apply_cache_policy(
    response,
    *,
    method,
    path,
    endpoint,
    status_code,
    query_v,
    has_user_session,
    response_mimetype,
    sensitive_prefixes,
    static_versioned_max_age_seconds,
    static_default_max_age_seconds,
    public_page_cache_max_age_seconds,
    public_page_cache_s_maxage_seconds,
):
    if str(method or "").upper() not in {"GET", "HEAD"} or int(status_code or 200) >= 400:
        set_no_store_cache_headers(response)
        return response

    if endpoint == "static" or str(path or "").startswith("/static/"):
        if query_v:
            response.headers["Cache-Control"] = (
                f"public, max-age={int(static_versioned_max_age_seconds)}, immutable"
            )
        else:
            response.headers["Cache-Control"] = (
                f"public, max-age={int(static_default_max_age_seconds)}"
            )
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
        append_vary(response, "Accept-Encoding")
        return response

    if is_sensitive_cache_path(path, sensitive_prefixes) or bool(has_user_session):
        set_no_store_cache_headers(response)
        append_vary(response, "Cookie")
        return response

    if response_mimetype == "text/html":
        cache_parts = [f"public, max-age={int(public_page_cache_max_age_seconds)}"]
        if int(public_page_cache_s_maxage_seconds) > 0:
            cache_parts.append(f"s-maxage={int(public_page_cache_s_maxage_seconds)}")
            cache_parts.append("stale-while-revalidate=60")
        response.headers["Cache-Control"] = ", ".join(cache_parts)
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
        append_vary(response, "Accept-Encoding")
        return response

    set_no_store_cache_headers(response)
    return response


def build_csp_header(
    nonce,
    *,
    allow_frame_embed,
    is_production,
    csp_report_uri,
    supabase_url,
):
    script_parts = ["'self'", "https://cdn.jsdelivr.net"]
    if nonce:
        script_parts.append(f"'nonce-{nonce}'")

    connect_parts = ["'self'", "https://*.supabase.co", "wss://*.supabase.co"]
    supabase_origin = normalize_origin(supabase_url)
    if supabase_origin:
        connect_parts.append(supabase_origin)

    frame_ancestors = "'self'" if allow_frame_embed else "'none'"
    directives = [
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        f"frame-ancestors {frame_ancestors}",
        "img-src 'self' data: https:",
        "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
        f"script-src {' '.join(script_parts)}",
        f"connect-src {' '.join(connect_parts)}",
        "form-action 'self'",
    ]
    if is_production:
        directives.append("upgrade-insecure-requests")
    if csp_report_uri:
        directives.append(f"report-uri {csp_report_uri}")
    return "; ".join(directives)
