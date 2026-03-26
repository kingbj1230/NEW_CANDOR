from routes_bootstrap import bind_core, runtime_error_response

bind_core(globals())

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
        return jsonify({"error": "??롢걵?????뵬 ?類ㅼ삢?癒?뿯??덈뼄."}), 400

    image_bytes = image_file.read()
    if not image_bytes:
        return jsonify({"error": "???筌왖 ???뵬????쑴堉???됰뮸??덈뼄."}), 400

    detected_ext, detected_mime = _detect_image_signature(image_bytes)
    if not detected_ext:
        return jsonify({"error": "???筌왖 ??볥젃??됱퓗???類ㅼ뵥??????용뮉 ???뵬??낅빍??"}), 400
    if extension and extension != detected_ext:
        return jsonify({"error": "???뵬 ?類ㅼ삢?癒? ??쇱젫 ???筌왖 ?類ㅻ뻼????깊뒄??? ??녿뮸??덈뼄."}), 400

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
        rows = _supabase_get_with_select_fallback(
            "candidates",
            query_params={
                "order": "created_at.desc",
                "limit": "1000",
            },
            select_candidates=[
                "id,name,image,birth_date,created_at,created_by",
                "id,name,image,created_at,created_by",
                "id,name,image,created_at",
                "id,name,image",
                "*",
            ],
        )
        return jsonify({"rows": rows})

    payload = request.get_json(silent=True) or {}
    uid = _session_user_id()
    name = str(payload.get("name") or "").strip()
    image = str(payload.get("image") or "").strip()
    try:
        birth_date = _normalize_date_only(payload.get("birth_date"), field_name="birth_date", allow_null=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not name or not image:
        return jsonify({"error": "name and image are required"}), 400

    now = _now_iso()
    _supabase_request(
        "POST",
        "candidates",
        payload={
            "name": name,
            "image": image,
            "birth_date": birth_date,
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
    title_value = payload.get("title")
    election_date_raw = payload.get("election_date")

    if title_value in (None, "") or not election_date_raw:
        return jsonify({"error": "title and election_date are required"}), 400

    try:
        title_number = _normalize_election_round_title(title_value, field_name="title")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        election_date = _normalize_date_only(
            election_date_raw,
            field_name="election_date",
            allow_null=False,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    now = _now_iso()
    _supabase_request(
        "POST",
        "elections",
        payload={
            "election_type": "대통령",
            "title": title_number,
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
    candidate_id = str(payload.get("candidate_id") or "").strip()
    election_id = str(payload.get("election_id") or "").strip()
    party = str(payload.get("party") or "").strip()
    result = str(payload.get("result") or "").strip()
    candidate_number = payload.get("candidate_number")
    term_position = str(payload.get("term_position") or "").strip()
    term_start_raw = payload.get("term_start")
    term_end_raw = payload.get("term_end")

    if not candidate_id or not election_id or not party or not result:
        return jsonify({"error": "candidate_id, election_id, party, result are required"}), 400

    try:
        candidate_number = int(candidate_number)
    except (TypeError, ValueError):
        return jsonify({"error": "candidate_number must be a number"}), 400
    if candidate_number < 1:
        return jsonify({"error": "candidate_number must be greater than or equal to 1"}), 400

    try:
        term_start = _normalize_date_only(
            term_start_raw,
            field_name="term_start",
            allow_null=True,
        )
        term_end = _normalize_date_only(
            term_end_raw,
            field_name="term_end",
            allow_null=True,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    duplicate_rows = _supabase_get_with_select_fallback(
        "candidate_elections",
        query_params={
            "candidate_id": f"eq.{candidate_id}",
            "election_id": f"eq.{election_id}",
            "limit": "1",
        },
        select_candidates=[
            "id,candidate_id,election_id",
            "id",
            "*",
        ],
    )
    if duplicate_rows:
        return jsonify({"error": "?대? 媛숈? ?꾨낫?먯? ?좉굅 議고빀???깅줉?섏뼱 ?덉뒿?덈떎."}), 409

    is_elect = 1 if _is_elected_result(result) else 0
    has_term_payload = bool(term_position or term_start or term_end)
    if has_term_payload:
        if not is_elect:
            return jsonify({"error": "?뱀꽑 寃곌낵???뚮쭔 ?뱀꽑 寃쎈젰???낅젰?????덉뒿?덈떎."}), 400
        if not term_position or not term_start:
            return jsonify({"error": "?뱀꽑 寃쎈젰????ν븯?ㅻ㈃ 吏곸콉怨??꾧린 ?쒖옉?쇱씠 ?꾩슂?⑸땲??"}), 400
        if term_end and term_end < term_start:
            return jsonify({"error": "term_end must be greater than or equal to term_start"}), 400

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
    if is_elect and has_term_payload:
        _upsert_term_for_candidate_election(
            candidate_id=candidate_id,
            election_id=election_id,
            position=term_position,
            term_start=term_start,
            term_end=term_end,
            user_id=uid,
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

