
import unittest

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app


class TestAPI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(create_app())
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def create_full_lobby(self):
        response = self.client.post("/api/lobbies")

        self.assertEqual(response.status_code, 200)

        host = response.json()
        lobby_id = host["lobby"]["id"]

        guests = []

        for _ in range(3):
            response = self.client.post(
                "/api/lobbies/join",
                json={"code": lobby_id},
            )

            self.assertEqual(response.status_code, 200)

            guests.append(response.json())

        return host, guests

    def test_health(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "ok",
        )

    def test_create_and_join(self):
        host = self.client.post(
            "/api/lobbies"
        ).json()

        lobby = host["lobby"]

        self.assertEqual(len(lobby["players"]), 1)
        self.assertEqual(len(lobby["pin"]), 6)

        response = self.client.post(
            "/api/lobbies/join",
            json={"code": lobby["pin"]},
        )

        self.assertEqual(response.status_code, 200)

        guest = response.json()

        self.assertEqual(
            guest["lobby"]["id"],
            lobby["id"],
        )

        self.assertNotEqual(
            guest["token"],
            host["token"],
        )

    def test_invalid_token(self):
        host = self.client.post(
            "/api/lobbies"
        ).json()

        lobby_id = host["lobby"]["id"]

        with self.client.websocket_connect(
            f"/ws/lobbies/{lobby_id}"
        ) as websocket:

            websocket.send_json({
                "type": "auth",
                "token": "fake-token",
            })

            with self.assertRaises(WebSocketDisconnect):
                websocket.receive_json()

    def test_start_and_drop(self):
        host, guests = self.create_full_lobby()

        lobby_id = host["lobby"]["id"]

        with self.client.websocket_connect(
            f"/ws/lobbies/{lobby_id}"
        ) as websocket:

            websocket.send_json({
                "type": "auth",
                "token": host["token"],
            })

            welcome = websocket.receive_json()
            initial = websocket.receive_json()

            self.assertEqual(welcome["type"], "welcome")
            self.assertEqual(initial["type"], "state")

            websocket.send_json({
                "type": "start",
            })

            started = websocket.receive_json()
            hand = websocket.receive_json()

            self.assertEqual(
                started["lobby"]["status"],
                "playing",
            )

            self.assertEqual(hand["type"], "hand")
            self.assertEqual(len(hand["jokers"]), 2)

            websocket.send_json({
                "type": "drop",
                "lane": 3,
            })

            updated = websocket.receive_json()

            self.assertEqual(updated["type"], "state")

            self.assertEqual(
                updated["lobby"]["board"][6][3],
                "red",
            )

            self.assertEqual(
                updated["lobby"]["current_turn"],
                1,
            )

    def test_public_state_hides_jokers(self):
        host, guests = self.create_full_lobby()

        lobby_id = host["lobby"]["id"]

        with self.client.websocket_connect(
            f"/ws/lobbies/{lobby_id}"
        ) as websocket:

            websocket.send_json({
                "type": "auth",
                "token": host["token"],
            })

            websocket.receive_json()
            websocket.receive_json()

            websocket.send_json({"type": "start"})

            public = websocket.receive_json()
            private = websocket.receive_json()

            self.assertNotIn(
                "jokers",
                public["lobby"],
            )

            for player in public["lobby"]["players"]:
                self.assertNotIn("jokers", player)
                self.assertEqual(player["joker_count"], 2)

            self.assertEqual(
                len(private["jokers"]),
                2,
            )

    def test_create_rate_limit(self):
        for _ in range(6):
            response = self.client.post("/api/lobbies")
            self.assertEqual(response.status_code, 200)

        response = self.client.post("/api/lobbies")

        self.assertEqual(response.status_code, 429)


if __name__ == "__main__":
    unittest.main()