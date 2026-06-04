"""Reachy persistent memory system — SQLite-backed storage for persons, conversations and facts."""

from .database import init_db
from .persons import create_person, ensure_default_person, get_person, update_last_seen, list_persons, set_attribute, get_attributes
from .conversations import start_conversation, end_conversation, log_message, get_recent_messages
from .facts import add_fact, get_facts, delete_fact
from .context import build_system_prompt

__all__ = [
    "init_db",
    "create_person",
    "ensure_default_person",
    "get_person",
    "update_last_seen",
    "list_persons",
    "set_attribute",
    "get_attributes",
    "start_conversation",
    "end_conversation",
    "log_message",
    "get_recent_messages",
    "add_fact",
    "get_facts",
    "delete_fact",
    "build_system_prompt",
]
