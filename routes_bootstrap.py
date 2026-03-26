import app as core


def bind_core(namespace):
    """Copy app.py globals into a route module namespace."""
    for name, value in core.__dict__.items():
        if not name.startswith("__"):
            namespace.setdefault(name, value)


def build_pledge_patch_payload(validated, now_iso):
    """Create a consistent pledge PATCH payload from validated pledge fields."""
    return {
        "candidate_election_id": validated["candidate_election_id"],
        "sort_order": validated["sort_order"],
        "title": validated["title"],
        "raw_text": validated["raw_text"],
        "category": validated["category"],
        "timeline_text": validated["timeline_text"],
        "finance_text": validated["finance_text"],
        "parse_type": validated["parse_type"],
        "structure_version": validated["structure_version"],
        "fulfillment_rate": validated["fulfillment_rate"],
        "status": validated["status"],
        "updated_at": now_iso,
        "updated_by": None,
    }


def runtime_error_response(
    exc,
    *,
    default_message,
    network_message=None,
    foreign_key_message=None,
    schema_message=None,
    debug_prefix=None,
):
    """Map runtime errors to HTTP status/message consistently."""
    status = 500
    message = default_message

    if foreign_key_message and core._is_foreign_key_runtime_error(exc):
        status = 409
        message = foreign_key_message
    elif network_message and core._is_network_runtime_error(exc):
        status = 503
        message = network_message
    elif schema_message and core._is_missing_schema_runtime_error(exc):
        status = 500
        message = schema_message
    elif debug_prefix and not core.IS_PRODUCTION:
        message = f"{debug_prefix}: {exc}"

    return core.jsonify({"error": message}), status
