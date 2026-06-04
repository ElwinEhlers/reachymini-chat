"""Storage and retrieval of facts — person-specific or global."""

from .database import get_connection


def add_fact(content: str, person_id: int | None = None) -> int:
    """Store a fact and return its id.

    Pass person_id to associate with a specific person; None for global facts.
    """
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO facts (person_id, content) VALUES (?, ?)",
        (person_id, content),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_facts(person_id: int | None = None) -> list[dict]:
    """Return facts as a list of dicts.

    person_id=None  → only global facts (person_id IS NULL)
    person_id=X     → only facts belonging to person X
    """
    conn = get_connection()
    if person_id is None:
        rows = conn.execute(
            "SELECT * FROM facts WHERE person_id IS NULL ORDER BY created_at",
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM facts WHERE person_id = ? ORDER BY created_at",
            (person_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_fact(fact_id: int) -> None:
    """Delete a fact by id."""
    conn = get_connection()
    conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    conn.commit()
