import os
import unittest
from unittest.mock import patch


os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

import app as app_module


class MypageProfileApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def _set_login_session(self, user_id="u-1", email="u1@example.com"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["email"] = email

    def test_get_profile_requires_login(self):
        resp = self.client.get("/api/mypage/profile")
        self.assertEqual(resp.status_code, 401)

    def test_get_profile_returns_profile_payload(self):
        self._set_login_session()
        with (
            patch.object(app_module, "ensure_user_profile"),
            patch.object(
                app_module,
                "_try_fetch_user_profile",
                return_value={
                    "nickname": "candor",
                    "role": "user",
                    "status": "active",
                    "created_at": "2026-03-26T00:00:00Z",
                    "updated_at": "2026-03-26T00:00:00Z",
                    "reputation_score": 7,
                },
            ),
            patch.object(app_module, "_is_admin", return_value=False),
        ):
            resp = self.client.get("/api/mypage/profile")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertFalse(payload.get("is_admin"))
        profile = payload.get("profile") or {}
        self.assertEqual(profile.get("nickname"), "candor")
        self.assertEqual(profile.get("email"), "u1@example.com")
        self.assertEqual(profile.get("status"), "active")

    def test_patch_profile_requires_login(self):
        resp = self.client.patch("/api/mypage/profile", json={"nickname": "newname"})
        self.assertEqual(resp.status_code, 401)

    def test_patch_profile_rejects_blank_or_short_nickname(self):
        self._set_login_session()

        resp_blank = self.client.patch("/api/mypage/profile", json={"nickname": "   "})
        self.assertEqual(resp_blank.status_code, 400)

        resp_short = self.client.patch("/api/mypage/profile", json={"nickname": "a"})
        self.assertEqual(resp_short.status_code, 400)

    def test_patch_profile_falls_back_to_user_id_column(self):
        self._set_login_session(user_id="u-42", email="u42@gmail.com")
        patch_calls = []

        def fake_patch(table, query_params=None, payload=None, optional_fields=None):
            patch_calls.append((table, dict(query_params or {}), dict(payload or {})))
            if "user__id" in (query_params or {}):
                raise RuntimeError('column "user__id" does not exist')
            return payload or {}

        with (
            patch.object(app_module, "ensure_user_profile"),
            patch.object(app_module, "_supabase_patch_with_optional_fields", side_effect=fake_patch),
            patch.object(
                app_module,
                "_try_fetch_user_profile",
                return_value={
                    "nickname": "새닉네임",
                    "role": "user",
                    "status": "active",
                    "created_at": "2026-03-26T00:00:00Z",
                    "updated_at": "2026-03-26T01:00:00Z",
                    "reputation_score": 0,
                },
            ),
            patch.object(app_module, "_is_admin", return_value=False),
        ):
            resp = self.client.patch("/api/mypage/profile", json={"nickname": "새닉네임"})

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json() or {}
        profile = payload.get("profile") or {}
        self.assertEqual(profile.get("nickname"), "새닉네임")
        self.assertEqual(len(patch_calls), 2)
        self.assertIn("user__id", patch_calls[0][1])
        self.assertIn("user_id", patch_calls[1][1])


if __name__ == "__main__":
    unittest.main()
