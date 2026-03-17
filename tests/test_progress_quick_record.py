import os
import unittest
from unittest.mock import patch


os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import app as app_module


class ProgressRecordApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def _set_login_session(self, user_id="u-1", email="u1@example.com"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["email"] = email

    @staticmethod
    def _execution_method_nodes():
        return [
            {
                "id": "goal-1",
                "pledge_id": "pledge-1",
                "name": "goal",
                "content": "이행 방법",
                "parent_id": None,
                "is_leaf": False,
                "sort_order": 1,
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "promise-1",
                "pledge_id": "pledge-1",
                "name": "promise",
                "content": "세부 약속",
                "parent_id": "goal-1",
                "is_leaf": False,
                "sort_order": 1,
                "created_at": "2026-01-01T00:00:00Z",
            },
        ]

    @staticmethod
    def _non_execution_nodes():
        return [
            {
                "id": "goal-1",
                "pledge_id": "pledge-1",
                "name": "goal",
                "content": "정책 목표",
                "parent_id": None,
                "is_leaf": False,
                "sort_order": 1,
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "promise-1",
                "pledge_id": "pledge-1",
                "name": "promise",
                "content": "세부 약속",
                "parent_id": "goal-1",
                "is_leaf": False,
                "sort_order": 1,
                "created_at": "2026-01-01T00:00:00Z",
            },
        ]

    def test_record_saves_progress_without_source(self):
        self._set_login_session()

        def fake_insert(table, payload, optional_fields):
            if table == "pledge_node_progress":
                return {"id": "progress-1", **(payload or {})}
            self.fail(f"unexpected insert table: {table}")

        with (
            patch.object(app_module, "_get_pledge_node", return_value={"id": "promise-1", "pledge_id": "pledge-1"}),
            patch.object(app_module, "_fetch_pledge_nodes", return_value=self._execution_method_nodes()),
            patch.object(app_module, "_fetch_latest_progress_row", return_value=None),
            patch.object(app_module, "_supabase_insert_with_optional_fields", side_effect=fake_insert),
        ):
            resp = self.client.post(
                "/api/progress-admin/record",
                json={
                    "pledge_node_id": "promise-1",
                    "progress_rate": 3.5,
                    "status": "in_progress",
                    "evaluation_date": "2026-03-15",
                },
            )

        self.assertEqual(resp.status_code, 201)
        payload = resp.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertEqual((payload.get("progress") or {}).get("id"), "progress-1")

    def test_record_saves_progress_with_new_source_and_link(self):
        self._set_login_session()

        def fake_insert(table, payload, optional_fields):
            if table == "pledge_node_progress":
                return {"id": "progress-1", **(payload or {})}
            if table == "sources":
                return {"id": "source-1", **(payload or {})}
            if table == "pledge_node_progress_sources":
                return {"id": "link-1", **(payload or {})}
            self.fail(f"unexpected insert table: {table}")

        with (
            patch.object(app_module, "_get_pledge_node", return_value={"id": "promise-1", "pledge_id": "pledge-1"}),
            patch.object(app_module, "_fetch_pledge_nodes", return_value=self._execution_method_nodes()),
            patch.object(app_module, "_fetch_latest_progress_row", return_value=None),
            patch.object(app_module, "_fetch_latest_progress_source_link", return_value=None),
            patch.object(app_module, "_supabase_insert_with_optional_fields", side_effect=fake_insert),
        ):
            resp = self.client.post(
                "/api/progress-admin/record",
                json={
                    "pledge_node_id": "promise-1",
                    "progress_rate": 4,
                    "status": "completed",
                    "evaluation_date": "2026-03-15",
                    "source_title": "2026년 보도자료",
                    "source_url": "https://example.com/article",
                    "source_role": "primary",
                    "quoted_text": "핵심 문장",
                },
            )

        self.assertEqual(resp.status_code, 201)
        payload = resp.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("source_id"), "source-1")
        self.assertEqual((payload.get("progress_source") or {}).get("id"), "link-1")

    def test_record_rejects_non_progress_target_node(self):
        self._set_login_session()

        with (
            patch.object(app_module, "_get_pledge_node", return_value={"id": "promise-1", "pledge_id": "pledge-1"}),
            patch.object(app_module, "_fetch_pledge_nodes", return_value=self._non_execution_nodes()),
        ):
            resp = self.client.post(
                "/api/progress-admin/record",
                json={
                    "pledge_node_id": "promise-1",
                    "progress_rate": 3,
                    "status": "in_progress",
                    "evaluation_date": "2026-03-15",
                },
            )

        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json() or {}
        self.assertIn("progress target", payload.get("error", ""))


if __name__ == "__main__":
    unittest.main()
