import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch


os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("ADMIN_ROLE_RECHECK_SECONDS", "60")

import app as app_module


class AdminSessionCacheTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.ttl = int(getattr(app_module, "ADMIN_ROLE_RECHECK_SECONDS", 60))

    def _set_login_session(
        self,
        user_id="u-1",
        email="u1@example.com",
        *,
        is_admin=None,
        checked_at=None,
        admin_uid=None,
    ):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["email"] = email
            if is_admin is not None:
                sess["is_admin"] = is_admin
            if checked_at is not None:
                sess["is_admin_checked_at"] = checked_at
            if admin_uid is not None:
                sess["is_admin_uid"] = admin_uid

    def test_auth_session_cache_hit_skips_lookup(self):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        self._set_login_session(is_admin=True, checked_at=now_ts, admin_uid="u-1")
        with patch.object(app_module, "_is_admin", side_effect=AssertionError("lookup should not run")):
            resp = self.client.get("/auth/session")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue((resp.get_json() or {}).get("is_admin"))

    def test_read_mode_allows_recent_fallback_when_refresh_fails(self):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        self._set_login_session(
            is_admin=True,
            checked_at=now_ts - (self.ttl + 1),
            admin_uid="u-1",
        )
        with patch.object(app_module, "_is_admin", side_effect=RuntimeError("network down")):
            resp = self.client.get("/auth/session")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue((resp.get_json() or {}).get("is_admin"))

    def test_read_mode_rejects_too_old_fallback(self):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        self._set_login_session(
            is_admin=True,
            checked_at=now_ts - (self.ttl * 2 + 1),
            admin_uid="u-1",
        )
        with patch.object(app_module, "_is_admin", side_effect=RuntimeError("network down")):
            resp = self.client.get("/auth/session")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse((resp.get_json() or {}).get("is_admin"))

    def test_strict_guard_denies_when_refresh_fails_after_expiry(self):
        now_ts = int(datetime.now(timezone.utc).timestamp())
        self._set_login_session(
            user_id="admin-1",
            email="admin@example.com",
            is_admin=True,
            checked_at=now_ts - (self.ttl + 1),
            admin_uid="admin-1",
        )
        with patch.object(app_module, "_is_admin", side_effect=RuntimeError("network down")):
            resp = self.client.delete("/api/admin/progress-records/pr-1")
        self.assertEqual(resp.status_code, 403)

    def test_logout_clears_admin_cache_keys(self):
        self._set_login_session(is_admin=True, checked_at=123456, admin_uid="u-1")
        resp = self.client.post("/auth/logout")
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("is_admin"))
            self.assertIsNone(sess.get("is_admin_checked_at"))
            self.assertIsNone(sess.get("is_admin_uid"))

    def test_login_replaces_old_admin_cache_with_new_uid(self):
        self._set_login_session(
            user_id="old-user",
            email="old@example.com",
            is_admin=True,
            checked_at=1,
            admin_uid="old-user",
        )
        with (
            patch.object(
                app_module,
                "_fetch_supabase_user",
                return_value={"id": "new-user", "email": "new@example.com"},
            ),
            patch.object(app_module, "ensure_user_profile"),
            patch.object(app_module, "_is_admin", return_value=False) as is_admin_mock,
        ):
            resp = self.client.post("/auth/login", json={"access_token": "token-1"})
        self.assertEqual(resp.status_code, 200)
        is_admin_mock.assert_called_once_with("new-user")
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_id"), "new-user")
            self.assertEqual(sess.get("is_admin_uid"), "new-user")
            self.assertIn("is_admin_checked_at", sess)


if __name__ == "__main__":
    unittest.main()
