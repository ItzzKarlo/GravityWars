
import os

from fastapi.middleware.cors import CORSMiddleware

import asyncio
import secrets
import time

from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from app.game.engine import change_gravity, play_turn
from app.game.jokers import gravity_is_locked, play_joker
from app.game.models import GameStatus, GravityDirection, JokerType
from app.lobby.manager import LobbyManager
from app.websocket.manager import ConnectionHub


class JoinRequest(BaseModel):
    code: str


def parse_position(value):
    """Validate a JSON board coordinate."""
    if value is None:
        return None

    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(number) is not int for number in value)
    ):
        raise ValueError("Position must be [row, column]")

    return tuple(value)


def create_app() -> FastAPI:
    lobbies = LobbyManager()
    hub = ConnectionHub()

    gravity_tasks: dict[str, asyncio.Task] = {}

    # Basic single-process HTTP rate limiting.
    attempts: dict[tuple[str, str], list[float]] = defaultdict(list)

    def rate_limit(
        request: Request,
        action: str,
        maximum: int,
    ) -> None:
        ip = request.client.host if request.client else "unknown"
        key = (action, ip)

        now = time.monotonic()

        attempts[key] = [
            timestamp
            for timestamp in attempts[key]
            if now - timestamp < 60
        ]

        if len(attempts[key]) >= maximum:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Try again later.",
            )

        attempts[key].append(now)

    def snapshot(lobby_id: str) -> dict:
        """Build the public state sent to all players."""
        state = lobbies.public_state(lobby_id)

        state["gravity_locked"] = gravity_is_locked(
            lobbies.get_lobby(lobby_id).game
        )

        return state

    async def publish(lobby_id: str) -> None:
        """Broadcast a fresh public state."""
        await hub.broadcast(
            lobby_id,
            {
                "type": "state",
                "lobby": snapshot(lobby_id),
            },
        )

    async def wait_until_unlocked(lobby_id: str) -> bool:
        """Wait for Gravity Lock to expire without blocking moves."""
        lock = hub.lock_for(lobby_id)

        while True:
            async with lock:
                try:
                    lobby = lobbies.get_lobby(lobby_id)
                except KeyError:
                    return False

                if lobby.game.status != GameStatus.PLAYING:
                    return False

                remaining = (
                    lobby.game.gravity_locked_until
                    - time.monotonic()
                )

            if remaining <= 0:
                return True

            await asyncio.sleep(remaining)

    async def gravity_loop(lobby_id: str) -> None:
        """Run natural gravity independently of player turns."""
        lock = hub.lock_for(lobby_id)
        wake = hub.timer_event(lobby_id)
        generator = secrets.SystemRandom()

        try:
            while True:
                # No countdown is sent to the players.
                delay = generator.uniform(10.0, 30.0)

                try:
                    await asyncio.wait_for(
                        wake.wait(),
                        timeout=delay,
                    )

                    # A Gravity Lock interrupted the timer.
                    wake.clear()

                    if not await wait_until_unlocked(lobby_id):
                        return

                    # Start a fresh random interval.
                    continue

                except TimeoutError:
                    pass

                locked = False

                async with lock:
                    try:
                        lobby = lobbies.get_lobby(lobby_id)
                    except KeyError:
                        return

                    if lobby.game.status != GameStatus.PLAYING:
                        return

                    if gravity_is_locked(lobby.game):
                        locked = True

                    else:
                        directions = [
                            direction
                            for direction in GravityDirection
                            if direction != lobby.game.gravity
                        ]

                        new_direction = generator.choice(directions)

                        change_gravity(
                            lobby.game,
                            new_direction,
                        )

                        lobbies.touch(lobby.id)

                        await publish(lobby.id)

                        if lobby.game.status == GameStatus.FINISHED:
                            return

                if locked:
                    if not await wait_until_unlocked(lobby_id):
                        return

                    # Gravity resumes with a new 10-30s interval.
                    wake.clear()

        finally:
            gravity_tasks.pop(lobby_id, None)

    async def cleanup_loop() -> None:
        """Periodically delete expired lobbies and connections."""
        while True:
            await asyncio.sleep(60)

            lobbies.cleanup_expired()

            for lobby_id in list(hub.sockets):
                try:
                    lobbies.get_lobby(lobby_id)
                except KeyError:
                    for websocket in list(
                        hub.sockets.get(lobby_id, {}).values()
                    ):
                        try:
                            await websocket.close(code=4004)
                        except (RuntimeError, OSError):
                            pass

                    hub.forget(lobby_id)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cleanup_task = asyncio.create_task(cleanup_loop())

        try:
            yield
        finally:
            cleanup_task.cancel()

            tasks = [
                cleanup_task,
                *gravity_tasks.values(),
            ]

            for task in tasks:
                task.cancel()

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

    app = FastAPI(
        title="Gravity Wars API",
        lifespan=lifespan,
    )


    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    if extra_origin := os.getenv("FRONTEND_ORIGIN"):
        allowed_origins.append(extra_origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # -----------------------------------------
    # HTTP API
    # -----------------------------------------

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/lobbies")
    async def create_lobby(request: Request):
        rate_limit(request, "create", 6)

        lobby, token = lobbies.create_lobby()

        return {
            "lobby": snapshot(lobby.id),
            "player_id": lobby.host_player_id,
            "token": token,
        }

    @app.post("/api/lobbies/join")
    async def join_lobby(
        request: Request,
        data: JoinRequest,
    ):
        rate_limit(request, "join", 12)

        try:
            lobby, token = lobbies.join_lobby(data.code)
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail="Lobby not found",
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            )

        return {
            "lobby": snapshot(lobby.id),
            "player_id": lobbies.authenticate(
                lobby.id,
                token,
            ).id,
            "token": token,
        }

    @app.get("/api/lobbies/{lobby_id}")
    async def get_lobby(lobby_id: str):
        lock = hub.lock_for(lobby_id)

        async with lock:
            try:
                return snapshot(lobby_id)
            except KeyError:
                raise HTTPException(
                    status_code=404,
                    detail="Lobby not found",
                )

    # -----------------------------------------
    # WEBSOCKET
    # -----------------------------------------

    @app.websocket("/ws/lobbies/{lobby_id}")
    async def game_socket(
        websocket: WebSocket,
        lobby_id: str,
    ):
        await websocket.accept()

        # Never authenticate using a token in the URL.
        try:
            auth = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10,
            )
        except (TimeoutError, WebSocketDisconnect, ValueError):
            try:
                await websocket.close(code=4401)
            except RuntimeError:
                pass
            return

        if not isinstance(auth, dict) or auth.get("type") != "auth":
            await websocket.close(code=4401)
            return

        token = auth.get("token")

        lock = hub.lock_for(lobby_id)

        async with lock:
            try:
                player = lobbies.authenticate(lobby_id, token)
            except (KeyError, PermissionError):
                await websocket.close(code=4401)
                return

            previous = hub.attach(
                lobby_id,
                player.id,
                websocket,
            )

            if previous is not None and previous is not websocket:
                try:
                    await previous.close(code=4001)
                except (RuntimeError, OSError):
                    pass

            player.connected = True
            lobbies.touch(lobby_id)

            # Only this player receives their secret hand.
            await websocket.send_json({
                "type": "welcome",
                **lobbies.private_state(lobby_id, token),
            })

            await publish(lobby_id)

        try:
            while True:
                message = await websocket.receive_json()

                async with lock:
                    # An older connection cannot play after reconnect.
                    if not hub.is_current(
                        lobby_id,
                        player.id,
                        websocket,
                    ):
                        await websocket.close(code=4001)
                        break

                    try:
                        lobby = lobbies.get_lobby(lobby_id)

                        if not isinstance(message, dict):
                            raise ValueError("Invalid message")

                        action = message.get("type")

                        if action == "start":
                            lobbies.start_lobby(
                                lobby.id,
                                token,
                            )

                        elif action == "drop":
                            lane = message.get("lane")

                            if type(lane) is not int:
                                raise ValueError(
                                    "Lane must be an integer"
                                )

                            play_turn(
                                lobby.game,
                                player.id,
                                lane,
                            )

                        elif action == "joker":
                            joker = JokerType(
                                message.get("joker")
                            )

                            play_joker(
                                lobby.game,
                                player.id,
                                joker,
                                target=parse_position(
                                    message.get("target")
                                ),
                                second_target=parse_position(
                                    message.get("second_target")
                                ),
                            )

                            if joker == JokerType.GRAVITY_LOCK:
                                hub.timer_event(lobby.id).set()

                        elif action == "rename":
                            lobbies.rename_player(
                                lobby.id,
                                token,
                                message.get("username", ""),
                            )

                        else:
                            raise ValueError("Unknown action")

                        lobbies.touch(lobby.id)

                    except (
                        ValueError,
                        TypeError,
                        KeyError,
                        PermissionError,
                    ) as exc:
                        await websocket.send_json({
                            "type": "error",
                            "message": str(exc),
                        })
                        continue

                    # Everyone receives the new public board.
                    await publish(lobby.id)

                    if action == "start":
                        # Secret hands are sent individually.
                        for other in lobby.game.players:
                            await hub.send_to(
                                lobby.id,
                                other.id,
                                {
                                    "type": "hand",
                                    "jokers": [
                                        joker.value
                                        for joker in other.jokers
                                    ],
                                },
                            )

                        gravity_tasks[lobby.id] = (
                            asyncio.create_task(
                                gravity_loop(lobby.id)
                            )
                        )

                    elif action == "joker":
                        # Update only the acting player's hand.
                        await hub.send_to(
                            lobby.id,
                            player.id,
                            {
                                "type": "hand",
                                "jokers": [
                                    joker.value
                                    for joker in player.jokers
                                ],
                            },
                        )

        except (WebSocketDisconnect, RuntimeError):
            pass

        finally:
            async with lock:
                if hub.detach(
                    lobby_id,
                    player.id,
                    websocket,
                ):
                    try:
                        lobby = lobbies.get_lobby(lobby_id)
                    except KeyError:
                        return

                    player.connected = False

                    await publish(lobby.id)

    return app


app = create_app()