from functools import wraps
from dotenv import load_dotenv
import json
import os
import re
import sys
from secrets import token_urlsafe
from threading import Lock

load_dotenv()

from datetime import datetime, timedelta, timezone
from urllib import error as urlerror
from urllib import parse, request as urlrequest
from uuid import uuid4

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from services.pledge_tree_service import (
    delete_pledge_tree as _service_delete_pledge_tree,
    fetch_node_source_rows as _service_fetch_node_source_rows,
    insert_node_source_row as _service_insert_node_source_row,
    insert_pledge_tree as _service_insert_pledge_tree,
)
from services.pledge_read_service import (
    attach_pledge_tree_rows as _service_attach_pledge_tree_rows,
    build_progress_node_context as _service_build_progress_node_context,
    fetch_pledge_nodes as _service_fetch_pledge_nodes,
    is_execution_method_goal_text as _service_is_execution_method_goal_text,
    normalize_compact_text as _service_normalize_compact_text,
    sorted_node_rows as _service_sorted_node_rows,
)
from services import auth_session_service as _auth_session_service
from services import http_security_service as _http_security_service
from services import supabase_service as _supabase_service
from utils.app_value_utils import (
    _detect_image_signature,
    _extract_missing_column_from_runtime_message,
    _format_presidential_election_title,
    _is_elected_result,
    _is_leaf_node,
    _normalize_date_only,
    _normalize_election_round_title,
    _normalize_fulfillment_rate,
    _normalize_image_extension,
    _normalize_node_source_role,
    _normalize_parse_type,
    _normalize_progress_rate,
    _normalize_progress_source_role,
    _normalize_progress_status,
    _normalize_sort_order,
    _normalize_source_type,
    _normalize_structure_version,
    _normalize_uuid,
    _safe_int,
    _sanitize_target_url,
    _to_in_filter,
    _year_from_date,
)
from utils.app_common_utils import (
    cache_clone as _util_cache_clone,
    is_status_in_markers as _util_is_status_in_markers,
    normalize_report_status_for_admin as _util_normalize_report_status_for_admin,
    normalize_report_type as _util_normalize_report_type,
    now_iso_utc as _util_now_iso_utc,
    pagination_params as _util_pagination_params,
    parse_env_bool as _util_parse_env_bool,
    parse_env_int as _util_parse_env_int,
    slice_rows as _util_slice_rows,
)




def _env_bool(name, default=False):
    return _util_parse_env_bool(os.getenv(name), default)


def _env_int(name, default):
    return _util_parse_env_int(os.getenv(name), default)


FLASK_ENV = os.getenv("FLASK_ENV", "production").strip().lower()
DEBUG_MODE = _env_bool("FLASK_DEBUG", FLASK_ENV == "development")
IS_PRODUCTION = not DEBUG_MODE and FLASK_ENV != "development"

app = Flask(__name__)
_secret_key = (os.getenv("FLASK_SECRET_KEY") or "").strip()
if not _secret_key:
    if IS_PRODUCTION:
        raise RuntimeError("FLASK_SECRET_KEY must be set in production.")
    _secret_key = "dev-secret-change-me"
app.secret_key = _secret_key

app.config["MAX_CONTENT_LENGTH"] = max(1, _env_int("MAX_UPLOAD_MB", 5)) * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = _env_bool(
    "TEMPLATES_AUTO_RELOAD", not IS_PRODUCTION
)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = _env_int(
    "SEND_FILE_MAX_AGE_DEFAULT", 3600 if IS_PRODUCTION else 0
)
app.jinja_env.auto_reload = app.config["TEMPLATES_AUTO_RELOAD"]

SESSION_IDLE_TIMEOUT_SECONDS = max(60, _env_int("SESSION_IDLE_TIMEOUT_SECONDS", 10800))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=SESSION_IDLE_TIMEOUT_SECONDS)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
app.config["SESSION_COOKIE_SECURE"] = _env_bool("SESSION_COOKIE_SECURE", IS_PRODUCTION)

if _env_bool("TRUST_PROXY", True):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://txumpkghskgiprwqpigg.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv(
    "SUPABASE_SERVICE_KEY",
    "",
)
SUPABASE_ANON_KEY = (os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY") or "").strip()
SUPABASE_REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1"
SUPABASE_STORAGE_BASE = f"{SUPABASE_URL.rstrip('/')}/storage/v1"
SUPABASE_CANDIDATE_IMAGE_BUCKET = os.getenv("SUPABASE_CANDIDATE_IMAGE_BUCKET", "candidate_images").strip() or "candidate_images"
SUPABASE_CANDIDATE_IMAGE_FOLDER = os.getenv("SUPABASE_CANDIDATE_IMAGE_FOLDER", "candidate_images").strip().strip("/")

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "jfif"}
MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

IS_VERCEL = (os.getenv("VERCEL") or "").strip() == "1"
STATIC_PAGES_SOURCE_DIR = os.path.join(app.root_path, "static", "pages")
STATIC_PAGES_RUNTIME_DIR = (
    os.path.join("/tmp", "static-pages") if IS_VERCEL else STATIC_PAGES_SOURCE_DIR
)
EDITABLE_STATIC_PAGES = {
    "about": {"filename": "about.html", "label": "소개"},
    "privacy": {"filename": "privacy.html", "label": "개인정보처리방침"},
    "contact": {"filename": "contact.html", "label": "문의"},
}
NODE_SOURCE_TABLE = "pledge_node_sources"
PROGRESS_SOURCE_TABLE = "pledge_node_progress_sources"
REPORT_TYPE_CHOICES = {"신고", "의견"}
OPEN_REPORT_STATUS_CHOICES = {"접수", "검토중"}
RESOLVED_REPORT_STATUS_MARKERS = {"resolved", "done", "closed", "처리완료", "완료", "해결", "종결"}
REJECTED_REPORT_STATUS_MARKERS = {"rejected", "반려"}
API_CACHE_TTL_SECONDS = max(0, _env_int("API_CACHE_TTL_SECONDS", 30))
_api_cache = {}
AUTH_LOGIN_RATE_LIMIT_PER_MINUTE = max(1, _env_int("AUTH_LOGIN_RATE_LIMIT_PER_MINUTE", 30))
REPORT_RATE_LIMIT_PER_MINUTE = max(1, _env_int("REPORT_RATE_LIMIT_PER_MINUTE", 20))
_rate_limit_store = {}
_rate_limit_lock = Lock()
SECURITY_HEADERS_ENABLED = _env_bool("SECURITY_HEADERS_ENABLED", True)
CSRF_ORIGIN_CHECK = _env_bool("CSRF_ORIGIN_CHECK", True)
CSRF_TRUSTED_ORIGINS = tuple(
    origin.strip().rstrip("/")
    for origin in (os.getenv("CSRF_TRUSTED_ORIGINS") or "").split(",")
    if origin.strip()
)
CSP_REPORT_ONLY = _env_bool("CSP_REPORT_ONLY", False)
CSP_REPORT_URI = (os.getenv("CSP_REPORT_URI") or "").strip()
ALLOW_FRAME_EMBED = _env_bool("ALLOW_FRAME_EMBED", False)
HSTS_MAX_AGE_SECONDS = max(0, _env_int("HSTS_MAX_AGE_SECONDS", 31536000))
ALLOW_INSECURE_LOCAL_LOGIN_FALLBACK = _env_bool("ALLOW_INSECURE_LOCAL_LOGIN_FALLBACK", not IS_PRODUCTION)
ADMIN_ROLE_RECHECK_SECONDS = max(1, _env_int("ADMIN_ROLE_RECHECK_SECONDS", 60))
ADMIN_ROLE_FALLBACK_SECONDS = ADMIN_ROLE_RECHECK_SECONDS * 2
ADMIN_CACHE_SESSION_KEYS = ("is_admin", "is_admin_checked_at", "is_admin_uid")
SENSITIVE_CACHE_PATH_PREFIXES = (
    "/auth/",
    "/api/",
    "/admin/",
    "/login",
    "/mypage",
    "/candidate",
    "/election",
    "/pledge",
)
STATIC_VERSIONED_CACHE_MAX_AGE_SECONDS = max(
    60,
    _env_int(
        "STATIC_VERSIONED_CACHE_MAX_AGE_SECONDS",
        31536000 if IS_PRODUCTION else 300,
    ),
)
STATIC_DEFAULT_CACHE_MAX_AGE_SECONDS = max(
    0,
    _env_int(
        "STATIC_DEFAULT_CACHE_MAX_AGE_SECONDS",
        3600 if IS_PRODUCTION else 60,
    ),
)
PUBLIC_PAGE_CACHE_MAX_AGE_SECONDS = max(
    0,
    _env_int(
        "PUBLIC_PAGE_CACHE_MAX_AGE_SECONDS",
        120 if IS_PRODUCTION else 0,
    ),
)
PUBLIC_PAGE_CACHE_S_MAXAGE_SECONDS = max(
    0,
    _env_int(
        "PUBLIC_PAGE_CACHE_S_MAXAGE_SECONDS",
        300 if IS_PRODUCTION else 0,
    ),
)


def _now_iso():
    return _util_now_iso_utc()


def _audit_log(action, **fields):
    record = {"action": action, "time": _now_iso(), **fields}
    app.logger.info("AUDIT %s", json.dumps(record, ensure_ascii=False, default=str))


def _cache_clone(value):
    return _util_cache_clone(value)


def _cache_get(key):
    if API_CACHE_TTL_SECONDS <= 0:
        return None
    entry = _api_cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    now_ts = datetime.now(timezone.utc).timestamp()
    if now_ts >= expires_at:
        _api_cache.pop(key, None)
        return None
    return _cache_clone(value)


def _cache_set(key, value):
    if API_CACHE_TTL_SECONDS <= 0:
        return
    expires_at = datetime.now(timezone.utc).timestamp() + API_CACHE_TTL_SECONDS
    _api_cache[key] = (expires_at, _cache_clone(value))


def _invalidate_api_cache():
    _api_cache.clear()


def _client_ip():
    fwd = str(request.headers.get("X-Forwarded-For") or "").strip()
    if fwd:
        return fwd.split(",")[0].strip()
    return str(request.remote_addr or "unknown").strip() or "unknown"


def _is_rate_limited(bucket, limit, window_seconds=60):
    now_ts = datetime.now(timezone.utc).timestamp()
    key = (str(bucket), _client_ip())
    with _rate_limit_lock:
        existing = _rate_limit_store.get(key) or []
        valid_hits = [ts for ts in existing if (now_ts - ts) < max(1, window_seconds)]
        if len(valid_hits) >= max(1, int(limit)):
            _rate_limit_store[key] = valid_hits
            return True
        valid_hits.append(now_ts)
        _rate_limit_store[key] = valid_hits
    return False


def _normalize_origin(raw_url):
    return _http_security_service.normalize_origin(raw_url)


def _request_origin():
    return _http_security_service.request_origin(request.host_url)


def _trusted_origins():
    return _http_security_service.trusted_origins(request.host_url, CSRF_TRUSTED_ORIGINS)


def _request_is_https():
    return _http_security_service.request_is_https(
        request_is_secure=request.is_secure,
        x_forwarded_proto=request.headers.get("X-Forwarded-Proto"),
    )


def _should_check_origin():
    return _http_security_service.should_check_origin(
        csrf_origin_check=CSRF_ORIGIN_CHECK,
        method=request.method,
        path=request.path,
    )


def _origin_allowed(value):
    return _http_security_service.origin_allowed(value, _trusted_origins())


def _append_vary(response, token):
    _http_security_service.append_vary(response, token)


def _set_no_store_cache_headers(response):
    _http_security_service.set_no_store_cache_headers(response)


def _is_sensitive_cache_path(path):
    return _http_security_service.is_sensitive_cache_path(path, SENSITIVE_CACHE_PATH_PREFIXES)


def _apply_cache_policy(response):
    return _http_security_service.apply_cache_policy(
        response,
        method=request.method,
        path=request.path,
        endpoint=request.endpoint,
        status_code=response.status_code,
        query_v=request.args.get("v"),
        has_user_session=bool(session.get("user_id")),
        response_mimetype=response.mimetype,
        sensitive_prefixes=SENSITIVE_CACHE_PATH_PREFIXES,
        static_versioned_max_age_seconds=STATIC_VERSIONED_CACHE_MAX_AGE_SECONDS,
        static_default_max_age_seconds=STATIC_DEFAULT_CACHE_MAX_AGE_SECONDS,
        public_page_cache_max_age_seconds=PUBLIC_PAGE_CACHE_MAX_AGE_SECONDS,
        public_page_cache_s_maxage_seconds=PUBLIC_PAGE_CACHE_S_MAXAGE_SECONDS,
    )






def _build_csp_header(nonce):
    return _http_security_service.build_csp_header(
        nonce,
        allow_frame_embed=ALLOW_FRAME_EMBED,
        is_production=IS_PRODUCTION,
        csp_report_uri=CSP_REPORT_URI,
        supabase_url=SUPABASE_URL,
    )


def _extract_bearer_token(header_value):
    text = str(header_value or "").strip()
    if not text:
        return ""
    if text.lower().startswith("bearer "):
        return text[7:].strip()
    return ""


def _supabase_auth_apikey():
    key = SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY
    if not key:
        raise RuntimeError("SUPABASE_ANON_KEY (or SUPABASE_SERVICE_ROLE_KEY) is not configured.")
    return key


def _fetch_supabase_user(access_token):
    token = str(access_token or "").strip()
    if not token:
        raise ValueError("access_token is required")

    req = urlrequest.Request(
        url=f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": _supabase_auth_apikey(),
        },
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError as exc:
        if exc.code in {401, 403}:
            raise PermissionError("Invalid Supabase access token.") from exc
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Supabase auth verification failed ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Supabase auth verification failed (network): {exc}") from exc


def _normalize_report_type(value, default="신고"):
    return _util_normalize_report_type(
        value,
        default=default,
        choices=REPORT_TYPE_CHOICES,
    )


def _normalize_report_status_for_admin(value, default="접수"):
    return _util_normalize_report_status_for_admin(
        value,
        default=default,
        allowed={"접수", "검토중", "처리완료", "반려"},
    )


def _is_resolved_report_status(value):
    return _util_is_status_in_markers(value, RESOLVED_REPORT_STATUS_MARKERS)


def _is_rejected_report_status(value):
    return _util_is_status_in_markers(value, REJECTED_REPORT_STATUS_MARKERS)




def _pagination_params(default_limit=None, max_limit=500):
    return _util_pagination_params(
        request.args.get("limit"),
        request.args.get("offset"),
        default_limit=default_limit,
        max_limit=max_limit,
    )


def _slice_rows(rows, limit, offset):
    return _util_slice_rows(rows, limit, offset)


def _build_supabase_headers(extra_headers=None):
    return _supabase_service.build_supabase_headers(
        SUPABASE_SERVICE_ROLE_KEY,
        extra_headers,
    )


def _supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
    return _supabase_service.supabase_request(
        method,
        table,
        rest_base=SUPABASE_REST_BASE,
        service_role_key=SUPABASE_SERVICE_ROLE_KEY,
        query_params=query_params,
        payload=payload,
        extra_headers=extra_headers,
        invalidate_cache_cb=_invalidate_api_cache,
    )


def _supabase_insert_returning(table, payload):
    return _supabase_service.supabase_insert_returning(
        table,
        payload,
        supabase_request_fn=_supabase_request,
    )


def _upload_to_supabase_storage(bucket, object_path, content_bytes, content_type):
    return _supabase_service.upload_to_supabase_storage(
        bucket,
        object_path,
        content_bytes,
        content_type,
        storage_base=SUPABASE_STORAGE_BASE,
        service_role_key=SUPABASE_SERVICE_ROLE_KEY,
    )




def _delete_pledge_tree(pledge_id):
    return _service_delete_pledge_tree(
        pledge_id,
        supabase_request=_supabase_request,
        safe_delete_rows=_safe_delete_rows,
        to_in_filter=_to_in_filter,
        is_missing_schema_runtime_error=_is_missing_schema_runtime_error,
        node_source_table=NODE_SOURCE_TABLE,
        progress_source_table=PROGRESS_SOURCE_TABLE,
        logger=app.logger,
    )


def _insert_pledge_tree(pledge_id, raw_text, created_by):
    return _service_insert_pledge_tree(
        pledge_id,
        raw_text,
        created_by,
        now_iso_fn=_now_iso,
        supabase_insert_returning=_supabase_insert_returning,
        supabase_request=_supabase_request,
    )


def _fetch_candidate_election(candidate_election_id):
    rows = _supabase_request(
        "GET",
        "candidate_elections",
        query_params={
            "select": "id,candidate_id,election_id",
            "id": f"eq.{candidate_election_id}",
            "limit": "1",
        },
    ) or []
    return rows[0] if rows else None
















def _next_pledge_sort_order(candidate_election_id, exclude_pledge_id=None):
    rows = _supabase_request(
        "GET",
        "pledges",
        query_params={
            "select": "id,sort_order",
            "candidate_election_id": f"eq.{candidate_election_id}",
            "order": "sort_order.desc.nullslast,created_at.desc",
            "limit": "1000",
        },
    ) or []

    max_sort = 0
    for row in rows:
        if exclude_pledge_id is not None and str(row.get("id")) == str(exclude_pledge_id):
            continue
        max_sort = max(max_sort, _safe_int(row.get("sort_order"), 0))
    return max_sort + 1 if max_sort > 0 else 1


def _validate_pledge_payload(payload, current_pledge=None):
    candidate_election_id = _normalize_uuid(payload.get("candidate_election_id"))
    title = (payload.get("title") or "").strip()
    raw_text = (payload.get("raw_text") or "").strip()
    category = (payload.get("category") or "").strip()
    timeline_raw = payload.get("timeline_text", (current_pledge or {}).get("timeline_text"))
    finance_raw = payload.get("finance_text", (current_pledge or {}).get("finance_text"))
    parse_type_raw = payload.get("parse_type", (current_pledge or {}).get("parse_type"))
    structure_version_raw = payload.get("structure_version", (current_pledge or {}).get("structure_version"))
    fulfillment_rate_raw = payload.get("fulfillment_rate", (current_pledge or {}).get("fulfillment_rate"))

    timeline_text = (timeline_raw or "").strip() or None
    finance_text = (finance_raw or "").strip() or None
    parse_type = _normalize_parse_type(parse_type_raw)
    structure_version = _normalize_structure_version(structure_version_raw)
    fulfillment_rate = _normalize_fulfillment_rate(fulfillment_rate_raw)
    status = (payload.get("status") or "active").strip() or "active"
    sort_order = _normalize_sort_order(payload.get("sort_order"))

    if not candidate_election_id or not title or not raw_text or not category:
        raise ValueError("candidate_election_id, title, raw_text, category are required")

    candidate_election = _fetch_candidate_election(candidate_election_id)
    if not candidate_election:
        raise ValueError("candidate_election not found")

    linked_candidate_id = candidate_election.get("candidate_id")
    if not linked_candidate_id:
        raise ValueError("candidate_election has no candidate_id")

    if sort_order is None:
        if current_pledge and str(current_pledge.get("candidate_election_id")) == str(candidate_election_id):
            existing = _safe_int(current_pledge.get("sort_order"), 0)
            if existing > 0:
                sort_order = existing
        if sort_order is None:
            sort_order = _next_pledge_sort_order(
                candidate_election_id,
                exclude_pledge_id=(current_pledge or {}).get("id"),
            )

    return {
        "candidate_election_id": candidate_election_id,
        "sort_order": sort_order,
        "title": title,
        "raw_text": raw_text,
        "category": category,
        "timeline_text": timeline_text,
        "finance_text": finance_text,
        "parse_type": parse_type,
        "structure_version": structure_version,
        "fulfillment_rate": fulfillment_rate,
        "status": status,
    }


def _get_pledge_row(pledge_id):
    rows = _supabase_request(
        "GET",
        "pledges",
        query_params={
            "select": "id,candidate_election_id,sort_order,title,raw_text,category,timeline_text,finance_text,parse_type,structure_version,fulfillment_rate,status,created_by",
            "id": f"eq.{pledge_id}",
            "limit": "1",
        },
    ) or []
    return rows[0] if rows else None






def _is_missing_column_runtime_error(exc):
    message = str(exc or "").lower()
    return "column" in message and "does not exist" in message


def _supabase_get_with_select_fallback(table, query_params, select_candidates):
    return _supabase_service.supabase_get_with_select_fallback(
        table,
        query_params,
        select_candidates,
        supabase_request_fn=_supabase_request,
        is_missing_relation_runtime_error_fn=_is_missing_relation_runtime_error,
        is_missing_column_runtime_error_fn=_is_missing_column_runtime_error,
    )


def _fetch_terms_rows(candidate_filter=None, candidate_id=None, limit="5000"):
    query_base = {"limit": str(limit)}
    if candidate_filter:
        query_base["candidate_id"] = candidate_filter
    elif candidate_id is not None:
        query_base["candidate_id"] = f"eq.{candidate_id}"

    select_candidates = [
        "id,candidate_id,election_id,position,term_start,term_end,created_at,created_by",
        "id,candidate_id,election_id,position,term_start,term_end,created_at",
        "id,candidate_id,election_id,position,term_start,term_end",
        "id,candidate_id,election_id,position,term_start",
        "id,candidate_id,election_id,position",
        "id,candidate_id,election_id",
        "*",
    ]

    for include_order in (True, False):
        for select_text in select_candidates:
            query_params = dict(query_base)
            query_params["select"] = select_text
            if include_order:
                query_params["order"] = "term_start.desc"
            try:
                return _supabase_request("GET", "terms", query_params=query_params) or []
            except RuntimeError as exc:
                if _is_missing_relation_runtime_error(exc):
                    return []
                if _is_missing_column_runtime_error(exc):
                    continue
                raise
    return []


def _upsert_term_for_candidate_election(*, candidate_id, election_id, position, term_start, term_end, user_id):
    candidate_id_text = str(candidate_id or "").strip()
    election_id_text = str(election_id or "").strip()
    position_text = str(position or "").strip()
    term_start_text = str(term_start or "").strip()
    term_end_text = str(term_end or "").strip()

    if not candidate_id_text or not election_id_text or not position_text or not term_start_text:
        raise ValueError("candidate_id, election_id, position, term_start are required")
    if term_end_text and term_end_text < term_start_text:
        raise ValueError("term_end must be greater than or equal to term_start")

    now = _now_iso()
    existing_rows = _fetch_terms_rows(candidate_id=candidate_id_text, limit="5000")
    target_row = None
    for row in existing_rows:
        if str(row.get("election_id") or "").strip() == election_id_text:
            target_row = row
            break

    if target_row and target_row.get("id") is not None:
        _supabase_patch_with_optional_fields(
            "terms",
            query_params={"id": f"eq.{target_row.get('id')}"},
            payload={
                "candidate_id": candidate_id_text,
                "election_id": election_id_text,
                "position": position_text,
                "term_start": term_start_text,
                "term_end": term_end_text or None,
                "updated_at": now,
                "updated_by": user_id,
            },
            optional_fields={"term_end", "updated_by"},
        )
        return

    _supabase_request(
        "POST",
        "terms",
        payload={
            "candidate_id": candidate_id_text,
            "election_id": election_id_text,
            "position": position_text,
            "term_start": term_start_text,
            "term_end": term_end_text or None,
            "created_at": now,
            "created_by": user_id,
            "updated_at": now,
            "updated_by": None,
        },
    )


def _enrich_candidates_with_latest(rows):
    if not rows:
        return rows

    candidate_ids = [row.get("id") for row in rows if row.get("id") is not None]
    candidate_filter = _to_in_filter(candidate_ids)
    if not candidate_filter:
        return rows

    candidate_elections = _supabase_get_with_select_fallback(
        "candidate_elections",
        query_params={
            "candidate_id": candidate_filter,
            "limit": "5000",
        },
        select_candidates=[
            "id,candidate_id,election_id,party,created_at",
            "id,candidate_id,election_id,party",
            "id,candidate_id,election_id",
            "*",
        ],
    )

    terms = _fetch_terms_rows(candidate_filter=candidate_filter, limit="5000")

    election_ids = []
    for row in candidate_elections:
        eid = row.get("election_id")
        if eid is not None and str(eid) not in election_ids:
            election_ids.append(str(eid))
    for row in terms:
        eid = row.get("election_id")
        if eid is not None and str(eid) not in election_ids:
            election_ids.append(str(eid))

    election_map = {}
    if election_ids:
        election_filter = _to_in_filter(election_ids)
        election_rows = _supabase_request(
            "GET",
            "elections",
            query_params={
                "select": "id,title,election_date",
                "id": election_filter,
                "limit": "5000",
            },
        ) or []
        election_map = {str(row.get("id")): row for row in election_rows if row.get("id") is not None}

    latest_link_by_candidate = {}
    for row in sorted(candidate_elections, key=lambda x: str(x.get("created_at") or ""), reverse=True):
        key = str(row.get("candidate_id"))
        if key and key not in latest_link_by_candidate:
            latest_link_by_candidate[key] = row

    latest_term_by_candidate = {}
    for row in sorted(terms, key=lambda x: str(x.get("term_start") or ""), reverse=True):
        key = str(row.get("candidate_id"))
        if key and key not in latest_term_by_candidate:
            latest_term_by_candidate[key] = row

    for row in rows:
        cid = str(row.get("id"))
        latest_link = latest_link_by_candidate.get(cid) or {}
        latest_term = latest_term_by_candidate.get(cid) or {}
        election_id = latest_link.get("election_id") or latest_term.get("election_id")
        election_info = election_map.get(str(election_id)) or {}

        row["party"] = latest_link.get("party")
        row["position"] = latest_term.get("position")
        row["term_start"] = latest_term.get("term_start")
        row["term_end"] = latest_term.get("term_end")
        row["election_title"] = _format_presidential_election_title(election_info.get("title"))
        row["election_year"] = _year_from_date(election_info.get("election_date"))

    return rows




def _attach_pledge_tree_rows(pledges):
    return _service_attach_pledge_tree_rows(
        pledges,
        to_in_filter=_to_in_filter,
        supabase_request=_supabase_request,
        fetch_node_source_rows=_fetch_node_source_rows,
        fetch_pledge_source_rows=_fetch_pledge_source_rows,
        safe_int=_safe_int,
        is_leaf_node=_is_leaf_node,
        is_missing_schema_runtime_error=_is_missing_schema_runtime_error,
    )


def _normalize_compact_text(value):
    return _service_normalize_compact_text(value)


def _is_execution_method_goal_text(text):
    return _service_is_execution_method_goal_text(text)


def _sorted_node_rows(rows):
    return _service_sorted_node_rows(
        rows,
        safe_int=_safe_int,
    )


def _fetch_pledge_nodes(pledge_id):
    pledge_id_text = str(pledge_id or "").strip()
    if not pledge_id_text:
        return []
    try:
        return _supabase_get_with_select_fallback(
            "pledge_nodes",
            query_params={
                "pledge_id": f"eq.{pledge_id_text}",
                "limit": "50000",
                "order": "sort_order.asc.nullslast,created_at.asc,id.asc",
            },
            select_candidates=[
                "id,pledge_id,node_type,name,content,level,sort_order,parent_id,is_leaf,created_at",
                "id,pledge_id,node_type,name,content,level,sort_order,parent_id,created_at",
                "id,pledge_id,node_type,name,content,level,sort_order,parent_id",
                "id,pledge_id,node_type,name,content,level,parent_id",
                "id,pledge_id,name,content,level,parent_id,sort_order,created_at",
                "id,pledge_id,name,content,parent_id,sort_order,created_at",
                "id,pledge_id,name,content,parent_id",
                "*",
            ],
        )
    except RuntimeError as exc:
        if _is_missing_schema_runtime_error(exc):
            return []
        raise


def _build_progress_node_context(node_rows):
    return _service_build_progress_node_context(
        node_rows,
        sorted_node_rows_fn=_sorted_node_rows,
        is_leaf_node=_is_leaf_node,
        is_execution_method_goal_text_fn=_is_execution_method_goal_text,
    )


def _get_pledge_node(pledge_node_id):
    pledge_node_id_text = str(pledge_node_id or "").strip()
    if not pledge_node_id_text:
        return None
    try:
        rows = _supabase_get_with_select_fallback(
            "pledge_nodes",
            query_params={
                "id": f"eq.{pledge_node_id_text}",
                "limit": "1",
            },
            select_candidates=[
                "id,pledge_id,node_type,name,content,parent_id,is_leaf,sort_order,created_at",
                "id,pledge_id,node_type,name,content,parent_id,sort_order,created_at",
                "id,pledge_id,node_type,name,content,parent_id,sort_order",
                "id,pledge_id,node_type,name,content,parent_id",
                "id,pledge_id,name,content,parent_id,is_leaf,sort_order,created_at",
                "id,pledge_id,name,content,parent_id,sort_order,created_at",
                "id,pledge_id,name,content,parent_id",
                "id,pledge_id",
                "*",
            ],
        )
    except RuntimeError as exc:
        if _is_missing_schema_runtime_error(exc):
            return None
        raise
    return rows[0] if rows else None












def _ensure_source_exists(source_id):
    rows = _supabase_request(
        "GET",
        "sources",
        query_params={"select": "id", "id": f"eq.{source_id}", "limit": "1"},
    ) or []
    return bool(rows)


def _is_missing_relation_runtime_error(exc):
    message = str(exc or "").lower()
    return "relation" in message and "does not exist" in message


def _is_missing_column_runtime_error(exc):
    message = str(exc or "").lower()
    return "column" in message and "does not exist" in message


def _is_missing_schema_runtime_error(exc):
    return _is_missing_relation_runtime_error(exc) or _is_missing_column_runtime_error(exc)


def _is_foreign_key_runtime_error(exc):
    message = str(exc or "").lower()
    return (
        "foreign key" in message
        or "violates" in message
        or "constraint" in message
        or "23503" in message
        or "is still referenced" in message
        or "update or delete on table" in message
    )


def _is_network_runtime_error(exc):
    message = str(exc or "").lower()
    network_markers = (
        "network",
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "temporarily unavailable",
        "name or service not known",
        "failed to establish a new connection",
    )
    return any(marker in message for marker in network_markers)


def _safe_delete_rows(table_name, query_params, ignore_missing_schema=True):
    try:
        _supabase_request("DELETE", table_name, query_params=query_params)
        return True
    except RuntimeError as exc:
        if ignore_missing_schema and _is_missing_schema_runtime_error(exc):
            return False
        raise


def _fetch_node_source_rows(node_filter):
    return _service_fetch_node_source_rows(
        node_filter,
        supabase_request=_supabase_request,
        is_missing_schema_runtime_error=_is_missing_schema_runtime_error,
        node_source_table=NODE_SOURCE_TABLE,
    )


def _fetch_pledge_source_rows(pledge_filter):
    if not pledge_filter:
        return []
    try:
        return _supabase_get_with_select_fallback(
            NODE_SOURCE_TABLE,
            query_params={
                "pledge_id": pledge_filter,
                "limit": "100000",
                "order": "id.desc",
            },
            select_candidates=[
                "id,pledge_id,pledge_node_id,source_id,source_role,note,created_at",
                "id,pledge_id,pledge_node_id,source_id,source_role,note",
                "id,pledge_id,pledge_node_id,source_id,source_role",
                "id,pledge_id,pledge_node_id,source_id",
                "id,pledge_id,source_id",
                "*",
            ],
        )
    except RuntimeError as exc:
        if _is_missing_schema_runtime_error(exc):
            return []
        raise


def _insert_node_source_row(payload):
    return _service_insert_node_source_row(
        payload=payload,
        supabase_insert_with_optional_fields=_supabase_insert_with_optional_fields,
        node_source_table=NODE_SOURCE_TABLE,
        optional_fields={"pledge_id", "created_at", "created_by", "updated_at", "updated_by"},
    )


def _latest_progress_row_map(progress_rows):
    latest = {}
    for row in sorted(
        progress_rows or [],
        key=lambda x: (str(x.get("evaluation_date") or ""), str(x.get("created_at") or ""), str(x.get("id") or "")),
        reverse=True,
    ):
        key = str(row.get("pledge_node_id"))
        if key and key not in latest:
            latest[key] = row
    return latest


def _supabase_insert_with_optional_fields(table, payload, optional_fields):
    working = dict(payload or {})
    remaining = set(optional_fields or [])

    while True:
        try:
            return _supabase_insert_returning(table, working)
        except RuntimeError as exc:
            message = str(exc)
            column = _extract_missing_column_from_runtime_message(message)
            if not column:
                raise
            if column not in remaining:
                raise

            working.pop(column, None)
            remaining.remove(column)


def _supabase_patch_with_optional_fields(table, query_params, payload, optional_fields):
    working = dict(payload or {})
    remaining = set(optional_fields or [])

    while True:
        try:
            _supabase_request("PATCH", table, query_params=query_params, payload=working)
            return working
        except RuntimeError as exc:
            message = str(exc)
            column = _extract_missing_column_from_runtime_message(message)
            if not column:
                raise
            if column not in remaining:
                raise

            working.pop(column, None)
            remaining.remove(column)




def _fetch_latest_progress_row(pledge_node_id):
    rows = _supabase_get_with_select_fallback(
        "pledge_node_progress",
        query_params={
            "pledge_node_id": f"eq.{pledge_node_id}",
            "order": "evaluation_date.desc,updated_at.desc,created_at.desc,id.desc",
            "limit": "1",
        },
        select_candidates=[
            "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date,created_at,created_by,updated_at,updated_by",
            "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date,created_at,updated_at",
            "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date,created_at",
            "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date",
            "id,pledge_node_id,progress_rate,status,reason,evaluator",
            "id,pledge_node_id,progress_rate,status,reason",
            "id,pledge_node_id,progress_rate,status",
            "id,pledge_node_id,progress_rate",
            "id,pledge_node_id",
            "*",
        ],
    )
    return rows[0] if rows else None


def _fetch_latest_progress_source_link(progress_id):
    rows = _supabase_get_with_select_fallback(
        "pledge_node_progress_sources",
        query_params={
            "pledge_node_progress_id": f"eq.{progress_id}",
            "order": "created_at.desc,id.desc",
            "limit": "1",
        },
        select_candidates=[
            "id,pledge_node_progress_id,source_id,source_role,quoted_text,page_no,note,created_at,updated_at",
            "id,pledge_node_progress_id,source_id,source_role,quoted_text,page_no,note,created_at",
            "id,pledge_node_progress_id,source_id,source_role,quoted_text,page_no,note",
            "id,pledge_node_progress_id,source_id,source_role,quoted_text,page_no",
            "id,pledge_node_progress_id,source_id,source_role",
            "id,pledge_node_progress_id,source_id",
            "id,pledge_node_progress_id",
            "*",
        ],
    )
    return rows[0] if rows else None


def _try_fetch_user_profile(user_id):
    attempts = [
        {"id_col": "user__id", "created_col": "create_at", "updated_col": "update_at"},
        {"id_col": "user_id", "created_col": "create_at", "updated_col": "update_at"},
        {"id_col": "user__id", "created_col": "created_at", "updated_col": "updated_at"},
        {"id_col": "user_id", "created_col": "created_at", "updated_col": "updated_at"},
    ]

    for attempt in attempts:
        try:
            rows = _supabase_request(
                "GET",
                "user_profiles",
                query_params={
                    "select": f"{attempt['id_col']},nickname,role,status,{attempt['created_col']},{attempt['updated_col']},reputation_score",
                    attempt["id_col"]: f"eq.{user_id}",
                    "limit": "1",
                },
            )
        except RuntimeError as exc:
            if "column" in str(exc):
                continue
            raise

        if rows:
            row = rows[0]
            row["created_at"] = row.get(attempt["created_col"])
            row["updated_at"] = row.get(attempt["updated_col"])
            return row

    return None


def ensure_user_profile(user_id, email):
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return

    if _try_fetch_user_profile(normalized_user_id):
        return

    nickname = (str(email or "").split("@")[0] or f"user_{normalized_user_id[:8]}").strip()
    now_iso = _now_iso()
    optional_fields = {
        "nickname",
        "role",
        "status",
        "reputation_score",
        "create_at",
        "update_at",
        "created_at",
        "updated_at",
    }
    last_error = None

    for id_column in ("user__id", "user_id"):
        payload = {
            id_column: normalized_user_id,
            "nickname": nickname,
            "role": "user",
            "status": "active",
            "reputation_score": 0,
            # user_profiles 스키마가 혼재되어 있어 타임스탬프 컬럼명을 모두 시도한다.
            "create_at": now_iso,
            "update_at": now_iso,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        try:
            _supabase_insert_with_optional_fields(
                "user_profiles",
                payload,
                optional_fields=optional_fields,
            )
            return
        except RuntimeError as exc:
            message = str(exc or "")
            lowered = message.lower()
            if "duplicate key value violates unique constraint" in lowered or "already exists" in lowered:
                return
            if _is_network_runtime_error(exc):
                raise

            missing_column = _extract_missing_column_from_runtime_message(message)
            if missing_column and missing_column == id_column:
                last_error = exc
                continue

            last_error = exc

    if last_error:
        raise last_error


def _session_user_id():
    return session.get("user_id")


def _clear_admin_session_cache():
    _auth_session_service.clear_admin_session_cache(session, ADMIN_CACHE_SESSION_KEYS)


def _normalize_session_admin_flag(value):
    return _auth_session_service.normalize_session_admin_flag(value)


def _normalize_session_admin_checked_at(value):
    return _auth_session_service.normalize_session_admin_checked_at(value)


def _normalize_session_admin_uid(value):
    return _auth_session_service.normalize_session_admin_uid(value)


def _admin_cache_debug(event, **fields):
    if not DEBUG_MODE:
        return
    details = " ".join(f"{key}={fields[key]}" for key in sorted(fields))
    app.logger.info("admin_cache %s %s", event, details)


def _set_admin_session_cache(uid, is_admin, *, checked_at=None):
    _auth_session_service.set_admin_session_cache(
        session,
        ADMIN_CACHE_SESSION_KEYS,
        uid=uid,
        is_admin=is_admin,
        checked_at=checked_at,
        now_ts_fn=lambda: int(datetime.now(timezone.utc).timestamp()),
    )


def _is_admin(user_id):
    if not user_id:
        return False
    profile = _try_fetch_user_profile(user_id) or {}
    role = str(profile.get("role") or "").lower()
    return role in {"admin", "super_admin"}


def _session_is_admin(*, strict=False):
    uid_text = _normalize_session_admin_uid(_session_user_id())
    if not uid_text:
        _admin_cache_debug("cache miss", reason="no_uid", strict=strict)
        return False

    now_ts = int(datetime.now(timezone.utc).timestamp())
    cached_uid = _normalize_session_admin_uid(session.get("is_admin_uid"))
    cached_admin = _normalize_session_admin_flag(session.get("is_admin"))
    checked_at = _normalize_session_admin_checked_at(session.get("is_admin_checked_at"))

    if cached_uid and cached_uid != uid_text:
        _admin_cache_debug(
            "cache miss",
            reason="uid_mismatch",
            session_uid=cached_uid,
            uid=uid_text,
            strict=strict,
        )
        _clear_admin_session_cache()
        cached_uid = None
        cached_admin = None
        checked_at = None

    has_cache = cached_uid == uid_text and cached_admin is not None and checked_at is not None
    cache_age = None
    if has_cache:
        cache_age = max(0, now_ts - checked_at)
        if cache_age <= ADMIN_ROLE_RECHECK_SECONDS:
            _admin_cache_debug("cache hit", uid=uid_text, age=cache_age, strict=strict)
            return cached_admin
        _admin_cache_debug("cache expired", uid=uid_text, age=cache_age, strict=strict)
    else:
        _admin_cache_debug("cache miss", uid=uid_text, strict=strict)

    try:
        fresh_is_admin = bool(_is_admin(uid_text))
        _set_admin_session_cache(uid_text, fresh_is_admin, checked_at=now_ts)
        _admin_cache_debug(
            "refresh success",
            uid=uid_text,
            strict=strict,
            is_admin=fresh_is_admin,
        )
        return fresh_is_admin
    except Exception as exc:
        _admin_cache_debug(
            "refresh failed",
            uid=uid_text,
            strict=strict,
            error=str(exc),
        )
        if strict:
            return False
        if has_cache and cache_age is not None and cache_age <= ADMIN_ROLE_FALLBACK_SECONDS:
            return cached_admin
        return False


def _static_page_path(page_key, runtime=False):
    config = EDITABLE_STATIC_PAGES.get(page_key)
    if not config:
        raise ValueError("invalid page key")
    base_dir = STATIC_PAGES_RUNTIME_DIR if runtime else STATIC_PAGES_SOURCE_DIR
    return os.path.join(base_dir, config["filename"])


def _read_static_page(page_key):
    runtime_path = _static_page_path(page_key, runtime=True)
    source_path = _static_page_path(page_key, runtime=False)
    paths = [runtime_path]
    if source_path != runtime_path:
        paths.append(source_path)

    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fp:
                return fp.read()
        except FileNotFoundError:
            continue
    return ""


def _write_static_page(page_key, content):
    path = _static_page_path(page_key, runtime=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(content or "")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not _session_user_id():
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)

    return wrapped_view


def api_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not _session_user_id():
            return jsonify({"error": "login required"}), 401
        return view(*args, **kwargs)

    return wrapped_view


def api_admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        uid = _session_user_id()
        if not uid:
            return jsonify({"error": "login required"}), 401
        if not _session_is_admin(strict=True):
            return jsonify({"error": "admin required"}), 403
        return view(*args, **kwargs)

    return wrapped_view


@app.errorhandler(RuntimeError)
def handle_runtime_error(exc):
    error_id = uuid4().hex
    app.logger.exception("RuntimeError [%s]: %s", error_id, exc)
    if request.path.startswith("/api/") or request.path.startswith("/auth/"):
        if not IS_PRODUCTION:
            return jsonify({"error": str(exc), "error_id": error_id}), 500
        return jsonify({"error": "internal server error", "error_id": error_id}), 500
    raise exc


@app.before_request
def assign_request_nonce():
    g.csp_nonce = token_urlsafe(16)
    return None


@app.before_request
def enforce_state_change_origin_check():
    if not _should_check_origin():
        return None

    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")

    if origin:
        if not _origin_allowed(origin):
            return jsonify({"error": "forbidden origin"}), 403
        return None

    if referer:
        if not _origin_allowed(referer):
            return jsonify({"error": "forbidden referer"}), 403
        return None

    # Non-browser clients may legitimately omit Origin/Referer.
    return None


@app.before_request
def enforce_idle_session_timeout():
    if request.endpoint == "static":
        return None

    uid = _session_user_id()
    if not uid:
        return None

    now_ts = int(datetime.now(timezone.utc).timestamp())
    last_ts = session.get("last_activity_ts")

    if (
        isinstance(last_ts, (int, float))
        and SESSION_IDLE_TIMEOUT_SECONDS > 0
        and (now_ts - int(last_ts)) > SESSION_IDLE_TIMEOUT_SECONDS
    ):
        session.clear()
        if request.path.startswith("/api/") or request.path.startswith("/auth/activity"):
            return jsonify({"error": "session expired"}), 401
        return redirect(url_for("login_page"))

    session["last_activity_ts"] = now_ts
    session.permanent = True
    return None


@app.after_request
def after_request(response):
    _apply_cache_policy(response)

    if SECURITY_HEADERS_ENABLED:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN" if ALLOW_FRAME_EMBED else "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        csp_value = _build_csp_header(getattr(g, "csp_nonce", ""))
        if CSP_REPORT_ONLY:
            response.headers["Content-Security-Policy-Report-Only"] = csp_value
        else:
            response.headers["Content-Security-Policy"] = csp_value
            response.headers.pop("Content-Security-Policy-Report-Only", None)

        if HSTS_MAX_AGE_SECONDS > 0 and _request_is_https():
            response.headers["Strict-Transport-Security"] = f"max-age={HSTS_MAX_AGE_SECONDS}; includeSubDomains"
    return response


@app.context_processor
def inject_template_flags():
    return {
        "is_admin_user": _session_is_admin(),
        "csp_nonce": getattr(g, "csp_nonce", ""),
        "debug_mode": DEBUG_MODE,
    }



# Route modules split by domain.
import routes.pages  # noqa: F401
import routes.auth  # noqa: F401
import routes.candidate  # noqa: F401
import routes.candidate_admin  # noqa: F401
import routes.election  # noqa: F401
import routes.pledge  # noqa: F401
import routes.progress  # noqa: F401
import routes.report  # noqa: F401
import routes.static_pages  # noqa: F401
import routes.admin_common  # noqa: F401

_ROUTE_MODULE_NAMES = (
    "routes.pages",
    "routes.auth",
    "routes.candidate",
    "routes.candidate_admin",
    "routes.election",
    "routes.pledge",
    "routes.progress",
    "routes.report",
    "routes.static_pages",
    "routes.admin_common",
)


def _sync_route_module_bindings():
    core_values = globals()
    for module_name in _ROUTE_MODULE_NAMES:
        module = sys.modules.get(module_name)
        if not module:
            continue
        module_dict = module.__dict__
        for key in tuple(module_dict.keys()):
            if key.startswith("__") or key in {"core", "_name", "_value"}:
                continue
            if key in core_values:
                module_dict[key] = core_values[key]


_sync_route_module_bindings()


@app.before_request
def refresh_route_module_bindings():
    _sync_route_module_bindings()
    return None

application = app

if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_RUN_HOST", "0.0.0.0"),
        port=_env_int("PORT", 8000),
        debug=DEBUG_MODE,
        use_reloader=False,
    )
