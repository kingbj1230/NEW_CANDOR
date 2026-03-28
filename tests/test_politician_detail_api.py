import os
import unittest
from unittest.mock import patch


os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import app as app_module
import routes.candidate as candidate_routes


EXPECTED_DETAIL_KEYS = {
    "candidate",
    "pledges",
    "election_history",
    "election_sections",
    "terms",
    "is_admin",
}


class PoliticianDetailApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        with candidate_routes._DETAIL_TREE_POSTPROCESS_CACHE_LOCK:
            candidate_routes._DETAIL_TREE_POSTPROCESS_CACHE.clear()
        with candidate_routes._DETAIL_JOIN_PATH_STATS_LOCK:
            candidate_routes._DETAIL_JOIN_PATH_STATS["fast_path"] = 0
            candidate_routes._DETAIL_JOIN_PATH_STATS["fallback"] = 0
            candidate_routes._DETAIL_JOIN_PATH_STATS["error"] = 0

    def _assert_detail_response_keys(self, payload):
        keys = set((payload or {}).keys())
        self.assertTrue(EXPECTED_DETAIL_KEYS.issubset(keys))
        extra_keys = keys - (EXPECTED_DETAIL_KEYS | {"warning"})
        self.assertEqual(extra_keys, set())

    def test_joined_path_call_tables_and_response_contract(self):
        tables = []

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method == "GET":
                tables.append(table)
            if method != "GET":
                return []

            if table == "candidates":
                return [{"id": "c-1", "name": "Alice", "image": None, "birth_date": "1970-01-01"}]

            if table == "candidate_elections":
                select_text = str((query_params or {}).get("select") or "")
                if "election:elections" in select_text:
                    return [
                        {
                            "id": "ce-1",
                            "candidate_id": "c-1",
                            "election_id": "e-1",
                            "party": "Party A",
                            "result": "win",
                            "is_elect": True,
                            "candidate_number": 1,
                            "created_at": "2026-01-01T00:00:00Z",
                            "election": {
                                "id": "e-1",
                                "election_type": "presidential",
                                "title": "22",
                                "election_date": "2025-03-09",
                            },
                            "pledges": [
                                {
                                    "id": "p-1",
                                    "candidate_election_id": "ce-1",
                                    "sort_order": 1,
                                    "title": "Pledge 1",
                                    "raw_text": "Body",
                                    "category": "economy",
                                    "status": "active",
                                    "created_at": "2026-01-02T00:00:00Z",
                                }
                            ],
                        }
                    ]
                return []

            if table == "terms":
                return [
                    {
                        "id": "t-1",
                        "candidate_id": "c-1",
                        "election_id": "e-1",
                        "position": "President",
                        "term_start": "2025-05-10",
                        "term_end": "2030-05-09",
                        "created_at": "2025-05-10T00:00:00Z",
                    }
                ]

            if table in {"pledges", "elections"}:
                raise AssertionError(f"joined path should not call {table}")

            return []

        with (
            patch.object(app_module, "_session_is_admin", return_value=False),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
            patch.object(app_module, "_attach_pledge_tree_rows", side_effect=lambda rows: rows),
        ):
            resp = self.client.get("/api/politicians/c-1")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        self._assert_detail_response_keys(payload)
        self.assertEqual([t for t in tables], ["candidates", "candidate_elections", "terms"])
        print(f"joined path tables: {tables}")

    def test_joined_path_applies_public_filter(self):
        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method != "GET":
                return []
            if table == "candidates":
                return [{"id": "c-1", "name": "Alice", "image": None}]
            if table == "candidate_elections":
                return [
                    {
                        "id": "ce-1",
                        "candidate_id": "c-1",
                        "election_id": "e-1",
                        "party": "Party A",
                        "result": "run",
                        "is_elect": False,
                        "candidate_number": 2,
                        "created_at": "2026-01-01T00:00:00Z",
                        "election": {"id": "e-1", "election_type": "presidential", "title": "22", "election_date": "2025-03-09"},
                        "pledges": [
                            {
                                "id": "p-active",
                                "candidate_election_id": "ce-1",
                                "sort_order": 1,
                                "title": "A",
                                "raw_text": "A",
                                "category": "x",
                                "status": "active",
                                "created_at": "2026-01-02T00:00:00Z",
                            },
                            {
                                "id": "p-hidden",
                                "candidate_election_id": "ce-1",
                                "sort_order": 2,
                                "title": "H",
                                "raw_text": "H",
                                "category": "x",
                                "status": "hidden",
                                "created_at": "2026-01-03T00:00:00Z",
                            },
                            {
                                "id": "p-deleted",
                                "candidate_election_id": "ce-1",
                                "sort_order": 3,
                                "title": "D",
                                "raw_text": "D",
                                "category": "x",
                                "status": "deleted",
                                "created_at": "2026-01-04T00:00:00Z",
                            },
                        ],
                    }
                ]
            if table == "terms":
                return []
            return []

        with (
            patch.object(app_module, "_session_is_admin", return_value=False),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
            patch.object(app_module, "_attach_pledge_tree_rows", side_effect=lambda rows: rows),
        ):
            resp = self.client.get("/api/politicians/c-1")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        pledge_ids = [str(row.get("id")) for row in (payload.get("pledges") or [])]
        self.assertEqual(pledge_ids, ["p-active"])
        section = (payload.get("election_sections") or [{}])[0]
        self.assertEqual(section.get("pledge_count"), 1)

    def test_joined_path_applies_admin_filter(self):
        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method != "GET":
                return []
            if table == "candidates":
                return [{"id": "c-1", "name": "Alice", "image": None}]
            if table == "candidate_elections":
                return [
                    {
                        "id": "ce-1",
                        "candidate_id": "c-1",
                        "election_id": "e-1",
                        "party": "Party A",
                        "result": "run",
                        "is_elect": False,
                        "candidate_number": 2,
                        "created_at": "2026-01-01T00:00:00Z",
                        "election": {"id": "e-1", "election_type": "presidential", "title": "22", "election_date": "2025-03-09"},
                        "pledges": [
                            {
                                "id": "p-active",
                                "candidate_election_id": "ce-1",
                                "sort_order": 1,
                                "title": "A",
                                "raw_text": "A",
                                "category": "x",
                                "status": "active",
                                "created_at": "2026-01-02T00:00:00Z",
                            },
                            {
                                "id": "p-hidden",
                                "candidate_election_id": "ce-1",
                                "sort_order": 2,
                                "title": "H",
                                "raw_text": "H",
                                "category": "x",
                                "status": "hidden",
                                "created_at": "2026-01-03T00:00:00Z",
                            },
                            {
                                "id": "p-deleted",
                                "candidate_election_id": "ce-1",
                                "sort_order": 3,
                                "title": "D",
                                "raw_text": "D",
                                "category": "x",
                                "status": "deleted",
                                "created_at": "2026-01-04T00:00:00Z",
                            },
                        ],
                    }
                ]
            if table == "terms":
                return []
            return []

        with (
            patch.object(app_module, "_session_is_admin", return_value=True),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
            patch.object(app_module, "_attach_pledge_tree_rows", side_effect=lambda rows: rows),
        ):
            resp = self.client.get("/api/politicians/c-1")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        pledge_ids = [str(row.get("id")) for row in (payload.get("pledges") or [])]
        self.assertEqual(pledge_ids, ["p-active", "p-hidden"])
        section = (payload.get("election_sections") or [{}])[0]
        self.assertEqual(section.get("pledge_count"), 2)

    def test_fallback_path_call_tables_and_response_contract(self):
        tables = []

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method == "GET":
                tables.append(table)
            if method != "GET":
                return []

            if table == "candidates":
                return [{"id": "c-1", "name": "Alice", "image": None, "birth_date": "1970-01-01"}]

            if table == "candidate_elections":
                select_text = str((query_params or {}).get("select") or "")
                if "election:elections" in select_text or "pledges:pledges" in select_text:
                    raise RuntimeError(
                        "Supabase request failed (400): "
                        "{\"code\":\"PGRST200\",\"message\":\"Could not find a relationship in the schema cache\"}"
                    )
                return [
                    {
                        "id": "ce-1",
                        "candidate_id": "c-1",
                        "election_id": "e-1",
                        "party": "Party A",
                        "result": "win",
                        "is_elect": True,
                        "candidate_number": 1,
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ]

            if table == "pledges":
                return [
                    {
                        "id": "p-1",
                        "candidate_election_id": "ce-1",
                        "sort_order": 1,
                        "title": "Pledge 1",
                        "raw_text": "Body",
                        "category": "economy",
                        "status": "active",
                        "created_at": "2026-01-02T00:00:00Z",
                    }
                ]

            if table == "elections":
                return [
                    {
                        "id": "e-1",
                        "election_type": "presidential",
                        "title": "22",
                        "election_date": "2025-03-09",
                    }
                ]

            if table == "terms":
                return []

            return []

        with (
            patch.object(app_module, "_session_is_admin", return_value=False),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
            patch.object(app_module, "_attach_pledge_tree_rows", side_effect=lambda rows: rows),
            patch.object(app_module.app.logger, "debug") as debug_mock,
        ):
            resp = self.client.get("/api/politicians/c-1")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        self._assert_detail_response_keys(payload)
        self.assertIn("pledges", tables)
        self.assertIn("elections", tables)
        self.assertGreaterEqual(tables.count("candidate_elections"), 2)
        self.assertGreaterEqual(debug_mock.call_count, 1)
        print(f"fallback path tables: {tables}")

    def test_latest_fields_prioritize_election_date_and_term_start(self):
        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method != "GET":
                return []
            if table == "candidates":
                return [{"id": "c-1", "name": "Alice", "image": None}]
            if table == "candidate_elections":
                return [
                    {
                        "id": "ce-created",
                        "candidate_id": "c-1",
                        "election_id": "e-created",
                        "party": "Party By CreatedAt",
                        "result": "run",
                        "is_elect": False,
                        "candidate_number": 1,
                        "created_at": "2026-08-01T00:00:00Z",
                        "election": {
                            "id": "e-created",
                            "election_type": "presidential",
                            "title": "21",
                            "election_date": None,
                        },
                        "pledges": [],
                    },
                    {
                        "id": "ce-date",
                        "candidate_id": "c-1",
                        "election_id": "e-date",
                        "party": "Party By ElectionDate",
                        "result": "win",
                        "is_elect": True,
                        "candidate_number": 2,
                        "created_at": "2025-01-01T00:00:00Z",
                        "election": {
                            "id": "e-date",
                            "election_type": "presidential",
                            "title": "22",
                            "election_date": "2027-03-01",
                        },
                        "pledges": [],
                    },
                ]
            if table == "terms":
                return [
                    {
                        "id": "t-created",
                        "candidate_id": "c-1",
                        "election_id": "e-created",
                        "position": "Role By CreatedAt",
                        "term_start": "2020-01-01",
                        "term_end": "2024-12-31",
                        "created_at": "2026-02-01T00:00:00Z",
                    },
                    {
                        "id": "t-start",
                        "candidate_id": "c-1",
                        "election_id": "e-date",
                        "position": "Role By TermStart",
                        "term_start": "2028-01-01",
                        "term_end": "2032-12-31",
                        "created_at": "2024-01-01T00:00:00Z",
                    },
                ]
            return []

        with (
            patch.object(app_module, "_session_is_admin", return_value=False),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
            patch.object(app_module, "_attach_pledge_tree_rows", side_effect=lambda rows: rows),
        ):
            resp = self.client.get("/api/politicians/c-1")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        candidate = payload.get("candidate") or {}
        self.assertEqual(candidate.get("party"), "Party By ElectionDate")
        self.assertEqual(candidate.get("position"), "Role By TermStart")
        self.assertEqual(str(candidate.get("election_year")), "2027")

    def test_tree_postprocess_cache_hit_skips_second_attach(self):
        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method != "GET":
                return []
            if table == "candidates":
                return [{"id": "c-1", "name": "Alice", "image": None}]
            if table == "candidate_elections":
                return [
                    {
                        "id": "ce-1",
                        "candidate_id": "c-1",
                        "election_id": "e-1",
                        "party": "Party A",
                        "result": "win",
                        "is_elect": True,
                        "candidate_number": 1,
                        "created_at": "2026-01-01T00:00:00Z",
                        "election": {"id": "e-1", "election_type": "presidential", "title": "22", "election_date": "2025-03-09"},
                        "pledges": [
                            {
                                "id": "p-1",
                                "candidate_election_id": "ce-1",
                                "sort_order": 1,
                                "title": "P1",
                                "raw_text": "Body",
                                "category": "economy",
                                "status": "active",
                                "created_at": "2026-01-02T00:00:00Z",
                            }
                        ],
                    }
                ]
            if table == "terms":
                return []
            return []

        with (
            patch.object(app_module, "_session_is_admin", return_value=False),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
            patch.object(app_module, "_attach_pledge_tree_rows", side_effect=lambda rows: rows) as attach_mock,
        ):
            first = self.client.get("/api/politicians/c-1")
            second = self.client.get("/api/politicians/c-1")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(attach_mock.call_count, 1)
        self.assertEqual(candidate_routes._DETAIL_JOIN_PATH_STATS.get("fast_path"), 2)

    def test_initial_view_returns_summary_payload_and_skips_tree_attach(self):
        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method != "GET":
                return []
            if table == "candidates":
                return [{"id": "c-1", "name": "Alice", "image": None, "birth_date": "1970-01-01"}]
            if table == "candidate_elections":
                return [
                    {
                        "id": "ce-1",
                        "candidate_id": "c-1",
                        "election_id": "e-1",
                        "party": "Party A",
                        "result": "win",
                        "is_elect": True,
                        "candidate_number": 1,
                        "created_at": "2026-01-01T00:00:00Z",
                        "election": {
                            "id": "e-1",
                            "election_type": "presidential",
                            "title": "22",
                            "election_date": "2025-03-09",
                        },
                        "pledges": [
                            {
                                "id": "p-1",
                                "candidate_election_id": "ce-1",
                                "sort_order": 1,
                                "title": "Pledge 1",
                                "raw_text": "Very long body",
                                "category": "economy",
                                "status": "active",
                                "created_at": "2026-01-02T00:00:00Z",
                            }
                        ],
                    }
                ]
            if table == "terms":
                return [
                    {
                        "id": "t-1",
                        "candidate_id": "c-1",
                        "election_id": "e-1",
                        "position": "President",
                        "term_start": "2025-05-10",
                        "term_end": "2030-05-09",
                        "created_at": "2025-05-10T00:00:00Z",
                    }
                ]
            return []

        with (
            patch.object(app_module, "_session_is_admin", return_value=False),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
            patch.object(app_module, "_attach_pledge_tree_rows", side_effect=lambda rows: rows) as attach_mock,
        ):
            resp = self.client.get("/api/politicians/c-1?view=initial")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        self._assert_detail_response_keys(payload)
        self.assertEqual(attach_mock.call_count, 0)
        self.assertEqual(payload.get("election_history"), [])
        self.assertEqual(payload.get("terms"), [])
        pledge_rows = payload.get("pledges") or []
        self.assertEqual(len(pledge_rows), 1)
        self.assertEqual(
            set((pledge_rows[0] or {}).keys()),
            {"id", "candidate_election_id", "sort_order", "title", "category", "created_at", "status"},
        )
        sections = payload.get("election_sections") or []
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].get("pledges"), [])
        self.assertEqual(sections[0].get("pledge_count"), 1)

    def test_pledge_detail_endpoint_returns_heavy_fields(self):
        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            if method != "GET":
                return []
            if table == "candidate_elections":
                return [{"id": "ce-1"}]
            if table == "pledges":
                return [
                    {
                        "id": "p-1",
                        "candidate_election_id": "ce-1",
                        "sort_order": 1,
                        "title": "Pledge 1",
                        "raw_text": "Body",
                        "category": "economy",
                        "timeline_text": "취임 후 2년",
                        "finance_text": "기존 예산 조정",
                        "parse_type": "type2",
                        "structure_version": 3,
                        "fulfillment_rate": 45,
                        "status": "active",
                        "created_at": "2026-01-02T00:00:00Z",
                    }
                ]
            return []

        def fake_attach(rows):
            next_rows = []
            for row in rows:
                copied = dict(row)
                copied["sources"] = [{"id": "link-1", "source_id": "s-1"}]
                copied["goals"] = [{"id": "g-1", "text": "Goal", "children": []}]
                next_rows.append(copied)
            return next_rows

        with (
            patch.object(app_module, "_session_is_admin", return_value=False),
            patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request),
            patch.object(app_module, "_attach_pledge_tree_rows", side_effect=fake_attach),
        ):
            resp = self.client.get("/api/politicians/c-1/pledges/p-1/detail")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        pledge = payload.get("pledge") or {}
        self.assertEqual(pledge.get("id"), "p-1")
        self.assertEqual(pledge.get("raw_text"), "Body")
        self.assertEqual(pledge.get("timeline_text"), "취임 후 2년")
        self.assertEqual(pledge.get("finance_text"), "기존 예산 조정")
        self.assertEqual(pledge.get("parse_type"), "type2")
        self.assertEqual(pledge.get("structure_version"), 3)
        self.assertEqual(pledge.get("fulfillment_rate"), 45)
        self.assertIsInstance(pledge.get("goals"), list)
        self.assertIsInstance(pledge.get("sources"), list)
        self.assertTrue(payload.get("candidate_id") == "c-1")


if __name__ == "__main__":
    unittest.main()
