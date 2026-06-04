"""Conversation and message logging."""

from .database import get_connection


def start_conversation(person_id: int | None = None) -> int:
    """Open a new conversation and return its id."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO conversations (person_id) VALUES (?)",
        (person_id,),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def end_conversation(conversation_id: int) -> None:
    """Set ended_at for a conversation."""
    conn = get_connection()
    conn.execute(
        "UPDATE conversations SET ended_at = CURRENT_TIMESTAMP WHERE id = ?",
        (conversation_id,),
    )
    conn.commit()


def log_message(conversation_id: int, role: str, content: str) -> None:
    """Append a message to a conversation."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (conversation_id, role, content),
    )
    conn.commit()


def get_recent_messages(conversation_id: int, limit: int = 20) -> list[dict]:
    """Return the most recent messages for a conversation, oldest first."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT role, content, created_at FROM messages
        WHERE conversation_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (conversation_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]
