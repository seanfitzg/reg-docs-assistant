# Persisting to /store is a separate loader, not a step inside ingestion

`/store`'s loader reads `ingestion/output`'s `Document`/`Chunk` JSON and writes it into Postgres, as its own standalone script — not a new step wired into `ingestion/pipeline.py`'s `run_pipeline`.

Ingestion's job stays exactly what it already is: PDFs in, schema-validated JSON out, fully regenerable from the corpus plus `manifest.json` (ADR-0012's projection analogy). Coupling it to a live Postgres connection would mean ingestion can no longer run — or be tested — without a database up, and would blur a pure transformation step with a stateful write. Keeping the loader separate also means it can be re-run against existing output on its own (e.g. after a `/store` schema change) without re-parsing every PDF, and leaves the door open for a second track to read the same JSON output independently later without going through this loader at all.
