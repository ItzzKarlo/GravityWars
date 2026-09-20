
import re
import secrets
import time

from collections.abc import Callable
from dataclasses import dataclass, field

from app.game.jokers import deal_jokers
from app.game.models import (
    GameState,
    GameStatus,
    Player,
    PlayerColor,
)


MAX_PLAYERS = 4

WAITING_TTL = 30 * 60
PLAYING_TTL = 2 * 60 * 60
FINISHED_TTL = 10 * 60


ADJECTIVES = [
    "Goofy",
    "Suspicious",
    "Sleepy",
    "Wobbly",
    "Certified",
    "Chaotic",
    "Invisible",
    "Confused",
    "Majestic",
    "Unhinged",
]

NOUNS = [
    "Diper",
    "Potato",
    "Goblin",
    "Toaster",
    "Waffle",
    "Penguin",
    "Noodle",
    "Duck",
    "Banana",
    "Gremlin",
]


PLAYER_COLORS = [
    PlayerColor.RED,
    PlayerColor.BLUE,
    PlayerColor.GREEN,
    PlayerColor.YELLOW,
]


@dataclass
class Lobby:
    id: str
    pin: str
    host_player_id: str
    game: GameState

    # Never expose these tokens in public responses.
    session_tokens: dict[str, str] = field(
        default_factory=dict
    )

    expires_at: float = 0.0


class LobbyManager:

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._clock = clock

        self._lobbies: dict[str, Lobby] = {}
        self._pins: dict[str, str] = {}

    # -----------------------------------------
    # INTERNAL HELPERS
    # -----------------------------------------

    def _generate_pin(self) -> str:
        """Generate an unused six-digit PIN."""

        for _ in range(100):
            pin = f"{secrets.randbelow(1_000_000):06d}"

            if pin not in self._pins:
                return pin

        raise RuntimeError("Could not generate lobby PIN")

    def _generate_lobby_id(self) -> str:
        """Generate an unpredictable lobby identifier."""

        while True:
            lobby_id = secrets.token_urlsafe(12)

            if lobby_id not in self._lobbies:
                return lobby_id

    def _generate_username(
        self,
        players: list[Player],
    ) -> str:
        """Generate a unique goofy username."""

        existing = {
            player.username.casefold()
            for player in players
        }

        for _ in range(100):
            name = (
                secrets.choice(ADJECTIVES)
                + secrets.choice(NOUNS)
            )

            if name.casefold() not in existing:
                return name

        raise RuntimeError("Could not generate username")

    def _touch(self, lobby: Lobby) -> None:
        """Refresh a lobby's expiration time."""

        if lobby.game.status == GameStatus.WAITING:
            ttl = WAITING_TTL

        elif lobby.game.status == GameStatus.PLAYING:
            ttl = PLAYING_TTL

        else:
            ttl = FINISHED_TTL

        lobby.expires_at = self._clock() + ttl

    def _delete(self, lobby: Lobby) -> None:
        """Remove a lobby and all temporary player data."""

        self._lobbies.pop(lobby.id, None)
        self._pins.pop(lobby.pin, None)

    # -----------------------------------------
    # EXPIRATION
    # -----------------------------------------

    def cleanup_expired(self) -> int:
        """Remove expired lobbies and return their count."""

        now = self._clock()

        expired = [
            lobby
            for lobby in self._lobbies.values()
            if lobby.expires_at <= now
        ]

        for lobby in expired:
            self._delete(lobby)

        return len(expired)

    def touch(self, lobby_id: str) -> None:
        """Refresh an active lobby after server activity."""

        lobby = self.get_lobby(lobby_id)
        self._touch(lobby)

    # -----------------------------------------
    # CREATE LOBBY
    # -----------------------------------------

    def create_lobby(self) -> tuple[Lobby, str]:
        """
        Create a lobby and its host.

        Returns:
            lobby, host_session_token
        """

        self.cleanup_expired()

        lobby_id = self._generate_lobby_id()
        pin = self._generate_pin()

        host = Player(
            id=secrets.token_urlsafe(12),
            username=self._generate_username([]),
            color=PLAYER_COLORS[0],
            connected=False,
        )

        token = secrets.token_urlsafe(32)

        game = GameState(players=[host])

        lobby = Lobby(
            id=lobby_id,
            pin=pin,
            host_player_id=host.id,
            game=game,
            session_tokens={host.id: token},
        )

        self._touch(lobby)

        self._lobbies[lobby_id] = lobby
        self._pins[pin] = lobby_id

        return lobby, token

    # -----------------------------------------
    # FIND LOBBY
    # -----------------------------------------

    def get_lobby(self, code: str) -> Lobby:
        """
        Find a lobby using either its ID or PIN.

        Expired lobbies are unavailable.
        """

        self.cleanup_expired()

        code = code.strip()

        # Support entering a PIN with spaces or hyphens.
        normalized_pin = code.replace(" ", "").replace("-", "")

        if normalized_pin in self._pins:
            lobby_id = self._pins[normalized_pin]
        else:
            lobby_id = code

        lobby = self._lobbies.get(lobby_id)

        if lobby is None:
            raise KeyError("Lobby not found or expired")

        return lobby

    # -----------------------------------------
    # JOIN LOBBY
    # -----------------------------------------

    def join_lobby(
        self,
        code: str,
    ) -> tuple[Lobby, str]:
        """
        Join a waiting lobby.

        Returns:
            lobby, new_player_session_token
        """

        lobby = self.get_lobby(code)

        if lobby.game.status != GameStatus.WAITING:
            raise ValueError("Game has already started")

        if len(lobby.game.players) >= MAX_PLAYERS:
            raise ValueError("Lobby is full")

        player = Player(
            id=secrets.token_urlsafe(12),
            username=self._generate_username(
                lobby.game.players
            ),
            color=PLAYER_COLORS[
                len(lobby.game.players)
            ],
            connected=False,
        )

        token = secrets.token_urlsafe(32)

        lobby.game.players.append(player)

        lobby.session_tokens[player.id] = token

        self._touch(lobby)

        return lobby, token

    # -----------------------------------------
    # PLAYER AUTHENTICATION
    # -----------------------------------------

    def authenticate(
        self,
        lobby_id: str,
        token: str,
    ) -> Player:
        """
        Identify an existing player by their private token.

        Used later by WebSocket connections and game actions.
        """

        lobby = self.get_lobby(lobby_id)

        if not isinstance(token, str) or not token:
            raise PermissionError("Invalid player token")

        for player in lobby.game.players:
            expected = lobby.session_tokens.get(player.id)

            if expected and secrets.compare_digest(
                expected,
                token,
            ):
                return player

        raise PermissionError("Invalid player token")

    # -----------------------------------------
    # CONNECTION STATUS
    # -----------------------------------------

    def set_connected(
        self,
        lobby_id: str,
        token: str,
        connected: bool,
    ) -> Player:
        """Update a player's connection status."""

        lobby = self.get_lobby(lobby_id)

        player = self.authenticate(
            lobby.id,
            token,
        )

        player.connected = connected

        self._touch(lobby)

        return player

    # -----------------------------------------
    # RENAME PLAYER
    # -----------------------------------------

    def rename_player(
        self,
        lobby_id: str,
        token: str,
        username: str,
    ) -> Player:
        """Change a player's username."""

        lobby = self.get_lobby(lobby_id)
        player = self.authenticate(lobby.id, token)

        username = username.strip()

        # 3-24 characters; letters, numbers,
        # spaces, underscores, and hyphens.
        valid_name = re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9 _-]{1,22}[A-Za-z0-9]",
            username,
        )

        if valid_name is None:
            raise ValueError(
                "Username must be 3-24 characters "
                "and contain only letters, numbers, "
                "spaces, underscores, or hyphens"
            )

        for other in lobby.game.players:
            if (
                other.id != player.id
                and other.username.casefold()
                == username.casefold()
            ):
                raise ValueError(
                    "Username is already taken"
                )

        player.username = username

        self._touch(lobby)

        return player

    # -----------------------------------------
    # START GAME
    # -----------------------------------------

    def start_lobby(
        self,
        lobby_id: str,
        token: str,
    ) -> Lobby:
        """Start a full lobby. Only the host may start."""

        lobby = self.get_lobby(lobby_id)
        player = self.authenticate(lobby.id, token)

        if player.id != lobby.host_player_id:
            raise PermissionError(
                "Only the host can start the game"
            )

        if lobby.game.status != GameStatus.WAITING:
            raise ValueError("Game has already started")

        if len(lobby.game.players) != MAX_PLAYERS:
            raise ValueError("Four players are required")

        # Each player receives two secret jokers.
        deal_jokers(lobby.game.players)

        lobby.game.status = GameStatus.PLAYING

        self._touch(lobby)

        return lobby

    # -----------------------------------------
    # PUBLIC STATE
    # -----------------------------------------

    def public_state(self, lobby_id: str) -> dict:
        """
        Build a public game snapshot.

        NEVER include session tokens or joker identities.
        """

        lobby = self.get_lobby(lobby_id)
        game = lobby.game

        return {
            "id": lobby.id,
            "pin": lobby.pin,
            "host_player_id": lobby.host_player_id,
            "status": game.status.value,
            "gravity": game.gravity.value,
            "current_turn": game.current_turn,
            "winner_ids": game.winner_ids.copy(),
            "board": [
                [
                    piece.value if piece else None
                    for piece in row
                ]
                for row in game.board
            ],
            "players": [
                {
                    "id": player.id,
                    "username": player.username,
                    "color": player.color.value,
                    "connected": player.connected,
                    "joker_count": len(player.jokers),
                }
                for player in game.players
            ],
        }

    # -----------------------------------------
    # PRIVATE PLAYER STATE
    # -----------------------------------------

    def private_state(
        self,
        lobby_id: str,
        token: str,
    ) -> dict:
        """
        Build a private snapshot for ONE player.

        Only send this through that player's
        authenticated connection.
        """

        player = self.authenticate(
            lobby_id,
            token,
        )

        return {
            "player_id": player.id,
            "jokers": [
                joker.value
                for joker in player.jokers
            ],
        }