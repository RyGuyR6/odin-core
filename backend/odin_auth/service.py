from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import AuthSettings
from .database import AuthDatabase
from .security import (
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": datetime.fromisoformat(row["created_at"]),
        "last_login": (
            datetime.fromisoformat(row["last_login"]) if row["last_login"] else None
        ),
    }


class AuthService:
    def __init__(self, database: AuthDatabase, settings: AuthSettings):
        self.database = database
        self.settings = settings

    def bootstrap_required(self) -> bool:
        with self.database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return count == 0

    def bootstrap_admin(
        self, username: str, email: str, password: str
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] != 0:
                raise ValueError("Administrator bootstrap has already been completed")
            now = utcnow().isoformat()
            cursor = connection.execute(
                """
                INSERT INTO users
                    (username, email, password_hash, role, is_active, created_at)
                VALUES (?, ?, ?, 'admin', 1, ?)
                """,
                (username.strip(), email.strip().lower(), hash_password(password), now),
            )
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return row_to_user(row)

    def authenticate(self, identity: str, password: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM users
                WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
                """,
                (identity.strip(), identity.strip()),
            ).fetchone()
            if row is None or not row["is_active"]:
                return None
            if not verify_password(password, row["password_hash"]):
                return None
            now = utcnow().isoformat()
            connection.execute(
                "UPDATE users SET last_login = ? WHERE id = ?", (now, row["id"])
            )
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (row["id"],)
            ).fetchone()
        return row_to_user(row)

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return row_to_user(row) if row else None

    def create_refresh_session(self, user_id: int, remember_me: bool) -> str:
        token = create_refresh_token()
        now = utcnow()
        days = self.settings.refresh_days if remember_me else 1
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO refresh_sessions
                    (id, user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    create_refresh_token()[:32],
                    user_id,
                    hash_token(token),
                    (now + timedelta(days=days)).isoformat(),
                    now.isoformat(),
                ),
            )
        return token

    def consume_refresh_token(self, token: str) -> dict[str, Any] | None:
        digest = hash_token(token)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT s.*, u.*
                FROM refresh_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.revoked_at IS NULL
                """,
                (digest,),
            ).fetchone()
            if row is None or datetime.fromisoformat(row["expires_at"]) <= utcnow():
                return None
            connection.execute(
                "UPDATE refresh_sessions SET revoked_at = ? WHERE token_hash = ?",
                (utcnow().isoformat(), digest),
            )
        return self.get_user(int(row["user_id"]))

    def revoke_refresh_token(self, token: str | None) -> None:
        if not token:
            return
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE refresh_sessions SET revoked_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (utcnow().isoformat(), hash_token(token)),
            )

    def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None or not verify_password(
                current_password, row["password_hash"]
            ):
                return False
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(new_password), user_id),
            )
            connection.execute(
                """
                UPDATE refresh_sessions SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (utcnow().isoformat(), user_id),
            )
        return True
