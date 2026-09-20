"""Invitation expiry must not eject an active friend; idle access still expires."""

import tempfile
import unittest

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.auth.store import AccessStore
from app.config import Settings
from app.main import create_app


class GuestSessionLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = [1_800_000_000.0]
        self.settings = Settings(
            database_path=f"{self.temp.name}/access.sqlite3",
            admin_password_hash=PasswordHasher(
                time_cost=1, memory_cost=8 * 1024, parallelism=1
            ).hash("private-test-password"),
            allowed_origins=("http://testserver",),
            guest_session_seconds=60,
            invite_seconds=30,
        )
        self.store = AccessStore(self.settings, clock=lambda: self.now[0])
        self.app = create_app(self.settings, self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_active_guest_cookie_has_no_fixed_expiry_but_idle_guest_expires(self):
        with TestClient(self.app) as admin, TestClient(self.app) as guest:
            login = admin.post(
                "/api/auth/login",
                json={"username": "admin", "password": "private-test-password"},
                headers={"origin": "http://testserver"},
            )
            self.assertEqual(login.status_code, 200, login.text)
            hosted = admin.post(
                "/api/lobbies",
                headers={
                    "origin": "http://testserver",
                    "x-csrf-token": admin.cookies.get("gw_csrf"),
                },
            )
            self.assertEqual(hosted.status_code, 200, hosted.text)
            lobby = hosted.json()
            joined = guest.post(
                "/api/invitations/redeem",
                json={"secret": lobby["invitations"][0]["secret"]},
                headers={"origin": "http://testserver"},
            )
            self.assertEqual(joined.status_code, 200, joined.text)
            guest_cookies = joined.headers.get_list("set-cookie")
            self.assertTrue(any(cookie.startswith("gw_session=") for cookie in guest_cookies))
            self.assertTrue(any("httponly" in cookie.lower() for cookie in guest_cookies))
            self.assertTrue(all("max-age=" not in cookie.lower() for cookie in guest_cookies))

            self.now[0] += 31  # The *invite* has expired, not this player.
            self.assertEqual(guest.get(f"/api/lobbies/{lobby['lobby']['id']}").status_code, 200)
            self.now[0] += 50  # Over the initial 60-second guest deadline.
            self.assertTrue(guest.get("/api/auth/session").json()["authenticated"])
            self.now[0] += 61  # No activity beyond the sliding 60-second window.
            self.assertFalse(guest.get("/api/auth/session").json()["authenticated"])
            self.assertEqual(guest.get(f"/api/lobbies/{lobby['lobby']['id']}").status_code, 403)


if __name__ == "__main__":
    unittest.main()
