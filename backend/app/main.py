from __future__ import annotations

import asyncio
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

from app.auth.store import (
    AccessSession,
    AccessStore,
    InvitationError,
    InvitationExpired,
    InvitationRevoked,
    InvitationUsed,
    SessionMaterial,
)
from app.config import Settings
from app.game.engine import change_gravity, play_turn
from app.game.jokers import deal_jokers, gravity_is_locked, play_joker
from app.game.models import GameState, GameStatus, GravityDirection, JokerType
from app.lobby.manager import LobbyManager
from app.websocket.manager import ConnectionHub


SESSION_COOKIE = "gw_session"
CSRF_COOKIE = "gw_csrf"
MAX_BODY_BYTES = 16 * 1024


class RequestSizeLimitMiddleware:
    """Reject declared and streamed HTTP bodies above the configured limit."""

    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        declared = headers.get(b"content-length")
        if declared:
            try:
                if int(declared) > self.max_bytes:
                    await PlainTextResponse(
                        "Request too large", status_code=413
                    )(scope, receive, send)
                    return
            except ValueError:
                await PlainTextResponse(
                    "Invalid content length", status_code=400
                )(scope, receive, send)
                return

        buffered: list[Message] = []
        received = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message["type"] != "http.request":
                break
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                await PlainTextResponse(
                    "Request too large", status_code=413
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        messages = iter(buffered)

        async def replay() -> Message:
            return next(messages, {"type": "http.disconnect"})

        await self.app(scope, replay, send)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class RedeemRequest(BaseModel):
    secret: str = Field(min_length=40, max_length=128)


class JoinRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128)


@dataclass(frozen=True)
class RedeemedPlayer:
    player_id: str
    token: str
    lobby_id: str


def parse_position(value):
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(number) is not int for number in value)
    ):
        raise ValueError("Position must be [row, column]")
    return tuple(value)


def create_app(
    settings: Settings | None = None,
    access_store: AccessStore | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    lobbies = LobbyManager()
    hub = ConnectionHub()
    access = access_store or AccessStore(settings)
    # Game state is intentionally in memory. Records from an earlier process
    # are orphaned and must fail closed after restart.
    access.purge_orphans(set())

    gravity_tasks: dict[str, asyncio.Task] = {}
    attempts: dict[tuple[str, str], list[float]] = defaultdict(list)
    password_hasher = PasswordHasher()

    def rate_limit(request: Request, action: str, maximum: int) -> None:
        address = request.client.host if request.client else "unknown"
        key = (action, address)
        now = time.monotonic()
        attempts[key] = [stamp for stamp in attempts[key] if now - stamp < 60]
        if len(attempts[key]) >= maximum:
            raise HTTPException(429, "Too many attempts. Try again later.")
        attempts[key].append(now)

    def require_origin(headers) -> None:
        origin = (headers.get("origin") or "").rstrip("/")
        if origin not in settings.allowed_origins:
            raise HTTPException(403, "Request origin is not allowed")

    def session_from(request: Request) -> tuple[str, AccessSession]:
        raw = request.cookies.get(SESSION_COOKIE)
        session = access.get_session(raw)
        if not raw or session is None:
            raise HTTPException(401, "Authentication required")
        return raw, session

    def require_csrf(request: Request, raw_session: str) -> None:
        require_origin(request.headers)
        header = request.headers.get("x-csrf-token")
        cookie = request.cookies.get(CSRF_COOKIE)
        if not header or not cookie or not secrets.compare_digest(header, cookie):
            raise HTTPException(403, "CSRF validation failed")
        if not access.validate_csrf(raw_session, header):
            raise HTTPException(403, "CSRF validation failed")

    def require_admin(request: Request, mutation: bool = False):
        raw, session = session_from(request)
        if session.role != "admin":
            raise HTTPException(403, "Administrator access required")
        if mutation:
            require_csrf(request, raw)
        return raw, session

    def require_lobby(request: Request, lobby_id: str) -> AccessSession:
        session = access.authorize_lobby(
            request.cookies.get(SESSION_COOKIE), lobby_id
        )
        if session is None:
            raise HTTPException(403, "You do not have access to this lobby")
        return session

    def set_session_cookies(response: Response, session: SessionMaterial) -> None:
        max_age = max(0, int(session.expires_at - time.time()))
        common = {
            "secure": settings.cookie_secure,
            "samesite": "strict",
            "path": "/",
            "max_age": max_age,
        }
        response.set_cookie(
            SESSION_COOKIE, session.token, httponly=True, **common
        )
        response.set_cookie(
            CSRF_COOKIE, session.csrf_token, httponly=False, **common
        )

    def clear_session_cookies(response: Response) -> None:
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")

    def snapshot(lobby_id: str) -> dict:
        state = lobbies.public_state(lobby_id)
        state["gravity_locked"] = gravity_is_locked(
            lobbies.get_lobby(lobby_id).game
        )
        return state

    async def publish(lobby_id: str) -> None:
        await hub.broadcast(
            lobby_id, {"type": "state", "lobby": snapshot(lobby_id)}
        )

    async def wait_until_unlocked(lobby_id: str) -> bool:
        lock = hub.lock_for(lobby_id)
        while True:
            async with lock:
                try:
                    lobby = lobbies.get_lobby(lobby_id)
                except KeyError:
                    return False
                if lobby.game.status != GameStatus.PLAYING:
                    return False
                remaining = lobby.game.gravity_locked_until - time.monotonic()
            if remaining <= 0:
                return True
            await asyncio.sleep(remaining)

    async def gravity_loop(lobby_id: str) -> None:
        lock = hub.lock_for(lobby_id)
        wake = hub.timer_event(lobby_id)
        generator = secrets.SystemRandom()
        try:
            while True:
                try:
                    await asyncio.wait_for(
                        wake.wait(),
                        timeout=generator.uniform(
                            settings.gravity_min_seconds,
                            settings.gravity_max_seconds,
                        ),
                    )
                    wake.clear()
                    if not await wait_until_unlocked(lobby_id):
                        return
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
                        choices = [
                            item for item in GravityDirection
                            if item != lobby.game.gravity
                        ]
                        change_gravity(lobby.game, generator.choice(choices))
                        lobbies.touch(lobby.id)
                        await publish(lobby.id)
                        if lobby.game.status == GameStatus.FINISHED:
                            return
                if locked:
                    if not await wait_until_unlocked(lobby_id):
                        return
                    wake.clear()
        finally:
            if gravity_tasks.get(lobby_id) is asyncio.current_task():
                gravity_tasks.pop(lobby_id, None)

    async def cleanup_loop() -> None:
        while True:
            await asyncio.sleep(60)
            lobbies.cleanup_expired()
            active = lobbies.active_lobby_ids()
            access.purge_orphans(active)
            for lobby_id in list(hub.sockets):
                if lobby_id not in active:
                    for socket in list(hub.sockets.get(lobby_id, {}).values()):
                        try:
                            await socket.close(code=4004)
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
            loop = asyncio.get_running_loop()
            tasks = [
                cleanup_task,
                *(task for task in gravity_tasks.values()
                  if task.get_loop() is loop),
            ]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Gravity Wars API", lifespan=lifespan)
    app.state.lobbies = lobbies
    app.state.access = access
    app.state.hub = hub

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/auth/login")
    async def login(request: Request, data: LoginRequest, response: Response):
        require_origin(request.headers)
        rate_limit(request, "login", 5)
        valid = data.username.casefold() == "admin"
        if valid and settings.admin_password_hash:
            try:
                valid = password_hasher.verify(
                    settings.admin_password_hash, data.password
                )
            except (VerifyMismatchError, InvalidHashError):
                valid = False
        else:
            valid = False
        if not valid:
            await asyncio.sleep(0.08)
            raise HTTPException(401, "Invalid administrator credentials")
        session = access.create_admin_session()
        set_session_cookies(response, session)
        return {"authenticated": True, "role": "admin"}

    @app.get("/api/auth/session")
    async def auth_session(request: Request):
        session = access.get_session(request.cookies.get(SESSION_COOKIE))
        if session is None:
            return {"authenticated": False, "role": None}
        return {
            "authenticated": True,
            "role": session.role,
            "lobby_id": session.lobby_id,
            "player_id": session.player_id,
        }

    @app.post("/api/auth/logout")
    async def logout(request: Request, response: Response):
        raw, session = session_from(request)
        require_csrf(request, raw)
        access.revoke_session(raw)
        if session.lobby_id and session.player_id:
            await hub.close_player(session.lobby_id, session.player_id)
        clear_session_cookies(response)
        return {"ok": True}

    @app.post("/api/lobbies")
    async def create_lobby(request: Request):
        raw, _ = require_admin(request, mutation=True)
        rate_limit(request, "create", 6)
        lobby, token = lobbies.create_lobby()
        try:
            invitations = access.create_lobby_invitations(
                raw, lobby.id, lobby.host_player_id
            )
        except Exception:
            lobbies.delete_lobby(lobby.id)
            raise
        return {
            "lobby": snapshot(lobby.id),
            "player_id": lobby.host_player_id,
            "token": token,
            "invitations": [
                {
                    "id": item.id,
                    "secret": item.secret,
                    "slot": item.slot,
                    "expires_at": item.expires_at,
                    "status": "unused",
                }
                for item in invitations
            ],
        }

    @app.post("/api/lobbies/join")
    async def blocked_pin_join(request: Request, data: JoinRequest):
        session_from(request)
        raise HTTPException(403, "A valid friend invitation is required")

    @app.post("/api/invitations/redeem")
    async def redeem_invitation(
        request: Request, data: RedeemRequest, response: Response
    ):
        require_origin(request.headers)
        rate_limit(request, "redeem", 12)

        def join(lobby_id: str) -> RedeemedPlayer:
            lobby, player_token = lobbies.join_lobby(lobby_id)
            player = lobbies.authenticate(lobby.id, player_token)
            return RedeemedPlayer(player.id, player_token, lobby.id)

        try:
            session, redeemed = access.redeem_invitation(data.secret, join)
        except (InvitationExpired, InvitationRevoked) as exc:
            raise HTTPException(410, str(exc)) from exc
        except InvitationUsed as exc:
            raise HTTPException(409, str(exc)) from exc
        except InvitationError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(410, "This lobby is no longer available") from exc
        set_session_cookies(response, session)
        return {
            "lobby": snapshot(redeemed.lobby_id),
            "player_id": redeemed.player_id,
            "token": redeemed.token,
        }

    @app.get("/api/lobbies/{lobby_id}")
    async def get_lobby(request: Request, lobby_id: str):
        require_lobby(request, lobby_id)
        lock = hub.lock_for(lobby_id)
        async with lock:
            try:
                return snapshot(lobby_id)
            except KeyError as exc:
                raise HTTPException(404, "Lobby not found") from exc

    @app.get("/api/lobbies/{lobby_id}/credentials")
    async def get_credentials(request: Request, lobby_id: str):
        session = require_lobby(request, lobby_id)
        try:
            lobby = lobbies.get_lobby(lobby_id)
            player_id = (
                lobby.host_player_id
                if session.role == "admin"
                else session.player_id
            )
            if player_id is None:
                raise KeyError
            return {
                "lobby_id": lobby.id,
                "player_id": player_id,
                "token": lobbies.token_for_player(lobby.id, player_id),
            }
        except KeyError as exc:
            raise HTTPException(
                404, "Lobby access is no longer available"
            ) from exc

    @app.get("/api/lobbies/{lobby_id}/invitations")
    async def list_invitations(request: Request, lobby_id: str):
        require_admin(request)
        try:
            lobbies.get_lobby(lobby_id)
        except KeyError as exc:
            raise HTTPException(404, "Lobby not found") from exc
        return {"invitations": access.list_invitations(lobby_id)}

    @app.post("/api/lobbies/{lobby_id}/invitations/{invitation_id}/revoke")
    async def revoke_invitation(
        request: Request, lobby_id: str, invitation_id: str
    ):
        require_admin(request, mutation=True)
        if not access.revoke_invitation(lobby_id, invitation_id):
            raise HTTPException(409, "Invitation is not available to revoke")
        return {"ok": True}

    @app.post("/api/lobbies/{lobby_id}/players/{player_id}/revoke")
    async def revoke_player(request: Request, lobby_id: str, player_id: str):
        require_admin(request, mutation=True)
        try:
            lobby = lobbies.get_lobby(lobby_id)
        except KeyError as exc:
            raise HTTPException(404, "Lobby not found") from exc
        if player_id == lobby.host_player_id:
            raise HTTPException(400, "The host cannot revoke themselves")
        if not access.revoke_player(lobby_id, player_id):
            raise HTTPException(404, "Player access is not active")
        player = next(
            (item for item in lobby.game.players if item.id == player_id), None
        )
        if player:
            player.connected = False
        await hub.close_player(lobby_id, player_id)
        await publish(lobby_id)
        return {"ok": True}

    @app.post("/api/lobbies/{lobby_id}/leave")
    async def leave_lobby(request: Request, response: Response, lobby_id: str):
        raw, session = session_from(request)
        require_csrf(request, raw)
        if session.role != "guest" or session.lobby_id != lobby_id:
            raise HTTPException(403, "Only a friend may leave this lobby")
        access.revoke_session(raw)
        if session.player_id:
            try:
                lobby = lobbies.get_lobby(lobby_id)
                player = next(
                    (
                        item for item in lobby.game.players
                        if item.id == session.player_id
                    ),
                    None,
                )
                if player:
                    player.connected = False
                await hub.close_player(lobby_id, session.player_id)
                await publish(lobby_id)
            except KeyError:
                pass
        clear_session_cookies(response)
        return {"ok": True}

    @app.websocket("/ws/lobbies/{lobby_id}")
    async def game_socket(websocket: WebSocket, lobby_id: str):
        origin = (websocket.headers.get("origin") or "").rstrip("/")
        if origin not in settings.allowed_origins:
            await websocket.close(code=4403)
            return
        raw_access = websocket.cookies.get(SESSION_COOKIE)
        access_session = access.authorize_lobby(raw_access, lobby_id)
        if access_session is None:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        try:
            auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
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
                lobby = lobbies.get_lobby(lobby_id)
            except (KeyError, PermissionError):
                await websocket.close(code=4401)
                return
            expected_player = (
                lobby.host_player_id
                if access_session.role == "admin"
                else access_session.player_id
            )
            if player.id != expected_player:
                await websocket.close(code=4403)
                return
            previous = hub.attach(lobby_id, player.id, websocket)
            if previous is not None and previous is not websocket:
                try:
                    await previous.close(code=4001)
                except (RuntimeError, OSError):
                    pass
            player.connected = True
            lobbies.touch(lobby_id)
            await websocket.send_json(
                {
                    "type": "welcome",
                    **lobbies.private_state(lobby_id, token),
                }
            )
            await publish(lobby_id)
        try:
            while True:
                message = await websocket.receive_json()
                async with lock:
                    current_access = access.authorize_lobby(
                        raw_access, lobby_id
                    )
                    expected = (
                        lobby.host_player_id
                        if current_access and current_access.role == "admin"
                        else current_access.player_id if current_access else None
                    )
                    if current_access is None or expected != player.id:
                        await websocket.close(code=4403)
                        break
                    if not hub.is_current(lobby_id, player.id, websocket):
                        await websocket.close(code=4001)
                        break
                    try:
                        lobby = lobbies.get_lobby(lobby_id)
                        if not isinstance(message, dict):
                            raise ValueError("Invalid message")
                        action = message.get("type")
                        if action == "start":
                            invited_players = {
                                item.id for item in lobby.game.players
                                if item.id != lobby.host_player_id
                            }
                            if not invited_players.issubset(
                                access.active_guest_player_ids(lobby.id)
                            ):
                                raise ValueError(
                                    "All four players need active access"
                                )
                            lobbies.start_lobby(lobby.id, token)
                        elif action == "rematch":
                            if player.id != lobby.host_player_id:
                                raise PermissionError("Only the host can start a rematch")
                            if lobby.game.status != GameStatus.FINISHED:
                                raise ValueError("The current match is not finished")
                            if len(lobby.game.players) != 4:
                                raise ValueError("Four players are required")
                            invited_players = {
                                item.id for item in lobby.game.players
                                if item.id != lobby.host_player_id
                            }
                            if not invited_players.issubset(
                                access.active_guest_player_ids(lobby.id)
                            ):
                                raise ValueError(
                                    "All four players need active access"
                                )
                            previous_task = gravity_tasks.get(lobby.id)
                            if previous_task is not None and not previous_task.done():
                                previous_task.cancel()
                            hub.timer_event(lobby.id).clear()
                            for participant in lobby.game.players:
                                participant.jokers.clear()
                            lobby.game = GameState(players=lobby.game.players)
                            deal_jokers(lobby.game.players)
                            lobby.game.status = GameStatus.PLAYING
                        elif action == "drop":
                            lane = message.get("lane")
                            if type(lane) is not int:
                                raise ValueError("Lane must be an integer")
                            play_turn(lobby.game, player.id, lane)
                        elif action == "joker":
                            joker = JokerType(message.get("joker"))
                            play_joker(
                                lobby.game,
                                player.id,
                                joker,
                                target=parse_position(message.get("target")),
                                second_target=parse_position(
                                    message.get("second_target")
                                ),
                            )
                            if joker == JokerType.GRAVITY_LOCK:
                                hub.timer_event(lobby.id).set()
                        elif action == "rename":
                            lobbies.rename_player(
                                lobby.id, token, message.get("username", "")
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
                        await websocket.send_json(
                            {"type": "error", "message": str(exc)}
                        )
                        continue
                    await publish(lobby.id)
                    if action in ("start", "rematch"):
                        for other in lobby.game.players:
                            await hub.send_to(
                                lobby.id,
                                other.id,
                                {
                                    "type": "hand",
                                    "jokers": [
                                        item.value for item in other.jokers
                                    ],
                                },
                            )
                        gravity_tasks[lobby.id] = asyncio.create_task(
                            gravity_loop(lobby.id)
                        )
                    elif action == "joker":
                        await hub.send_to(
                            lobby.id,
                            player.id,
                            {
                                "type": "hand",
                                "jokers": [
                                    item.value for item in player.jokers
                                ],
                            },
                        )
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            async with lock:
                if hub.detach(lobby_id, player.id, websocket):
                    try:
                        lobby = lobbies.get_lobby(lobby_id)
                    except KeyError:
                        lobby = None
                    if lobby is not None:
                        player.connected = False
                        await publish(lobby.id)

    return app


app = create_app()
