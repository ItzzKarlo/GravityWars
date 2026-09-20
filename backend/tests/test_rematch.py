"""Regression tests for host-only rematches with the original invited crew."""

import tempfile
import unittest

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.auth.store import AccessStore
from app.config import Settings
from app.game.models import GameStatus, PlayerColor
from app.main import create_app


ORIGIN = "http://testserver"


class RematchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = [1_800_000_000.0]
        settings = Settings(
            database_path=f"{self.temp.name}/access.sqlite3",
            admin_password_hash=PasswordHasher(
                time_cost=1, memory_cost=8 * 1024, parallelism=1
            ).hash("private-test-password"),
            allowed_origins=(ORIGIN,),
            gravity_min_seconds=120,
            gravity_max_seconds=120,
        )
        self.store = AccessStore(settings, clock=lambda: self.now[0])
        self.app = create_app(settings, self.store)
        self.admin = TestClient(self.app)
        self.admin.__enter__()
        login = self.admin.post(
            "/api/auth/login",
            json={"username": "admin", "password": "private-test-password"},
            headers={"origin": ORIGIN},
        )
        self.assertEqual(login.status_code, 200, login.text)
        hosted = self.admin.post(
            "/api/lobbies",
            headers={
                "origin": ORIGIN,
                "x-csrf-token": self.admin.cookies.get("gw_csrf"),
            },
        )
        self.assertEqual(hosted.status_code, 200, hosted.text)
        self.hosted = hosted.json()
        self.lobby_id = self.hosted["lobby"]["id"]
        self.clients = [self.admin]
        self.tokens = [self.hosted["token"]]
        for invitation in self.hosted["invitations"]:
            guest = TestClient(self.app)
            guest.__enter__()
            redeemed = guest.post(
                "/api/invitations/redeem",
                json={"secret": invitation["secret"]},
                headers={"origin": ORIGIN},
            )
            self.assertEqual(redeemed.status_code, 200, redeemed.text)
            self.clients.append(guest)
            self.tokens.append(redeemed.json()["token"])

    def tearDown(self):
        for client in reversed(self.clients):
            client.__exit__(None, None, None)
        self.temp.cleanup()

    def test_only_host_replays_with_original_players_after_invites_expire(self):
        sockets = []
        try:
            for index, (client, token) in enumerate(zip(self.clients, self.tokens)):
                socket = client.websocket_connect(
                    f"/ws/lobbies/{self.lobby_id}",
                    headers={"origin": ORIGIN},
                ).__enter__()
                sockets.append(socket)
                socket.send_json({"type": "auth", "token": token})
                self.assertEqual(socket.receive_json()["type"], "welcome")
                self.assertEqual(socket.receive_json()["type"], "state")
                for previous in sockets[:-1]:
                    self.assertEqual(previous.receive_json()["type"], "state")

            sockets[0].send_json({"type": "start"})
            for socket in sockets:
                self.assertEqual(socket.receive_json()["type"], "state")
                self.assertEqual(socket.receive_json()["type"], "hand")

            original_ids = [player.id for player in self.app.state.lobbies.get_lobby(self.lobby_id).game.players]
            self.now[0] += 1801  # Unused links are now expired; sessions still work.
            for _ in range(2):
                lobby = self.app.state.lobbies.get_lobby(self.lobby_id)
                lobby.game.status = GameStatus.FINISHED
                lobby.game.board[0][0] = PlayerColor.RED
                lobby.game.winner_ids = [original_ids[0]]
                sockets[1].send_json({"type": "rematch"})
                error = sockets[1].receive_json()
                self.assertEqual(error["type"], "error")
                self.assertIn("Only the host", error["message"])
                self.assertEqual(lobby.game.status, GameStatus.FINISHED)
                sockets[0].send_json({"type": "rematch"})
                for socket in sockets:
                    state = socket.receive_json()
                    hand = socket.receive_json()
                    self.assertEqual(state["type"], "state")
                    self.assertEqual(state["lobby"]["status"], "playing")
                    self.assertEqual(state["lobby"]["winner_ids"], [])
                    self.assertTrue(all(piece is None for row in state["lobby"]["board"] for piece in row))
                    self.assertEqual(hand["type"], "hand")
                    self.assertEqual(len(hand["jokers"]), 2)
                    self.assertNotIn("jokers", str(state["lobby"]))
                lobby = self.app.state.lobbies.get_lobby(self.lobby_id)
                self.assertEqual([player.id for player in lobby.game.players], original_ids)
                for client in self.clients[1:]:
                    self.assertEqual(client.get(f"/api/lobbies/{self.lobby_id}").status_code, 200)
        finally:
            for socket in reversed(sockets):
                try:
                    socket.__exit__(None, None, None)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
