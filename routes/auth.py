from routes_bootstrap import bind_core, runtime_error_response

bind_core(globals())

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


