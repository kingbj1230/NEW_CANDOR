from routes_bootstrap import bind_core

bind_core(globals())

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "time": _now_iso()}), 200

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/mypage")
@login_required
def mypage():
    return render_template("mypage.html")

@app.route("/hall-of-fame")
def hall_of_fame_page():
    return render_template("hall_of_fame.html")


@app.route("/pledge/paste-guide")
def pledge_paste_guide_page():
    return render_template("pledge_paste_guide.html")
