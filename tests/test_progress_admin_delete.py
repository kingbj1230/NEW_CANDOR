import os
import unittest
from unittest.mock import patch


os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import app as app_module


class ProgressAdminDeleteApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def _set_login_session(self, user_id="admin-1", email="admin@example.com"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["email"] = email

    def test_requires_login(self):
        resp = self.client.delete("/api/admin/progress-records/pr-1")
        self.assertEqual(resp.status_code, 401)

    def test_requires_admin_role(self):
        self._set_login_session(user_id="user-1", email="user@example.com")
        with patch.object(app_module, "_is_admin", return_value=False):
            resp = self.client.delete("/api/admin/progress-records/pr-1")
        self.assertEqual(resp.status_code, 403)

    def test_returns_404_when_progress_not_found(self):
        self._set_login_session()
        with (
            patch.object(app_module, "_is_admin", return_value=True),
            patch.object(app_module, "_supabase_get_with_select_fallback", return_value=[]),
        ):
            resp = self.client.delete("/api/admin/progress-records/pr-404")

        self.assertEqual(resp.status_code, 404)
        payload = resp.get_json() or {}
        self.assertEqual(payload.get("error"), "not found")

    def test_deletes_progress_and_only_orphan_sources(self):
        self._set_login_session()
        delete_calls = []

        def fake_get(table, query_params=None, select_candidates=None):
            query_params = dict(query_params or {})

            if table == "pledge_node_progress":
                if query_params.get("id") == "eq.pr-1":
                    return [{"id": "pr-1", "pledge_node_id": "node-1"}]
                return []

            if table == "pledge_node_progress_sources":
                if query_params.get("pledge_node_progress_id") == "eq.pr-1":
                    return [
                        {"id": "link-1", "source_id": "s-orphan"},
                        {"id": "link-2", "source_id": "s-shared"},
                    ]
                if query_params.get("source_id") == "eq.s-orphan":
                    return []
                if query_params.get("source_id") == "eq.s-shared":
                    return [{"id": "still-used"}]
                return []

            if table == "pledge_node_sources":
                if query_params.get("source_id") == "eq.s-orphan":
                    return []
                if query_params.get("source_id") == "eq.s-shared":
                    return [{"id": "node-link-1"}]
                return []

            return []

        def fake_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method == "DELETE":
                delete_calls.append((table, dict(query_params or {})))
            return []

        with (
            patch.object(app_module, "_is_admin", return_value=True),
            patch.object(app_module, "_supabase_get_with_select_fallback", side_effect=fake_get),
            patch.object(app_module, "_supabase_request", side_effect=fake_request),
            patch.object(app_module, "_invalidate_api_cache") as invalidate_cache,
        ):
            resp = self.client.delete("/api/admin/progress-records/pr-1")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("deleted_progress_id"), "pr-1")
        self.assertEqual(payload.get("deleted_orphan_source_ids"), ["s-orphan"])

        self.assertIn(("pledge_node_progress_sources", {"pledge_node_progress_id": "eq.pr-1"}), delete_calls)
        self.assertIn(("pledge_node_progress", {"id": "eq.pr-1"}), delete_calls)
        self.assertIn(("sources", {"id": "eq.s-orphan"}), delete_calls)
        self.assertNotIn(("sources", {"id": "eq.s-shared"}), delete_calls)
        invalidate_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
