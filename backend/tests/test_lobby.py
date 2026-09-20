
import unittest

from unittest.mock import patch

from app.game.models import GameStatus
from app.lobby.manager import LobbyManager


class TestLobbyManager(unittest.TestCase):

    def setUp(self):
        # Fake clock lets us test expiration instantly.
        self.now = [1000.0]

        self.manager = LobbyManager(
            clock=lambda: self.now[0]
        )

    def create_full_lobby(self):
        lobby, host_token = (
            self.manager.create_lobby()
        )

        guest_tokens = []

        for _ in range(3):
            _, token = self.manager.join_lobby(
                lobby.pin
            )

            guest_tokens.append(token)

        return lobby, host_token, guest_tokens

    def test_create_lobby(self):
        lobby, token = self.manager.create_lobby()

        self.assertEqual(len(lobby.pin), 6)
        self.assertTrue(lobby.pin.isdigit())

        self.assertEqual(
            len(lobby.game.players),
            1,
        )

        self.assertEqual(
            lobby.game.status,
            GameStatus.WAITING,
        )

        self.assertEqual(
            self.manager.authenticate(
                lobby.id,
                token,
            ).id,
            lobby.host_player_id,
        )

    def test_join_with_pin(self):
        lobby, _ = self.manager.create_lobby()

        joined_lobby, _ = (
            self.manager.join_lobby(lobby.pin)
        )

        self.assertIs(joined_lobby, lobby)

        self.assertEqual(
            len(lobby.game.players),
            2,
        )

    def test_join_with_link_id(self):
        lobby, _ = self.manager.create_lobby()

        joined_lobby, _ = (
            self.manager.join_lobby(lobby.id)
        )

        self.assertIs(joined_lobby, lobby)

    def test_unique_usernames(self):
        lobby, _, _ = self.create_full_lobby()

        names = [
            player.username.casefold()
            for player in lobby.game.players
        ]

        self.assertEqual(len(set(names)), 4)

    def test_unique_player_colors(self):
        lobby, _, _ = self.create_full_lobby()

        colors = [
            player.color
            for player in lobby.game.players
        ]

        self.assertEqual(len(set(colors)), 4)

    def test_lobby_is_full(self):
        lobby, _, _ = self.create_full_lobby()

        with self.assertRaises(ValueError):
            self.manager.join_lobby(lobby.pin)

    def test_rename_player(self):
        lobby, token = self.manager.create_lobby()

        player = self.manager.rename_player(
            lobby.id,
            token,
            "Sir Waffles",
        )

        self.assertEqual(
            player.username,
            "Sir Waffles",
        )

    def test_duplicate_username_rejected(self):
        lobby, host_token = (
            self.manager.create_lobby()
        )

        _, guest_token = (
            self.manager.join_lobby(lobby.pin)
        )

        self.manager.rename_player(
            lobby.id,
            host_token,
            "GoofyDiper",
        )

        with self.assertRaises(ValueError):
            self.manager.rename_player(
                lobby.id,
                guest_token,
                "goofydiper",
            )

    def test_invalid_username_rejected(self):
        lobby, token = self.manager.create_lobby()

        with self.assertRaises(ValueError):
            self.manager.rename_player(
                lobby.id,
                token,
                "a",
            )

    def test_invalid_token_rejected(self):
        lobby, _ = self.manager.create_lobby()

        with self.assertRaises(PermissionError):
            self.manager.authenticate(
                lobby.id,
                "not-a-real-token",
            )

    def test_reconnect_existing_player(self):
        lobby, token = self.manager.create_lobby()

        original_player = self.manager.authenticate(
            lobby.id,
            token,
        )

        self.manager.set_connected(
            lobby.id,
            token,
            True,
        )

        self.manager.set_connected(
            lobby.id,
            token,
            False,
        )

        reconnected = self.manager.set_connected(
            lobby.id,
            token,
            True,
        )

        self.assertEqual(
            original_player.id,
            reconnected.id,
        )

        self.assertTrue(reconnected.connected)

        self.assertEqual(
            len(lobby.game.players),
            1,
        )

    def test_only_host_can_start(self):
        lobby, _, guests = (
            self.create_full_lobby()
        )

        with self.assertRaises(PermissionError):
            self.manager.start_lobby(
                lobby.id,
                guests[0],
            )

    def test_start_requires_four_players(self):
        lobby, token = (
            self.manager.create_lobby()
        )

        with self.assertRaises(ValueError):
            self.manager.start_lobby(
                lobby.id,
                token,
            )

    def test_start_distributes_jokers(self):
        lobby, token, _ = (
            self.create_full_lobby()
        )

        self.manager.start_lobby(
            lobby.id,
            token,
        )

        self.assertEqual(
            lobby.game.status,
            GameStatus.PLAYING,
        )

        for player in lobby.game.players:
            self.assertEqual(
                len(player.jokers),
                2,
            )

    def test_cannot_join_started_game(self):
        lobby, token, _ = (
            self.create_full_lobby()
        )

        self.manager.start_lobby(
            lobby.id,
            token,
        )

        with self.assertRaises(ValueError):
            self.manager.join_lobby(lobby.pin)

    def test_jokers_are_private(self):
        lobby, host_token, guests = (
            self.create_full_lobby()
        )

        self.manager.start_lobby(
            lobby.id,
            host_token,
        )

        public = self.manager.public_state(
            lobby.id
        )

        private = self.manager.private_state(
            lobby.id,
            host_token,
        )

        # Public state only reveals card counts.
        self.assertNotIn("jokers", str(public))
        self.assertNotIn(
            host_token,
            str(public),
        )

        self.assertNotIn(
            guests[0],
            str(public),
        )

        self.assertEqual(
            len(private["jokers"]),
            2,
        )

        self.assertEqual(
            private["player_id"],
            lobby.host_player_id,
        )

    def test_lobby_expires(self):
        lobby, _ = self.manager.create_lobby()

        self.now[0] += 1801

        with self.assertRaises(KeyError):
            self.manager.get_lobby(lobby.id)

        self.assertNotIn(
            lobby.pin,
            self.manager._pins,
        )

    def test_activity_refreshes_expiration(self):
        lobby, _ = self.manager.create_lobby()

        self.now[0] += 1700

        self.manager.join_lobby(lobby.pin)

        self.now[0] += 1700

        self.assertIs(
            self.manager.get_lobby(lobby.id),
            lobby,
        )

    def test_pin_collision_generates_new_pin(self):
        with patch(
            "app.lobby.manager.secrets.randbelow",
            side_effect=[
                123456,
                123456,
                654321,
            ],
        ):
            first, _ = self.manager.create_lobby()
            second, _ = self.manager.create_lobby()

        self.assertEqual(first.pin, "123456")
        self.assertEqual(second.pin, "654321")


if __name__ == "__main__":
    unittest.main()