"""CRUD operations for persons and their attributes."""

from .database import get_connection


def ensure_default_person(name: str = "Unbekannt") -> None:
    """Ensure person with id=1 exists; insert with explicit id if missing.

    Uses INSERT OR IGNORE so existing data is never overwritten.
    """
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO persons (id, name) VALUES (1, ?)",
        (name,),
    )
    conn.commit()


def create_person(name: str, face_embedding: bytes | None = None) -> int:
    """Insert a new person and return their id."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO persons (name, face_embedding) VALUES (?, ?)",
        (name, face_embedding),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_person(person_id: int) -> dict | None:
    """Return person row as dict or None if not found."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    return dict(row) if row else None


def update_last_seen(person_id: int) -> None:
    """Update last_seen timestamp for a person."""
    conn = get_connection()
    conn.execute(
        "UPDATE persons SET last_seen = CURRENT_TIMESTAMP WHERE id = ?",
        (person_id,),
    )
    conn.commit()


def list_persons() -> list[dict]:
    """Return all persons as a list of dicts."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM persons ORDER BY last_seen DESC").fetchall()
    return [dict(r) for r in rows]


def set_attribute(person_id: int, key: str, value: str) -> None:
    """Insert or replace a person attribute (upsert)."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO person_attributes (person_id, key, value, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(person_id, key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (person_id, key, value),
    )
    conn.commit()


def get_attributes(person_id: int) -> dict[str, str]:
    """Return all attributes for a person as {key: value}."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT key, value FROM person_attributes WHERE person_id = ? ORDER BY key",
        (person_id,),
    ).fetchall()
    return {r["key"]: r["value"] for r in rows}
