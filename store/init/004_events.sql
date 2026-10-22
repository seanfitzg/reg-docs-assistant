-- Events (CONTEXT.md, ADR-0031): one append-only table for every Event type.
--
-- recorded_at is the database's clock, not the caller's: the Event schema has
-- no timestamp, and a database-side one can't be forged or skewed by the
-- application. payload is the full Event exactly as validated against /schema;
-- the application validates, the database does not re-check its shape.
CREATE TABLE events (
    id           TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload      JSONB NOT NULL
);

CREATE INDEX idx_events_event_type ON events (event_type);

-- "Never edited after being written" (ADR-0001) is enforced here rather than
-- by convention, so no buggy query or hand-typed statement can break it.
-- A correction is a new Event. FOR EACH ROW triggers don't fire on TRUNCATE,
-- which is how store/src/regdocs_store/testing.py clears regdocs_test.
CREATE FUNCTION reject_event_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'events is append-only: % is not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER events_are_immutable
    BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION reject_event_change();

-- Same replicate-into-regdocs_test guard as 003_chunk_embeddings.sql.
\if :{?applied_to_test}
\else
    \set applied_to_test 1
    \c regdocs_test
    \i /docker-entrypoint-initdb.d/004_events.sql
\endif
