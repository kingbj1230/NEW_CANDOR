import os
import unittest
from unittest.mock import patch


os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import app as app_module
import routes.pledge as routes_pledge_module


class PledgeSourceUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def _set_login_session(self, user_id="u-1", email="u1@example.com"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["email"] = email

    @staticmethod
    def _validated_payload():
        return {
            "candidate_election_id": "ce-1",
            "sort_order": 1,
            "title": "Pledge title",
            "raw_text": "Goal\nMethod\n- Action",
            "category": "economy",
            "timeline_text": None,
            "finance_text": None,
            "parse_type": "type3",
            "structure_version": 1,
            "fulfillment_rate": 0,
            "status": "active",
        }

    @staticmethod
    def _created_nodes():
        return [
            {
                "id": "goal-1",
                "pledge_id": "pledge-1",
                "name": "goal",
                "content": "Goal",
                "sort_order": 1,
                "parent_id": None,
                "is_leaf": False,
                "created_at": "2026-03-15T00:00:00Z",
            },
            {
                "id": "promise-1",
                "pledge_id": "pledge-1",
                "name": "promise",
                "content": "Method",
                "sort_order": 1,
                "parent_id": "goal-1",
                "is_leaf": False,
                "created_at": "2026-03-15T00:00:00Z",
            },
            {
                "id": "item-1",
                "pledge_id": "pledge-1",
                "name": "item",
                "content": "Action",
                "sort_order": 1,
                "parent_id": "promise-1",
                "is_leaf": True,
                "created_at": "2026-03-15T00:00:00Z",
            },
        ]

    def test_extract_missing_column_from_runtime_message_variants(self):
        self.assertEqual(
            app_module._extract_missing_column_from_runtime_message(
                "Could not find the 'updated_at' column of 'pledge_node_sources' in the schema cache"
            ),
            "updated_at",
        )
        self.assertEqual(
            app_module._extract_missing_column_from_runtime_message(
                'column "updated_by" of relation "pledge_node_sources" does not exist'
            ),
            "updated_by",
        )

    def test_legacy_source_endpoints_are_removed_and_source_library_is_available(self):
        self._set_login_session()

        self.assertEqual(
            self.client.post("/api/progress-admin/sources", json={"title": "x"}).status_code,
            404,
        )
        with patch.object(routes_pledge_module, "_build_candidate_election_source_library", return_value=[]):
            source_library_resp = self.client.get("/api/pledges/source-library?candidate_election_id=ce-1")
        self.assertEqual(source_library_resp.status_code, 200)
        self.assertEqual((source_library_resp.get_json() or {}).get("rows"), [])
        self.assertEqual(
            self.client.post("/api/progress-admin/node-sources", json={"source_id": "s-1"}).status_code,
            404,
        )

    def test_source_library_endpoint_aggregates_reusable_sources(self):

        def fake_get_with_select_fallback(table, query_params=None, select_candidates=None):
            if table == "pledges":
                return [
                    {"id": "p-1", "status": "active"},
                    {"id": "p-2", "status": "deleted"},
                    {"id": "p-3", "status": "active"},
                ]
            if table == app_module.NODE_SOURCE_TABLE:
                return [
                    {"source_id": "s-2", "created_at": "2026-03-20T00:00:00Z"},
                    {"source_id": "s-1", "created_at": "2026-03-19T00:00:00Z"},
                    {"source_id": "s-1", "created_at": "2026-03-18T00:00:00Z"},
                ]
            if table == "sources":
                return [
                    {"id": "s-1", "title": "Source 1", "url": "https://example.com/one"},
                    {"id": "s-2", "title": "Source 2", "url": "https://example.com/two"},
                ]
            return []

        with patch.object(routes_pledge_module, "_supabase_get_with_select_fallback", side_effect=fake_get_with_select_fallback):
            rows = routes_pledge_module._build_candidate_election_source_library("ce-1")

        self.assertEqual(len(rows), 2)
        self.assertEqual([row.get("id") for row in rows], ["s-2", "s-1"])
        self.assertEqual((rows[0] or {}).get("usage_count"), 1)
        self.assertEqual((rows[1] or {}).get("usage_count"), 2)

    def test_api_pledges_saves_source_with_target_path(self):
        self._set_login_session()

        def fake_insert_with_optional_fields(table, payload, optional_fields):
            if table == "pledges":
                return {"id": "pledge-1", **(payload or {})}
            if table == "sources":
                return {"id": "source-1", **(payload or {})}
            self.fail(f"unexpected table for optional insert: {table}")

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_insert_pledge_tree"),
            patch.object(app_module, "_fetch_pledge_nodes", return_value=self._created_nodes()),
            patch.object(routes_pledge_module, "_find_existing_source_by_url", return_value=None),
            patch.object(app_module, "_supabase_insert_with_optional_fields", side_effect=fake_insert_with_optional_fields),
            patch.object(
                routes_pledge_module,
                "_upsert_pledge_node_source_link",
                return_value={"id": 101, "pledge_node_id": "goal-1"},
            ) as upsert_mock,
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "Pledge title",
                    "raw_text": "Goal\nMethod\n- Action",
                    "category": "economy",
                    "sources": [
                        {
                            "title": "Official pledge PDF",
                            "url": "https://example.com/manifesto",
                            "source_type": "government",
                            "source_role": "origin",
                            "link_scope": "goal",
                            "target_path": "g:1",
                            "note": "official source",
                        }
                    ],
                },
            )

        self.assertEqual(resp.status_code, 201)
        payload = resp.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("pledge_id"), "pledge-1")
        self.assertEqual(len(payload.get("source_links") or []), 1)
        self.assertEqual((payload.get("source_links") or [{}])[0].get("pledge_node_id"), "goal-1")

        upsert_kwargs = upsert_mock.call_args.kwargs
        self.assertEqual(upsert_kwargs.get("pledge_node_id"), "goal-1")
        self.assertEqual(upsert_kwargs.get("pledge_id"), "pledge-1")
        self.assertEqual(upsert_kwargs.get("source_role"), "원문출처")

    def test_api_pledges_rolls_back_when_target_path_is_invalid(self):
        self._set_login_session()
        supabase_calls = []

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            supabase_calls.append((method, table, dict(query_params or {}), payload))
            return []

        def fake_insert_with_optional_fields(table, payload, optional_fields):
            if table == "pledges":
                return {"id": "pledge-1", **(payload or {})}
            if table == "sources":
                return {"id": "source-1", **(payload or {})}
            self.fail(f"unexpected table for optional insert: {table}")

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_insert_pledge_tree"),
            patch.object(app_module, "_fetch_pledge_nodes", return_value=self._created_nodes()),
            patch.object(app_module, "_supabase_insert_with_optional_fields", side_effect=fake_insert_with_optional_fields),
            patch.object(routes_pledge_module, "_find_existing_source_by_url", return_value=None),
            patch.object(app_module, "_delete_pledge_tree") as delete_tree_mock,
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "Pledge title",
                    "raw_text": "Goal\nMethod\n- Action",
                    "category": "economy",
                    "sources": [
                        {
                            "title": "Source 1",
                            "url": "https://example.com/source",
                            "link_scope": "goal",
                            "target_path": "g:99",
                        }
                    ],
                },
            )

        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json() or {}
        self.assertIn("target_path", payload.get("error", ""))
        delete_tree_mock.assert_called_once_with("pledge-1")
        delete_calls = [c for c in supabase_calls if c[0] == "DELETE" and c[1] == "pledges"]
        self.assertEqual(len(delete_calls), 1)
        self.assertEqual(delete_calls[0][2].get("id"), "eq.pledge-1")

    def test_api_pledges_requires_all_goals_when_goal_scope_used(self):
        self._set_login_session()

        def fake_insert_with_optional_fields(table, payload, optional_fields):
            if table == "pledges":
                return {"id": "pledge-1", **(payload or {})}
            if table == "sources":
                return {"id": "source-1", **(payload or {})}
            self.fail(f"unexpected table for optional insert: {table}")

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_insert_pledge_tree"),
            patch.object(
                app_module,
                "_fetch_pledge_nodes",
                return_value=[
                    {
                        "id": "goal-1",
                        "pledge_id": "pledge-1",
                        "name": "goal",
                        "content": "Goal 1",
                        "sort_order": 1,
                        "parent_id": None,
                        "is_leaf": False,
                        "created_at": "2026-03-15T00:00:00Z",
                    },
                    {
                        "id": "goal-2",
                        "pledge_id": "pledge-1",
                        "name": "goal",
                        "content": "Goal 2",
                        "sort_order": 2,
                        "parent_id": None,
                        "is_leaf": False,
                        "created_at": "2026-03-15T00:00:00Z",
                    },
                ],
            ),
            patch.object(app_module, "_delete_pledge_tree") as delete_tree_mock,
            patch.object(app_module, "_supabase_request", return_value=[]),
            patch.object(routes_pledge_module, "_find_existing_source_by_url", return_value=None),
            patch.object(app_module, "_supabase_insert_with_optional_fields", side_effect=fake_insert_with_optional_fields),
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "Pledge title",
                    "raw_text": "Goal\nMethod\n- Action",
                    "category": "economy",
                    "sources": [
                        {
                            "title": "Source 1",
                            "url": "https://example.com/source",
                            "link_scope": "goal",
                            "target_path": "g:1",
                        }
                    ],
                },
            )

        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json() or {}
        self.assertIn("모든 대항목", payload.get("error", ""))
        delete_tree_mock.assert_called_once_with("pledge-1")

    def test_api_pledges_returns_json_when_insert_runtime_error_occurs(self):
        self._set_login_session()

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_supabase_insert_with_optional_fields", side_effect=RuntimeError("timeout")),
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "Pledge title",
                    "raw_text": "Goal\nMethod\n- Action",
                    "category": "economy",
                    "sources": [
                        {
                            "title": "Source 1",
                            "url": "https://example.com/source",
                            "link_scope": "pledge",
                        }
                    ],
                },
            )

        self.assertEqual(resp.status_code, 503)
        payload = resp.get_json() or {}
        self.assertIn("error", payload)

    def test_api_pledges_falls_back_to_goal_link_when_pledge_scope_requires_node_link(self):
        self._set_login_session()

        def fake_insert_with_optional_fields(table, payload, optional_fields):
            if table == "pledges":
                return {"id": "pledge-1", **(payload or {})}
            if table == "sources":
                return {"id": "source-1", **(payload or {})}
            self.fail(f"unexpected table for optional insert: {table}")

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_insert_pledge_tree"),
            patch.object(app_module, "_fetch_pledge_nodes", return_value=self._created_nodes()),
            patch.object(routes_pledge_module, "_find_existing_source_by_url", return_value=None),
            patch.object(app_module, "_supabase_insert_with_optional_fields", side_effect=fake_insert_with_optional_fields),
            patch.object(
                routes_pledge_module,
                "_upsert_pledge_source_link",
                side_effect=RuntimeError('null value in column "pledge_node_id" violates not-null constraint'),
            ),
            patch.object(
                routes_pledge_module,
                "_upsert_pledge_node_source_link",
                return_value={"id": 404, "pledge_node_id": "goal-1", "pledge_id": "pledge-1"},
            ) as fallback_upsert_mock,
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "Fallback Test",
                    "raw_text": "Goal\nMethod\n- Action",
                    "category": "economy",
                    "sources": [
                        {
                            "title": "Source 1",
                            "url": "https://example.com/source",
                            "link_scope": "pledge",
                        }
                    ],
                },
            )

        self.assertEqual(resp.status_code, 201)
        payload = resp.get_json() or {}
        self.assertTrue(payload.get("ok"))
        fallback_kwargs = fallback_upsert_mock.call_args.kwargs
        self.assertEqual(fallback_kwargs.get("pledge_node_id"), "goal-1")
        self.assertEqual(fallback_kwargs.get("pledge_id"), "pledge-1")

    def test_build_goal_target_map_supports_localized_goal_names_with_node_type(self):
        goal_map = routes_pledge_module._build_pledge_goal_target_map(
            [
                {
                    "id": "goal-kor-1",
                    "pledge_id": "pledge-1",
                    "name": "목표",
                    "node_type": "goal",
                    "content": "목표",
                    "sort_order": 1,
                    "parent_id": None,
                    "is_leaf": False,
                    "created_at": "2026-03-15T00:00:00Z",
                },
                {
                    "id": "goal-kor-2",
                    "pledge_id": "pledge-1",
                    "name": "이행 방법",
                    "node_type": "goal",
                    "content": "이행 방법",
                    "sort_order": 2,
                    "parent_id": None,
                    "is_leaf": False,
                    "created_at": "2026-03-15T00:00:00Z",
                },
            ]
        )

        self.assertEqual((goal_map.get("g:1") or {}).get("node_id"), "goal-kor-1")
        self.assertEqual((goal_map.get("g:2") or {}).get("node_id"), "goal-kor-2")


if __name__ == "__main__":
    unittest.main()
