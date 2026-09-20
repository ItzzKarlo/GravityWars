
import random
import unittest

from app.game.jokers import (
    deal_jokers,
    gravity_is_locked,
    play_joker,
)

from app.game.models import (
    GameState,
    GameStatus,
    GravityDirection,
    JokerType,
    Player,
    PlayerColor,
)


def create_test_game() -> GameState:

    return GameState(
        players=[
            Player("p1", "GoofyDiper", PlayerColor.RED),
            Player("p2", "SirWaffles", PlayerColor.BLUE),
            Player("p3", "GoblinMode", PlayerColor.GREEN),
            Player("p4", "TaxEvadingDuck", PlayerColor.YELLOW),
        ],
        status=GameStatus.PLAYING,
    )


class TestJokers(unittest.TestCase):

    def test_deal_jokers(self):
        game = create_test_game()

        deal_jokers(
            game.players,
            rng=random.Random(42),
        )

        for player in game.players:
            self.assertEqual(len(player.jokers), 2)
            self.assertEqual(len(set(player.jokers)), 2)

    def test_cannot_deal_twice(self):
        game = create_test_game()

        deal_jokers(game.players)

        with self.assertRaises(ValueError):
            deal_jokers(game.players)

    def test_gravity_roulette(self):
        game = create_test_game()

        game.players[0].jokers = [
            JokerType.GRAVITY_ROULETTE
        ]

        game.board[0][0] = PlayerColor.RED

        original_gravity = game.gravity

        play_joker(
            game,
            "p1",
            JokerType.GRAVITY_ROULETTE,
            rng=random.Random(42),
        )

        self.assertNotEqual(
            game.gravity,
            original_gravity,
        )

        self.assertEqual(game.current_turn, 0)
        self.assertEqual(game.players[0].jokers, [])

    def test_fifty_fifty(self):
        game = create_test_game()

        game.players[0].jokers = [
            JokerType.FIFTY_FIFTY
        ]

        colors = list(PlayerColor)

        # Eight occupied cells.
        for index in range(8):
            row = index // 4
            column = index % 4

            game.board[row][column] = colors[index % 4]

        play_joker(
            game,
            "p1",
            JokerType.FIFTY_FIFTY,
            rng=random.Random(42),
        )

        remaining = sum(
            piece is not None
            for row in game.board
            for piece in row
        )

        self.assertEqual(remaining, 4)

    def test_skip(self):
        game = create_test_game()

        game.current_turn = 1

        game.players[0].jokers = [
            JokerType.SKIP
        ]

        play_joker(
            game,
            "p1",
            JokerType.SKIP,
        )

        self.assertEqual(game.current_turn, 2)
        self.assertEqual(game.players[0].jokers, [])

    def test_cannot_skip_yourself(self):
        game = create_test_game()

        game.players[0].jokers = [
            JokerType.SKIP
        ]

        with self.assertRaises(ValueError):
            play_joker(
                game,
                "p1",
                JokerType.SKIP,
            )

        self.assertEqual(
            game.players[0].jokers,
            [JokerType.SKIP],
        )

    def test_steal(self):
        game = create_test_game()

        game.players[0].jokers = [
            JokerType.STEAL
        ]

        game.board[6][0] = PlayerColor.BLUE

        play_joker(
            game,
            "p1",
            JokerType.STEAL,
            target=(6, 0),
        )

        self.assertEqual(
            game.board[6][0],
            PlayerColor.RED,
        )

    def test_cannot_steal_empty_cell(self):
        game = create_test_game()

        game.players[0].jokers = [
            JokerType.STEAL
        ]

        with self.assertRaises(ValueError):
            play_joker(
                game,
                "p1",
                JokerType.STEAL,
                target=(6, 0),
            )

        self.assertEqual(
            game.players[0].jokers,
            [JokerType.STEAL],
        )

    def test_swap(self):
        game = create_test_game()

        game.players[0].jokers = [
            JokerType.SWAP
        ]

        game.board[6][0] = PlayerColor.BLUE
        game.board[6][1] = PlayerColor.GREEN

        play_joker(
            game,
            "p1",
            JokerType.SWAP,
            target=(6, 0),
            second_target=(6, 1),
        )

        self.assertEqual(
            game.board[6][0],
            PlayerColor.GREEN,
        )

        self.assertEqual(
            game.board[6][1],
            PlayerColor.BLUE,
        )

    def test_gravity_lock(self):
        game = create_test_game()

        game.players[0].jokers = [
            JokerType.GRAVITY_LOCK
        ]

        play_joker(
            game,
            "p1",
            JokerType.GRAVITY_LOCK,
            now=100.0,
        )

        self.assertTrue(
            gravity_is_locked(game, now=110.0)
        )

        self.assertFalse(
            gravity_is_locked(game, now=115.0)
        )

        self.assertEqual(
            game.gravity_locked_until,
            115.0,
        )

    def test_joker_can_create_winner(self):
        game = create_test_game()

        game.players[0].jokers = [
            JokerType.STEAL
        ]

        for column in range(3):
            game.board[6][column] = PlayerColor.RED

        game.board[6][3] = PlayerColor.BLUE

        play_joker(
            game,
            "p1",
            JokerType.STEAL,
            target=(6, 3),
        )

        self.assertEqual(
            game.status,
            GameStatus.FINISHED,
        )

        self.assertEqual(
            game.winner_ids,
            ["p1"],
        )

    def test_cannot_use_another_players_joker(self):
        game = create_test_game()

        game.players[1].jokers = [
            JokerType.GRAVITY_ROULETTE
        ]

        with self.assertRaises(ValueError):
            play_joker(
                game,
                "p1",
                JokerType.GRAVITY_ROULETTE,
            )

        self.assertEqual(
            game.gravity,
            GravityDirection.DOWN,
        )

    def test_cannot_play_after_game_ends(self):
        game = create_test_game()

        game.status = GameStatus.FINISHED

        game.players[0].jokers = [
            JokerType.GRAVITY_ROULETTE
        ]

        with self.assertRaises(ValueError):
            play_joker(
                game,
                "p1",
                JokerType.GRAVITY_ROULETTE,
            )


if __name__ == "__main__":
    unittest.main()