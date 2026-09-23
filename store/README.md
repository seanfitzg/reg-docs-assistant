# /store

Postgres schema for RegDocs Assistant's persisted `Document`/`Chunk`/`Chunking Generation` records (`CONTEXT.md`, `/schema`). This is where ingestion's output actually lives once loaded — `ingestion/output`'s JSON is a regenerable projection (ADR-0012), not storage.

## Setup

```
cd store
docker compose up -d
```

`pgvector/pgvector:pg16` starts on `localhost:5432` (user/db `regdocs`, password `regdocs_dev_only` — local development only, not a real secret). The schema in `init/001_schema.sql` is applied automatically on first start via Postgres's `docker-entrypoint-initdb.d` mechanism; nothing else to run.

Connect with any Postgres client, e.g.:

```
docker compose exec postgres psql -U regdocs -d regdocs
```

**Init scripts only run once**, against an empty data volume. If you change `init/001_schema.sql` after the volume already has data, `docker compose up` will *not* re-apply it — reset first:

```
docker compose down -v
docker compose up -d
```

## Layout

- `docker-compose.yml` — the Postgres+pgvector container definition.
- `init/001_schema.sql` — the schema: `documents`, `chunking_generations`, `chunks`, with foreign keys and indexes. Plain SQL, no migration framework (see ADR-0020/0021/0022) — a second file (`002_...sql`) is where the next schema change would go, once there's an actual sequence of changes to apply in order.

Not built yet: a loader to actually populate this from `ingestion/output`, and the `embedding` column pgvector's extension is standing by for — both tracked as follow-up issues to #17.
