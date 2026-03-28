# Candora Flask Project Structure (Safe-Split Refactor)

## 1) Scope and Guardrails
- Functional behavior unchanged.
- DB schema unchanged.
- Supabase integration style unchanged.
- Existing URL and API response contracts unchanged.
- Compatibility entry layers preserved:
  - `app.py`
  - `routes/candidate.py`
  - `routes/pledge.py`

## 2) Current Structure
```text
candidate/
  app.py
  routes/
    auth.py
    candidate.py
    candidate_admin.py
    election.py
    pages.py
    pledge.py
    progress.py
    report.py
    static_pages.py
    admin_common.py
  services/
    auth_session_service.py
    candidate_detail_service.py
    http_security_service.py
    pledge_read_service.py
    pledge_source_service.py
    pledge_tree_service.py
    supabase_service.py
  utils/
    app_common_utils.py
    app_value_utils.py
  templates/
    *.html
  static/
    css/*.css
    js/*.js
    pages/*.html
```

## 3) Layer Responsibilities
- `app.py`
  - Flask app initialization and runtime configuration.
  - Compatibility alias layer: keeps legacy symbol names that routes/tests patch.
  - Core binding source for `bind_core(...)`.
- `routes/*`
  - URL handlers and request/response boundary logic.
  - Delegates heavy logic to services while keeping endpoint signatures stable.
- `services/*`
  - Non-route business/data/security/session logic.
  - Supabase I/O helpers and fallback behavior.
  - Candidate detail assembly and pledge source normalization/save flows.
- `utils/*`
  - Pure utility helpers (env parsing, pagination, status normalization, cloning).
- `templates` + `static`
  - UI rendering assets. Re-layout/re-locate minimized in this refactor stage.

## 4) Compatibility Layer (Kept Intact)
- `app.py` still exposes legacy helper symbols used by:
  - `routes_bootstrap.bind_core`
  - route modules (`routes/*.py`)
  - tests with monkeypatch/patch
- `routes/candidate.py` and `routes/pledge.py` remain import/route entry modules, but long helper responsibilities were moved to:
  - `services/candidate_detail_service.py`
  - `services/pledge_source_service.py`

## 5) Import Rules (Cycle Prevention)
- Rule 1: `utils` imports no project layers.
- Rule 2: `services` may import `utils`, but must not import `app` or `routes`.
- Rule 3: `routes` must not directly import `app`; use `bind_core(globals())`.
- Rule 4: `app.py` may import `services/utils`, and route modules only for registration.
- Rule 5: shared logic changes go to `services`/`utils`; keep route files thin.

Cycle check result (AST import graph): `0` cycles detected.

## 6) Template / Static Mapping (Documentation-First)
- `templates/index.html` -> `static/css/index.css`
- `templates/login.html` -> `static/css/login.css`, `static/js/login-ui.js`
- `templates/mypage.html` -> `static/css/mypage.css`, `static/js/mypage.js`
- `templates/candidate.html` -> `static/css/candidate.css`, `static/js/candidate-admin.js`
- `templates/election.html` -> `static/css/candidate.css`, `static/js/election-admin.js`
- `templates/pledge.html` -> `static/css/pledge.css`, `static/js/pledge-parse-utils.js`, `static/js/pledge-admin-utils.js`, `static/js/pledge-admin-preview.js`, `static/js/pledge-admin.js`
- `templates/politicians.html` -> `static/css/browse.css`, `static/js/browse.js`
- `templates/promises.html` -> `static/css/browse.css`, `static/js/browse.js`
- `templates/politician_detail.html` -> `static/css/browse.css`, `static/js/politician-detail-tree.js`, `static/js/politicianDetail.js`
- `templates/progress.html` -> `static/css/progress.css`, `static/js/progress-admin.js`
- `templates/static_pages_admin.html` -> `static/css/static-pages-admin.css`
- `templates/layout.html` (base) -> `static/css/main.css`, `static/css/button-theme.css`, `static/js/userAuth.js`, `static/js/feedback-widget.js`, `static/pages/about.html`, `static/pages/privacy.html`, `static/pages/contact.html`

Note: static asset relocation was intentionally minimized in this stage. Mapping is documented for future safe migration.

## 7) Dead Code Candidate List (No Deletion in This Refactor)
Confirmed dead code: none.

Low-confidence candidates for future audit (needs runtime usage/log verification):
- `templates/hall_of_fame.html` (+ route `/hall-of-fame`)
  - Reason: dedicated page with isolated usage path.
  - Risk if removed: direct URL users break.
- `static/css/static-pages.css`
  - Reason: referenced only by `static/pages/*.html` fragments.
  - Risk if removed: About/Privacy/Contact modal/page styling regression.
- `routes/static_pages.py` and `templates/static_pages_admin.html`
  - Reason: admin-only feature surface; traffic unknown.
  - Risk if removed: static-page admin workflow break.

## 8) Stage Execution Notes
- Stage 0: Baseline route/test snapshot captured.
- Stage 1: Pure helpers moved to `utils/app_common_utils.py` with `app.py` aliases preserved.
- Stage 2: Supabase I/O moved to `services/supabase_service.py` with `app.py` aliases preserved.
- Stage 3: Security/session/admin-cache helpers moved to `services/http_security_service.py` and `services/auth_session_service.py`.
- Stage 4: Long candidate/pledge helper responsibilities moved to `services/candidate_detail_service.py` and `services/pledge_source_service.py` (route compatibility kept).
- Stage 5: Static structure documented (minimal physical movement).
- Stage 6: Dead code candidates documented only (no deletion).
