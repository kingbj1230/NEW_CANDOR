import os
import unittest
from unittest.mock import patch


os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import app as app_module
import routes_misc as routes_misc_module


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
            "title": "공약 제목",
            "raw_text": "□ 목표\n○ 약속\n- 세부 항목",
            "category": "경제",
            "status": "active",
        }

    @staticmethod
    def _created_nodes():
        return [
            {
                "id": "goal-1",
                "pledge_id": "pledge-1",
                "name": "goal",
                "content": "목표",
                "sort_order": 1,
                "parent_id": None,
                "is_leaf": False,
                "created_at": "2026-03-15T00:00:00Z",
            },
            {
                "id": "promise-1",
                "pledge_id": "pledge-1",
                "name": "promise",
                "content": "약속",
                "sort_order": 1,
                "parent_id": "goal-1",
                "is_leaf": False,
                "created_at": "2026-03-15T00:00:00Z",
            },
            {
                "id": "item-1",
                "pledge_id": "pledge-1",
                "name": "item",
                "content": "세부 항목",
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

    def test_api_pledges_saves_source_with_target_path(self):
        self._set_login_session()

        def fake_insert_with_optional_fields(table, payload, optional_fields):
            if table == "sources":
                return {"id": "source-1", **(payload or {})}
            self.fail(f"unexpected table for optional insert: {table}")

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_supabase_insert_returning", return_value={"id": "pledge-1"}),
            patch.object(app_module, "_insert_pledge_tree"),
            patch.object(app_module, "_fetch_pledge_nodes", return_value=self._created_nodes()),
            patch.object(app_module, "_resolve_default_source_target_node_id", return_value="goal-1"),
            patch.object(routes_misc_module, "_find_existing_source_by_url", return_value=None),
            patch.object(app_module, "_supabase_insert_with_optional_fields", side_effect=fake_insert_with_optional_fields),
            patch.object(routes_misc_module, "_upsert_pledge_node_source_link", return_value={"id": 101, "pledge_node_id": "goal-1"}) as upsert_mock,
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "공약 제목",
                    "raw_text": "□ 목표\n○ 약속\n- 세부 항목",
                    "category": "경제",
                    "sources": [
                        {
                            "title": "공식 공약집",
                            "url": "https://example.com/manifesto",
                            "source_type": "정부",
                            "source_role": "origin",
                            "link_scope": "goal",
                            "target_path": "g:1",
                            "note": "핵심 출처",
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

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_supabase_insert_returning", return_value={"id": "pledge-1"}),
            patch.object(app_module, "_insert_pledge_tree"),
            patch.object(app_module, "_fetch_pledge_nodes", return_value=self._created_nodes()),
            patch.object(app_module, "_resolve_default_source_target_node_id", return_value="goal-1"),
            patch.object(app_module, "_supabase_insert_with_optional_fields", return_value={"id": "source-1"}),
            patch.object(routes_misc_module, "_find_existing_source_by_url", return_value=None),
            patch.object(app_module, "_delete_pledge_tree") as delete_tree_mock,
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "공약 제목",
                    "raw_text": "□ 목표\n○ 약속\n- 세부 항목",
                    "category": "경제",
                    "sources": [
                        {
                            "title": "출처 1",
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

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_supabase_insert_returning", return_value={"id": "pledge-1"}),
            patch.object(app_module, "_insert_pledge_tree"),
            patch.object(
                app_module,
                "_fetch_pledge_nodes",
                return_value=[
                    {"id": "goal-1", "pledge_id": "pledge-1", "name": "goal", "content": "목표 1", "sort_order": 1, "parent_id": None, "is_leaf": False, "created_at": "2026-03-15T00:00:00Z"},
                    {"id": "goal-2", "pledge_id": "pledge-1", "name": "goal", "content": "목표 2", "sort_order": 2, "parent_id": None, "is_leaf": False, "created_at": "2026-03-15T00:00:00Z"},
                ],
            ),
            patch.object(app_module, "_delete_pledge_tree") as delete_tree_mock,
            patch.object(app_module, "_supabase_request", return_value=[]),
            patch.object(routes_misc_module, "_find_existing_source_by_url", return_value=None),
            patch.object(app_module, "_supabase_insert_with_optional_fields", return_value={"id": "source-1"}),
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "공약 제목",
                    "raw_text": "□ 목표\n○ 약속\n- 세부 항목",
                    "category": "경제",
                    "sources": [
                        {
                            "title": "출처 1",
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

    def test_progress_admin_node_source_upserts_with_resolved_pledge_id(self):
        self._set_login_session()

        with (
            patch.object(app_module, "_resolve_default_source_target_node_id", return_value="node-1"),
            patch.object(app_module, "_get_pledge_node", return_value={"id": "node-1", "pledge_id": "pledge-1"}),
            patch.object(app_module, "_ensure_source_exists", return_value=True),
            patch.object(routes_misc_module, "_upsert_pledge_node_source_link", return_value={"id": 22, "pledge_id": "pledge-1"}) as upsert_mock,
        ):
            resp = self.client.post(
                "/api/progress-admin/node-sources",
                json={
                    "pledge_id": "pledge-1",
                    "link_scope": "node",
                    "source_id": "source-1",
                    "source_role": "reference",
                },
            )

        self.assertEqual(resp.status_code, 201)
        payload = resp.get_json() or {}
        self.assertTrue(payload.get("ok"))
        upsert_kwargs = upsert_mock.call_args.kwargs
        self.assertEqual(upsert_kwargs.get("pledge_node_id"), "node-1")
        self.assertEqual(upsert_kwargs.get("pledge_id"), "pledge-1")
        self.assertEqual(upsert_kwargs.get("source_id"), "source-1")

    def test_progress_admin_node_source_upserts_pledge_scope(self):
        self._set_login_session()

        with (
            patch.object(app_module, "_ensure_source_exists", return_value=True),
            patch.object(app_module, "_get_pledge_row", return_value={"id": "pledge-1"}),
            patch.object(routes_misc_module, "_upsert_pledge_source_link", return_value={"id": 31, "pledge_id": "pledge-1"}) as upsert_mock,
        ):
            resp = self.client.post(
                "/api/progress-admin/node-sources",
                json={
                    "pledge_id": "pledge-1",
                    "link_scope": "pledge",
                    "source_id": "source-1",
                    "source_role": "reference",
                },
            )

        self.assertEqual(resp.status_code, 201)
        payload = resp.get_json() or {}
        self.assertTrue(payload.get("ok"))
        upsert_kwargs = upsert_mock.call_args.kwargs
        self.assertEqual(upsert_kwargs.get("pledge_id"), "pledge-1")
        self.assertEqual(upsert_kwargs.get("source_id"), "source-1")

    def test_api_pledges_returns_json_when_insert_runtime_error_occurs(self):
        self._set_login_session()

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_supabase_insert_returning", side_effect=RuntimeError("timeout")),
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "공약 제목",
                    "raw_text": "목표\n세부 공약\n- 실행 항목",
                    "category": "경제",
                    "sources": [
                        {
                            "title": "출처 1",
                            "url": "https://example.com/source",
                            "link_scope": "pledge",
                        }
                    ],
                },
            )

        self.assertEqual(resp.status_code, 503)
        payload = resp.get_json() or {}
        self.assertIn("error", payload)

    def test_source_library_returns_sources_for_candidate_election(self):
        self._set_login_session()

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method == "GET" and table == "pledges":
                return [
                    {"id": "p-1", "title": "공약 A", "candidate_election_id": "ce-1"},
                    {"id": "p-2", "title": "공약 B", "candidate_election_id": "ce-1"},
                ]
            if method == "GET" and table == "sources":
                return [
                    {
                        "id": "s-1",
                        "title": "공통 출처",
                        "url": "https://example.com/s1",
                        "source_type": "정부",
                        "publisher": "기관",
                        "published_at": "2026-03-01",
                        "summary": "요약",
                        "note": None,
                    }
                ]
            return []

        with (
            patch.object(app_module, "_fetch_candidate_election", return_value={"id": "ce-1"}),
            patch.object(app_module, "_fetch_pledge_source_rows", return_value=[
                {"id": 1, "pledge_id": "p-1", "pledge_node_id": None, "source_id": "s-1", "source_role": "원문출처", "note": None, "created_at": "2026-03-10T00:00:00Z"},
                {"id": 2, "pledge_id": "p-2", "pledge_node_id": "node-1", "source_id": "s-1", "source_role": "참고출처", "note": None, "created_at": "2026-03-11T00:00:00Z"},
            ]),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
        ):
            resp = self.client.get("/api/pledges/source-library?candidate_election_id=ce-1")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        rows = payload.get("rows") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("source_id"), "s-1")
        self.assertEqual(rows[0].get("usage_count"), 2)

    def test_api_pledges_falls_back_to_goal_link_when_pledge_scope_requires_node_link(self):
        self._set_login_session()

        with (
            patch.object(app_module, "_validate_pledge_payload", return_value=self._validated_payload()),
            patch.object(app_module, "_supabase_insert_returning", return_value={"id": "pledge-1"}),
            patch.object(app_module, "_insert_pledge_tree"),
            patch.object(app_module, "_fetch_pledge_nodes", return_value=self._created_nodes()),
            patch.object(routes_misc_module, "_find_existing_source_by_url", return_value=None),
            patch.object(app_module, "_supabase_insert_with_optional_fields", return_value={"id": "source-1"}),
            patch.object(
                routes_misc_module,
                "_upsert_pledge_source_link",
                side_effect=RuntimeError('null value in column "pledge_node_id" violates not-null constraint'),
            ),
            patch.object(
                routes_misc_module,
                "_upsert_pledge_node_source_link",
                return_value={"id": 404, "pledge_node_id": "goal-1", "pledge_id": "pledge-1"},
            ) as fallback_upsert_mock,
        ):
            resp = self.client.post(
                "/api/pledges",
                json={
                    "candidate_election_id": "ce-1",
                    "title": "Fallback Test",
                    "raw_text": "목표\n세부 공약\n- 실행 항목",
                    "category": "경제",
                    "sources": [
                        {
                            "title": "출처 1",
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


    def test_source_library_includes_related_candidate_election_rows(self):
        self._set_login_session()
        seen_pledge_filter = {"value": ""}

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method == "GET" and table == "candidate_elections":
                return [
                    {"id": "ce-1", "candidate_id": "cand-1", "election_id": "el-1"},
                    {"id": "ce-2", "candidate_id": "cand-1", "election_id": "el-1"},
                ]
            if method == "GET" and table == "pledges":
                seen_pledge_filter["value"] = str((query_params or {}).get("candidate_election_id") or "")
                return [
                    {"id": "p-legacy", "title": "기존 공약", "candidate_election_id": "ce-2"},
                ]
            if method == "GET" and table == "pledge_nodes":
                return []
            if method == "GET" and table == "sources":
                return [
                    {
                        "id": "s-legacy",
                        "title": "기존 출처",
                        "url": "https://example.com/legacy",
                        "source_type": "정부",
                        "publisher": "기관",
                        "published_at": "2026-03-10",
                        "summary": "요약",
                        "note": None,
                    }
                ]
            return []

        with (
            patch.object(
                app_module,
                "_fetch_candidate_election",
                return_value={"id": "ce-1", "candidate_id": "cand-1", "election_id": "el-1"},
            ),
            patch.object(
                app_module,
                "_fetch_pledge_source_rows",
                return_value=[
                    {
                        "id": 101,
                        "pledge_id": "p-legacy",
                        "pledge_node_id": None,
                        "source_id": "s-legacy",
                        "source_role": "참고출처",
                        "note": None,
                        "created_at": "2026-03-11T00:00:00Z",
                    }
                ],
            ),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
        ):
            resp = self.client.get("/api/pledges/source-library?candidate_election_id=ce-1")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        rows = payload.get("rows") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("source_id"), "s-legacy")
        links = rows[0].get("links") or []
        self.assertEqual((links[0] or {}).get("pledge_id"), "p-legacy")
        self.assertEqual((links[0] or {}).get("pledge_title"), "기존 공약")
        self.assertIn("ce-1", seen_pledge_filter["value"])
        self.assertIn("ce-2", seen_pledge_filter["value"])


if __name__ == "__main__":
    unittest.main()
