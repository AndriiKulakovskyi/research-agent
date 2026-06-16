"""The initiative_id column must be added in-place to threads tables created by
older deployments, and applying the migration twice must be a no-op."""

import sqlite3

from deep_harness.server.db import AppDB


def _columns(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(threads)")}
    finally:
        conn.close()


def test_migration_upgrades_legacy_threads_table(tmp_path):
    db_path = tmp_path / "app.db"
    # Simulate a pre-initiatives schema: threads without initiative_id, one row.
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT, password_hash TEXT,
            salt TEXT, created_at REAL);
        CREATE TABLE threads (id TEXT PRIMARY KEY, user_id TEXT, title TEXT,
            created_at REAL, updated_at REAL);
        INSERT INTO users VALUES ('u1', 'alice', 'h', 's', 0.0);
        INSERT INTO threads VALUES ('t1', 'u1', 'old thread', 0.0, 0.0);
        """
    )
    legacy.commit()
    legacy.close()
    assert "initiative_id" not in _columns(db_path)

    # Opening through AppDB upgrades the table without losing data.
    db = AppDB(db_path)
    assert "initiative_id" in _columns(db_path)
    rows = db.list_threads("u1")
    assert len(rows) == 1 and rows[0]["title"] == "old thread"
    assert rows[0]["initiative_id"] is None

    # Idempotent: re-opening the already-migrated DB does not error or duplicate.
    AppDB(db_path)
    assert sorted(_columns(db_path)).count("initiative_id") == 1
