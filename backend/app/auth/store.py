from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from app.config import Settings


T = TypeVar("T")


class InvitationError(ValueError):
    code = "invalid"


class InvitationExpired(InvitationError):
    code = "expired"


class InvitationUsed(InvitationError):
    code = "used"


class InvitationRevoked(InvitationError):
    code = "revoked"


@dataclass(frozen=True)
class AccessSession:
    token_hash: str
    role: str
    lobby_id: str | None
    player_id: str | None
    expires_at: float


@dataclass(frozen=True)
class SessionMaterial:
    token: str
    csrf_token: str
    expires_at: float
    role: str
    lobby_id: str | None
    player_id: str | None


@dataclass(frozen=True)
class InvitationMaterial:
    id: str
    secret: str
    expires_at: float
    slot: int


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AccessStore:
    """SQLite-backed access state. Raw bearer secrets are never persisted."""

    def __init__(
        self,
        settings: Settings,
        clock: Callable[[], float] = time.time,
    ):
        self.settings = settings
        self.clock = clock
        self._lock = threading.RLock()
        path = Path(settings.database_path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        self.path = str(path)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(
            self.path,
            timeout=10,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connect() as database:
            database.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    csrf_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'guest')),
                    lobby_id TEXT,
                    player_id TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked_at REAL
                );
                CREATE TABLE IF NOT EXISTS invitations (
                    id TEXT PRIMARY KEY,
                    secret_hash TEXT NOT NULL UNIQUE,
                    lobby_id TEXT NOT NULL,
                    slot INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 3),
                    status TEXT NOT NULL CHECK (status IN ('unused', 'used', 'revoked')),
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    redeemed_session_hash TEXT,
                    UNIQUE (lobby_id, slot)
                );
                CREATE INDEX IF NOT EXISTS sessions_lobby_idx
                    ON sessions(lobby_id, player_id);
                CREATE INDEX IF NOT EXISTS invitations_lobby_idx
                    ON invitations(lobby_id);
                """
            )
        if Path(self.path).exists():
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    def _new_session(
        self,
        database: sqlite3.Connection,
        role: str,
        lobby_id: str | None = None,
        player_id: str | None = None,
    ) -> SessionMaterial:
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        now = self.clock()
        duration = (
            self.settings.admin_session_seconds
            if role == "admin"
            else self.settings.guest_session_seconds
        )
        expires_at = now + duration
        database.execute(
            """INSERT INTO sessions
               (token_hash, csrf_hash, role, lobby_id, player_id,
                created_at, expires_at, revoked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (
                digest(token), digest(csrf), role, lobby_id, player_id,
                now, expires_at,
            ),
        )
        return SessionMaterial(
            token, csrf, expires_at, role, lobby_id, player_id
        )

    def create_admin_session(self) -> SessionMaterial:
        with self._lock, self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            session = self._new_session(database, "admin")
            database.commit()
            return session

    def get_session(self, token: str | None) -> AccessSession | None:
        if not token:
            return None
        now = self.clock()
        with self._lock, self._connect() as database:
            row = database.execute(
                """SELECT token_hash, role, lobby_id, player_id, expires_at
                   FROM sessions
                   WHERE token_hash = ? AND revoked_at IS NULL
                         AND expires_at > ?""",
                (digest(token), now),
            ).fetchone()
        if row is None:
            return None
        return AccessSession(**dict(row))

    def validate_csrf(self, token: str, csrf: str | None) -> bool:
        if not csrf:
            return False
        with self._lock, self._connect() as database:
            row = database.execute(
                """SELECT 1 FROM sessions
                   WHERE token_hash = ? AND csrf_hash = ?
                         AND revoked_at IS NULL AND expires_at > ?""",
                (digest(token), digest(csrf), self.clock()),
            ).fetchone()
        return row is not None

    def create_lobby_invitations(
        self,
        admin_token: str,
        lobby_id: str,
        player_id: str,
    ) -> list[InvitationMaterial]:
        now = self.clock()
        expires_at = now + self.settings.invite_seconds
        invitations: list[InvitationMaterial] = []
        with self._lock, self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            admin_hash = digest(admin_token)
            result = database.execute(
                """UPDATE sessions SET lobby_id = ?, player_id = ?
                   WHERE token_hash = ? AND role = 'admin'
                         AND revoked_at IS NULL AND expires_at > ?""",
                (lobby_id, player_id, admin_hash, now),
            )
            if result.rowcount != 1:
                database.rollback()
                raise PermissionError("Admin session is not active")
            for slot in range(1, 4):
                invite_id = secrets.token_urlsafe(12)
                secret = secrets.token_urlsafe(48)
                database.execute(
                    """INSERT INTO invitations
                       (id, secret_hash, lobby_id, slot, status,
                        created_at, expires_at, redeemed_session_hash)
                       VALUES (?, ?, ?, ?, 'unused', ?, ?, NULL)""",
                    (
                        invite_id, digest(secret), lobby_id, slot,
                        now, expires_at,
                    ),
                )
                invitations.append(
                    InvitationMaterial(invite_id, secret, expires_at, slot)
                )
            database.commit()
        return invitations

    def list_invitations(self, lobby_id: str) -> list[dict]:
        now = self.clock()
        with self._lock, self._connect() as database:
            rows = database.execute(
                """SELECT id, slot, status, expires_at
                   FROM invitations WHERE lobby_id = ? ORDER BY slot""",
                (lobby_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "slot": row["slot"],
                "status": (
                    "expired"
                    if row["status"] == "unused" and row["expires_at"] <= now
                    else row["status"]
                ),
                "expires_at": row["expires_at"],
            }
            for row in rows
        ]

    def redeem_invitation(
        self,
        secret: str,
        join: Callable[[str], T],
    ) -> tuple[SessionMaterial, T]:
        if not isinstance(secret, str) or not 40 <= len(secret) <= 128:
            raise InvitationError("Invitation is invalid")
        now = self.clock()
        with self._lock, self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                """SELECT id, lobby_id, status, expires_at
                   FROM invitations WHERE secret_hash = ?""",
                (digest(secret),),
            ).fetchone()
            if row is None:
                database.rollback()
                raise InvitationError("Invitation is invalid")
            if row["status"] == "used":
                database.rollback()
                raise InvitationUsed("Invitation has already been used")
            if row["status"] == "revoked":
                database.rollback()
                raise InvitationRevoked("Invitation was revoked")
            if row["expires_at"] <= now:
                database.rollback()
                raise InvitationExpired("Invitation has expired")
            try:
                joined = join(row["lobby_id"])
                player_id = getattr(joined, "player_id")
                session = self._new_session(
                    database, "guest", row["lobby_id"], player_id
                )
                result = database.execute(
                    """UPDATE invitations
                       SET status = 'used', redeemed_session_hash = ?
                       WHERE id = ? AND status = 'unused'""",
                    (digest(session.token), row["id"]),
                )
                if result.rowcount != 1:
                    raise InvitationUsed("Invitation has already been used")
                database.commit()
                return session, joined
            except Exception:
                database.rollback()
                raise

    def revoke_invitation(self, lobby_id: str, invitation_id: str) -> bool:
        with self._lock, self._connect() as database:
            result = database.execute(
                """UPDATE invitations SET status = 'revoked'
                   WHERE id = ? AND lobby_id = ? AND status = 'unused'""",
                (invitation_id, lobby_id),
            )
        return result.rowcount == 1

    def revoke_player(self, lobby_id: str, player_id: str) -> bool:
        with self._lock, self._connect() as database:
            result = database.execute(
                """UPDATE sessions SET revoked_at = ?
                   WHERE role = 'guest' AND lobby_id = ? AND player_id = ?
                         AND revoked_at IS NULL""",
                (self.clock(), lobby_id, player_id),
            )
        return result.rowcount > 0

    def active_guest_player_ids(self, lobby_id: str) -> set[str]:
        """Return players whose invitation-backed session remains active."""
        with self._lock, self._connect() as database:
            rows = database.execute(
                """SELECT player_id FROM sessions
                   WHERE role = 'guest' AND lobby_id = ?
                         AND player_id IS NOT NULL AND revoked_at IS NULL
                         AND expires_at > ?""",
                (lobby_id, self.clock()),
            ).fetchall()
        return {row["player_id"] for row in rows}

    def revoke_session(self, token: str) -> AccessSession | None:
        session = self.get_session(token)
        if session is None:
            return None
        with self._lock, self._connect() as database:
            database.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token_hash = ?",
                (self.clock(), session.token_hash),
            )
        return session

    def authorize_lobby(
        self, token: str | None, lobby_id: str
    ) -> AccessSession | None:
        session = self.get_session(token)
        if session is None:
            return None
        if session.role == "admin" or session.lobby_id == lobby_id:
            return session
        return None

    def purge_orphans(self, active_lobby_ids: set[str]) -> None:
        with self._lock, self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            rows = database.execute(
                "SELECT DISTINCT lobby_id FROM invitations"
            ).fetchall()
            orphaned = {
                row["lobby_id"] for row in rows
                if row["lobby_id"] not in active_lobby_ids
            }
            for lobby_id in orphaned:
                database.execute(
                    "DELETE FROM invitations WHERE lobby_id = ?", (lobby_id,)
                )
                database.execute(
                    """UPDATE sessions SET revoked_at = ?
                       WHERE role = 'guest' AND lobby_id = ?
                             AND revoked_at IS NULL""",
                    (self.clock(), lobby_id),
                )
                database.execute(
                    """UPDATE sessions SET lobby_id = NULL, player_id = NULL
                       WHERE role = 'admin' AND lobby_id = ?""",
                    (lobby_id,),
                )
            database.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (self.clock(),)
            )
            database.commit()
