import io
import os
import unittest
from unittest.mock import patch


os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import app as app_module


REPORT_TYPE_REPORT = "\uc2e0\uace0"
REPORT_STATUS_RECEIVED = "\uc811\uc218"
REPORT_STATUS_RESOLVED = "\ucc98\ub9ac\uc644\ub8cc"


class SecurityHardeningTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_auth_login_requires_access_token(self):
        resp = self.client.post("/auth/login", json={})
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json() or {}
        self.assertIn("access_token", payload.get("error", ""))

    def test_auth_login_returns_503_when_auth_provider_unavailable(self):
        with patch.object(app_module, "_fetch_supabase_user", side_effect=RuntimeError("network down")):
            resp = self.client.post("/auth/login", json={"access_token": "token-1"})

        self.assertEqual(resp.status_code, 503)
        payload = resp.get_json() or {}
        self.assertIn("authentication provider unavailable", payload.get("error", ""))

    def test_auth_login_uses_verified_user(self):
        with (
            patch.object(app_module, "_fetch_supabase_user", return_value={"id": "u-1", "email": "u1@example.com"}),
            patch.object(app_module, "ensure_user_profile"),
            patch.object(app_module, "_is_admin", return_value=False),
        ):
            resp = self.client.post("/auth/login", json={"access_token": "token-1"})

        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_id"), "u-1")
            self.assertEqual(sess.get("email"), "u1@example.com")

    def test_api_report_does_not_hide_pledge_immediately(self):
        calls = []

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            calls.append((method, table, query_params, payload))
            if method == "GET" and table == "pledges":
                return [{"id": "p-1"}]
            if method == "GET" and table == "reports":
                return []
            if method == "POST" and table == "reports":
                return {"id": "r-1"}
            return []

        with self.client.session_transaction() as sess:
            sess["user_id"] = "u-1"
            sess["email"] = "u1@example.com"

        with patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request):
            resp = self.client.post(
                "/api/report",
                json={
                    "pledge_id": "p-1",
                    "reason": "test report",
                    "report_type": REPORT_TYPE_REPORT,
                },
            )

        self.assertEqual(resp.status_code, 200)
        patch_pledge_calls = [c for c in calls if c[0] == "PATCH" and c[1] == "pledges"]
        self.assertEqual(patch_pledge_calls, [])

    def test_admin_report_resolve_hides_pledge(self):
        calls = []

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            calls.append((method, table, query_params, payload))
            if method == "GET" and table == "reports":
                return [{"id": "r-1", "pledge_id": "p-1", "report_type": REPORT_TYPE_REPORT, "status": REPORT_STATUS_RECEIVED}]
            if method == "PATCH" and table == "reports":
                return {"ok": True}
            if method == "PATCH" and table == "pledges":
                return {"ok": True}
            return []

        with self.client.session_transaction() as sess:
            sess["user_id"] = "admin-1"
            sess["email"] = "admin@example.com"

        with (
            patch.object(app_module, "_is_admin", return_value=True),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
        ):
            resp = self.client.patch("/api/mypage/reports/r-1", json={"status": REPORT_STATUS_RESOLVED})

        self.assertEqual(resp.status_code, 200)
        patch_pledge_calls = [c for c in calls if c[0] == "PATCH" and c[1] == "pledges"]
        self.assertTrue(patch_pledge_calls)

    def test_blocks_cross_origin_state_change(self):
        resp = self.client.post("/auth/logout", headers={"Origin": "https://evil.example"})
        self.assertEqual(resp.status_code, 403)

    def test_allows_same_origin_state_change(self):
        resp = self.client.post("/auth/logout", headers={"Origin": "http://localhost"})
        self.assertEqual(resp.status_code, 200)

    def test_security_headers_present(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("script-src", resp.headers.get("Content-Security-Policy", ""))

    def test_upload_rejects_signature_mismatch(self):
        png_header = b"\x89PNG\r\n\x1a\n" + b"x" * 20
        with self.client.session_transaction() as sess:
            sess["user_id"] = "u-1"
            sess["email"] = "u1@example.com"

        data = {"image": (io.BytesIO(png_header), "fake.jpg")}
        resp = self.client.post("/api/upload-image", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 400)

    def test_admin_delete_pledge_returns_503_instead_of_internal_error(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = "admin-1"
            sess["email"] = "admin@example.com"

        with (
            patch.object(app_module, "_is_admin", return_value=True),
            patch.object(app_module, "_get_pledge_row", return_value={"id": "p-1"}),
            patch.object(app_module, "_safe_delete_rows", return_value=True),
            patch.object(app_module, "_delete_pledge_tree", side_effect=RuntimeError("Supabase request failed (network): timeout")),
        ):
            resp = self.client.delete("/api/admin/pledges/p-1")

        self.assertEqual(resp.status_code, 503)
        payload = resp.get_json() or {}
        self.assertIn("연결 문제", payload.get("error", ""))

    def test_admin_delete_pledge_returns_409_on_foreign_key_error(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = "admin-1"
            sess["email"] = "admin@example.com"

        with (
            patch.object(app_module, "_is_admin", return_value=True),
            patch.object(app_module, "_get_pledge_row", return_value={"id": "p-1"}),
            patch.object(app_module, "_safe_delete_rows", return_value=True),
            patch.object(app_module, "_delete_pledge_tree", side_effect=RuntimeError("update or delete on table \"pledges\" violates foreign key constraint")),
        ):
            resp = self.client.delete("/api/admin/pledges/p-1")

        self.assertEqual(resp.status_code, 409)
        payload = resp.get_json() or {}
        self.assertIn("삭제할 수 없습니다", payload.get("error", ""))

    def test_admin_delete_pledge_never_soft_deletes_status(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = "admin-1"
            sess["email"] = "admin@example.com"

        with (
            patch.object(app_module, "_is_admin", return_value=True),
            patch.object(app_module, "_get_pledge_row", return_value={"id": "p-1"}),
            patch.object(app_module, "_safe_delete_rows", return_value=True),
            patch.object(
                app_module,
                "_delete_pledge_tree",
                side_effect=RuntimeError("update or delete on table \"pledges\" violates foreign key constraint"),
            ),
            patch.object(
                app_module,
                "_supabase_request",
                side_effect=RuntimeError("Supabase request failed (network): timeout"),
            ),
            patch.object(app_module, "_supabase_patch_with_optional_fields") as patch_soft_delete,
        ):
            resp = self.client.delete("/api/admin/pledges/p-1")

        self.assertIn(resp.status_code, (409, 503))
        patch_soft_delete.assert_not_called()

    def test_delete_pledge_tree_cleans_related_links_and_orphan_sources(self):
        calls = []

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            query_params = dict(query_params or {})
            calls.append((method, table, query_params, payload))

            if method == "GET" and table == "pledge_nodes":
                return [{"id": "n-1"}, {"id": "n-2"}]
            if method == "GET" and table == "pledge_node_progress":
                return [{"id": "pr-1"}]
            if method == "GET" and table == "pledge_node_sources":
                if query_params.get("select") in {"source_id", "id,source_id"}:
                    return [{"id": 1, "source_id": "s-orphan"}, {"id": 2, "source_id": "s-shared"}]
                if query_params.get("select") == "id":
                    source_filter = str(query_params.get("source_id") or "")
                    if source_filter == "eq.s-shared":
                        return [{"id": "ref-1"}]
                    return []
            if method == "GET" and table == "pledge_node_progress_sources":
                if query_params.get("select") in {"source_id", "id,source_id"}:
                    return [{"id": "ps-1", "source_id": "sp-orphan"}, {"id": "ps-2", "source_id": "s-shared"}]
                if query_params.get("select") == "id":
                    return []
            if method == "DELETE":
                return []
            return []

        with patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request):
            app_module._delete_pledge_tree("p-1")

        delete_calls = [(table, params) for method, table, params, _ in calls if method == "DELETE"]
        deleted_tables = {table for table, _ in delete_calls}
        self.assertIn("pledge_node_progress_sources", deleted_tables)
        self.assertIn("pledge_node_progress", deleted_tables)
        self.assertIn("pledge_node_sources", deleted_tables)
        self.assertIn("pledge_nodes", deleted_tables)

        deleted_source_filters = sorted(
            params.get("id")
            for table, params in delete_calls
            if table == "sources" and params.get("id")
        )
        self.assertEqual(deleted_source_filters, ["eq.s-orphan", "eq.sp-orphan"])

    def test_delete_pledge_tree_deletes_nodes_bottom_up(self):
        calls = []

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            query_params = dict(query_params or {})
            calls.append((method, table, query_params, payload))

            if method == "GET" and table == "pledge_nodes":
                return [
                    {"id": "goal-1", "parent_id": None},
                    {"id": "promise-1", "parent_id": "goal-1"},
                    {"id": "item-1", "parent_id": "promise-1"},
                ]
            if method == "GET" and table == "pledge_node_sources":
                return []
            if method == "GET" and table == "pledge_node_progress":
                return []
            if method == "DELETE":
                return []
            return []

        with patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request):
            app_module._delete_pledge_tree("p-1")

        pledge_node_delete_filters = [
            params.get("id")
            for method, table, params, _ in calls
            if method == "DELETE" and table == "pledge_nodes"
        ]
        self.assertGreaterEqual(len(pledge_node_delete_filters), 3)
        self.assertIn('"item-1"', str(pledge_node_delete_filters[0]))
        self.assertIn('"promise-1"', str(pledge_node_delete_filters[1]))
        self.assertIn('"goal-1"', str(pledge_node_delete_filters[2]))


if __name__ == "__main__":
    unittest.main()
