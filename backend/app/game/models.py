
from dataclasses import dataclass, field
from enum import Enum


# Board configuration
BOARD_ROWS = 7
BOARD_COLUMNS = 7


# Enums
class PlayerColor(str, Enum):
    RED = "red"
    BLUE = "blue"
    GREEN = "green"
    YELLOW = "yellow"


class GravityDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class GameStatus(str, Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"


class JokerType(str, Enum):
    GRAVITY_ROULETTE = "gravity_roulette"
    FIFTY_FIFTY = "fifty_fifty"
    SKIP = "skip"
    STEAL = "steal"
    SWAP = "swap"
    GRAVITY_LOCK = "gravity_lock"


# Board types
Board = list[list[PlayerColor | None]]


def create_empty_board() -> Board:
    """Create a fresh, empty 7x7 game board."""
    return [
        [None for _ in range(BOARD_COLUMNS)]
        for _ in range(BOARD_ROWS)
    ]


# Player model
@dataclass
class Player:
    id: str
    username: str
    color: PlayerColor
    jokers: list[JokerType] = field(default_factory=list)
    connected: bool = True


# Game state
@dataclass
class GameState:
    board: Board = field(default_factory=create_empty_board)
    players: list[Player] = field(default_factory=list)

    gravity: GravityDirection = GravityDirection.DOWN

    current_turn: int = 0
    status: GameStatus = GameStatus.WAITING

    winner_ids: list[str] = field(default_factory=list)

    gravity_locked_until: float = 0.0