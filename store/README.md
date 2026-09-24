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

## Embedding chunks

`embed.py` computes a vector embedding (768 floats, via a local [Ollama](https://ollama.com) model, `nomic-embed-text`) for every Chunk in each Document's *active* Chunking Generation and stores them in `chunk_embeddings` (ADR-0024/0025/0026). It doesn't search anything — that's the later retrieval work.

One-time setup: install Ollama, then pull the model (a ~270 MB download):

```
ollama pull nomic-embed-text
```

Ollama serves on `http://localhost:11434` (running the desktop app or `ollama serve`). With that up, the container running, and data loaded by `loader.py`:

```
python store/embed.py
```

- Safe to re-run: a Chunk that already has an embedding for this model is skipped, never recomputed or overwritten, and each embedding is committed as it's computed — so after a crash a re-run resumes where it stopped.
- Fails loudly on the first error (Ollama not running, model not pulled) instead of skipping chunks, so a systemic problem shows up on the first Chunk.
- Env vars: `STORE_DATABASE_URL` (as for `loader.py`) and `OLLAMA_HOST` (default `http://localhost:11434`).
- The test suite never needs Ollama — it injects a fake client.

**Existing containers need the migration applied by hand.** `init/*.sql` only runs on an empty volume, so if your container predates `003`, either reset (`docker compose down -v`, then `up -d` — you'll need to re-run `loader.py`) or apply just the new file, which creates the table in both `regdocs` and `regdocs_test`:

```
docker compose exec postgres psql -U regdocs -d regdocs -f /docker-entrypoint-initdb.d/003_chunk_embeddings.sql
```

## Running the tests

```
python -m pytest store/tests
```

Needs the container from **Setup** running. Tests run against `regdocs_test`, not `regdocs` — **running the suite never touches or wipes any real data you've loaded** into `regdocs`. Tests that need Postgres skip themselves (not fail) if it isn't reachable, the same pattern `ingestion/tests` uses for corpus PDFs — see `store/tests/test_loader.py`.

## Layout

- `docker-compose.yml` — the Postgres+pgvector container definition.
- `init/001_schema.sql` — the schema: `documents`, `chunking_generations`, `chunks`, with foreign keys and indexes. Plain SQL, no migration framework (see ADR-0020/0021/0022).
- `init/002_test_database.sql` — creates `regdocs_test`, schema-identical to `regdocs`, for test isolation.
- `init/003_chunk_embeddings.sql` — the `chunk_embeddings` table (keyed by chunk + embedding model), applied to both databases.
- `db.py` — shared Postgres helpers (`DEFAULT_DB_URL`, `upsert_immutable`) used by `loader.py` and `embed.py`.
- `embed.py` — embeds active-generation Chunks via Ollama into `chunk_embeddings`. Standalone, like `loader.py`.
- `loader.py` — reads `ingestion/output` + `ingestion/manifest.json`, loads into the schema above. Standalone (ADR-0020) — not a step inside `ingestion/pipeline.py`.
- `tests/` — one integration test file per script (`test_loader.py`, `test_embed.py`), each exercising its script's single seam (`load_store`, `embed_chunks`) end-to-end against a real (but isolated) Postgres database.

Not built yet: a vector-similarity index (`hnsw`/`ivfflat`) and a retrieval/query API against the embeddings — follow-up work.
