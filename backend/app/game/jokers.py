
import random
import secrets
import time

from .engine import update_game_result
from .gravity import apply_gravity
from .models import (
    GameState,
    GameStatus,
    GravityDirection,
    JokerType,
    Player,
)


# Number of copies of each joker in the deck.
# Destructive jokers are intentionally less common.
CHAOS_DECK = (
    [JokerType.GRAVITY_ROULETTE] * 4
    + [JokerType.FIFTY_FIFTY]
    + [JokerType.SKIP] * 3
    + [JokerType.STEAL] * 3
    + [JokerType.SWAP] * 2
    + [JokerType.GRAVITY_LOCK] * 2
)

JOKERS_PER_PLAYER = 2
GRAVITY_LOCK_DURATION = 15.0

Position = tuple[int, int]


def deal_jokers(
    players: list[Player],
    rng: random.Random | None = None,
) -> None:
    """
    Randomly distribute two secret jokers per player.

    Jokers are drawn from a shared deck.
    No player receives the same joker twice.
    """

    if len(players) != 4:
        raise ValueError("Exactly four players are required")

    if any(player.jokers for player in players):
        raise ValueError("Jokers have already been distributed")

    generator = rng if rng is not None else secrets.SystemRandom()

    deck = CHAOS_DECK.copy()

    # Deal one card to each player per round.
    for _ in range(JOKERS_PER_PLAYER):
        for player in players:

            # Exclude joker types the player already owns.
            available = [
                index
                for index, joker in enumerate(deck)
                if joker not in player.jokers
            ]

            if not available:
                raise ValueError("Not enough unique jokers")

            index = generator.choice(available)

            player.jokers.append(deck.pop(index))


def gravity_is_locked(
    state: GameState,
    now: float | None = None,
) -> bool:
    """Check whether natural gravity changes are frozen."""

    current_time = time.monotonic() if now is None else now

    return current_time < state.gravity_locked_until


def play_joker(
    state: GameState,
    player_id: str,
    joker: JokerType,
    target: Position | None = None,
    second_target: Position | None = None,
    rng: random.Random | None = None,
    now: float | None = None,
) -> GameState:
    """
    Execute a player's joker.

    Jokers may be played outside the player's turn.

    Invalid actions do not consume a joker.
    The supplied game state is modified and returned.
    """

    if state.status != GameStatus.PLAYING:
        raise ValueError("Game is not active")

    player = next(
        (p for p in state.players if p.id == player_id),
        None,
    )

    if player is None:
        raise ValueError("Player not found")

    if joker not in player.jokers:
        raise ValueError("Player does not own this joker")

    generator = rng if rng is not None else secrets.SystemRandom()
    current_time = time.monotonic() if now is None else now

    rows = len(state.board)
    columns = len(state.board[0])

    def get_piece(position: Position | None):
        """Validate a board position and return its piece."""

        if position is None:
            raise ValueError("Target position required")

        row, column = position

        if not (0 <= row < rows and 0 <= column < columns):
            raise ValueError("Target is outside the board")

        return state.board[row][column]

    # ----------------------------------------
    # GRAVITY ROULETTE
    # ----------------------------------------

    if joker == JokerType.GRAVITY_ROULETTE:

        directions = [
            direction
            for direction in GravityDirection
            if direction != state.gravity
        ]

        new_direction = generator.choice(directions)

        state.board = apply_gravity(
            state.board,
            new_direction,
        )

        state.gravity = new_direction

    # ----------------------------------------
    # THE 50/50
    # ----------------------------------------

    elif joker == JokerType.FIFTY_FIFTY:

        occupied = [
            (row, column)
            for row in range(rows)
            for column in range(columns)
            if state.board[row][column] is not None
        ]

        if len(occupied) < 2:
            raise ValueError(
                "At least two pieces are required"
            )

        # Remove half the occupied pieces.
        # For odd counts, round down.
        amount = len(occupied) // 2

        selected = generator.sample(
            occupied,
            amount,
        )

        new_board = [
            row.copy()
            for row in state.board
        ]

        for row, column in selected:
            new_board[row][column] = None

        # Remaining pieces settle under current gravity.
        state.board = apply_gravity(
            new_board,
            state.gravity,
        )

    # ----------------------------------------
    # SKIP
    # ----------------------------------------

    elif joker == JokerType.SKIP:

        if not state.players:
            raise ValueError("No players in the game")

        current_player = state.players[state.current_turn]

        if current_player.id == player_id:
            raise ValueError(
                "You cannot skip your own turn"
            )

        state.current_turn = (
            state.current_turn + 1
        ) % len(state.players)

    # ----------------------------------------
    # STEAL
    # ----------------------------------------

    elif joker == JokerType.STEAL:

        piece = get_piece(target)

        if piece is None:
            raise ValueError("Cannot steal an empty cell")

        if piece == player.color:
            raise ValueError("Cannot steal your own piece")

        row, column = target

        new_board = [
            board_row.copy()
            for board_row in state.board
        ]

        new_board[row][column] = player.color

        state.board = new_board

    # ----------------------------------------
    # SWAP
    # ----------------------------------------

    elif joker == JokerType.SWAP:

        first_piece = get_piece(target)
        second_piece = get_piece(second_target)

        if first_piece is None or second_piece is None:
            raise ValueError("Cannot swap empty cells")

        if target == second_target:
            raise ValueError("Choose two different pieces")

        if first_piece == second_piece:
            raise ValueError(
                "Pieces must have different colors"
            )

        row1, col1 = target
        row2, col2 = second_target

        new_board = [
            board_row.copy()
            for board_row in state.board
        ]

        new_board[row1][col1] = second_piece
        new_board[row2][col2] = first_piece

        state.board = new_board

    # ----------------------------------------
    # GRAVITY LOCK
    # ----------------------------------------

    elif joker == JokerType.GRAVITY_LOCK:

        # A second lock extends the existing lock.
        state.gravity_locked_until = (
            max(
                state.gravity_locked_until,
                current_time,
            )
            + GRAVITY_LOCK_DURATION
        )

    else:
        raise ValueError("Unknown joker type")

    # The joker is consumed ONLY after its action succeeds.
    player.jokers.remove(joker)

    # Board-changing jokers can create winning lines.
    update_game_result(state)

    return state