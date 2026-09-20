
import asyncio

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class ConnectionHub:
    def __init__(self):
        self.sockets: dict[str, dict[str, WebSocket]] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.timer_events: dict[str, asyncio.Event] = {}

    def lock_for(self, lobby_id: str) -> asyncio.Lock:
        """Each lobby gets its own action lock."""
        if lobby_id not in self.locks:
            self.locks[lobby_id] = asyncio.Lock()

        return self.locks[lobby_id]

    def timer_event(self, lobby_id: str) -> asyncio.Event:
        """Wake the gravity scheduler when a lock is played."""
        if lobby_id not in self.timer_events:
            self.timer_events[lobby_id] = asyncio.Event()

        return self.timer_events[lobby_id]

    def attach(
        self,
        lobby_id: str,
        player_id: str,
        websocket: WebSocket,
    ) -> WebSocket | None:
        """Attach or replace a player's connection."""
        connections = self.sockets.setdefault(lobby_id, {})

        previous = connections.get(player_id)
        connections[player_id] = websocket

        return previous

    def is_current(
        self,
        lobby_id: str,
        player_id: str,
        websocket: WebSocket,
    ) -> bool:
        return (
            self.sockets.get(lobby_id, {}).get(player_id)
            is websocket
        )

    def detach(
        self,
        lobby_id: str,
        player_id: str,
        websocket: WebSocket,
    ) -> bool:
        """Only remove the connection if it is still current."""
        if not self.is_current(lobby_id, player_id, websocket):
            return False

        connections = self.sockets[lobby_id]
        del connections[player_id]

        if not connections:
            del self.sockets[lobby_id]

        return True

    async def send_to(
        self,
        lobby_id: str,
        player_id: str,
        message: dict,
    ) -> None:
        """Send a private message to one connected player."""
        websocket = self.sockets.get(lobby_id, {}).get(player_id)

        if websocket is None:
            return

        try:
            await websocket.send_json(message)
        except (RuntimeError, WebSocketDisconnect, OSError):
            self.detach(lobby_id, player_id, websocket)

    async def broadcast(
        self,
        lobby_id: str,
        message: dict,
    ) -> None:
        """Send the same public message to everyone."""
        player_ids = list(
            self.sockets.get(lobby_id, {}).keys()
        )

        for player_id in player_ids:
            await self.send_to(lobby_id, player_id, message)

    def forget(self, lobby_id: str) -> None:
        """Discard internal resources for an expired lobby."""
        self.sockets.pop(lobby_id, None)
        self.locks.pop(lobby_id, None)
        self.timer_events.pop(lobby_id, None)