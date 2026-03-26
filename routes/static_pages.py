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


