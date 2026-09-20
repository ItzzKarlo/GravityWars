import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from types import SimpleNamespace

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth.store import AccessStore, InvitationUsed
from app.config import Settings
from app.main import create_app


ORIGIN = "http://testserver"
PASSWORD = "correct horse battery staple"


class TestFriendsOnlyAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = [1_800_000_000.0]
        self.settings = Settings(
            database_path=f"{self.temp.name}/access.sqlite3",
            admin_password_hash=PasswordHasher(
                time_cost=1, memory_cost=8 * 1024, parallelism=1
            ).hash(PASSWORD),
            allowed_origins=(ORIGIN,),
            invite_seconds=1800,
            gravity_min_seconds=120,
            gravity_max_seconds=120,
        )
        self.store = AccessStore(self.settings, clock=lambda: self.now[0])
        self.app = create_app(self.settings, self.store)
        self.admin = TestClient(self.app)
        self.admin.__enter__()

    def tearDown(self):
        self.admin.__exit__(None, None, None)
        self.temp.cleanup()

    def csrf_headers(self, client):
        return {
            "origin": ORIGIN,
            "x-csrf-token": client.cookies.get("gw_csrf"),
        }

    def login(self, client=None):
        client = client or self.admin
        response = client.post(
            "/api/auth/login",
            json={"username": "ADMIN", "password": PASSWORD},
            headers={"origin": ORIGIN},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(client.cookies.get("gw_session"))
        return client

    def create_lobby(self):
        self.login()
        response = self.admin.post(
            "/api/lobbies", headers=self.csrf_headers(self.admin)
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def redeem(self, secret):
        client = TestClient(self.app)
        client.__enter__()
        response = client.post(
            "/api/invitations/redeem",
            json={"secret": secret},
            headers={"origin": ORIGIN},
        )
        return client, response

    def test_unauthenticated_cannot_create_join_read_or_websocket(self):
        self.assertEqual(self.admin.post("/api/lobbies").status_code, 401)
        self.assertEqual(
            self.admin.post("/api/lobbies/join", json={"code": "123456"}).status_code,
            401,
        )
        self.assertEqual(self.admin.get("/api/lobbies/anything").status_code, 403)
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.admin.websocket_connect(
                "/ws/lobbies/anything", headers={"origin": ORIGIN}
            ):
                pass
        self.assertEqual(caught.exception.code, 4403)
        oversized = self.admin.post(
            "/api/auth/login",
            content=(b"x" * 9000 for _ in range(2)),
            headers={
                "origin": ORIGIN,
                "content-type": "application/json",
            },
        )
        self.assertEqual(oversized.status_code, 413)

    def test_login_origin_csrf_logout_and_rate_limit(self):
        self.assertEqual(
            self.admin.post(
                "/api/auth/login",
                json={"username": "ADMIN", "password": PASSWORD},
            ).status_code,
            403,
        )
        self.login()
        self.assertEqual(self.admin.post("/api/lobbies").status_code, 403)
        self.assertEqual(
            self.admin.post(
                "/api/auth/logout", headers=self.csrf_headers(self.admin)
            ).status_code,
            200,
        )
        self.assertFalse(
            self.admin.get("/api/auth/session").json()["authenticated"]
        )
        for _ in range(4):
            denied = self.admin.post(
                "/api/auth/login",
                json={"username": "ADMIN", "password": "wrong password"},
                headers={"origin": ORIGIN},
            )
            self.assertEqual(denied.status_code, 401)
        limited = self.admin.post(
            "/api/auth/login",
            json={"username": "ADMIN", "password": "wrong password"},
            headers={"origin": ORIGIN},
        )
        self.assertEqual(limited.status_code, 429)

    def test_create_generates_exactly_three_unique_high_entropy_invites(self):
        hosted = self.create_lobby()
        invites = hosted["invitations"]
        self.assertEqual(len(invites), 3)
        self.assertEqual({item["slot"] for item in invites}, {1, 2, 3})
        secrets = {item["secret"] for item in invites}
        self.assertEqual(len(secrets), 3)
        self.assertTrue(all(len(item) >= 40 for item in secrets))
        with open(self.settings.database_path, "rb") as database_file:
            database_text = database_file.read().decode(
                "latin1", errors="ignore"
            )
        self.assertTrue(all(item not in database_text for item in secrets))
        metadata = self.admin.get(
            f"/api/lobbies/{hosted['lobby']['id']}/invitations"
        ).json()["invitations"]
        self.assertTrue(all("secret" not in item for item in metadata))

    def test_preview_get_does_not_redeem(self):
        hosted = self.create_lobby()
        secret = hosted["invitations"][0]["secret"]
        response = self.admin.get("/api/invitations/redeem")
        self.assertEqual(response.status_code, 405)
        guest, redeemed = self.redeem(secret)
        try:
            self.assertEqual(redeemed.status_code, 200, redeemed.text)
        finally:
            guest.__exit__(None, None, None)

    def test_used_revoked_expired_and_unknown_invites_fail_safely(self):
        hosted = self.create_lobby()
        first, second, third = hosted["invitations"]
        guest, redeemed = self.redeem(first["secret"])
        self.assertEqual(redeemed.status_code, 200)
        guest.__exit__(None, None, None)
        duplicate, used = self.redeem(first["secret"])
        self.assertEqual(used.status_code, 409)
        duplicate.__exit__(None, None, None)
        revoked = self.admin.post(
            f"/api/lobbies/{hosted['lobby']['id']}/invitations/{second['id']}/revoke",
            headers=self.csrf_headers(self.admin),
        )
        self.assertEqual(revoked.status_code, 200)
        client, denied = self.redeem(second["secret"])
        self.assertEqual(denied.status_code, 410)
        client.__exit__(None, None, None)
        self.now[0] += 1801
        client, expired = self.redeem(third["secret"])
        self.assertEqual(expired.status_code, 410)
        client.__exit__(None, None, None)
        client, unknown = self.redeem("x" * 64)
        self.assertEqual(unknown.status_code, 404)
        client.__exit__(None, None, None)

    def test_concurrent_redemption_only_admits_one_player(self):
        hosted = self.create_lobby()
        secret = hosted["invitations"][0]["secret"]

        @dataclass
        class Joined:
            player_id: str

        calls = []

        def attempt(number):
            try:
                self.store.redeem_invitation(
                    secret,
                    lambda _lobby: calls.append(number) or Joined(f"p{number}"),
                )
                return "ok"
            except InvitationUsed:
                return "used"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [1, 2]))
        self.assertEqual(sorted(results), ["ok", "used"])
        self.assertEqual(len(calls), 1)

    def test_guest_only_accesses_authorized_lobby_and_cannot_create(self):
        first = self.create_lobby()
        second_response = self.admin.post(
            "/api/lobbies", headers=self.csrf_headers(self.admin)
        )
        self.assertEqual(second_response.status_code, 200)
        second = second_response.json()
        guest, response = self.redeem(first["invitations"][0]["secret"])
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(guest.post("/api/lobbies").status_code, 403)
            self.assertEqual(
                guest.post(
                    "/api/lobbies/join", json={"code": first["lobby"]["pin"]}
                ).status_code,
                403,
            )
            self.assertEqual(
                guest.get(f"/api/lobbies/{first['lobby']['id']}").status_code,
                200,
            )
            self.assertEqual(
                guest.get(f"/api/lobbies/{second['lobby']['id']}").status_code,
                403,
            )
            self.assertEqual(
                guest.get(
                    f"/api/lobbies/{first['lobby']['id']}/invitations"
                ).status_code,
                403,
            )
            self.assertEqual(
                guest.post(
                    f"/api/lobbies/{first['lobby']['id']}/invitations/"
                    f"{first['invitations'][1]['id']}/revoke",
                    headers=self.csrf_headers(guest),
                ).status_code,
                403,
            )
            with self.assertRaises(WebSocketDisconnect) as rejected:
                with guest.websocket_connect(
                    f"/ws/lobbies/{first['lobby']['id']}",
                    headers={"origin": "https://evil.example"},
                ):
                    pass
            self.assertEqual(rejected.exception.code, 4403)
        finally:
            guest.__exit__(None, None, None)

    def test_refresh_disconnect_reconnect_and_explicit_leave(self):
        hosted = self.create_lobby()
        guest, redeemed = self.redeem(hosted["invitations"][0]["secret"])
        self.assertEqual(redeemed.status_code, 200)
        lobby_id = hosted["lobby"]["id"]
        token = redeemed.json()["token"]
        with guest.websocket_connect(
            f"/ws/lobbies/{lobby_id}", headers={"origin": ORIGIN}
        ) as socket:
            socket.send_json({"type": "auth", "token": token})
            self.assertEqual(socket.receive_json()["type"], "welcome")
            socket.receive_json()
        with guest.websocket_connect(
            f"/ws/lobbies/{lobby_id}", headers={"origin": ORIGIN}
        ) as socket:
            socket.send_json({"type": "auth", "token": token})
            self.assertEqual(socket.receive_json()["type"], "welcome")
            socket.receive_json()
        credentials = guest.get(f"/api/lobbies/{lobby_id}/credentials")
        self.assertEqual(credentials.status_code, 200)
        left = guest.post(
            f"/api/lobbies/{lobby_id}/leave", headers=self.csrf_headers(guest)
        )
        self.assertEqual(left.status_code, 200)
        self.assertEqual(guest.get(f"/api/lobbies/{lobby_id}").status_code, 403)
        guest.__exit__(None, None, None)

    def test_revocation_closes_existing_websocket(self):
        hosted = self.create_lobby()
        guest, redeemed = self.redeem(hosted["invitations"][0]["secret"])
        lobby_id = hosted["lobby"]["id"]
        player_id = redeemed.json()["player_id"]
        token = redeemed.json()["token"]
        try:
            with guest.websocket_connect(
                f"/ws/lobbies/{lobby_id}", headers={"origin": ORIGIN}
            ) as socket:
                socket.send_json({"type": "auth", "token": token})
                socket.receive_json()
                socket.receive_json()
                revoked = self.admin.post(
                    f"/api/lobbies/{lobby_id}/players/{player_id}/revoke",
                    headers=self.csrf_headers(self.admin),
                )
                self.assertEqual(revoked.status_code, 200, revoked.text)
                with self.assertRaises(WebSocketDisconnect) as closed:
                    socket.receive_json()
                self.assertEqual(closed.exception.code, 4403)
            self.assertEqual(
                guest.get(f"/api/lobbies/{lobby_id}").status_code, 403
            )
        finally:
            guest.__exit__(None, None, None)

    def test_four_sessions_finish_real_game_and_hands_stay_private(self):
        hosted = self.create_lobby()
        lobby_id = hosted["lobby"]["id"]
        access_tokens = [self.admin.cookies.get("gw_session")]
        tokens = [hosted["token"]]
        for invitation in hosted["invitations"]:
            joined_token = []

            def join(invited_lobby_id):
                lobby, token = self.app.state.lobbies.join_lobby(
                    invited_lobby_id
                )
                joined_token.append(token)
                player = self.app.state.lobbies.authenticate(lobby.id, token)
                return SimpleNamespace(player_id=player.id)

            session, _ = self.store.redeem_invitation(
                invitation["secret"], join
            )
            access_tokens.append(session.token)
            tokens.append(joined_token[0])
        sockets = []
        try:
            for access_token, token in zip(access_tokens, tokens):
                socket = self.admin.websocket_connect(
                    f"/ws/lobbies/{lobby_id}",
                    headers={
                        "origin": ORIGIN,
                        "cookie": f"gw_session={access_token}",
                    },
                ).__enter__()
                sockets.append(socket)
                socket.send_json({"type": "auth", "token": token})
                self.assertEqual(socket.receive_json()["type"], "welcome")
                socket.receive_json()
            for index, socket in enumerate(sockets):
                for _ in range(3 - index):
                    socket.receive_json()
            sockets[0].send_json({"type": "start"})
            hands = []
            for socket in sockets:
                public = socket.receive_json()
                private = socket.receive_json()
                self.assertEqual(public["type"], "state")
                self.assertNotIn("jokers", str(public["lobby"]))
                self.assertEqual(private["type"], "hand")
                self.assertEqual(len(private["jokers"]), 2)
                hands.append(private["jokers"])
            lanes = [0, 6, 6, 6, 1, 5, 5, 5, 2, 4, 4, 4, 3]
            final = None
            for turn, lane in enumerate(lanes):
                sockets[turn % 4].send_json({"type": "drop", "lane": lane})
                states = [socket.receive_json() for socket in sockets]
                self.assertTrue(all(message["type"] == "state" for message in states))
                final = states[0]["lobby"]
            self.assertEqual(final["status"], "finished", final)
            self.assertEqual(final["winner_ids"], [hosted["player_id"]])
            self.assertEqual(len(hands), 4)
            lobby = self.app.state.lobbies.get_lobby(lobby_id)
            self.assertEqual(
                hands,
                [[joker.value for joker in player.jokers]
                 for player in lobby.game.players],
            )
        finally:
            for socket in sockets:
                try:
                    socket.__exit__(None, None, None)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
