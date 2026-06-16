"""Application database (users, tokens, threads) on stdlib sqlite3.

Kept deliberately simple: short-lived connections per call, fine for the
request rates this app serves. Agent conversation state lives separately in
the LangGraph checkpointer database.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from deep_harness.crypto import encrypt_secret

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS initiatives (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    goal TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    initiative_id TEXT REFERENCES initiatives(id),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS user_settings (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    compute_backend TEXT NOT NULL DEFAULT 'local',
    gpu_type TEXT NOT NULL DEFAULT 'A10G',
    modal_token_id TEXT NOT NULL DEFAULT '',
    modal_token_secret TEXT NOT NULL DEFAULT '',
    gate_plan INTEGER NOT NULL DEFAULT 1,
    gate_training_jobs INTEGER NOT NULL DEFAULT 1,
    gate_shell INTEGER NOT NULL DEFAULT 1,
    updated_at REAL NOT NULL
);
"""

# Columns added to user_settings after its first release; backfilled on existing
# databases via ALTER TABLE (sqlite has no ADD COLUMN IF NOT EXISTS).
_USER_SETTINGS_MIGRATIONS = {
    "gate_plan": "INTEGER NOT NULL DEFAULT 1",
    "gate_training_jobs": "INTEGER NOT NULL DEFAULT 1",
    "gate_shell": "INTEGER NOT NULL DEFAULT 1",
}


class AppDB:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Idempotent in-place migrations for columns `CREATE TABLE IF NOT EXISTS`
        cannot add to tables that already exist in older deployments."""
        settings_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(user_settings)")
        }
        for column, ddl in _USER_SETTINGS_MIGRATIONS.items():
            if column not in settings_columns:
                conn.execute(f"ALTER TABLE user_settings ADD COLUMN {column} {ddl}")
        thread_columns = {row["name"] for row in conn.execute("PRAGMA table_info(threads)")}
        if "initiative_id" not in thread_columns:
            conn.execute("ALTER TABLE threads ADD COLUMN initiative_id TEXT")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # -- users ---------------------------------------------------------------

    def create_user(self, username: str, password_hash: str, salt: str) -> str:
        user_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                (user_id, username, password_hash, salt, time.time()),
            )
        return user_id

    def get_user_by_username(self, username: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    def get_user(self, user_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    # -- tokens --------------------------------------------------------------

    def store_token(self, token_hash: str, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO tokens VALUES (?, ?, ?)", (token_hash, user_id, time.time()))

    def get_user_id_for_token(self, token_hash: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return row["user_id"] if row else None

    def delete_token(self, token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM tokens WHERE token_hash = ?", (token_hash,))

    # -- user settings ---------------------------------------------------------

    def get_user_settings(self, user_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
            ).fetchone()

    def upsert_user_settings(
        self,
        user_id: str,
        compute_backend: str,
        gpu_type: str,
        modal_token_id: str | None,
        modal_token_secret: str | None,
        gate_plan: bool,
        gate_training_jobs: bool,
        gate_shell: bool,
    ) -> None:
        """Update settings; ``None`` for a token field keeps the stored value
        (so clients never have to echo secrets back). The Modal token secret is
        encrypted before storage (see deep_harness.crypto)."""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
            token_id = modal_token_id if modal_token_id is not None else (
                existing["modal_token_id"] if existing else ""
            )
            # A newly supplied secret is encrypted at rest; None means "keep the
            # already-encrypted value on file".
            token_secret = encrypt_secret(modal_token_secret) if modal_token_secret is not None else (
                existing["modal_token_secret"] if existing else ""
            )
            conn.execute(
                """INSERT INTO user_settings
                     (user_id, compute_backend, gpu_type, modal_token_id, modal_token_secret,
                      gate_plan, gate_training_jobs, gate_shell, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     compute_backend = excluded.compute_backend,
                     gpu_type = excluded.gpu_type,
                     modal_token_id = excluded.modal_token_id,
                     modal_token_secret = excluded.modal_token_secret,
                     gate_plan = excluded.gate_plan,
                     gate_training_jobs = excluded.gate_training_jobs,
                     gate_shell = excluded.gate_shell,
                     updated_at = excluded.updated_at""",
                (
                    user_id,
                    compute_backend,
                    gpu_type,
                    token_id,
                    token_secret,
                    int(gate_plan),
                    int(gate_training_jobs),
                    int(gate_shell),
                    time.time(),
                ),
            )

    # -- threads -------------------------------------------------------------

    def create_thread(
        self, user_id: str, title: str, initiative_id: str | None = None
    ) -> sqlite3.Row:
        thread_id = uuid.uuid4().hex
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO threads (id, user_id, title, initiative_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (thread_id, user_id, title, initiative_id, now, now),
            )
            return conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()

    def list_threads(self, user_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM threads WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
            ).fetchall()

    def get_thread(self, thread_id: str, user_id: str) -> sqlite3.Row | None:
        """Fetch a thread only if it belongs to `user_id` (ownership check)."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM threads WHERE id = ? AND user_id = ?", (thread_id, user_id)
            ).fetchone()

    def touch_thread(self, thread_id: str, title: str | None = None) -> None:
        with self._connect() as conn:
            if title:
                conn.execute(
                    "UPDATE threads SET updated_at = ?, title = ? WHERE id = ?",
                    (time.time(), title, thread_id),
                )
            else:
                conn.execute(
                    "UPDATE threads SET updated_at = ? WHERE id = ?", (time.time(), thread_id)
                )

    def delete_thread(self, thread_id: str, user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM threads WHERE id = ? AND user_id = ?", (thread_id, user_id)
            )
            return cur.rowcount > 0

    def set_thread_initiative(
        self, thread_id: str, user_id: str, initiative_id: str | None
    ) -> bool:
        """Move a thread into an initiative (or out of one when `initiative_id` is
        None). Ownership-scoped; returns False if the thread isn't the user's."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE threads SET initiative_id = ? WHERE id = ? AND user_id = ?",
                (initiative_id, thread_id, user_id),
            )
            return cur.rowcount > 0

    # -- initiatives ---------------------------------------------------------

    def create_initiative(self, user_id: str, name: str, goal: str = "") -> sqlite3.Row:
        initiative_id = uuid.uuid4().hex
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO initiatives (id, user_id, name, goal, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'active', ?, ?)",
                (initiative_id, user_id, name, goal, now, now),
            )
            return conn.execute(
                "SELECT * FROM initiatives WHERE id = ?", (initiative_id,)
            ).fetchone()

    def list_initiatives(self, user_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM initiatives WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
            ).fetchall()

    def get_initiative(self, initiative_id: str, user_id: str) -> sqlite3.Row | None:
        """Fetch an initiative only if it belongs to `user_id` (ownership check)."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM initiatives WHERE id = ? AND user_id = ?", (initiative_id, user_id)
            ).fetchone()

    def update_initiative(
        self,
        initiative_id: str,
        user_id: str,
        name: str | None = None,
        goal: str | None = None,
        status: str | None = None,
    ) -> sqlite3.Row | None:
        """Update the provided fields (leaving others untouched) and return the row,
        or None if the initiative isn't the user's."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM initiatives WHERE id = ? AND user_id = ?", (initiative_id, user_id)
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE initiatives SET name = ?, goal = ?, status = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ?",
                (
                    name if name is not None else row["name"],
                    goal if goal is not None else row["goal"],
                    status if status is not None else row["status"],
                    time.time(),
                    initiative_id,
                    user_id,
                ),
            )
            return conn.execute(
                "SELECT * FROM initiatives WHERE id = ?", (initiative_id,)
            ).fetchone()

    def delete_initiative(self, initiative_id: str, user_id: str) -> bool:
        """Delete an initiative; its threads survive and become unfiled."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM initiatives WHERE id = ? AND user_id = ?",
                (initiative_id, user_id),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE threads SET initiative_id = NULL WHERE initiative_id = ? AND user_id = ?",
                (initiative_id, user_id),
            )
            conn.execute("DELETE FROM initiatives WHERE id = ?", (initiative_id,))
            return True

    def count_threads_by_initiative(self, user_id: str) -> dict[str, int]:
        """Map initiative_id -> number of threads, for overview counts."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT initiative_id, COUNT(*) AS n FROM threads "
                "WHERE user_id = ? AND initiative_id IS NOT NULL GROUP BY initiative_id",
                (user_id,),
            ).fetchall()
        return {row["initiative_id"]: row["n"] for row in rows}
