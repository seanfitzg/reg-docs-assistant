# The events table's guarantees (issue #44, ADR-0031), tested directly in SQL:
# UPDATE and DELETE are rejected, and recorded_at is stamped by the database.

import json

import psycopg
import pytest
from regdocs_store.testing import (
    DB_URL,
    clean_db,  # noqa: F401
    requires_postgres,
)

pytestmark = requires_postgres


def _insert_event(conn, event_id="event-1"):
    payload = {"id": event_id, "event_type": "QueryAnswered"}
    conn.execute(
        "INSERT INTO events (id, event_type, payload) VALUES (%s, %s, %s)",
        (event_id, "QueryAnswered", json.dumps(payload)),
    )


def test_update_on_events_is_rejected(clean_db):  # noqa: F811
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        _insert_event(conn)

        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute("UPDATE events SET event_type = 'AnswerOverridden'")


def test_delete_on_events_is_rejected(clean_db):  # noqa: F811
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        _insert_event(conn)

        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            conn.execute("DELETE FROM events")

        count = conn.execute("SELECT count(*) FROM events").fetchone()[0]
        assert count == 1


def test_recorded_at_is_stamped_by_the_database(clean_db):  # noqa: F811
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        _insert_event(conn)

        within_a_minute = conn.execute(
            "SELECT recorded_at BETWEEN now() - interval '1 minute' AND now() "
            "FROM events"
        ).fetchone()[0]

        assert within_a_minute
