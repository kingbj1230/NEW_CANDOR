from routes_bootstrap import bind_core, runtime_error_response

bind_core(globals())

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
            save_message = "??λ릺?덉뒿?덈떎. ?덈줈怨좎묠?섎㈃ ?ъ씠?몄뿉 利됱떆 諛섏쁺?⑸땲??"
        except Exception as exc:
            app.logger.exception("Failed to update static page: %s", exc)
            content = submitted_content
            save_error = f"????ㅽ뙣: {exc}"

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
    legacy_user_id = str(payload.get("user_id") or "").strip()
    legacy_email = str(payload.get("email") or "").strip()

    user_id = ""
    email = ""
    if access_token:
        try:
            user = _fetch_supabase_user(access_token)
            user_id = str(user.get("id") or "").strip()
            email = str(user.get("email") or "").strip()
        except PermissionError:
            session.clear()
            return jsonify({"error": "invalid access token"}), 401
        except RuntimeError as exc:
            if ALLOW_INSECURE_LOCAL_LOGIN_FALLBACK and legacy_user_id and legacy_email:
                app.logger.warning("auth_login token verification failed; using local fallback in non-production mode: %s", exc)
                user_id = legacy_user_id
                email = legacy_email
            else:
                return jsonify({"error": "authentication provider unavailable"}), 503
    else:
        if ALLOW_INSECURE_LOCAL_LOGIN_FALLBACK and legacy_user_id and legacy_email:
            app.logger.warning("auth_login using legacy payload fallback without access_token")
            user_id = legacy_user_id
            email = legacy_email
        else:
            return jsonify({"error": "access_token is required"}), 400

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


@app.route("/auth/session", methods=["GET"])
def auth_session():
    uid = _session_user_id()
    email = str(session.get("email") or "").strip()
    is_admin = bool(session.get("is_admin")) if uid else False
    return jsonify(
        {
            "logged_in": bool(uid),
            "user_id": uid or None,
            "email": email or None,
            "is_admin": is_admin,
        }
    ), 200


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
        return jsonify({"error": "?섎せ???뚯씪 ?뺤옣?먯엯?덈떎."}), 400

    image_bytes = image_file.read()
    if not image_bytes:
        return jsonify({"error": "?대?吏 ?뚯씪??鍮꾩뼱 ?덉뒿?덈떎."}), 400

    detected_ext, detected_mime = _detect_image_signature(image_bytes)
    if not detected_ext:
        return jsonify({"error": "?대?吏 ?쒓렇?덉쿂瑜??뺤씤?????녿뒗 ?뚯씪?낅땲??"}), 400
    if extension and extension != detected_ext:
        return jsonify({"error": "?뚯씪 ?뺤옣?먯? ?ㅼ젣 ?대?吏 ?뺤떇???쇱튂?섏? ?딆뒿?덈떎."}), 400

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

    is_elect = 1 if result == "?뱀꽑" else 0

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


def _normalize_source_target_path(value):
    text = str(value or "").strip().lower().replace(" ", "")
    if not text or text in {"__auto__", "auto", "default", "root"}:
        return None

    parts = [part for part in text.split("/") if part]
    if not parts:
        return None
    if len(parts) > 3:
        raise ValueError("source target_path is invalid")

    expected = ["g", "p", "i"]
    normalized_parts = []
    for idx, part in enumerate(parts):
        if ":" not in part:
            raise ValueError("source target_path is invalid")
        kind, order_text = part.split(":", 1)
        if idx >= len(expected) or kind != expected[idx]:
            raise ValueError("source target_path is invalid")
        try:
            order = int(order_text)
        except (TypeError, ValueError):
            raise ValueError("source target_path is invalid")
        if order < 1:
            raise ValueError("source target_path is invalid")
        normalized_parts.append(f"{kind}:{order}")

    return "/".join(normalized_parts)


def _normalize_source_link_scope(value):
    raw = str(value or "").strip()
    if not raw:
        return "pledge"
    compact = raw.lower().replace(" ", "").replace("_", "").replace("-", "")
    if compact in {"pledge", "pledges", "pledgeid", "공약"}:
        return "pledge"
    if compact in {"goal", "goals", "대항목"}:
        return "goal"
    if compact in {"node", "pledgenode", "pledgenodeid", "노드"}:
        # Backward compatibility: old node scope is treated as goal scope.
        return "goal"
    raise ValueError("source link_scope must be pledge or goal")


def _build_pledge_goal_target_map(node_rows):
    goal_map = {}
    rows = _sorted_node_rows(node_rows or [])
    if not rows:
        return goal_map

    root_rows = [
        row
        for row in rows
        if row.get("parent_id") is None and str(row.get("name") or "").strip().lower() == "goal"
    ]
    goal_rows = _sorted_node_rows(root_rows)
    for goal_idx, goal_row in enumerate(goal_rows, start=1):
        goal_id = goal_row.get("id")
        if goal_id is None:
            continue
        goal_path = f"g:{goal_idx}"
        goal_map[goal_path] = {
            "node_id": str(goal_id),
            "title": str(goal_row.get("content") or "").strip(),
        }
    return goal_map


def _validate_goal_source_coverage(source_rows, goal_map):
    if not source_rows:
        return

    uses_goal_scope = any(str(row.get("link_scope") or "") == "goal" for row in source_rows)
    if not uses_goal_scope:
        return
    if not goal_map:
        raise ValueError("goal 연결 대상을 찾을 수 없습니다.")

    covered_paths = set()
    for row in source_rows:
        if str(row.get("link_scope") or "") != "goal":
            continue
        target_path = str(row.get("target_path") or "").strip()
        pledge_node_id = str(row.get("pledge_node_id") or "").strip()

        if target_path:
            if target_path not in goal_map:
                raise ValueError(f"goal target_path not found: {target_path}")
            covered_paths.add(target_path)
            continue

        if pledge_node_id:
            matched = None
            for path, info in goal_map.items():
                if str(info.get("node_id") or "") == pledge_node_id:
                    matched = path
                    break
            if not matched:
                raise ValueError("goal pledge_node_id is invalid")
            covered_paths.add(matched)
            continue

        raise ValueError("goal 연결 시 target_path가 필요합니다.")

    missing_paths = [path for path in goal_map.keys() if path not in covered_paths]
    if missing_paths:
        missing_labels = [str((goal_map.get(path) or {}).get("title") or path) for path in missing_paths]
        raise ValueError(f"goal 연결을 선택한 경우 모든 대항목(goal)에 출처가 필요합니다: {', '.join(missing_labels)}")


def _first_goal_node_id(goal_map):
    for info in (goal_map or {}).values():
        node_id = str((info or {}).get("node_id") or "").strip()
        if node_id:
            return node_id
    return None


def _is_not_null_constraint_error(exc, column_name=None):
    message = str(exc or "").lower()
    if "23502" not in message and "not-null constraint" not in message and "null value in column" not in message:
        return False
    if not column_name:
        return True
    return str(column_name or "").lower() in message


def _find_existing_source_by_url(url):
    source_url = str(url or "").strip()
    if not source_url:
        return None

    rows = _supabase_get_with_select_fallback(
        "sources",
        query_params={
            "url": f"eq.{source_url}",
            "limit": "5",
        },
        select_candidates=[
            "id,title,url,source_type,publisher,published_at,summary,note",
            "id,title,url,source_type,publisher,published_at,summary",
            "id,title,url,source_type,publisher,published_at",
            "id,title,url,source_type,publisher",
            "id,title,url,source_type",
            "id,title,url",
            "id,url",
            "*",
        ],
    ) or []

    for row in rows:
        if str(row.get("url") or "").strip() == source_url and row.get("id") is not None:
            return row
    return None


def _upsert_pledge_node_source_link(
    *,
    pledge_node_id,
    pledge_id,
    source_id,
    source_role,
    note,
    uid,
    now_iso,
):
    existing_rows = _supabase_get_with_select_fallback(
        NODE_SOURCE_TABLE,
        query_params={
            "pledge_node_id": f"eq.{pledge_node_id}",
            "source_id": f"eq.{source_id}",
            "limit": "1",
            "order": "id.desc",
        },
        select_candidates=[
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at,created_by,updated_at,updated_by",
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at,updated_at",
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at",
            "id,pledge_node_id,pledge_id,source_id,source_role,note",
            "id,pledge_node_id,source_id,source_role,note",
            "id,pledge_node_id,source_id",
            "*",
        ],
    )
    existing = existing_rows[0] if existing_rows else None
    if existing and existing.get("id") is not None:
        link_id = existing.get("id")
        patched = _supabase_patch_with_optional_fields(
            NODE_SOURCE_TABLE,
            query_params={"id": f"eq.{link_id}"},
            payload={
                "pledge_id": pledge_id,
                "source_role": source_role,
                "note": note,
                "updated_at": now_iso,
                "updated_by": uid,
            },
            optional_fields={"pledge_id", "source_role", "note", "updated_at", "updated_by"},
        )
        merged = dict(existing)
        merged.update(patched)
        merged["id"] = link_id
        return merged

    return _insert_node_source_row(
        payload={
            "pledge_node_id": pledge_node_id,
            "pledge_id": pledge_id,
            "source_id": source_id,
            "source_role": source_role,
            "note": note,
            "created_at": now_iso,
            "created_by": uid,
            "updated_at": now_iso,
            "updated_by": uid,
        }
    )


def _upsert_pledge_source_link(
    *,
    pledge_id,
    source_id,
    source_role,
    note,
    uid,
    now_iso,
):
    existing_rows = _supabase_get_with_select_fallback(
        NODE_SOURCE_TABLE,
        query_params={
            "pledge_id": f"eq.{pledge_id}",
            "pledge_node_id": "is.null",
            "source_id": f"eq.{source_id}",
            "limit": "1",
            "order": "id.desc",
        },
        select_candidates=[
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at,created_by,updated_at,updated_by",
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at,updated_at",
            "id,pledge_node_id,pledge_id,source_id,source_role,note,created_at",
            "id,pledge_node_id,pledge_id,source_id,source_role,note",
            "id,pledge_node_id,pledge_id,source_id",
            "id,pledge_id,source_id",
            "*",
        ],
    )
    existing = existing_rows[0] if existing_rows else None
    if existing and existing.get("id") is not None:
        link_id = existing.get("id")
        patched = _supabase_patch_with_optional_fields(
            NODE_SOURCE_TABLE,
            query_params={"id": f"eq.{link_id}"},
            payload={
                "source_role": source_role,
                "note": note,
                "updated_at": now_iso,
                "updated_by": uid,
            },
            optional_fields={"source_role", "note", "updated_at", "updated_by"},
        )
        merged = dict(existing)
        merged.update(patched)
        merged["id"] = link_id
        return merged

    return _insert_node_source_row(
        payload={
            "pledge_node_id": None,
            "pledge_id": pledge_id,
            "source_id": source_id,
            "source_role": source_role,
            "note": note,
            "created_at": now_iso,
            "created_by": uid,
            "updated_at": now_iso,
            "updated_by": uid,
        }
    )


def _normalize_pledge_sources_payload(raw_sources):
    if raw_sources is None:
        return []
    if not isinstance(raw_sources, list):
        raise ValueError("sources must be an array")
    if not raw_sources:
        raise ValueError("sources must contain at least one row")

    normalized = []
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise ValueError("source row must be an object")

        source_id = str(raw.get("source_id") or "").strip() or None
        title = str(raw.get("title") or "").strip()
        if not title and not source_id:
            raise ValueError("source title is required")

        inferred_scope = "goal"
        try:
            link_scope = _normalize_source_link_scope(raw.get("link_scope") or inferred_scope)
        except ValueError as exc:
            raise ValueError(str(exc))

        source_url = str(raw.get("url") or "").strip() or None
        if source_url:
            try:
                parsed_source_url = parse.urlparse(source_url)
            except Exception:
                raise ValueError("source url is invalid")
            if str(parsed_source_url.scheme or "").lower() not in {"http", "https"}:
                raise ValueError("source url must be http(s)")

        published_at = str(raw.get("published_at") or "").strip() or None
        if published_at:
            try:
                datetime.strptime(published_at, "%Y-%m-%d")
            except ValueError:
                raise ValueError("source published_at must be in YYYY-MM-DD format")

        normalized_target_path = _normalize_source_target_path(raw.get("target_path")) if link_scope == "goal" else None
        if link_scope == "goal" and normalized_target_path and "/" in normalized_target_path:
            raise ValueError("goal target_path must use g:<순번> 형식입니다.")

        normalized.append(
            {
                "source_id": source_id,
                "link_scope": link_scope,
                "pledge_node_id": str(raw.get("pledge_node_id") or "").strip() or None if link_scope == "goal" else None,
                "target_path": normalized_target_path,
                "source_role": _normalize_node_source_role(raw.get("source_role") or "reference"),
                "title": title or None,
                "url": source_url,
                "source_type": _normalize_source_type(raw.get("source_type")),
                "publisher": str(raw.get("publisher") or "").strip() or None,
                "published_at": published_at,
                "summary": str(raw.get("summary") or "").strip() or None,
                "note": str(raw.get("note") or "").strip() or None,
            }
        )

    return normalized


def _save_pledge_source_rows(pledge_id, source_rows, created_nodes, uid):
    if not source_rows:
        return [], []

    now_iso = _now_iso()
    goal_map = _build_pledge_goal_target_map(created_nodes)
    _validate_goal_source_coverage(source_rows, goal_map)

    saved_source_rows = []
    saved_link_rows = []

    for source_row in source_rows:
        link_scope = source_row.get("link_scope") or "pledge"
        source_id = source_row.get("source_id")
        source_db_row = None
        if source_id:
            if not _ensure_source_exists(source_id):
                raise ValueError("source_id not found")
        else:
            source_db_row = _find_existing_source_by_url(source_row.get("url"))
            source_id = (source_db_row or {}).get("id")

        if not source_id:
            source_db_row = _supabase_insert_with_optional_fields(
                "sources",
                payload={
                    "title": source_row.get("title"),
                    "url": source_row.get("url"),
                    "source_type": source_row.get("source_type"),
                    "publisher": source_row.get("publisher"),
                    "published_at": source_row.get("published_at"),
                    "summary": source_row.get("summary"),
                    "note": source_row.get("note"),
                    "created_at": now_iso,
                    "created_by": uid,
                    "updated_at": now_iso,
                    "updated_by": uid,
                },
                optional_fields={
                    "url",
                    "source_type",
                    "publisher",
                    "published_at",
                    "summary",
                    "note",
                    "created_at",
                    "created_by",
                    "updated_at",
                    "updated_by",
                },
            )
            source_id = source_db_row.get("id")

        if not source_id:
            raise RuntimeError("source insert failed")

        if link_scope == "pledge":
            try:
                link_row = _upsert_pledge_source_link(
                    pledge_id=pledge_id,
                    source_id=source_id,
                    source_role=source_row.get("source_role"),
                    note=source_row.get("note"),
                    uid=uid,
                    now_iso=now_iso,
                )
            except RuntimeError as exc:
                fallback_goal_node_id = _first_goal_node_id(goal_map)
                can_fallback_to_goal_node = (
                    fallback_goal_node_id
                    and (
                        _is_foreign_key_runtime_error(exc)
                        or _is_not_null_constraint_error(exc, "pledge_node_id")
                    )
                )
                if not can_fallback_to_goal_node:
                    raise
                link_row = _upsert_pledge_node_source_link(
                    pledge_node_id=fallback_goal_node_id,
                    pledge_id=pledge_id,
                    source_id=source_id,
                    source_role=source_row.get("source_role"),
                    note=source_row.get("note"),
                    uid=uid,
                    now_iso=now_iso,
                )
        else:
            target_node_id = None
            target_path = str(source_row.get("target_path") or "").strip()
            if target_path:
                target_node_id = str((goal_map.get(target_path) or {}).get("node_id") or "").strip() or None
            if not target_node_id:
                pledge_node_id = str(source_row.get("pledge_node_id") or "").strip()
                if pledge_node_id:
                    target_node_id = pledge_node_id
            if not target_node_id:
                raise ValueError("goal 연결에 사용할 대항목을 찾을 수 없습니다.")
            link_row = _upsert_pledge_node_source_link(
                pledge_node_id=target_node_id,
                pledge_id=pledge_id,
                source_id=source_id,
                source_role=source_row.get("source_role"),
                note=source_row.get("note"),
                uid=uid,
                now_iso=now_iso,
            )

        if source_db_row:
            saved_source_rows.append(source_db_row)
        saved_link_rows.append(link_row)

    return saved_source_rows, saved_link_rows


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


@app.route("/api/pledges/source-library", methods=["GET"])
@api_login_required
def api_pledge_source_library():
    candidate_election_id = str(request.args.get("candidate_election_id") or "").strip()
    if not candidate_election_id:
        return jsonify({"error": "candidate_election_id is required"}), 400

    candidate_election = _fetch_candidate_election(candidate_election_id)
    if not candidate_election:
        return jsonify({"error": "candidate_election not found"}), 404

    candidate_election_ids = []
    requested_ce_id = str(candidate_election.get("id") or candidate_election_id).strip()
    if requested_ce_id:
        candidate_election_ids.append(requested_ce_id)

    related_candidate_id = str(candidate_election.get("candidate_id") or "").strip()
    related_election_id = str(candidate_election.get("election_id") or "").strip()
    if related_candidate_id and related_election_id:
        try:
            related_rows = _supabase_request(
                "GET",
                "candidate_elections",
                query_params={
                    "select": "id,candidate_id,election_id",
                    "candidate_id": f"eq.{related_candidate_id}",
                    "election_id": f"eq.{related_election_id}",
                    "limit": "5000",
                },
            ) or []
        except RuntimeError as exc:
            if _is_missing_schema_runtime_error(exc):
                related_rows = []
            else:
                raise
        for row in related_rows:
            rid = row.get("id")
            if rid is None:
                continue
            rid_text = str(rid)
            if rid_text not in candidate_election_ids:
                candidate_election_ids.append(rid_text)

    candidate_election_filter = _to_in_filter(candidate_election_ids)
    if not candidate_election_filter:
        candidate_election_filter = f"eq.{candidate_election_id}"

    pledges = _supabase_request(
        "GET",
        "pledges",
        query_params={
            "select": "id,title,candidate_election_id",
            "candidate_election_id": candidate_election_filter,
            "limit": "5000",
        },
    ) or []
    pledge_ids = [row.get("id") for row in pledges if row.get("id") is not None]
    pledge_filter = _to_in_filter(pledge_ids)
    if not pledge_filter:
        return jsonify({"rows": []}), 200

    link_rows = _fetch_pledge_source_rows(pledge_filter) or []
    pledge_nodes = _supabase_request(
        "GET",
        "pledge_nodes",
        query_params={
            "select": "id,pledge_id",
            "pledge_id": pledge_filter,
            "limit": "50000",
        },
    ) or []
    node_ids = [row.get("id") for row in pledge_nodes if row.get("id") is not None]
    node_filter = _to_in_filter(node_ids)
    node_to_pledge = {str(row.get("id")): row.get("pledge_id") for row in pledge_nodes if row.get("id") is not None}
    if node_filter:
        fallback_links = _fetch_node_source_rows(node_filter) or []
        for link in fallback_links:
            node_key = str(link.get("pledge_node_id") or "")
            if not link.get("pledge_id") and node_key in node_to_pledge:
                link["pledge_id"] = node_to_pledge.get(node_key)

        if link_rows:
            merged = {}
            for link in [*link_rows, *fallback_links]:
                link_id = link.get("id")
                if link_id is not None:
                    key = f"id:{link_id}"
                else:
                    key = "legacy:{pledge_id}:{pledge_node_id}:{source_id}:{created_at}".format(
                        pledge_id=str(link.get("pledge_id") or ""),
                        pledge_node_id=str(link.get("pledge_node_id") or ""),
                        source_id=str(link.get("source_id") or ""),
                        created_at=str(link.get("created_at") or ""),
                    )
                existing = merged.get(key)
                if (
                    existing
                    and str(existing.get("pledge_id") or "").strip()
                    and not str(link.get("pledge_id") or "").strip()
                ):
                    continue
                merged[key] = link
            link_rows = list(merged.values())
        else:
            link_rows = fallback_links

    source_ids = []
    for row in link_rows:
        source_id = row.get("source_id")
        if source_id is None:
            continue
        sid = str(source_id)
        if sid not in source_ids:
            source_ids.append(sid)
    source_filter = _to_in_filter(source_ids)
    if not source_filter:
        return jsonify({"rows": []}), 200

    source_rows = _supabase_get_with_select_fallback(
        "sources",
        query_params={
            "id": source_filter,
            "limit": "50000",
        },
        select_candidates=[
            "id,title,url,source_type,publisher,published_at,summary,note,created_at,updated_at",
            "id,title,url,source_type,publisher,published_at,summary,note,created_at",
            "id,title,url,source_type,publisher,published_at,summary,note",
            "id,title,url,source_type,publisher,published_at,summary",
            "id,title,url,source_type,publisher,published_at",
            "id,title,url,source_type,publisher",
            "id,title,url,source_type",
            "id,title,url",
            "id,title",
            "*",
        ],
    )
    source_map = {str(row.get("id")): row for row in source_rows if row.get("id") is not None}
    pledge_title_map = {str(row.get("id")): str(row.get("title") or "").strip() for row in pledges if row.get("id") is not None}

    aggregated = {}
    for link in link_rows:
        source_id = link.get("source_id")
        if source_id is None:
            continue
        sid = str(source_id)
        source = source_map.get(sid)
        if not source:
            continue

        if sid not in aggregated:
            aggregated[sid] = {
                "source_id": sid,
                "title": source.get("title"),
                "url": source.get("url"),
                "source_type": source.get("source_type"),
                "publisher": source.get("publisher"),
                "published_at": source.get("published_at"),
                "summary": source.get("summary"),
                "note": source.get("note"),
                "usage_count": 0,
                "latest_link_at": "",
                "links": [],
            }

        bucket = aggregated[sid]
        link_created_at = str(link.get("created_at") or "")
        if link_created_at and link_created_at > str(bucket.get("latest_link_at") or ""):
            bucket["latest_link_at"] = link_created_at
        bucket["usage_count"] = int(bucket.get("usage_count") or 0) + 1

        pledge_id = str(link.get("pledge_id") or "").strip()
        bucket["links"].append(
            {
                "pledge_id": pledge_id or None,
                "pledge_title": pledge_title_map.get(pledge_id) or None,
                "pledge_node_id": link.get("pledge_node_id"),
                "source_role": link.get("source_role"),
                "note": link.get("note"),
                "created_at": link.get("created_at"),
            }
        )

    rows = sorted(
        aggregated.values(),
        key=lambda row: (
            str(row.get("published_at") or ""),
            str(row.get("latest_link_at") or ""),
            int(row.get("usage_count") or 0),
            str(row.get("source_id") or ""),
        ),
        reverse=True,
    )
    for row in rows:
        links = row.get("links") or []
        row["links"] = sorted(
            links,
            key=lambda link: (str(link.get("created_at") or ""), str(link.get("pledge_id") or "")),
            reverse=True,
        )[:20]
    return jsonify({"rows": rows}), 200


@app.route("/api/progress-admin/node-sources", methods=["POST"])
@api_login_required
def api_progress_admin_node_sources():
    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}
    pledge_node_id = (payload.get("pledge_node_id") or "").strip()
    pledge_id = (payload.get("pledge_id") or "").strip()
    source_id = (payload.get("source_id") or "").strip()
    try:
        link_scope = _normalize_source_link_scope(
            payload.get("link_scope") or "node"
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        source_role = _normalize_node_source_role(payload.get("source_role") or "reference")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    note = (payload.get("note") or "").strip() or None

    if not source_id:
        return jsonify({"error": "source_id is required"}), 400

    if not _ensure_source_exists(source_id):
        return jsonify({"error": "source not found"}), 404

    now_iso = _now_iso()
    if link_scope == "pledge":
        resolved_pledge_id = pledge_id
        if not resolved_pledge_id and pledge_node_id:
            pledge_node = _get_pledge_node(pledge_node_id)
            if not pledge_node:
                return jsonify({"error": "pledge_node not found"}), 404
            resolved_pledge_id = str(pledge_node.get("pledge_id") or "").strip()
        if not resolved_pledge_id:
            return jsonify({"error": "pledge_id or pledge_node_id is required"}), 400
        if not _get_pledge_row(resolved_pledge_id):
            return jsonify({"error": "pledge not found"}), 404
        inserted = _upsert_pledge_source_link(
            pledge_id=resolved_pledge_id,
            source_id=source_id,
            source_role=source_role,
            note=note,
            uid=uid,
            now_iso=now_iso,
        )
    else:
        if not pledge_node_id and pledge_id:
            pledge_node_id = _resolve_default_source_target_node_id(pledge_id) or ""
        if not pledge_node_id:
            return jsonify({"error": "pledge_node_id or pledge_id is required"}), 400

        pledge_node = _get_pledge_node(pledge_node_id)
        if not pledge_node:
            return jsonify({"error": "pledge_node not found"}), 404
        if pledge_id and str(pledge_node.get("pledge_id")) != str(pledge_id):
            return jsonify({"error": "pledge_node does not belong to pledge_id"}), 400
        resolved_pledge_id = str(pledge_node.get("pledge_id") or pledge_id or "").strip() or None
        inserted = _upsert_pledge_node_source_link(
            pledge_node_id=pledge_node_id,
            pledge_id=resolved_pledge_id,
            source_id=source_id,
            source_role=source_role,
            note=note,
            uid=uid,
            now_iso=now_iso,
        )
    return jsonify({"ok": True, "row": inserted}), 201


@app.route("/api/progress-admin/record", methods=["POST"])
@api_login_required
def api_progress_admin_record():
    uid = _session_user_id()
    payload = request.get_json(silent=True) or {}

    pledge_node_id = str(payload.get("pledge_node_id") or "").strip()
    evaluation_date = str(payload.get("evaluation_date") or "").strip()
    reason = str(payload.get("reason") or "").strip() or None
    evaluator = str(payload.get("evaluator") or "").strip() or None

    source_id = str(payload.get("source_id") or "").strip() or None
    source_title = str(payload.get("source_title") or "").strip()
    source_url = str(payload.get("source_url") or "").strip() or None
    source_type = _normalize_source_type(payload.get("source_type"))
    source_publisher = str(payload.get("source_publisher") or "").strip() or None
    source_published_at = str(payload.get("source_published_at") or "").strip() or None
    source_summary = str(payload.get("source_summary") or "").strip() or None
    source_role = str(payload.get("source_role") or "").strip() or "primary"
    quoted_text = str(payload.get("quoted_text") or "").strip() or None
    page_no = str(payload.get("page_no") or "").strip() or None
    link_note = str(payload.get("note") or "").strip() or None

    if not pledge_node_id:
        return jsonify({"error": "pledge_node_id is required"}), 400
    if not evaluation_date:
        return jsonify({"error": "evaluation_date is required"}), 400
    try:
        datetime.strptime(evaluation_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "evaluation_date must be in YYYY-MM-DD format"}), 400

    if source_published_at:
        try:
            datetime.strptime(source_published_at, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "source_published_at must be in YYYY-MM-DD format"}), 400

    if source_url:
        try:
            parsed_source_url = parse.urlparse(source_url)
        except Exception:
            return jsonify({"error": "source_url is invalid"}), 400
        if str(parsed_source_url.scheme or "").lower() not in {"http", "https"}:
            return jsonify({"error": "source_url must be http(s)"}), 400

    try:
        progress_rate = _normalize_progress_rate(payload.get("progress_rate"))
        status = _normalize_progress_status(payload.get("status"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    pledge_node = _get_pledge_node(pledge_node_id)
    if not pledge_node:
        return jsonify({"error": "pledge_node not found"}), 404

    pledge_id = pledge_node.get("pledge_id")
    node_context = _build_progress_node_context(_fetch_pledge_nodes(pledge_id))
    target_ids = {str(row.get("id")) for row in (node_context.get("progress_targets") or []) if row.get("id") is not None}
    if str(pledge_node_id) not in target_ids:
        return jsonify({"error": "progress target must be an item or an item-less promise under an execution-method goal"}), 400

    now = _now_iso()
    try:
        latest_progress = _fetch_latest_progress_row(pledge_node_id)
        if latest_progress and latest_progress.get("id") is not None:
            progress_id = latest_progress.get("id")
            patched = _supabase_patch_with_optional_fields(
                "pledge_node_progress",
                query_params={"id": f"eq.{progress_id}"},
                payload={
                    "progress_rate": progress_rate,
                    "status": status,
                    "reason": reason,
                    "evaluator": evaluator,
                    "evaluation_date": evaluation_date,
                    "updated_at": now,
                    "updated_by": uid,
                },
                optional_fields={"status", "reason", "evaluator", "evaluation_date", "updated_at", "updated_by"},
            )
            progress_row = dict(latest_progress)
            progress_row.update(patched)
            progress_row["id"] = progress_id
        else:
            progress_row = _supabase_insert_with_optional_fields(
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
                    "updated_by": uid,
                },
                optional_fields={
                    "status",
                    "reason",
                    "evaluator",
                    "evaluation_date",
                    "created_at",
                    "created_by",
                    "updated_at",
                    "updated_by",
                },
            )
    except RuntimeError as exc:
        app.logger.exception("progress save failed: pledge_node_id=%s error=%s", pledge_node_id, exc)
        return runtime_error_response(
            exc,
            default_message="이행률 저장 중 오류가 발생했습니다.",
            network_message="데이터베이스 연결 문제로 저장에 실패했습니다.",
            schema_message="이행률 테이블 스키마를 확인해 주세요.",
        )

    progress_id = progress_row.get("id")
    if not progress_id:
        return jsonify({"error": "progress save failed"}), 500

    warning_code = None
    saved_source_id = source_id
    source_row = None
    progress_source_row = None

    try:
        if saved_source_id:
            if not _ensure_source_exists(saved_source_id):
                return jsonify({"error": "source not found"}), 404
        elif source_title:
            source_row = _supabase_insert_with_optional_fields(
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
                    "updated_by": uid,
                },
                optional_fields={
                    "url",
                    "source_type",
                    "publisher",
                    "published_at",
                    "summary",
                    "created_at",
                    "created_by",
                    "updated_at",
                    "updated_by",
                },
            )
            saved_source_id = source_row.get("id")
            if not saved_source_id:
                warning_code = "source_insert_failed"

        if saved_source_id:
            existing_progress_source = _fetch_latest_progress_source_link(progress_id)
            if existing_progress_source and existing_progress_source.get("id") is not None:
                progress_source_id = existing_progress_source.get("id")
                patched_link = _supabase_patch_with_optional_fields(
                    "pledge_node_progress_sources",
                    query_params={"id": f"eq.{progress_source_id}"},
                    payload={
                        "source_id": saved_source_id,
                        "source_role": source_role,
                        "quoted_text": quoted_text,
                        "page_no": page_no,
                        "note": link_note,
                        "updated_at": now,
                        "updated_by": uid,
                    },
                    optional_fields={"source_role", "quoted_text", "page_no", "note", "updated_at", "updated_by"},
                )
                progress_source_row = dict(existing_progress_source)
                progress_source_row.update(patched_link)
                progress_source_row["id"] = progress_source_id
            else:
                progress_source_row = _supabase_insert_with_optional_fields(
                    "pledge_node_progress_sources",
                    payload={
                        "pledge_node_progress_id": progress_id,
                        "source_id": saved_source_id,
                        "source_role": source_role,
                        "quoted_text": quoted_text,
                        "page_no": page_no,
                        "note": link_note,
                        "created_at": now,
                        "created_by": uid,
                        "updated_at": now,
                        "updated_by": uid,
                    },
                    optional_fields={
                        "source_role",
                        "quoted_text",
                        "page_no",
                        "note",
                        "created_at",
                        "created_by",
                        "updated_at",
                        "updated_by",
                    },
                )
        elif source_title:
            warning_code = warning_code or "source_link_skipped"
    except RuntimeError as exc:
        app.logger.exception("progress source save failed: progress_id=%s error=%s", progress_id, exc)
        warning_code = "source_save_failed"

    response_payload = {
        "ok": True,
        "progress": progress_row,
        "source_id": saved_source_id,
        "source": source_row,
        "progress_source": progress_source_row,
    }
    if warning_code:
        response_payload["warning"] = warning_code
    return jsonify(response_payload), 201


@app.route("/api/pledges", methods=["POST"])
def api_pledges():
    uid = _session_user_id()
    if not uid:
        return jsonify({"error": "login required"}), 401
    save_uid = uid

    payload = request.get_json(silent=True) or {}
    try:
        validated = _validate_pledge_payload(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        source_rows = _normalize_pledge_sources_payload(payload.get("sources"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    def _rollback_new_pledge(target_pledge_id):
        try:
            _delete_pledge_tree(target_pledge_id)
        except Exception as rollback_exc:
            app.logger.warning("Failed to rollback pledge tree %s: %s", target_pledge_id, rollback_exc)
        try:
            _supabase_request("DELETE", "pledges", query_params={"id": f"eq.{target_pledge_id}"})
        except Exception as rollback_exc:
            app.logger.warning("Failed to rollback pledge row %s: %s", target_pledge_id, rollback_exc)

    now = _now_iso()
    try:
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
                "created_by": save_uid,
                "updated_at": now,
                "updated_by": None,
            },
        )
    except RuntimeError as exc:
        app.logger.exception("Pledge insert failed: %s", exc)
        return runtime_error_response(
            exc,
            default_message="공약 저장 중 오류가 발생했습니다.",
            network_message="데이터베이스 연결 문제로 공약 저장에 실패했습니다.",
            schema_message="pledges 테이블 스키마를 확인해 주세요.",
            debug_prefix="pledge insert failed",
        )
    pledge_id = inserted.get("id")
    if not pledge_id:
        return jsonify({"error": "pledge insert failed"}), 500

    try:
        _insert_pledge_tree(pledge_id, validated["raw_text"], save_uid)
    except ValueError as exc:
        _rollback_new_pledge(pledge_id)
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        _rollback_new_pledge(pledge_id)
        app.logger.exception("Pledge tree insert failed for pledge_id=%s: %s", pledge_id, exc)
        return runtime_error_response(
            exc,
            default_message="공약 구조 저장 중 오류가 발생했습니다.",
            network_message="데이터베이스 연결 문제로 공약 구조 저장에 실패했습니다.",
            schema_message="pledge_nodes 테이블 스키마를 확인해 주세요.",
            debug_prefix="pledge tree insert failed",
        )
    except Exception:
        _rollback_new_pledge(pledge_id)
        raise

    try:
        created_nodes = _fetch_pledge_nodes(pledge_id)
    except RuntimeError as exc:
        _rollback_new_pledge(pledge_id)
        app.logger.exception("Pledge node fetch failed for pledge_id=%s: %s", pledge_id, exc)
        return runtime_error_response(
            exc,
            default_message="공약 구조 조회 중 오류가 발생했습니다.",
            network_message="데이터베이스 연결 문제로 공약 구조 조회에 실패했습니다.",
            schema_message="pledge_nodes 테이블 스키마를 확인해 주세요.",
            debug_prefix="pledge node fetch failed",
        )
    saved_source_rows = []
    saved_source_links = []
    if source_rows:
        try:
            saved_source_rows, saved_source_links = _save_pledge_source_rows(
                pledge_id,
                source_rows,
                created_nodes,
                save_uid,
            )
        except ValueError as exc:
            _rollback_new_pledge(pledge_id)
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            app.logger.exception("Pledge source save failed for pledge_id=%s: %s", pledge_id, exc)
            _rollback_new_pledge(pledge_id)
            return runtime_error_response(
                exc,
                default_message="공약 출처 저장 중 오류가 발생했습니다.",
                network_message="데이터베이스 연결 문제로 공약 출처 저장에 실패했습니다.",
                foreign_key_message="공약 출처 연결 관계가 유효하지 않습니다. pledge_node_sources의 FK를 확인해 주세요.",
                schema_message="공약 출처 테이블 스키마를 확인해 주세요.",
                debug_prefix="pledge source save failed",
            )
        except Exception as exc:
            _rollback_new_pledge(pledge_id)
            app.logger.exception("Unexpected pledge source save error for pledge_id=%s: %s", pledge_id, exc)
            return jsonify({"error": str(exc) if not IS_PRODUCTION else "공약 출처 저장 중 알 수 없는 오류가 발생했습니다."}), 500

    return jsonify(
        {
            "ok": True,
            "pledge_id": pledge_id,
            "nodes": created_nodes,
            "sources": saved_source_rows,
            "source_links": saved_source_links,
        }
    ), 201


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
        report_type = _normalize_report_type(payload.get("report_type"), default="?좉퀬")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    reason_category = (payload.get("reason_category") or "").strip() or None
    status = "?묒닔"
    target_url = _sanitize_target_url(payload.get("target_url")) or _sanitize_target_url(request.headers.get("Referer"))
    now = _now_iso()

    if not reason:
        return jsonify({"error": "reason is required"}), 400
    if len(reason) > 2000:
        return jsonify({"error": "reason is too long (max 2000 chars)"}), 400
    if candidate_id and pledge_id:
        return jsonify({"error": "candidate_id and pledge_id cannot both be set"}), 400
    if report_type == "?좉퀬" and not (candidate_id or pledge_id):
        return jsonify({"error": "?좉퀬???꾨낫???먮뒗 怨듭빟 ??곸쓣 吏?뺥빐???⑸땲??"}), 400

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

    if report_type == "?좉퀬":
        duplicate_query = {
            "select": "id,status",
            "user_id": f"eq.{uid}",
            "report_type": "eq.?좉퀬",
            "limit": "50",
            "order": "created_at.desc",
        }
        if candidate_id:
            duplicate_query["candidate_id"] = f"eq.{candidate_id}"
        if pledge_id:
            duplicate_query["pledge_id"] = f"eq.{pledge_id}"
        duplicates = _supabase_request("GET", "reports", query_params=duplicate_query) or []
        if any(str(row.get("status") or "").strip() in OPEN_REPORT_STATUS_CHOICES for row in duplicates):
            return jsonify({"error": "?대? ?묒닔/寃?좎쨷???좉퀬媛 ?덉뒿?덈떎."}), 409

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

