"""SQLite connection and schema setup for the Reachy memory system."""

import sqlite3
import threading
from pathlib import Path

DB_PATH = Path("/home/sbin/reachy/memory/reachy.db")

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with WAL mode and row factory."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def init_db() -> None:
    """Create all tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS persons (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            face_embedding BLOB,
            first_seen    DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS person_attributes (
            id         INTEGER  PRIMARY KEY AUTOINCREMENT,
            person_id  INTEGER  NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
            key        TEXT     NOT NULL,
            value      TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(person_id, key)
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER  PRIMARY KEY AUTOINCREMENT,
            person_id  INTEGER  REFERENCES persons(id) ON DELETE SET NULL,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at   DATETIME
        );

        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER  PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER  NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            TEXT     NOT NULL,
            content         TEXT     NOT NULL,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS facts (
            id         INTEGER  PRIMARY KEY AUTOINCREMENT,
            person_id  INTEGER  REFERENCES persons(id) ON DELETE CASCADE,
            content    TEXT     NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
