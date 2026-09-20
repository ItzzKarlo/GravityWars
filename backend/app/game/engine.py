
from .gravity import apply_gravity
from .models import (
    Board,
    GameState,
    GameStatus,
    GravityDirection,
    PlayerColor,
)


CONNECT_LENGTH = 4


def drop_piece(
    board: Board,
    gravity: GravityDirection,
    lane: int,
    color: PlayerColor,
) -> Board:
    """
    Drop a piece into a lane.

    A lane is a column for vertical gravity
    or a row for horizontal gravity.

    Returns a new board.
    """

    rows = len(board)
    columns = len(board[0])

    new_board = [row.copy() for row in board]

    # Vertical gravity: select a column
    if gravity in (
        GravityDirection.DOWN,
        GravityDirection.UP,
    ):
        if not 0 <= lane < columns:
            raise ValueError("Invalid column")

        if gravity == GravityDirection.DOWN:
            positions = range(rows - 1, -1, -1)
        else:
            positions = range(rows)

        for row in positions:
            if new_board[row][lane] is None:
                new_board[row][lane] = color
                return new_board

    # Horizontal gravity: select a row
    elif gravity in (
        GravityDirection.LEFT,
        GravityDirection.RIGHT,
    ):
        if not 0 <= lane < rows:
            raise ValueError("Invalid row")

        if gravity == GravityDirection.LEFT:
            positions = range(columns)
        else:
            positions = range(columns - 1, -1, -1)

        for column in positions:
            if new_board[lane][column] is None:
                new_board[lane][column] = color
                return new_board

    else:
        raise ValueError("Invalid gravity direction")

    raise ValueError("This lane is full")


def find_winners(board: Board) -> set[PlayerColor]:
    """
    Find every color with four consecutive pieces.

    Checks horizontal, vertical, and both diagonals.
    Multiple players may win simultaneously.
    """

    rows = len(board)
    columns = len(board[0])

    winners: set[PlayerColor] = set()

    directions = [
        (0, 1),   # Horizontal
        (1, 0),   # Vertical
        (1, 1),   # Diagonal down-right
        (1, -1),  # Diagonal down-left
    ]

    for row in range(rows):
        for column in range(columns):

            color = board[row][column]

            if color is None:
                continue

            for dr, dc in directions:

                end_row = row + (CONNECT_LENGTH - 1) * dr
                end_column = column + (CONNECT_LENGTH - 1) * dc

                # Skip lines extending outside the board
                if not (
                    0 <= end_row < rows
                    and 0 <= end_column < columns
                ):
                    continue

                # Check the next three positions
                if all(
                    board[row + i * dr][column + i * dc] == color
                    for i in range(1, CONNECT_LENGTH)
                ):
                    winners.add(color)

    return winners


def is_board_full(board: Board) -> bool:
    """Check whether every cell is occupied."""

    return all(
        piece is not None
        for row in board
        for piece in row
    )


def update_game_result(state: GameState) -> None:
    """
    Check for winners or a draw.

    Updates the game state in place.
    """

    winning_colors = find_winners(state.board)

    if winning_colors:

        state.winner_ids = [
            player.id
            for player in state.players
            if player.color in winning_colors
        ]

        state.status = GameStatus.FINISHED

    elif is_board_full(state.board):
        state.winner_ids = []
        state.status = GameStatus.FINISHED


def play_turn(
    state: GameState,
    player_id: str,
    lane: int,
) -> GameState:
    """
    Execute one player's move.

    Validates the turn, drops the piece,
    checks the result, and advances the turn.

    Modifies and returns the given game state.
    """

    if state.status != GameStatus.PLAYING:
        raise ValueError("Game is not active")

    if not state.players:
        raise ValueError("Game has no players")

    current_player = state.players[state.current_turn]

    if current_player.id != player_id:
        raise ValueError("It is not your turn")

    # Drop the current player's piece
    state.board = drop_piece(
        state.board,
        state.gravity,
        lane,
        current_player.color,
    )

    # Check for a winner or draw
    update_game_result(state)

    # Only advance if the game continues
    if state.status == GameStatus.PLAYING:
        state.current_turn = (
            state.current_turn + 1
        ) % len(state.players)

    return state


def change_gravity(
    state: GameState,
    new_direction: GravityDirection,
) -> GameState:
    """
    Change gravity and settle every piece.

    Gravity changes do not advance or reset
    the current player's turn.

    Modifies and returns the given game state.
    """

    if state.status != GameStatus.PLAYING:
        raise ValueError("Game is not active")

    if new_direction == state.gravity:
        raise ValueError("Gravity direction has not changed")

    state.board = apply_gravity(
        state.board,
        new_direction,
    )

    state.gravity = new_direction

    # A gravity change can create a winning line
    update_game_result(state)

    return state