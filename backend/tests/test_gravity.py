
import unittest

from app.game.gravity import apply_gravity
from app.game.models import (
    create_empty_board,
    GravityDirection,
    PlayerColor,
)


class TestGravity(unittest.TestCase):

    def test_gravity_down(self):
        board = create_empty_board()

        board[0][3] = PlayerColor.RED
        board[2][3] = PlayerColor.BLUE

        result = apply_gravity(board, GravityDirection.DOWN)

        self.assertEqual(result[6][3], PlayerColor.BLUE)
        self.assertEqual(result[5][3], PlayerColor.RED)

    def test_gravity_up(self):
        board = create_empty_board()

        board[4][3] = PlayerColor.RED
        board[6][3] = PlayerColor.BLUE

        result = apply_gravity(board, GravityDirection.UP)

        self.assertEqual(result[0][3], PlayerColor.RED)
        self.assertEqual(result[1][3], PlayerColor.BLUE)

    def test_gravity_left(self):
        board = create_empty_board()

        board[3][2] = PlayerColor.RED
        board[3][5] = PlayerColor.BLUE

        result = apply_gravity(board, GravityDirection.LEFT)

        self.assertEqual(result[3][0], PlayerColor.RED)
        self.assertEqual(result[3][1], PlayerColor.BLUE)

    def test_gravity_right(self):
        board = create_empty_board()

        board[3][1] = PlayerColor.RED
        board[3][4] = PlayerColor.BLUE

        result = apply_gravity(board, GravityDirection.RIGHT)

        self.assertEqual(result[3][5], PlayerColor.RED)
        self.assertEqual(result[3][6], PlayerColor.BLUE)

    def test_original_board_unchanged(self):
        board = create_empty_board()

        board[0][0] = PlayerColor.RED

        result = apply_gravity(board, GravityDirection.DOWN)

        self.assertEqual(board[0][0], PlayerColor.RED)
        self.assertEqual(result[6][0], PlayerColor.RED)
        self.assertIsNot(result, board)

    def test_empty_board(self):
        board = create_empty_board()

        for direction in GravityDirection:
            with self.subTest(direction=direction):
                result = apply_gravity(board, direction)
                self.assertEqual(result, board)

    def test_gravity_preserves_piece_count(self):
        board = create_empty_board()

        board[0][0] = PlayerColor.RED
        board[2][3] = PlayerColor.BLUE
        board[5][6] = PlayerColor.GREEN

        for direction in GravityDirection:
            with self.subTest(direction=direction):
                result = apply_gravity(board, direction)

                pieces = sum(
                    piece is not None
                    for row in result
                    for piece in row
                )

                self.assertEqual(pieces, 3)


if __name__ == "__main__":
    unittest.main()