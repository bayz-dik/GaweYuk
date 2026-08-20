from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )

        migrations_dir = Path(__file__).with_name("migrations")

        for path in sorted(migrations_dir.glob("*.sql")):
            version = path.stem

            exists = conn.execute(
                """
                SELECT 1
                FROM schema_migrations
                WHERE version = ?
                """,
                (version,),
            ).fetchone()

            if exists is not None:
                continue

            conn.executescript(path.read_text())

            conn.execute(
                """
                INSERT INTO schema_migrations (
                    version,
                    applied_at
                )
                VALUES (?, datetime('now'))
                """,
                (version,),
            )

    def initialize(self):
        schema = Path(__file__).with_name("schema.sql").read_text()

        with self._connect() as conn:
            conn.executescript(schema)
            self._apply_migrations(conn)

    @contextmanager
    def connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
