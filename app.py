from functools import wraps
from dotenv import load_dotenv
import json
import os
import re
from secrets import token_urlsafe
from threading import Lock

load_dotenv()

from datetime import datetime, timedelta, timezone
from urllib import error as urlerror
from urllib import parse, request as urlrequest
from uuid import uuid4

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix




def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


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

SESSION_IDLE_TIMEOUT_SECONDS = max(60, _env_int("SESSION_IDLE_TIMEOUT_SECONDS", 3600))
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
NODE_SOURCE_TABLE_CANDIDATES = ("pledge_node_sources", "pledge_node__sources")
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


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _audit_log(action, **fields):
    record = {"action": action, "time": _now_iso(), **fields}
    app.logger.info("AUDIT %s", json.dumps(record, ensure_ascii=False, default=str))


def _cache_clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


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
    text = str(raw_url or "").strip()
    if not text:
        return ""
    parsed = parse.urlparse(text)
    scheme = str(parsed.scheme or "").lower()
    netloc = str(parsed.netloc or "").strip().lower()
    if scheme not in {"http", "https"} or not netloc:
        return ""
    return f"{scheme}://{netloc}"


def _request_origin():
    origin = _normalize_origin(request.host_url)
    return origin.rstrip("/")


def _trusted_origins():
    trusted = {_request_origin()}
    for origin in CSRF_TRUSTED_ORIGINS:
        normalized = _normalize_origin(origin)
        if normalized:
            trusted.add(normalized)
    return trusted


def _request_is_https():
    if request.is_secure:
        return True
    x_proto = str(request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    return x_proto == "https"


def _should_check_origin():
    if not CSRF_ORIGIN_CHECK:
        return False
    if str(request.method or "").upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    if request.path.startswith("/static/"):
        return False
    return True


def _origin_allowed(value):
    normalized = _normalize_origin(value)
    if not normalized:
        return False
    return normalized in _trusted_origins()


def _normalize_image_extension(ext):
    raw = str(ext or "").strip().lower()
    if raw in {"jpeg", "jfif"}:
        return "jpg"
    return raw


def _detect_image_signature(content_bytes):
    data = content_bytes or b""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif", "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None, None


def _build_csp_header(nonce):
    script_parts = ["'self'", "https://cdn.jsdelivr.net"]
    if nonce:
        script_parts.append(f"'nonce-{nonce}'")

    connect_parts = ["'self'", "https://*.supabase.co", "wss://*.supabase.co"]
    supabase_origin = _normalize_origin(SUPABASE_URL)
    if supabase_origin:
        connect_parts.append(supabase_origin)

    frame_ancestors = "'self'" if ALLOW_FRAME_EMBED else "'none'"
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
    if IS_PRODUCTION:
        directives.append("upgrade-insecure-requests")
    if CSP_REPORT_URI:
        directives.append(f"report-uri {CSP_REPORT_URI}")
    return "; ".join(directives)


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
    raw = str(value or "").strip() or default
    if raw not in REPORT_TYPE_CHOICES:
        raise ValueError(f"report_type must be one of: {', '.join(sorted(REPORT_TYPE_CHOICES))}")
    return raw


def _normalize_report_status_for_admin(value, default="접수"):
    raw = str(value or "").strip() or default
    allowed = {"접수", "검토중", "처리완료", "반려"}
    if raw not in allowed:
        raise ValueError(f"status must be one of: {', '.join(sorted(allowed))}")
    return raw


def _is_resolved_report_status(value):
    normalized = str(value or "").replace(" ", "").lower()
    return normalized in RESOLVED_REPORT_STATUS_MARKERS


def _is_rejected_report_status(value):
    normalized = str(value or "").replace(" ", "").lower()
    return normalized in REJECTED_REPORT_STATUS_MARKERS


def _sanitize_target_url(raw_url):
    text = str(raw_url or "").strip()
    if not text:
        return None
    if len(text) > 2048:
        text = text[:2048]
    try:
        parsed = parse.urlparse(text)
    except Exception:
        return None
    if parsed.scheme in {"http", "https"}:
        return text
    return None


def _pagination_params(default_limit=None, max_limit=500):
    limit_raw = str(request.args.get("limit") or "").strip()
    offset_raw = str(request.args.get("offset") or "").strip()

    offset = 0
    if offset_raw:
        try:
            offset = max(0, int(offset_raw))
        except (TypeError, ValueError):
            offset = 0

    if not limit_raw:
        return default_limit, offset

    try:
        parsed_limit = int(limit_raw)
    except (TypeError, ValueError):
        return default_limit, offset
    parsed_limit = max(1, parsed_limit)
    if max_limit > 0:
        parsed_limit = min(parsed_limit, max_limit)
    return parsed_limit, offset


def _slice_rows(rows, limit, offset):
    total = len(rows or [])
    if limit is None:
        return rows, total
    sliced = (rows or [])[offset: offset + limit]
    return sliced, total


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "time": _now_iso()}), 200


def _build_supabase_headers(extra_headers=None):
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_KEY) is not configured.")

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
    if str(method or "").upper() in {"POST", "PATCH", "DELETE"}:
        _invalidate_api_cache()
    query = f"?{parse.urlencode(query_params)}" if query_params else ""
    url = f"{SUPABASE_REST_BASE}/{table}{query}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")

    req = urlrequest.Request(
        url=url,
        data=body,
        headers=_build_supabase_headers(extra_headers),
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


def _supabase_insert_returning(table, payload):
    rows = _supabase_request(
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


def _upload_to_supabase_storage(bucket, object_path, content_bytes, content_type):
    encoded_path = parse.quote(object_path, safe="/")
    url = f"{SUPABASE_STORAGE_BASE}/object/{bucket}/{encoded_path}"
    req = urlrequest.Request(
        url=url,
        data=content_bytes,
        headers=_build_supabase_headers(
            {
                "Content-Type": content_type or "application/octet-stream",
                "x-upsert": "true",
            }
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

    return f"{SUPABASE_STORAGE_BASE}/object/public/{bucket}/{encoded_path}"


def _to_in_filter(values):
    quoted = []
    for value in values:
        if value is None:
            continue
        escaped = str(value).replace('"', r"\"")
        quoted.append(f'"{escaped}"')
    if not quoted:
        return None
    return f"in.({','.join(quoted)})"


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


def _delete_pledge_tree(pledge_id):
    node_rows = _supabase_request(
        "GET",
        "pledge_nodes",
        query_params={
            "select": "id",
            "pledge_id": f"eq.{pledge_id}",
            "limit": "50000",
        },
    ) or []
    node_ids = [row.get("id") for row in node_rows if row.get("id") is not None]
    node_filter = _to_in_filter(node_ids)

    if node_filter:
        progress_rows = _supabase_request(
            "GET",
            "pledge_node_progress",
            query_params={
                "select": "id",
                "pledge_node_id": node_filter,
                "limit": "50000",
            },
        ) or []
        progress_ids = [row.get("id") for row in progress_rows if row.get("id") is not None]
        progress_filter = _to_in_filter(progress_ids)

        if progress_filter:
            _supabase_request(
                "DELETE",
                "pledge_node_progress_sources",
                query_params={"pledge_node_progress_id": progress_filter},
            )
        _supabase_request(
            "DELETE",
            "pledge_node_progress",
            query_params={"pledge_node_id": node_filter},
        )
        _delete_node_source_rows(node_filter)

    _supabase_request("DELETE", "pledge_nodes", query_params={"pledge_id": f"eq.{pledge_id}"})


def _insert_pledge_tree(pledge_id, raw_text, created_by):
    goals = _parse_pledges_text(raw_text or "")
    now = _now_iso()

    for goal_idx, goal in enumerate(goals, start=1):
        goal_text = str(goal.get("title") or "").strip()
        if not goal_text:
            continue

        inserted_goal = _supabase_insert_returning(
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

            inserted_promise = _supabase_insert_returning(
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
                _supabase_request(
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


def _normalize_uuid(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    return raw


def _normalize_sort_order(value):
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("sort_order must be a number")
    if parsed < 1:
        raise ValueError("sort_order must be greater than or equal to 1")
    return parsed


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
        "status": status,
    }


def _get_pledge_row(pledge_id):
    rows = _supabase_request(
        "GET",
        "pledges",
        query_params={
            "select": "id,candidate_election_id,sort_order,title,raw_text,category,status,created_by",
            "id": f"eq.{pledge_id}",
            "limit": "1",
        },
    ) or []
    return rows[0] if rows else None


def _is_leaf_node(value):
    return value in (True, 1, "1", "t", "true", "True")


def _year_from_date(value):
    text = str(value or "").strip()
    if len(text) < 4:
        return None
    year_text = text[:4]
    return int(year_text) if year_text.isdigit() else None


def _is_missing_column_runtime_error(exc):
    message = str(exc or "").lower()
    return "column" in message and "does not exist" in message


def _supabase_get_with_select_fallback(table, query_params, select_candidates):
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
                return _supabase_request("GET", table, query_params=current_query) or []
            except RuntimeError as exc:
                if _is_missing_relation_runtime_error(exc):
                    return []
                if _is_missing_column_runtime_error(exc):
                    last_missing_column_error = exc
                    continue
                raise

    if last_missing_column_error:
        raise last_missing_column_error
    return []


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
        row["election_title"] = election_info.get("title")
        row["election_year"] = _year_from_date(election_info.get("election_date"))

    return rows


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _attach_pledge_tree_rows(pledges):
    if not pledges:
        return pledges

    pledge_ids = [row.get("id") for row in pledges if row.get("id") is not None]
    pledge_filter = _to_in_filter(pledge_ids)
    if not pledge_filter:
        for pledge in pledges:
            pledge["goals"] = []
        return pledges

    node_rows = _supabase_request(
        "GET",
        "pledge_nodes",
        query_params={
            "select": "id,pledge_id,name,content,sort_order,parent_id,is_leaf,created_at",
            "pledge_id": pledge_filter,
            "limit": "50000",
        },
    ) or []
    node_ids = [row.get("id") for row in node_rows if row.get("id") is not None]
    node_filter = _to_in_filter(node_ids)

    progress_rows = []
    node_source_rows = []
    progress_source_rows = []
    source_rows = []

    if node_filter:
        progress_rows = _supabase_request(
            "GET",
            "pledge_node_progress",
            query_params={
                "select": "id,pledge_node_id,progress_rate,status,reason,evaluator,evaluation_date,created_at,created_by,updated_at,updated_by",
                "pledge_node_id": node_filter,
                "limit": "100000",
            },
        ) or []

        node_source_rows = _fetch_node_source_rows(node_filter)

        progress_ids = [row.get("id") for row in progress_rows if row.get("id") is not None]
        progress_filter = _to_in_filter(progress_ids)
        if progress_filter:
            progress_source_rows = _supabase_request(
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

        source_filter = _to_in_filter(source_ids)
        if source_filter:
            source_rows = _supabase_request(
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
            key=lambda x: (_safe_int(x.get("sort_order"), 999999), str(x.get("created_at") or ""), str(x.get("id") or "")),
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
        if _is_leaf_node(goal.get("is_leaf")):
            continue

        promise_rows = _sorted_nodes(children_by_parent.get(str(goal_id), []))
        promise_list = []
        for promise in promise_rows:
            promise_id = promise.get("id")
            if not promise_id or _is_leaf_node(promise.get("is_leaf")):
                continue
            item_rows = _sorted_nodes(children_by_parent.get(str(promise_id), []))
            item_list = []
            for item in item_rows:
                if not _is_leaf_node(item.get("is_leaf")):
                    continue
                item_list.append(_node_payload(item))
            promise_payload = _node_payload(promise)
            promise_payload["items"] = item_list
            promise_list.append(promise_payload)

        goal_payload = _node_payload(goal)
        goal_payload["promises"] = promise_list
        goals_by_pledge.setdefault(pledge_id, []).append(goal_payload)

    for pledge in pledges:
        pledge["goals"] = goals_by_pledge.get(str(pledge.get("id")), [])

    return pledges


def _normalize_compact_text(value):
    return re.sub(r"\s+", "", str(value or ""))


def _is_execution_method_goal_text(text):
    normalized = _normalize_compact_text(text)
    return ("이행방법" in normalized) or ("실행방법" in normalized)


def _sorted_node_rows(rows):
    return sorted(
        rows,
        key=lambda x: (_safe_int(x.get("sort_order"), 999999), str(x.get("created_at") or ""), str(x.get("id") or "")),
    )


def _fetch_pledge_nodes(pledge_id):
    return _supabase_request(
        "GET",
        "pledge_nodes",
        query_params={
            "select": "id,pledge_id,name,content,sort_order,parent_id,is_leaf,created_at",
            "pledge_id": f"eq.{pledge_id}",
            "limit": "50000",
        },
    ) or []


def _build_progress_node_context(node_rows):
    children_by_parent = {}
    for row in node_rows:
        parent_key = str(row.get("parent_id")) if row.get("parent_id") is not None else "__root__"
        children_by_parent.setdefault(parent_key, []).append(row)
    for key in list(children_by_parent.keys()):
        children_by_parent[key] = _sorted_node_rows(children_by_parent[key])

    def _node_name(row):
        raw = str(row.get("name") or "").strip().lower()
        if raw in {"goal", "promise", "item"}:
            return raw
        return "item" if _is_leaf_node(row.get("is_leaf")) else "promise"

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
                "is_leaf": _is_leaf_node(node_row.get("is_leaf")),
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
        if _node_name(goal_row) != "goal":
            continue
        goal_title = _node_title(goal_row)
        if not _is_execution_method_goal_text(goal_title):
            continue

        promise_rows = [row for row in children_by_parent.get(str(goal_id), []) if _node_name(row) == "promise"]
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


def _get_pledge_node(pledge_node_id):
    rows = _supabase_request(
        "GET",
        "pledge_nodes",
        query_params={
            "select": "id,pledge_id,name,content,parent_id,is_leaf,sort_order,created_at",
            "id": f"eq.{pledge_node_id}",
            "limit": "1",
        },
    ) or []
    return rows[0] if rows else None


def _resolve_default_source_target_node_id(pledge_id):
    pledge_key = str(pledge_id or "").strip()
    if not pledge_key:
        return None

    rows = _sorted_node_rows(_fetch_pledge_nodes(pledge_key))
    if not rows:
        return None

    root_rows = [row for row in rows if row.get("parent_id") is None]
    goal_roots = [row for row in root_rows if str(row.get("name") or "").strip().lower() == "goal"]

    for candidate in goal_roots + root_rows + rows:
        node_id = candidate.get("id")
        if node_id is not None:
            return str(node_id)
    return None


def _normalize_progress_rate(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError("progress_rate must be a number")
    if parsed < 0 or parsed > 5:
        raise ValueError("progress_rate must be between 0 and 5")
    scaled = parsed * 2
    if abs(round(scaled) - scaled) > 1e-9:
        raise ValueError("progress_rate must be in 0.5 increments")
    return round(scaled) / 2


def _normalize_progress_status(value):
    allowed = {"not_started", "in_progress", "partially_completed", "completed", "failed", "unknown"}
    status = str(value or "unknown").strip().lower() or "unknown"
    if status not in allowed:
        raise ValueError("status must be one of not_started, in_progress, partially_completed, completed, failed, unknown")
    return status


def _normalize_source_type(value):
    raw = str(value or "").strip()
    if not raw:
        return None

    compact = raw.lower().replace(" ", "").replace("_", "").replace("-", "")
    mapping = {
        "government": "정부",
        "정부": "정부",
        "news": "언론",
        "언론": "언론",
        "report": "보고서",
        "보고서": "보고서",
        "research": "연구",
        "연구": "연구",
        "budget": "예산",
        "예산": "예산",
        "pressrelease": "보도자료",
        "보도자료": "보도자료",
        "speech": "연설",
        "연설": "연설",
        "law": "법령",
        "법": "법령",
        "법령": "법령",
    }
    return mapping.get(compact, raw)


def _normalize_progress_source_role(value):
    raw = str(value or "").strip()
    compact = raw.lower().replace(" ", "").replace("_", "").replace("-", "")
    mapping = {
        "primary": "주요근거",
        "주요근거": "주요근거",
        "supporting": "보조근거",
        "보조근거": "보조근거",
        "counter": "반박자료",
        "반박자료": "반박자료",
    }
    normalized = mapping.get(compact)
    if not normalized:
        raise ValueError("source_role must be one of 주요근거, 보조근거, 반박자료")
    return normalized


def _normalize_node_source_role(value):
    raw = str(value or "").strip()
    if not raw:
        return "참고출처"
    compact = raw.lower().replace(" ", "").replace("_", "").replace("-", "")
    mapping = {
        "origin": "원문출처",
        "원문출처": "원문출처",
        "공식공약집": "원문출처",
        "공식공약": "원문출처",
        "reference": "참고출처",
        "참고출처": "참고출처",
        "보조근거": "참고출처",
        "보조출처": "참고출처",
        "참고출처자료": "참고출처",
        "related": "관련자료",
        "관련자료": "관련자료",
        "관련출처": "관련자료",
    }
    normalized = mapping.get(compact)
    return normalized or raw


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


def _fetch_node_source_rows(node_filter):
    last_missing_error = None
    for table_name in NODE_SOURCE_TABLE_CANDIDATES:
        try:
            return _supabase_request(
                "GET",
                table_name,
                query_params={
                    "select": "id,pledge_node_id,source_id,source_role,note,created_at",
                    "pledge_node_id": node_filter,
                    "limit": "100000",
                },
            ) or []
        except RuntimeError as exc:
            if _is_missing_relation_runtime_error(exc):
                last_missing_error = exc
                continue
            raise
    if last_missing_error:
        return []
    return []


def _insert_node_source_row(payload):
    optional_fields = {"created_at", "created_by", "updated_at", "updated_by"}
    last_missing_error = None
    for table_name in NODE_SOURCE_TABLE_CANDIDATES:
        try:
            return _supabase_insert_with_optional_fields(table_name, payload=payload, optional_fields=optional_fields)
        except RuntimeError as exc:
            if _is_missing_relation_runtime_error(exc):
                last_missing_error = exc
                continue
            raise
    if last_missing_error:
        raise last_missing_error
    raise RuntimeError("pledge node source insert failed")


def _delete_node_source_rows(node_filter):
    for table_name in NODE_SOURCE_TABLE_CANDIDATES:
        try:
            _supabase_request("DELETE", table_name, query_params={"pledge_node_id": node_filter})
        except RuntimeError as exc:
            if _is_missing_relation_runtime_error(exc):
                continue
            raise


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
            match = re.search(r"column\s+([A-Za-z0-9_\.\"']+)\s+does not exist", message)
            if not match:
                raise

            column = str(match.group(1) or "").strip("'\"")
            if "." in column:
                column = column.split(".")[-1]
            if column not in remaining:
                raise

            working.pop(column, None)
            remaining.remove(column)


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
    if _try_fetch_user_profile(user_id):
        return

    payload = {
        "user__id": user_id,
        "nickname": (email or "").split("@")[0] or f"user_{user_id[:8]}",
        "role": "user",
        "status": "active",
        "reputation_score": 0,
        "create_at": _now_iso(),
        "update_at": _now_iso(),
    }
    _supabase_request("POST", "user_profiles", payload=payload)


def _session_user_id():
    return session.get("user_id")


def _is_admin(user_id):
    if not user_id:
        return False
    profile = _try_fetch_user_profile(user_id) or {}
    role = str(profile.get("role") or "").lower()
    return role in {"admin", "super_admin"}


def _session_is_admin():
    uid = _session_user_id()
    if not uid:
        return False
    # role 변경이 즉시 반영되도록 매 요청마다 user_profiles.role을 재확인한다.
    try:
        is_admin = bool(_is_admin(uid))
        session["is_admin"] = is_admin
        return is_admin
    except Exception:
        cached = session.get("is_admin")
        return bool(cached) if isinstance(cached, bool) else False


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
        if not _is_admin(uid):
            return jsonify({"error": "admin required"}), 403
        return view(*args, **kwargs)

    return wrapped_view


@app.errorhandler(RuntimeError)
def handle_runtime_error(exc):
    error_id = uuid4().hex
    app.logger.exception("RuntimeError [%s]: %s", error_id, exc)
    if request.path.startswith("/api/"):
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
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"

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
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/candidate")
@login_required
def candidate_page():
    return render_template("candidate.html")


@app.route("/election")
@login_required
def election_page():
    return render_template("election.html")


@app.route("/pledge")
@login_required
def pledge_page():
    return render_template("pledge.html")


@app.route("/progress")
def progress_page():
    return render_template("progress.html")


@app.route("/promises")
def promises_page():
    return render_template("promises.html")


@app.route("/politicians")
def politicians_page():
    return render_template("politicians.html")


@app.route("/politicians/<candidate_id>")
def politician_detail_page(candidate_id):
    normalized = str(candidate_id or "").strip().lower()
    if not normalized or normalized in {"undefined", "null", "none", "nan"}:
        return redirect(url_for("politicians_page"))
    return render_template("politician_detail.html", candidate_id=candidate_id)


@app.route("/mypage")
@login_required
def mypage():
    return render_template("mypage.html")


@app.route("/admin/static-pages", methods=["GET", "POST"])
@login_required
def static_pages_admin_page():
    if not _session_is_admin():
        abort(404)

    page_key = (request.values.get("page") or "about").strip().lower()
    if page_key not in EDITABLE_STATIC_PAGES:
        page_key = "about"

    save_message = None
    save_error = None
    content = _read_static_page(page_key)

    if request.method == "POST":
        submitted_content = request.form.get("content", "")
        try:
            _write_static_page(page_key, submitted_content)
            content = submitted_content
            save_message = "저장되었습니다. 새로고침하면 사이트에 즉시 반영됩니다."
        except Exception as exc:
            app.logger.exception("Failed to update static page: %s", exc)
            content = submitted_content
            save_error = f"저장 실패: {exc}"

    return render_template(
        "static_pages_admin.html",
        page_key=page_key,
        page_options=EDITABLE_STATIC_PAGES,
        content=content,
        save_message=save_message,
        save_error=save_error,
    )


@app.route("/auth/login", methods=["POST"])
def auth_login():
    if _is_rate_limited("auth_login", AUTH_LOGIN_RATE_LIMIT_PER_MINUTE, window_seconds=60):
        return jsonify({"error": "too many login attempts"}), 429

    payload = request.get_json(silent=True) or {}
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        access_token = _extract_bearer_token(request.headers.get("Authorization"))

    if not access_token:
        return jsonify({"error": "access_token is required"}), 400

    try:
        user = _fetch_supabase_user(access_token)
    except PermissionError:
        session.clear()
        return jsonify({"error": "invalid access token"}), 401

    user_id = str(user.get("id") or "").strip()
    email = str(user.get("email") or "").strip()
    if not user_id or not email:
        session.clear()
        return jsonify({"error": "invalid auth payload"}), 401

    session.clear()
    session["user_id"] = user_id
    session["email"] = email
    session["last_activity_ts"] = int(datetime.now(timezone.utc).timestamp())
    session.permanent = True

    try:
        ensure_user_profile(user_id, email)
        session["is_admin"] = bool(_is_admin(user_id))
    except Exception as exc:
        app.logger.exception("Failed to ensure user_profiles row: %s", exc)
        session["is_admin"] = False

    return jsonify({"ok": True}), 200


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True}), 200


@app.route("/auth/activity", methods=["POST"])
def auth_activity():
    if not _session_user_id():
        return jsonify({"error": "login required"}), 401
    session["last_activity_ts"] = int(datetime.now(timezone.utc).timestamp())
    session.permanent = True
    return jsonify({"ok": True}), 200


@app.route("/api/upload-image", methods=["POST"])
@login_required
def upload_image():
    if "image" not in request.files:
        return jsonify({"error": "image file is required"}), 400

    image_file = request.files["image"]
    if image_file.filename == "":
        return jsonify({"error": "image filename is empty"}), 400

    original_name = image_file.filename or ""
    extension = ""
    if "." in original_name:
        extension = _normalize_image_extension(original_name.rsplit(".", 1)[1])
    elif image_file.mimetype in MIME_TO_EXT:
        extension = _normalize_image_extension(MIME_TO_EXT[image_file.mimetype])

    if extension not in {_normalize_image_extension(ext) for ext in ALLOWED_IMAGE_EXTENSIONS}:
        return jsonify({"error": "잘못된 파일 확장자입니다."}), 400

    image_bytes = image_file.read()
    if not image_bytes:
        return jsonify({"error": "이미지 파일이 비어 있습니다."}), 400

    detected_ext, detected_mime = _detect_image_signature(image_bytes)
    if not detected_ext:
        return jsonify({"error": "이미지 시그니처를 확인할 수 없는 파일입니다."}), 400
    if extension and extension != detected_ext:
        return jsonify({"error": "파일 확장자와 실제 이미지 형식이 일치하지 않습니다."}), 400

    saved_name = f"{uuid4().hex}.{detected_ext}"
    object_path = f"{SUPABASE_CANDIDATE_IMAGE_FOLDER}/{saved_name}" if SUPABASE_CANDIDATE_IMAGE_FOLDER else saved_name

    public_url = _upload_to_supabase_storage(
        bucket=SUPABASE_CANDIDATE_IMAGE_BUCKET,
        object_path=object_path,
        content_bytes=image_bytes,
        content_type=detected_mime or image_file.mimetype or f"image/{detected_ext}",
    )
    return jsonify({"ok": True, "path": public_url, "filename": saved_name}), 200


@app.route("/api/candidate-admin/candidates", methods=["GET", "POST"])
@api_login_required
def api_candidate_admin_candidates():
    if request.method == "GET":
        rows = _supabase_request(
            "GET",
            "candidates",
            query_params={
                "select": "id,name,image,created_at,created_by",
                "order": "created_at.desc",
                "limit": "1000",
            },
        ) or []
        return jsonify({"rows": rows})

    payload = request.get_json(silent=True) or {}
    uid = _session_user_id()
    name = payload.get("name")
    image = payload.get("image")

    if not name or not image:
        return jsonify({"error": "name and image are required"}), 400

    now = _now_iso()
    _supabase_request(
        "POST",
        "candidates",
        payload={
            "name": name,
            "image": image,
            "created_at": now,
            "created_by": uid,
            "updated_at": now,
            "updated_by": None,
        },
    )
    return jsonify({"ok": True}), 201


@app.route("/api/candidate-admin/elections", methods=["GET", "POST"])
@api_login_required
def api_candidate_admin_elections():
    if request.method == "GET":
        rows = _supabase_request(
            "GET",
            "elections",
            query_params={
                "select": "id,election_type,title,election_date,created_at,created_by",
                "order": "election_date.desc",
                "limit": "1000",
            },
        ) or []
        return jsonify({"rows": rows})

    payload = request.get_json(silent=True) or {}
    uid = _session_user_id()
    election_type = payload.get("election_type")
    title = payload.get("title")
    election_date = payload.get("election_date")

    if not election_type or not title or not election_date:
        return jsonify({"error": "election_type, title, election_date are required"}), 400

    now = _now_iso()
    _supabase_request(
        "POST",
        "elections",
        payload={
            "election_type": election_type,
            "title": title,
            "election_date": election_date,
            "created_at": now,
            "created_by": uid,
            "updated_at": now,
            "updated_by": None,
        },
    )
    return jsonify({"ok": True}), 201


@app.route("/api/candidate-admin/candidate-elections", methods=["GET", "POST"])
@api_login_required
def api_candidate_admin_candidate_elections():
    if request.method == "GET":
        rows = _supabase_request(
            "GET",
            "candidate_elections",
            query_params={
                "select": "id,candidate_id,election_id,party,result,is_elect,candidate_number,created_at,created_by",
                "order": "created_at.desc",
                "limit": "1000",
            },
        ) or []
        return jsonify({"rows": rows})

    payload = request.get_json(silent=True) or {}
    uid = _session_user_id()
    candidate_id = payload.get("candidate_id")
    election_id = payload.get("election_id")
    party = str(payload.get("party") or "").strip()
    result = str(payload.get("result") or "").strip()
    candidate_number = payload.get("candidate_number")

    if not candidate_id or not election_id or not party or not result:
        return jsonify({"error": "candidate_id, election_id, party, result are required"}), 400

    try:
        candidate_number = int(candidate_number)
    except (TypeError, ValueError):
        return jsonify({"error": "candidate_number must be a number"}), 400
    if candidate_number < 1:
        return jsonify({"error": "candidate_number must be greater than or equal to 1"}), 400

    is_elect = 1 if result == "당선" else 0

    now = _now_iso()
    _supabase_request(
        "POST",
        "candidate_elections",
        payload={
            "candidate_id": candidate_id,
            "election_id": election_id,
            "party": party,
            "result": result,
            "is_elect": is_elect,
            "candidate_number": candidate_number,
            "created_at": now,
            "created_by": uid,
            "updated_at": now,
            "updated_by": None,
        },
    )
    return jsonify({"ok": True}), 201


@app.route("/api/candidate-admin/terms", methods=["GET", "POST"])
@api_login_required
def api_candidate_admin_terms():
    if request.method == "GET":
        rows = _fetch_terms_rows(limit="1000")
        return jsonify({"rows": rows})

    payload = request.get_json(silent=True) or {}
    uid = _session_user_id()
    candidate_id = payload.get("candidate_id")
    election_id = payload.get("election_id")
    position = (payload.get("position") or "").strip()
    term_start = payload.get("term_start")
    term_end = payload.get("term_end")

    if not candidate_id or not election_id or not position or not term_start:
        return jsonify({"error": "candidate_id, election_id, position, term_start are required"}), 400

    if term_end and str(term_end) < str(term_start):
        return jsonify({"error": "term_end must be greater than or equal to term_start"}), 400

    now = _now_iso()
    _supabase_request(
        "POST",
        "terms",
        payload={
            "candidate_id": candidate_id,
            "election_id": election_id,
            "position": position,
            "term_start": term_start,
            "term_end": term_end or None,
            "created_at": now,
            "created_by": uid,
            "updated_at": now,
            "updated_by": None,
        },
    )
    return jsonify({"ok": True}), 201


@app.route("/api/progress-admin/sources", methods=["POST"])
@api_login_required
def api_progress_admin_sources():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    url = (payload.get("url") or "").strip() or None
    source_type = _normalize_source_type(payload.get("source_type"))
    publisher = (payload.get("publisher") or "").strip() or None
    published_at = (payload.get("published_at") or "").strip() or None
    summary = (payload.get("summary") or "").strip() or None
    note = (payload.get("note") or "").strip() or None

    if not title:
        return jsonify({"error": "title is required"}), 400

    inserted = _supabase_insert_with_optional_fields(
        "sources",
        payload={
            "title": title,
            "url": url,
            "source_type": source_type,
            "publisher": publisher,
            "published_at": published_at,
            "summary": summary,
            "note": note,
            "created_at": _now_iso(),
            "created_by": _session_user_id(),
            "updated_at": _now_iso(),
            "updated_by": None,
        },
        optional_fields={"note", "created_at", "created_by", "updated_at", "updated_by"},
    )
    return jsonify({"ok": True, "row": inserted}), 201


@app.route("/api/progress-admin/node-sources", methods=["POST"])
@api_login_required
def api_progress_admin_node_sources():
    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}
    pledge_node_id = (payload.get("pledge_node_id") or "").strip()
    pledge_id = (payload.get("pledge_id") or "").strip()
    source_id = (payload.get("source_id") or "").strip()
    try:
        source_role = _normalize_node_source_role(payload.get("source_role") or "참고출처")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    note = (payload.get("note") or "").strip() or None

    if not source_id:
        return jsonify({"error": "source_id is required"}), 400

    if not pledge_node_id and pledge_id:
        pledge_node_id = _resolve_default_source_target_node_id(pledge_id) or ""

    if not pledge_node_id:
        return jsonify({"error": "pledge_node_id or pledge_id is required"}), 400

    pledge_node = _get_pledge_node(pledge_node_id)
    if not pledge_node:
        return jsonify({"error": "pledge_node not found"}), 404
    if pledge_id and str(pledge_node.get("pledge_id")) != str(pledge_id):
        return jsonify({"error": "pledge_node does not belong to pledge_id"}), 400
    if not _ensure_source_exists(source_id):
        return jsonify({"error": "source not found"}), 404

    inserted = _insert_node_source_row(
        payload={
            "pledge_node_id": pledge_node_id,
            "source_id": source_id,
            "source_role": source_role,
            "note": note,
            "created_at": _now_iso(),
            "created_by": uid,
            "updated_at": _now_iso(),
            "updated_by": None,
        }
    )
    return jsonify({"ok": True, "row": inserted}), 201


@app.route("/api/progress-admin/quick-record", methods=["POST"])
@api_login_required
def api_progress_admin_quick_record():
    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}

    pledge_node_id = (payload.get("pledge_node_id") or "").strip()
    evaluation_date = (payload.get("evaluation_date") or "").strip()
    reason = (payload.get("reason") or "").strip() or None
    evaluator = (payload.get("evaluator") or "").strip() or None
    try:
        source_role = _normalize_progress_source_role(payload.get("source_role") or "주요근거")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    quoted_text = (payload.get("quoted_text") or "").strip() or None
    note = (payload.get("note") or "").strip() or None

    source_id = (payload.get("source_id") or "").strip() or None
    source_title = (payload.get("source_title") or "").strip()
    source_url = (payload.get("source_url") or "").strip() or None
    source_type = _normalize_source_type(payload.get("source_type"))
    source_publisher = (payload.get("source_publisher") or "").strip() or None
    source_published_at = (payload.get("source_published_at") or "").strip() or None
    source_summary = (payload.get("source_summary") or "").strip() or None

    if not pledge_node_id:
        return jsonify({"error": "pledge_node_id is required"}), 400
    if not evaluation_date:
        return jsonify({"error": "evaluation_date is required"}), 400

    pledge_node = _get_pledge_node(pledge_node_id)
    if not pledge_node:
        return jsonify({"error": "pledge_node not found"}), 404

    pledge_id = pledge_node.get("pledge_id")
    node_context = _build_progress_node_context(_fetch_pledge_nodes(pledge_id))
    target_ids = {str(row.get("id")) for row in node_context["progress_targets"] if row.get("id") is not None}
    if str(pledge_node_id) not in target_ids:
        return jsonify({"error": "평가 대상은 실행항목(item) 또는 item이 없는 중항목(promise)만 가능합니다."}), 400

    try:
        progress_rate = _normalize_progress_rate(payload.get("progress_rate"))
        status = _normalize_progress_status(payload.get("status"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    page_no = None
    page_no_raw = payload.get("page_no")
    if page_no_raw not in (None, ""):
        try:
            page_no = int(page_no_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "page_no must be an integer"}), 400

    now = _now_iso()
    inserted_progress = _supabase_insert_with_optional_fields(
        "pledge_node_progress",
        payload={
            "pledge_node_id": pledge_node_id,
            "progress_rate": progress_rate,
            "status": status,
            "reason": reason,
            "evaluator": evaluator,
            "evaluation_date": evaluation_date,
            "created_at": now,
            "created_by": uid,
            "updated_at": now,
            "updated_by": None,
        },
        optional_fields={"created_at", "created_by", "updated_at", "updated_by"},
    )
    progress_id = inserted_progress.get("id")
    if not progress_id:
        return jsonify({"error": "progress insert failed"}), 500

    if source_id:
        if not _ensure_source_exists(source_id):
            return jsonify({"error": "source not found"}), 404
    else:
        if not source_title:
            return jsonify({"error": "source_title is required"}), 400
        inserted_source = _supabase_insert_with_optional_fields(
            "sources",
            payload={
                "title": source_title,
                "url": source_url,
                "source_type": source_type,
                "publisher": source_publisher,
                "published_at": source_published_at,
                "summary": source_summary,
                "created_at": now,
                "created_by": uid,
                "updated_at": now,
                "updated_by": None,
            },
            optional_fields={"created_at", "created_by", "updated_at", "updated_by"},
        )
        source_id = inserted_source.get("id")
        if not source_id:
            return jsonify({"error": "source insert failed"}), 500

    inserted_link = _supabase_insert_with_optional_fields(
        "pledge_node_progress_sources",
        payload={
            "pledge_node_progress_id": progress_id,
            "source_id": source_id,
            "source_role": source_role,
            "quoted_text": quoted_text,
            "page_no": page_no,
            "note": note,
            "created_at": now,
            "created_by": uid,
            "updated_at": now,
            "updated_by": None,
        },
        optional_fields={"created_at", "created_by", "updated_at", "updated_by"},
    )

    return jsonify({"ok": True, "progress": inserted_progress, "source_id": source_id, "progress_source": inserted_link}), 201


@app.route("/api/pledges", methods=["POST"])
def api_pledges():
    uid = _session_user_id()
    if not uid:
        return jsonify({"error": "login required"}), 401

    payload = request.get_json(silent=True) or {}
    try:
        validated = _validate_pledge_payload(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    now = _now_iso()
    inserted = _supabase_insert_returning(
        "pledges",
        payload={
            "candidate_election_id": validated["candidate_election_id"],
            "sort_order": validated["sort_order"],
            "title": validated["title"],
            "raw_text": validated["raw_text"],
            "category": validated["category"],
            "status": validated["status"],
            "created_at": now,
            "created_by": uid,
            "updated_at": now,
            "updated_by": None,
        },
    )
    pledge_id = inserted.get("id")
    if not pledge_id:
        return jsonify({"error": "pledge insert failed"}), 500

    try:
        _insert_pledge_tree(pledge_id, validated["raw_text"], uid)
    except Exception:
        _delete_pledge_tree(pledge_id)
        _supabase_request("DELETE", "pledges", query_params={"id": f"eq.{pledge_id}"})
        raise

    created_nodes = _fetch_pledge_nodes(pledge_id)
    return jsonify({"ok": True, "pledge_id": pledge_id, "nodes": created_nodes}), 201


@app.route("/api/politicians", methods=["GET"])
def api_politicians():
    rows = _supabase_request(
        "GET",
        "candidates",
        query_params={
            "select": "id,name,image",
            "order": "name.asc",
            "limit": "500",
        },
    ) or []
    rows = _enrich_candidates_with_latest(rows)

    return jsonify({"politicians": rows})


@app.route("/api/promises", methods=["GET"])
def api_promises():
    limit, offset = _pagination_params(default_limit=None, max_limit=500)
    is_admin = _is_admin(_session_user_id())
    cache_key = f"api_promises:{'admin' if is_admin else 'public'}"
    cached = _cache_get(cache_key)
    if cached:
        candidates = cached.get("candidates") or []
        cards = cached.get("cards") or []
    else:
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
                "select": "id,candidate_election_id,sort_order,title,raw_text,category,status,created_at,created_by,updated_at,updated_by",
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
            pledge["election_title"] = election.get("title")
            pledge["election_date"] = election.get("election_date")

        if not is_admin:
            pledges = [p for p in pledges if str(p.get("status") or "active") != "hidden"]

        pledges = _attach_pledge_tree_rows(pledges)
        cards = []

        for pledge in pledges:
            goals = pledge.get("goals") or []
            for goal in goals:
                goal_text = str(goal.get("text") or "").strip()
                if not _is_execution_method_goal_text(goal_text):
                    continue

                promises = goal.get("promises") or []
                for promise in promises:
                    promise_text = str(promise.get("text") or "").strip()
                    items = promise.get("items") or []

                    item_texts = []
                    item_rates = []
                    for item in items:
                        item_text = str(item.get("text") or "").strip()
                        if item_text:
                            item_texts.append(item_text)
                        rate_raw = item.get("progress_rate")
                        try:
                            rate = float(rate_raw)
                        except (TypeError, ValueError):
                            continue
                        if 0 <= rate <= 5:
                            item_rates.append(rate)

                    if item_texts:
                        content = " / ".join(item_texts)
                        progress_rate = round(sum(item_rates) / len(item_rates), 2) if item_rates else None
                    else:
                        content = ""
                        progress_rate = None
                        rate_raw = promise.get("progress_rate")
                        try:
                            rate = float(rate_raw)
                        except (TypeError, ValueError):
                            rate = None
                        if rate is not None and 0 <= rate <= 5:
                            progress_rate = round(rate, 2)

                    if not promise_text and not content:
                        continue

                    cards.append(
                        {
                            "id": f"{pledge.get('id')}:{promise.get('id')}",
                            "candidate_id": pledge.get("candidate_id"),
                            "candidate_election_id": pledge.get("candidate_election_id"),
                            "pledge_id": pledge.get("id"),
                            "promise_node_id": promise.get("id"),
                            "promise_title": promise_text,
                            "content": content,
                            "progress_rate": progress_rate,
                            "category": pledge.get("category"),
                            "election_id": pledge.get("election_id"),
                            "election_type": pledge.get("election_type"),
                            "election_title": pledge.get("election_title"),
                            "election_date": pledge.get("election_date"),
                            "party": pledge.get("party"),
                            "result": pledge.get("result"),
                            "candidate_number": pledge.get("candidate_number"),
                            "pledge_sort_order": pledge.get("sort_order"),
                            "promise_sort_order": promise.get("sort_order"),
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

    rows, total = _slice_rows(cards, limit, offset)
    return jsonify({"candidates": candidates, "promises": rows, "total": total, "limit": limit, "offset": offset})


@app.route("/api/progress-overview", methods=["GET"])
def api_progress_overview():
    limit, offset = _pagination_params(default_limit=None, max_limit=2000)
    election_type_filter = _normalize_compact_text(request.args.get("election_type"))
    is_admin = _is_admin(_session_user_id())
    cache_key = f"api_progress_overview:{'admin' if is_admin else 'public'}:{election_type_filter or '-'}"
    cached = _cache_get(cache_key)
    if cached:
        cached_rows = cached.get("rows") or []
        rows, total = _slice_rows(cached_rows, limit, offset)
        return jsonify({"rows": rows, "total": total, "limit": limit, "offset": offset})

    candidates = _supabase_request(
        "GET",
        "candidates",
        query_params={
            "select": "id,name,image",
            "order": "name.asc",
            "limit": "2000",
        },
    ) or []
    candidate_map = {str(row.get("id")): row for row in candidates if row.get("id") is not None}

    candidate_elections = _supabase_request(
        "GET",
        "candidate_elections",
        query_params={
            "select": "id,candidate_id,election_id,party,result,is_elect,candidate_number,created_at",
            "order": "created_at.desc",
            "limit": "10000",
        },
    ) or []
    if not candidate_elections:
        return jsonify({"rows": [], "total": 0, "limit": limit, "offset": offset})

    election_ids = []
    for row in candidate_elections:
        eid = row.get("election_id")
        if eid is None:
            continue
        eid_str = str(eid)
        if eid_str not in election_ids:
            election_ids.append(eid_str)
    election_map = {}
    if election_ids:
        election_filter = _to_in_filter(election_ids)
        election_rows = _supabase_request(
            "GET",
            "elections",
            query_params={
                "select": "id,election_type,title,election_date",
                "id": election_filter,
                "limit": "10000",
            },
        ) or []
        election_map = {str(row.get("id")): row for row in election_rows if row.get("id") is not None}

    candidate_election_ids = [row.get("id") for row in candidate_elections if row.get("id") is not None]
    ce_filter = _to_in_filter(candidate_election_ids)
    pledges = []
    if ce_filter:
        pledges = _supabase_request(
            "GET",
            "pledges",
            query_params={
                "select": "id,candidate_election_id,sort_order,title,status,created_at",
                "candidate_election_id": ce_filter,
                "order": "sort_order.asc.nullslast,created_at.desc",
                "limit": "50000",
            },
        ) or []
        if not is_admin:
            pledges = [row for row in pledges if str(row.get("status") or "active") != "hidden"]

    pledge_ids = [row.get("id") for row in pledges if row.get("id") is not None]
    pledge_filter = _to_in_filter(pledge_ids)
    node_rows = []
    if pledge_filter:
        node_rows = _supabase_request(
            "GET",
            "pledge_nodes",
            query_params={
                "select": "id,pledge_id,name,content,sort_order,parent_id,is_leaf,created_at",
                "pledge_id": pledge_filter,
                "limit": "100000",
            },
        ) or []

    node_ids = [row.get("id") for row in node_rows if row.get("id") is not None]
    node_filter = _to_in_filter(node_ids)
    progress_rows = []
    if node_filter:
        progress_rows = _supabase_request(
            "GET",
            "pledge_node_progress",
            query_params={
                "select": "id,pledge_node_id,progress_rate,evaluation_date,created_at",
                "pledge_node_id": node_filter,
                "limit": "200000",
            },
        ) or []
    latest_progress_by_node = _latest_progress_row_map(progress_rows)

    nodes_by_pledge = {}
    for row in node_rows:
        key = str(row.get("pledge_id"))
        if not key:
            continue
        nodes_by_pledge.setdefault(key, []).append(row)

    stats_by_candidate_election = {}
    for pledge in pledges:
        ce_key = str(pledge.get("candidate_election_id"))
        if not ce_key:
            continue
        context = _build_progress_node_context(nodes_by_pledge.get(str(pledge.get("id")), []))
        targets = context.get("progress_targets") or []
        stat = stats_by_candidate_election.setdefault(
            ce_key,
            {"target_count": 0, "evaluated_count": 0, "rate_sum": 0.0, "rate_count": 0},
        )
        for target in targets:
            node_id = target.get("id")
            if node_id is None:
                continue
            stat["target_count"] += 1
            latest = latest_progress_by_node.get(str(node_id))
            if not latest:
                continue
            rate_raw = latest.get("progress_rate")
            try:
                rate = float(rate_raw)
            except (TypeError, ValueError):
                continue
            if rate < 0 or rate > 5:
                continue
            stat["evaluated_count"] += 1
            stat["rate_sum"] += rate
            stat["rate_count"] += 1

    rows = []
    for row in candidate_elections:
        election = election_map.get(str(row.get("election_id"))) or {}
        election_type = election.get("election_type")
        if election_type_filter and election_type_filter != _normalize_compact_text(election_type):
            continue

        candidate = candidate_map.get(str(row.get("candidate_id"))) or {}
        stat = stats_by_candidate_election.get(str(row.get("id"))) or {}
        rate_count = int(stat.get("rate_count") or 0)
        avg_progress = None
        if rate_count > 0:
            avg_progress = round(float(stat.get("rate_sum") or 0) / rate_count, 2)

        rows.append(
            {
                "candidate_election_id": row.get("id"),
                "candidate_id": row.get("candidate_id"),
                "candidate_name": candidate.get("name"),
                "candidate_image": candidate.get("image"),
                "election_id": row.get("election_id"),
                "election_type": election_type,
                "election_title": election.get("title"),
                "election_date": election.get("election_date"),
                "party": row.get("party"),
                "result": row.get("result"),
                "candidate_number": row.get("candidate_number"),
                "target_count": int(stat.get("target_count") or 0),
                "evaluated_count": int(stat.get("evaluated_count") or 0),
                "avg_progress": avg_progress,
            }
        )

    rows = sorted(
        rows,
        key=lambda x: (str(x.get("election_date") or ""), str(x.get("election_title") or ""), str(x.get("candidate_name") or "")),
        reverse=True,
    )
    _cache_set(cache_key, {"rows": rows})
    sliced_rows, total = _slice_rows(rows, limit, offset)
    return jsonify({"rows": sliced_rows, "total": total, "limit": limit, "offset": offset})


@app.route("/api/politicians/<candidate_id>", methods=["GET"])
def api_politician_detail(candidate_id):
    candidate_id = str(candidate_id or "").strip()
    if not candidate_id or candidate_id.lower() in {"undefined", "null", "none", "nan"}:
        return jsonify({"error": "invalid candidate_id"}), 400

    try:
        is_admin = bool(_is_admin(_session_user_id()))
    except Exception as exc:
        app.logger.exception("api_politician_detail admin check failed: candidate_id=%s error=%s", candidate_id, exc)
        is_admin = False
    detail_warnings = []
    candidate_fetch_failed = False
    try:
        candidates = _supabase_get_with_select_fallback(
            "candidates",
            query_params={
                "id": f"eq.{candidate_id}",
                "limit": "1",
            },
            select_candidates=[
                "id,name,image,created_at,created_by,updated_at,updated_by",
                "id,name,image,created_at,updated_at",
                "id,name,image,created_at",
                "id,name,image",
                "*",
            ],
        )
    except Exception as exc:
        app.logger.exception("api_politician_detail candidate fetch failed: candidate_id=%s error=%s", candidate_id, exc)
        candidates = []
        candidate_fetch_failed = True
        detail_warnings.append("candidate")

    if not candidates and not candidate_fetch_failed:
        return jsonify({"error": "not found"}), 404

    if candidates:
        try:
            candidates = _enrich_candidates_with_latest(candidates)
        except Exception as exc:
            app.logger.exception("api_politician_detail candidate enrich failed: candidate_id=%s error=%s", candidate_id, exc)
            detail_warnings.append("candidate_enrich")
    candidate = (candidates[0] if candidates else {"id": candidate_id, "name": f"정치인 {candidate_id}", "image": None})

    try:
        candidate_elections_for_candidate = _supabase_get_with_select_fallback(
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
    except Exception as exc:
        app.logger.exception("api_politician_detail candidate_elections fetch failed: candidate_id=%s error=%s", candidate_id, exc)
        candidate_elections_for_candidate = []
        detail_warnings.append("candidate_elections")

    candidate_election_ids = [row.get("id") for row in candidate_elections_for_candidate if row.get("id") is not None]
    pledge_filter = _to_in_filter(candidate_election_ids)
    pledges = []
    if pledge_filter:
        try:
            pledges = _supabase_get_with_select_fallback(
                "pledges",
                query_params={
                    "candidate_election_id": pledge_filter,
                    "order": "sort_order.asc.nullslast,created_at.desc",
                    "limit": "1000",
                },
                select_candidates=[
                    "id,candidate_election_id,sort_order,title,raw_text,category,status,created_at,created_by,updated_at,updated_by",
                    "id,candidate_election_id,sort_order,title,raw_text,category,status,created_at,updated_at",
                    "id,candidate_election_id,sort_order,title,raw_text,category,status,created_at",
                    "id,candidate_election_id,sort_order,title,raw_text,category,status",
                    "id,candidate_election_id,title,raw_text,category,status",
                    "id,candidate_election_id,title,raw_text",
                    "*",
                ],
            )
        except Exception as exc:
            app.logger.exception("api_politician_detail pledges fetch failed: candidate_id=%s error=%s", candidate_id, exc)
            pledges = []
            detail_warnings.append("pledges")
        for pledge in pledges:
            pledge["candidate_id"] = candidate_id

    if not is_admin:
        pledges = [p for p in pledges if str(p.get("status") or "active") != "hidden"]
    try:
        pledges = _attach_pledge_tree_rows(pledges)
    except Exception as exc:
        app.logger.exception("api_politician_detail pledge tree attach failed: candidate_id=%s error=%s", candidate_id, exc)
        detail_warnings.append("pledge_tree")
        for pledge in pledges:
            pledge["goals"] = []

    election_links = candidate_elections_for_candidate

    election_ids = []
    for row in election_links:
        eid = row.get("election_id")
        if eid is None:
            continue
        eid_str = str(eid)
        if eid_str not in election_ids:
            election_ids.append(eid_str)

    election_map = {}
    if election_ids:
        election_filter = _to_in_filter(election_ids)
        try:
            election_rows = _supabase_get_with_select_fallback(
                "elections",
                query_params={
                    "id": election_filter,
                    "limit": "5000",
                },
                select_candidates=[
                    "id,election_type,title,election_date",
                    "id,election_type,title",
                    "id,title,election_date",
                    "id,title",
                    "*",
                ],
            )
        except Exception as exc:
            app.logger.exception("api_politician_detail elections fetch failed: candidate_id=%s error=%s", candidate_id, exc)
            election_rows = []
            detail_warnings.append("elections")
        election_map = {str(row.get("id")): row for row in election_rows if row.get("id") is not None}

    for row in election_links:
        election_info = election_map.get(str(row.get("election_id"))) or {}
        row["election"] = {
            "id": election_info.get("id"),
            "election_type": election_info.get("election_type"),
            "title": election_info.get("title"),
            "election_date": election_info.get("election_date"),
        }

    pledges_by_candidate_election = {}
    for pledge in pledges:
        key = str(pledge.get("candidate_election_id"))
        if not key:
            continue
        pledges_by_candidate_election.setdefault(key, []).append(pledge)

    election_sections = []
    for row in election_links:
        candidate_election_key = str(row.get("id"))
        election_info = row.get("election") or {}
        linked_pledges = sorted(
            pledges_by_candidate_election.get(candidate_election_key, []),
            key=lambda p: (_safe_int(p.get("sort_order"), 999999), str(p.get("created_at") or "")),
        )
        election_sections.append(
            {
                "candidate_election_id": row.get("id"),
                "party": row.get("party"),
                "result": row.get("result"),
                "is_elect": row.get("is_elect"),
                "candidate_number": row.get("candidate_number"),
                "created_at": row.get("created_at"),
                "election": election_info,
                "pledges": linked_pledges,
                "pledge_count": len(linked_pledges),
            }
        )

    election_sections = sorted(
        election_sections,
        key=lambda x: (str((x.get("election") or {}).get("election_date") or ""), str(x.get("created_at") or "")),
        reverse=True,
    )

    try:
        terms = _fetch_terms_rows(candidate_id=candidate_id, limit="200")
    except Exception as exc:
        app.logger.exception("api_politician_detail terms fetch failed: candidate_id=%s error=%s", candidate_id, exc)
        terms = []
        detail_warnings.append("terms")

    payload = {
        "candidate": candidate,
        "pledges": pledges,
        "election_history": election_links,
        "election_sections": election_sections,
        "terms": terms,
        "is_admin": is_admin,
    }
    if detail_warnings:
        payload["warning"] = f"partial_data:{','.join(detail_warnings)}"
    return jsonify(payload)


@app.route("/api/report", methods=["POST"])
@api_login_required
def api_report():
    if _is_rate_limited("api_report", REPORT_RATE_LIMIT_PER_MINUTE, window_seconds=60):
        return jsonify({"error": "too many report requests"}), 429

    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}
    candidate_id = payload.get("candidate_id") or None
    pledge_id = payload.get("pledge_id") or None
    reason = (payload.get("reason") or "").strip()
    try:
        report_type = _normalize_report_type(payload.get("report_type"), default="신고")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    reason_category = (payload.get("reason_category") or "").strip() or None
    status = "접수"
    target_url = _sanitize_target_url(payload.get("target_url")) or _sanitize_target_url(request.headers.get("Referer"))
    now = _now_iso()

    if not reason:
        return jsonify({"error": "reason is required"}), 400
    if len(reason) > 2000:
        return jsonify({"error": "reason is too long (max 2000 chars)"}), 400
    if candidate_id and pledge_id:
        return jsonify({"error": "candidate_id and pledge_id cannot both be set"}), 400
    if report_type == "신고" and not (candidate_id or pledge_id):
        return jsonify({"error": "신고는 후보자 또는 공약 대상을 지정해야 합니다."}), 400

    if candidate_id:
        candidate_rows = _supabase_request(
            "GET",
            "candidates",
            query_params={"select": "id", "id": f"eq.{candidate_id}", "limit": "1"},
        ) or []
        if not candidate_rows:
            return jsonify({"error": "candidate not found"}), 404
    if pledge_id:
        pledge_rows = _supabase_request(
            "GET",
            "pledges",
            query_params={"select": "id", "id": f"eq.{pledge_id}", "limit": "1"},
        ) or []
        if not pledge_rows:
            return jsonify({"error": "pledge not found"}), 404

    if report_type == "신고":
        duplicate_query = {
            "select": "id,status",
            "user_id": f"eq.{uid}",
            "report_type": "eq.신고",
            "limit": "50",
            "order": "created_at.desc",
        }
        if candidate_id:
            duplicate_query["candidate_id"] = f"eq.{candidate_id}"
        if pledge_id:
            duplicate_query["pledge_id"] = f"eq.{pledge_id}"
        duplicates = _supabase_request("GET", "reports", query_params=duplicate_query) or []
        if any(str(row.get("status") or "").strip() in OPEN_REPORT_STATUS_CHOICES for row in duplicates):
            return jsonify({"error": "이미 접수/검토중인 신고가 있습니다."}), 409

    _supabase_request(
        "POST",
        "reports",
        payload={
            "user_id": uid,
            "candidate_id": candidate_id,
            "pledge_id": pledge_id,
            "reason": reason,
            "status": status,
            "report_type": report_type,
            "reason_category": reason_category,
            "target_url": target_url,
            "created_at": now,
            "updated_at": now,
        },
    )
    _audit_log(
        "report_created",
        user_id=uid,
        report_type=report_type,
        candidate_id=candidate_id,
        pledge_id=pledge_id,
        status=status,
        reason_category=reason_category,
    )
    return jsonify({"ok": True, "status": status})


@app.route("/api/mypage/reports", methods=["GET"])
@api_admin_required
def api_mypage_reports():
    rows = _supabase_request(
        "GET",
        "reports",
        query_params={
            "select": "id,user_id,candidate_id,pledge_id,created_at,updated_at,reason,status,report_type,admin_note,resolved_at,resolved_by,target_url,reason_category",
            "order": "created_at.desc",
            "limit": "500",
        },
    ) or []

    candidate_ids = [row.get("candidate_id") for row in rows if row.get("candidate_id")]
    pledge_ids = [row.get("pledge_id") for row in rows if row.get("pledge_id")]
    candidate_filter = _to_in_filter(candidate_ids)
    pledge_filter = _to_in_filter(pledge_ids)

    candidate_map = {}
    pledge_map = {}

    if candidate_filter:
        candidates = _supabase_request(
            "GET",
            "candidates",
            query_params={"select": "id,name", "id": candidate_filter, "limit": "1000"},
        ) or []
        candidate_map = {str(row.get("id")): row for row in candidates if row.get("id")}

    if pledge_filter:
        pledges = _supabase_request(
            "GET",
            "pledges",
            query_params={"select": "id,title,status", "id": pledge_filter, "limit": "1000"},
        ) or []
        pledge_map = {str(row.get("id")): row for row in pledges if row.get("id")}

    enriched = []
    for row in rows:
        candidate_id = row.get("candidate_id")
        pledge_id = row.get("pledge_id")
        candidate = candidate_map.get(str(candidate_id)) if candidate_id else None
        pledge = pledge_map.get(str(pledge_id)) if pledge_id else None

        if candidate_id:
            target_type = "정치인"
            target_name = (candidate or {}).get("name") or f"정치인({candidate_id})"
        elif pledge_id:
            target_type = "공약"
            target_name = (pledge or {}).get("title") or f"공약({pledge_id})"
        else:
            target_type = "의견"
            target_name = "일반 의견"

        enriched.append(
            {
                **row,
                "target_type": target_type,
                "target_name": target_name,
                "pledge_status": (pledge or {}).get("status"),
            }
        )

    return jsonify({"reports": enriched})


@app.route("/api/mypage/reports/<report_id>", methods=["PATCH"])
@api_admin_required
def api_mypage_report_update(report_id):
    uid = _session_user_id()
    report_rows = _supabase_request(
        "GET",
        "reports",
        query_params={"select": "id,pledge_id,report_type,status", "id": f"eq.{report_id}", "limit": "1"},
    ) or []
    if not report_rows:
        return jsonify({"error": "not found"}), 404
    report_row = report_rows[0]

    payload = request.get_json(silent=True) or {}
    patch_payload = {"updated_at": _now_iso()}

    if "status" in payload:
        try:
            patch_payload["status"] = _normalize_report_status_for_admin(payload.get("status"), default="접수")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if _is_resolved_report_status(patch_payload["status"]):
            patch_payload["resolved_at"] = patch_payload["updated_at"]
            patch_payload["resolved_by"] = uid
        else:
            patch_payload["resolved_at"] = None
            patch_payload["resolved_by"] = None

    if "admin_note" in payload:
        admin_note = (payload.get("admin_note") or "").strip()
        patch_payload["admin_note"] = admin_note or None

    if len(patch_payload) == 1:
        return jsonify({"error": "status or admin_note is required"}), 400

    _supabase_request(
        "PATCH",
        "reports",
        query_params={"id": f"eq.{report_id}"},
        payload=patch_payload,
    )
    _audit_log(
        "report_updated",
        admin_user_id=uid,
        report_id=report_id,
        status=patch_payload.get("status"),
        has_admin_note=("admin_note" in patch_payload),
    )

    # 신고 처리 상태를 관리자 판단 이후에만 공약 숨김 상태에 반영한다.
    if "status" in patch_payload and str(report_row.get("report_type") or "") == "신고":
        pledge_id = report_row.get("pledge_id")
        if pledge_id:
            if _is_resolved_report_status(patch_payload["status"]):
                _supabase_request("PATCH", "pledges", query_params={"id": f"eq.{pledge_id}"}, payload={"status": "hidden"})
                _audit_log("pledge_hidden_by_report_resolution", admin_user_id=uid, report_id=report_id, pledge_id=pledge_id)
            elif _is_rejected_report_status(patch_payload["status"]):
                _supabase_request("PATCH", "pledges", query_params={"id": f"eq.{pledge_id}"}, payload={"status": "active"})
                _audit_log("pledge_restored_by_report_rejection", admin_user_id=uid, report_id=report_id, pledge_id=pledge_id)

    return jsonify({"ok": True})


@app.route("/api/mypage/candidates/<candidate_id>", methods=["PATCH"])
@api_login_required
def api_mypage_candidate_update(candidate_id):
    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}
    now = _now_iso()
    patch_payload = {
        "updated_at": now,
        "updated_by": None,
    }
    if "name" in payload:
        patch_payload["name"] = payload.get("name")
    if "image" in payload:
        patch_payload["image"] = payload.get("image")

    _supabase_request(
        "PATCH",
        "candidates",
        query_params={"id": f"eq.{candidate_id}", "created_by": f"eq.{uid}"},
        payload=patch_payload,
    )
    return jsonify({"ok": True})


@app.route("/api/mypage/pledges/<pledge_id>", methods=["PATCH"])
@api_login_required
def api_mypage_pledge_update(pledge_id):
    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}
    current_pledge = _get_pledge_row(pledge_id)
    if not current_pledge:
        return jsonify({"error": "not found"}), 404
    if str(current_pledge.get("created_by") or "") != str(uid):
        return jsonify({"error": "forbidden"}), 403

    try:
        validated = _validate_pledge_payload(payload, current_pledge=current_pledge)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    now = _now_iso()
    _supabase_request(
        "PATCH",
        "pledges",
        query_params={"id": f"eq.{pledge_id}", "created_by": f"eq.{uid}"},
        payload={
            "candidate_election_id": validated["candidate_election_id"],
            "sort_order": validated["sort_order"],
            "title": validated["title"],
            "raw_text": validated["raw_text"],
            "category": validated["category"],
            "status": validated["status"],
            "updated_at": now,
            "updated_by": None,
        },
    )
    _delete_pledge_tree(pledge_id)
    _insert_pledge_tree(pledge_id, validated["raw_text"], uid)
    return jsonify({"ok": True})


@app.route("/api/admin/candidates/<candidate_id>", methods=["PATCH", "DELETE"])
@api_admin_required
def api_admin_candidate(candidate_id):
    candidate_id = str(candidate_id or "").strip()
    if not candidate_id:
        return jsonify({"error": "invalid candidate_id"}), 400

    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        patch_payload = {
            "updated_at": _now_iso(),
            "updated_by": None,
        }
        if "name" in payload:
            patch_payload["name"] = payload.get("name")
        if "image" in payload:
            patch_payload["image"] = payload.get("image")

        _supabase_request("PATCH", "candidates", query_params={"id": f"eq.{candidate_id}"}, payload=patch_payload)
        return jsonify({"ok": True})

    candidate_rows = _supabase_request(
        "GET",
        "candidates",
        query_params={"select": "id", "id": f"eq.{candidate_id}", "limit": "1"},
    ) or []
    if not candidate_rows:
        return jsonify({"error": "not found"}), 404

    def _delete_relation_rows_if_exists(table_name, query_params):
        try:
            _supabase_request("DELETE", table_name, query_params=query_params)
        except RuntimeError as exc:
            if _is_missing_relation_runtime_error(exc):
                return
            raise

    candidate_elections = _supabase_get_with_select_fallback(
        "candidate_elections",
        query_params={"candidate_id": f"eq.{candidate_id}", "limit": "5000"},
        select_candidates=[
            "id,candidate_id,election_id",
            "id,candidate_id",
            "id",
            "*",
        ],
    )
    candidate_election_ids = [row.get("id") for row in candidate_elections if row.get("id") is not None]
    candidate_election_filter = _to_in_filter(candidate_election_ids)

    pledge_ids = []
    if candidate_election_filter:
        pledges = _supabase_get_with_select_fallback(
            "pledges",
            query_params={"candidate_election_id": candidate_election_filter, "limit": "5000"},
            select_candidates=[
                "id,candidate_election_id",
                "id",
                "*",
            ],
        )
        pledge_ids = [row.get("id") for row in pledges if row.get("id") is not None]

    pledge_filter = _to_in_filter(pledge_ids)
    if pledge_filter:
        _delete_relation_rows_if_exists("reports", {"pledge_id": pledge_filter})

    _delete_relation_rows_if_exists("reports", {"candidate_id": f"eq.{candidate_id}"})

    for pledge_id in pledge_ids:
        _delete_pledge_tree(pledge_id)

    if candidate_election_filter:
        _delete_relation_rows_if_exists("pledges", {"candidate_election_id": candidate_election_filter})

    _delete_relation_rows_if_exists("terms", {"candidate_id": f"eq.{candidate_id}"})
    _delete_relation_rows_if_exists("candidate_elections", {"candidate_id": f"eq.{candidate_id}"})
    _supabase_request("DELETE", "candidates", query_params={"id": f"eq.{candidate_id}"})
    return jsonify({"ok": True})


@app.route("/api/admin/pledges/<pledge_id>", methods=["PATCH", "DELETE"])
@api_admin_required
def api_admin_pledge(pledge_id):
    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        if "raw_text" in payload or "candidate_election_id" in payload:
            current_pledge = _get_pledge_row(pledge_id)
            if not current_pledge:
                return jsonify({"error": "not found"}), 404
            try:
                validated = _validate_pledge_payload(payload, current_pledge=current_pledge)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            uid = _session_user_id()
            _supabase_request(
                "PATCH",
                "pledges",
                query_params={"id": f"eq.{pledge_id}"},
                payload={
                    "candidate_election_id": validated["candidate_election_id"],
                    "sort_order": validated["sort_order"],
                    "title": validated["title"],
                    "raw_text": validated["raw_text"],
                    "category": validated["category"],
                    "status": validated["status"],
                    "updated_at": _now_iso(),
                    "updated_by": None,
                },
            )
            _delete_pledge_tree(pledge_id)
            _insert_pledge_tree(pledge_id, validated["raw_text"], uid)
            return jsonify({"ok": True})

        _supabase_request("PATCH", "pledges", query_params={"id": f"eq.{pledge_id}"}, payload=payload)
        return jsonify({"ok": True})

    _delete_pledge_tree(pledge_id)
    _supabase_request("DELETE", "pledges", query_params={"id": f"eq.{pledge_id}"})
    return jsonify({"ok": True})


application = app

if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_RUN_HOST", "0.0.0.0"),
        port=_env_int("PORT", 8000),
        debug=DEBUG_MODE,
        use_reloader=False,
    )

