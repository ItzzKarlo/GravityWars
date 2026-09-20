from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_secret(name: str, file_name: str) -> str:
    if value := os.getenv(name):
        return value.strip()
    path = os.getenv(file_name)
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return ""


@dataclass(frozen=True)
class Settings:
    database_path: str = "./data/access.sqlite3"
    admin_password_hash: str = ""
    environment: str = "development"
    cookie_secure: bool = False
    allowed_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    admin_session_seconds: int = 12 * 60 * 60
    guest_session_seconds: int = 3 * 60 * 60
    invite_seconds: int = 30 * 60
    gravity_min_seconds: float = 10.0
    gravity_max_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("APP_ENV", "development").strip().lower()
        origins = [
            origin.strip().rstrip("/")
            for origin in os.getenv(
                "ALLOWED_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            ).split(",")
            if origin.strip()
        ]
        settings = cls(
            database_path=os.getenv(
                "ACCESS_DATABASE_PATH",
                "./data/access.sqlite3",
            ),
            admin_password_hash=_read_secret(
                "ADMIN_PASSWORD_HASH",
                "ADMIN_PASSWORD_HASH_FILE",
            ),
            environment=environment,
            cookie_secure=(
                os.getenv("COOKIE_SECURE", "").lower()
                in {"1", "true", "yes"}
                or environment == "production"
            ),
            allowed_origins=tuple(origins),
            gravity_min_seconds=float(
                os.getenv("GRAVITY_MIN_SECONDS", "10")
            ),
            gravity_max_seconds=float(
                os.getenv("GRAVITY_MAX_SECONDS", "30")
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.environment == "production":
            if not self.admin_password_hash:
                raise RuntimeError(
                    "ADMIN_PASSWORD_HASH or ADMIN_PASSWORD_HASH_FILE "
                    "is required in production"
                )
            if not self.cookie_secure:
                raise RuntimeError("Secure cookies are required in production")
            if not self.allowed_origins:
                raise RuntimeError("ALLOWED_ORIGINS is required in production")
            if any(origin.startswith("http://") for origin in self.allowed_origins):
                raise RuntimeError("Production origins must use HTTPS")
        if not 0 < self.gravity_min_seconds <= self.gravity_max_seconds:
            raise RuntimeError("Gravity interval is invalid")
