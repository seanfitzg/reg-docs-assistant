# Shared Postgres helpers for /store's Python modules.
#
# Extracted from loader.py so the embeddings loader (ADR-0024) can reuse the
# same connection default and immutable-upsert helper instead of duplicating
# them. Like loader.py, this module never imports anything from /ingestion --
# /store has its own venv/requirements.txt (ADR-0020, ADR-0023).

from typing import Any

import psycopg

# The connection string /store's docker-compose.yml's local-dev credentials
# resolve to. Defined once, here, so nothing else needs to repeat the
# host/user/password by hand -- store/tests/test_loader.py derives its own
# default (a *different* database, for test isolation -- see
# store/init/002_test_database.sql) from this same constant, rather than
# hand-copying the credentials a second time.
DEFAULT_DB_URL = "postgresql://regdocs:regdocs_dev_only@localhost:5432/regdocs"


def upsert_immutable(
    cur: psycopg.Cursor,
    table: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    conflict_columns: list[str] | None = None,
) -> None:
    """Insert rows into `table`; silently skip any row whose key already exists.

    `conflict_columns` names the unique key a "duplicate" is detected on;
    it defaults to ["id"], which is what documents/chunking_generations/
    chunks use. A table keyed differently -- chunk_embeddings is keyed on
    (chunk_id, embedding_model), with no `id` column at all -- passes its
    own key here.

    documents, chunking_generations, and chunks are each immutable once
    written (CONTEXT.md), and chunk_embeddings follows the same "old stays"
    rule (ADR-0024), so unlike a typical upsert this never updates an
    existing row's content -- only inserts genuinely new ones. The two
    versions of a "conflicting" row are expected to already carry identical
    content, since every id here is derived deterministically from stable
    inputs (ingestion/ids.py), not chosen by hand or from row content.

    One consequence worth knowing: if a document's ingested JSON changes
    under the *same* id (e.g. a manifest typo gets fixed and ingestion is
    re-run without bumping any id), this loader will NOT apply that fix --
    the original row wins. That's intentional, not an oversight: per
    CONTEXT.md, a real correction to an already-loaded Document is supposed
    to be a *new* Document linked via `supersedes`, not a silent edit to
    the existing one.

    `table`, `columns`, and `conflict_columns` are always fixed literals from
    the call sites, never user input -- so building the SQL with an f-string here is
    safe. Only the *row values* need protecting against SQL injection, and
    those go through %(name)s placeholders, substituted safely by psycopg,
    never by string interpolation.
    """
    if not rows:
        return
    column_list = ", ".join(columns)
    # %(name)s is psycopg's named-parameter placeholder: each placeholder
    # names which key of a row dict it binds to, rather than relying on
    # positional order the way plain "%s, %s, %s" would. cur.executemany
    # runs the same parameterized statement once per row in `rows` -- one
    # Python call standing in for a hand-written loop of cur.execute(...)
    # calls, though it still issues one statement per row over the wire
    # (fine at this corpus's current size -- ~2000 Chunks load in seconds;
    # worth revisiting only if that ever becomes a real bottleneck).
    placeholders = ", ".join(f"%({column})s" for column in columns)
    conflict_list = ", ".join(conflict_columns or ["id"])
    cur.executemany(
        f"INSERT INTO {table} ({column_list}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_list}) DO NOTHING",
        rows,
    )
