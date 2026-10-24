# The Event writer (issue #44, ADR-0031): validate an Event against its JSON
# Schema, then append it to the events table. The table is immutable (004),
# so a PII leak could never be cleaned up: callers must hand in an Event that
# answer_question has already Redacted (ADR-0008, ADR-0034), and validation
# is the last gate before the write.

import json
from pathlib import Path

import psycopg
from regdocs_schema.testing import load_json, validate

SCHEMA_DIR = Path(__file__).parents[3] / "schema"

SCHEMA_FILES = {
    "QueryAnswered": "event.schema.json",
    "EventFlagged": "event-flagged.schema.json",
    "AnswerOverridden": "answer-overridden.schema.json",
}


def read_event(event_id: str, db_url: str) -> dict | None:
    """Return the stored Event with this id, or None if there isn't one."""
    with psycopg.connect(db_url) as conn:
        row = conn.execute(
            "SELECT payload FROM events WHERE id = %s", (event_id,)
        ).fetchone()
    if row is None:
        return None
    return row[0]


def list_queries(db_url: str, limit: int, offset: int) -> tuple[list[dict], int]:
    """Return one page of QueryAnswered Events, newest first, and the total count.

    Each row is {"event_id", "recorded_at", "query"}; the query is the stored
    (already Redacted) text.
    """
    with psycopg.connect(db_url) as conn:
        total = conn.execute(
            "SELECT count(*) FROM events WHERE event_type = 'QueryAnswered'"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT id, recorded_at, payload->>'query' FROM events"
            " WHERE event_type = 'QueryAnswered'"
            " ORDER BY recorded_at DESC, id LIMIT %s OFFSET %s",
            (limit, offset),
        ).fetchall()
    items = []
    for event_id, recorded_at, query in rows:
        items.append(
            {
                "event_id": event_id,
                "recorded_at": recorded_at.isoformat(),
                "query": query,
            }
        )
    return items, total


def write_event(event: dict, db_url: str) -> None:
    """Validate `event` and append it to the events table.

    Raises jsonschema.ValidationError for an Event that fails its schema and
    ValueError for an unknown event_type; nothing is written in either case.
    recorded_at is left to the database's default.
    """
    event_type = event.get("event_type")
    if event_type not in SCHEMA_FILES:
        raise ValueError(f"unknown event_type: {event_type!r}")
    validate(event, load_json(SCHEMA_DIR / SCHEMA_FILES[event_type]))
    with psycopg.connect(db_url) as conn:
        conn.execute(
            "INSERT INTO events (id, event_type, payload) VALUES (%s, %s, %s)",
            (event["id"], event_type, json.dumps(event)),
        )
