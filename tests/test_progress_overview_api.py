import os
import unittest
from unittest.mock import patch


os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import app as app_module


class ProgressOverviewApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_overview_handles_large_candidate_elections_with_paging(self):
        calls = []

        candidate_elections = []
        elections = []
        for idx in range(1, 191):
            candidate_elections.append(
                {
                    "id": f"ce-{idx}",
                    "candidate_id": f"c-{idx}",
                    "election_id": str(idx),
                    "party": "정당",
                    "result": "후보",
                    "candidate_number": idx,
                    "created_at": f"2026-01-{(idx % 28) + 1:02d}T00:00:00Z",
                }
            )
            elections.append(
                {
                    "id": str(idx),
                    "election_type": "대통령",
                    "title": idx,
                    "election_date": f"202{idx % 10}-01-01",
                }
            )

        def fake_supabase_request(method, table, query_params=None, payload=None, extra_headers=None):
            calls.append((method, table, dict(query_params or {})))
            if method != "GET":
                return []
            if table == "candidates":
                return []
            if table == "candidate_elections":
                return candidate_elections
            if table == "elections":
                return elections
            if table == "pledges":
                return []
            if table == "pledge_nodes":
                return []
            if table == "pledge_node_progress":
                return []
            return []

        with patch.object(app_module, "_supabase_request", side_effect=fake_supabase_request):
            resp = self.client.get("/api/progress-overview?limit=2&offset=0")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        self.assertEqual(payload.get("total"), 190)
        self.assertEqual(len(payload.get("rows") or []), 2)

        election_calls = [c for c in calls if c[1] == "elections"]
        self.assertGreaterEqual(len(election_calls), 2)

    def test_overview_runtime_error_maps_to_503(self):
        with patch.object(app_module, "_supabase_request", side_effect=RuntimeError("Supabase request failed (network): timeout")):
            resp = self.client.get("/api/progress-overview")

        self.assertEqual(resp.status_code, 503)
        payload = resp.get_json() or {}
        self.assertIn("연결 문제", payload.get("error", ""))


if __name__ == "__main__":
    unittest.main()
