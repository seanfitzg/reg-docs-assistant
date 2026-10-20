# Events are one append-only JSONB table, with immutability enforced by the database

Every Event (`QueryAnswered`, `AnswerOverridden`, `EventFlagged`) is a row in a single `events` table in `/store`, added by `store/init/004_events.sql`:

- `id` (text, primary key), taken from the Event itself.
- `event_type` (text), a real column so "show me every override" needs no JSON digging.
- `recorded_at` (timestamptz, default `now()`), stamped by the database on insert.
- `payload` (jsonb), the full Event exactly as validated against `/schema`.

A trigger raises an error on any `UPDATE` or `DELETE`. The application validates each Event against its JSON Schema before inserting; the database does not re-check the payload's shape.

This follows ADR-0022: Events are the one place JSONB is right, because their shape varies by `event_type` and a fixed column set can't hold all three. `event_type` and `recorded_at` are the exceptions, pulled out because they are what audit queries filter on first.

`recorded_at` is a column, not an Event field, because the Event schema deliberately has no timestamp. A database-side clock also can't be forged or skewed by the caller.

Immutability is enforced by a trigger rather than by convention. "Never edited after being written" (ADR-0001) is the property the whole audit trail rests on, and a convention only holds until one buggy query, hand-typed statement or future track breaks it silently. The trigger makes it hold against all of them, the way an event store with no update operation does. The cost is that a genuine mistake can't be fixed in place, which is the point: a correction is a new Event.

Querying into `payload` (for example "every answer that cited document X") uses Postgres JSONB operators. A GIN index is deferred until a query is actually slow.
