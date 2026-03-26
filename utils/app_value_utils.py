import re
from datetime import datetime
from urllib import parse


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
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None, None


def _sanitize_target_url(raw_url):
    text = str(raw_url or "").strip()
    if not text:
        return ""
    parsed = parse.urlparse(text)
    if str(parsed.scheme or "").lower() not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{path}{query}"[:500]


def _to_in_filter(values):
    tokens = []
    for value in values or []:
        if value is None:
            continue

        raw = str(value).strip()
        if not raw:
            continue

        if isinstance(value, bool):
            tokens.append("true" if value else "false")
            continue

        is_numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not is_numeric and re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
            is_numeric = True

        if is_numeric:
            tokens.append(raw)
            continue

        escaped = raw.replace("\\", "\\\\").replace('"', r"\"")
        tokens.append(f'"{escaped}"')

    if not tokens:
        return None
    return f"in.({','.join(tokens)})"


def _normalize_uuid(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("candidate_election_id is required")
    return text


def _normalize_date_only(value, field_name="date", allow_null=True):
    raw = str(value or "").strip()
    if not raw:
        if allow_null:
            return None
        raise ValueError(f"{field_name} is required")
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format") from exc
    return raw


def _is_elected_result(value):
    normalized = str(value or "").replace(" ", "").strip().lower()
    if not normalized:
        return False
    return normalized in {
        "당선",
        "당선자",
        "win",
        "winner",
        "elected",
        "1",
        "true",
        "t",
        "yes",
        "y",
    }


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


def _normalize_election_round_title(value, field_name="title"):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is required")
    if not re.fullmatch(r"\d+", raw):
        raise ValueError(f"{field_name} must be numeric only")
    parsed = int(raw)
    if parsed < 1:
        raise ValueError(f"{field_name} must be greater than or equal to 1")
    if parsed > 32767:
        raise ValueError(f"{field_name} must be less than or equal to 32767")
    return parsed


def _format_presidential_election_title(value):
    raw = str(value or "").strip()
    if not raw:
        return "선거 정보 없음"
    if not re.fullmatch(r"\d+", raw):
        return raw
    parsed = int(raw)
    if parsed < 1:
        return raw
    return f"제{parsed}대 대통령 선거"


def _normalize_parse_type(value):
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw not in {"type1", "type2", "type3"}:
        raise ValueError("parse_type must be one of type1, type2, type3")
    return raw


def _normalize_structure_version(value):
    if value in (None, ""):
        return 2
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("structure_version must be a number")
    if parsed < 1:
        raise ValueError("structure_version must be greater than or equal to 1")
    return parsed


def _normalize_fulfillment_rate(value):
    if value in (None, ""):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("fulfillment_rate must be a number")
    if parsed < 0 or parsed > 100:
        raise ValueError("fulfillment_rate must be between 0 and 100")
    return parsed


def _is_leaf_node(value):
    return value in (True, 1, "1", "t", "true", "True")


def _year_from_date(value):
    text = str(value or "").strip()
    if len(text) < 4:
        return None
    year_text = text[:4]
    return int(year_text) if year_text.isdigit() else None


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_progress_rate(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError("progress_rate must be a number")

    if parsed < 0:
        raise ValueError("progress_rate must be between 0 and 100")

    # Backward compatibility: old clients still submit 0~5 scores.
    if parsed <= 5:
        scaled = parsed * 2
        if abs(round(scaled) - scaled) > 1e-9:
            raise ValueError("progress_rate score must be in 0.5 increments")
        return round((parsed * 20), 2)

    if parsed > 100:
        raise ValueError("progress_rate must be between 0 and 100")
    return round(parsed, 2)


def _normalize_progress_status(value):
    raw = str(value or "").strip().lower()
    mapping = {
        "planned": "planned",
        "not_started": "planned",
        "unknown": "planned",
        "in_progress": "in_progress",
        "inprogress": "in_progress",
        "ongoing": "in_progress",
        "partially_completed": "partially_completed",
        "partial": "partially_completed",
        "completed": "completed",
        "done": "completed",
        "failed": "failed",
        "suspended": "suspended",
        "paused": "suspended",
    }
    normalized = mapping.get(raw or "planned")
    if normalized is None:
        raise ValueError("status must be one of planned, in_progress, completed, failed, partially_completed, suspended")
    return normalized


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


def _extract_missing_column_from_runtime_message(message):
    text = str(message or "")
    if not text:
        return None
    patterns = [
        r"Could not find the '([^']+)' column",
        r'column "([^"]+)" of relation',
        r"column '([^']+)' does not exist",
        r'column "([^"]+)" does not exist',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            column = str(match.group(1) or "").strip()
            if column:
                return column
    return None
