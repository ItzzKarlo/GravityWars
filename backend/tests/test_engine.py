
import unittest

from app.game.engine import (
    change_gravity,
    drop_piece,
    find_winners,
    play_turn,
)
from app.game.models import (
    GameState,
    GameStatus,
    GravityDirection,
    Player,
    PlayerColor,
    create_empty_board,
)


def create_test_game() -> GameState:
    """Create a running game with four players."""

    return GameState(
        players=[
            Player("p1", "GoofyDiper", PlayerColor.RED),
            Player("p2", "SirWaffles", PlayerColor.BLUE),
            Player("p3", "GoblinMode", PlayerColor.GREEN),
            Player("p4", "TaxEvadingDuck", PlayerColor.YELLOW),
        ],
        status=GameStatus.PLAYING,
    )


class TestEngine(unittest.TestCase):

    def test_drop_piece_all_directions(self):
        cases = [
            (GravityDirection.DOWN, 6, 2),
            (GravityDirection.UP, 0, 2),
            (GravityDirection.LEFT, 2, 0),
            (GravityDirection.RIGHT, 2, 6),
        ]

        for gravity, row, column in cases:
            with self.subTest(gravity=gravity):

                board = create_empty_board()

                result = drop_piece(
                    board,
                    gravity,
                    2,
                    PlayerColor.RED,
                )

                self.assertEqual(
                    result[row][column],
                    PlayerColor.RED,
                )

    def test_drop_piece_does_not_modify_original(self):
        board = create_empty_board()

        result = drop_piece(
            board,
            GravityDirection.DOWN,
            3,
            PlayerColor.RED,
        )

        self.assertIsNone(board[6][3])
        self.assertEqual(result[6][3], PlayerColor.RED)

    def test_full_lane_rejected(self):
        board = create_empty_board()

        for row in range(7):
            board[row][3] = PlayerColor.RED

        with self.assertRaises(ValueError):
            drop_piece(
                board,
                GravityDirection.DOWN,
                3,
                PlayerColor.BLUE,
            )

    def test_invalid_lane_rejected(self):
        board = create_empty_board()

        with self.assertRaises(ValueError):
            drop_piece(
                board,
                GravityDirection.DOWN,
                7,
                PlayerColor.RED,
            )

    def test_horizontal_win(self):
        board = create_empty_board()

        for column in range(4):
            board[6][column] = PlayerColor.RED

        self.assertEqual(
            find_winners(board),
            {PlayerColor.RED},
        )

    def test_vertical_win(self):
        board = create_empty_board()

        for row in range(3, 7):
            board[row][0] = PlayerColor.BLUE

        self.assertEqual(
            find_winners(board),
            {PlayerColor.BLUE},
        )

    def test_diagonal_win(self):
        board = create_empty_board()

        for index in range(4):
            board[index][index] = PlayerColor.GREEN

        self.assertEqual(
            find_winners(board),
            {PlayerColor.GREEN},
        )

    def test_turn_advances(self):
        game = create_test_game()

        play_turn(game, "p1", 3)

        self.assertEqual(game.current_turn, 1)
        self.assertEqual(game.board[6][3], PlayerColor.RED)

    def test_wrong_player_rejected(self):
        game = create_test_game()

        with self.assertRaises(ValueError):
            play_turn(game, "p2", 3)

        self.assertEqual(game.current_turn, 0)

    def test_player_wins(self):
        game = create_test_game()

        # Three red pieces already positioned
        for column in range(3):
            game.board[6][column] = PlayerColor.RED

        play_turn(game, "p1", 3)

        self.assertEqual(
            game.status,
            GameStatus.FINISHED,
        )

        self.assertEqual(game.winner_ids, ["p1"])

    def test_gravity_does_not_advance_turn(self):
        game = create_test_game()

        game.board[6][1] = PlayerColor.RED

        change_gravity(
            game,
            GravityDirection.RIGHT,
        )

        self.assertEqual(game.current_turn, 0)
        self.assertEqual(game.gravity, GravityDirection.RIGHT)
        self.assertEqual(game.board[6][6], PlayerColor.RED)

    def test_gravity_can_create_winner(self):
        game = create_test_game()

        # Four separated pieces in the bottom row
        for column in (0, 2, 4, 6):
            game.board[6][column] = PlayerColor.RED

        # Gravity pulls them together
        change_gravity(
            game,
            GravityDirection.LEFT,
        )

        self.assertEqual(
            game.status,
            GameStatus.FINISHED,
        )

        self.assertEqual(game.winner_ids, ["p1"])

    def test_multiple_winners(self):
        game = create_test_game()

        for column in range(4):
            game.board[0][column] = PlayerColor.RED
            game.board[1][column] = PlayerColor.BLUE

        change_gravity(
            game,
            GravityDirection.LEFT,
        )

        self.assertEqual(
            set(game.winner_ids),
            {"p1", "p2"},
        )


if __name__ == "__main__":
    unittest.main()