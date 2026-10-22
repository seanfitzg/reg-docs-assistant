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
