# /store

Postgres schema for RegDocs Assistant's persisted `Document`/`Chunk`/`Chunking Generation` records (`CONTEXT.md`, `/schema`). This is where ingestion's output actually lives once loaded — `ingestion/output`'s JSON is a regenerable projection (ADR-0012), not storage.

## Setup

```
cd store
docker compose up -d
```

`pgvector/pgvector:pg16` starts on `localhost:5432` (user/db `regdocs`, password `regdocs_dev_only` — local development only, not a real secret). Two databases are created automatically on first start via Postgres's `docker-entrypoint-initdb.d` mechanism: `regdocs` (real data, schema from `init/001_schema.sql`) and `regdocs_test` (same schema, always empty — for the test suite, see **Running the tests**); nothing manual to run.

Connect with any Postgres client, e.g.:

```
docker compose exec postgres psql -U regdocs -d regdocs
```

**Init scripts only run once**, against an empty data volume. If you change `init/001_schema.sql` after the volume already has data, `docker compose up` will *not* re-apply it — reset first:

```
docker compose down -v
docker compose up -d
```

## Loading data

```
python -m venv store/.venv
store/.venv/Scripts/activate      # Windows
# source store/.venv/bin/activate # macOS/Linux
pip install -r store/requirements.txt
```

With the container up and `ingestion/output` already generated (see `ingestion/README.md`):

```
python store/loader.py
```

Reads `ingestion/output`'s `Document`/`Chunk` JSON plus `ingestion/manifest.json` (for `chunking_strategy` — the one field ingestion's JSON output doesn't itself carry, ADR-0014) and loads everything into the schema above, keyed by each record's own deterministic id. Safe to run repeatedly: `documents`/`chunking_generations`/`chunks` are each immutable once written, so a conflicting id is always skipped, never overwritten — nothing is ever deleted or edited in place, only added (see `loader.py`'s own docstrings for the exact semantics and the one deliberate exception: a Document's *active* Chunking Generation pointer, which is expected to change over time, ADR-0004).

Point it at a different database with the `STORE_DATABASE_URL` environment variable (default matches `docker-compose.yml`'s local credentials, database `regdocs`).

## Running the tests

```
python -m pytest store/tests
```

Needs the container from **Setup** running. Tests run against `regdocs_test`, not `regdocs` — **running the suite never touches or wipes any real data you've loaded** into `regdocs`. Tests that need Postgres skip themselves (not fail) if it isn't reachable, the same pattern `ingestion/tests` uses for corpus PDFs — see `store/tests/test_loader.py`.

## Layout

- `docker-compose.yml` — the Postgres+pgvector container definition.
- `init/001_schema.sql` — the schema: `documents`, `chunking_generations`, `chunks`, with foreign keys and indexes. Plain SQL, no migration framework (see ADR-0020/0021/0022).
- `init/002_test_database.sql` — creates `regdocs_test`, schema-identical to `regdocs`, for test isolation. A third file (`003_...sql`) is where the next real schema change would go, once there's an actual sequence of changes to apply in order.
- `loader.py` — reads `ingestion/output` + `ingestion/manifest.json`, loads into the schema above. Standalone (ADR-0020) — not a step inside `ingestion/pipeline.py`.
- `tests/` — one integration test file (`test_loader.py`) exercising `loader.py`'s single seam, `load_store`, end-to-end against a real (but isolated) Postgres database.

Not built yet: the `embedding` column pgvector's extension is standing by for, and a retrieval/query API against this data — both tracked as follow-up issues to #17.
