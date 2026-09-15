# Document metadata for ingestion is manifest-driven, not CLI-supplied

New documents enter the pipeline via a structured manifest (filename → title, publisher, published_date, supersedes), extending the existing `corpus/SOURCES.md` pattern, rather than as command-line flags passed to an ingest invocation per file. The pipeline ingests whatever's in the manifest but not yet reflected in the `Document` table, keyed by filename.

PDF text alone can't reliably supply this metadata (no consistent extractable title/publisher/date across the corpus), and `supersedes` links require a human judgment call a parser can't make safely — so per-document human input is unavoidable either way. A manifest makes that input durable and diffable (reviewable in a PR, with history), where CLI args leave no trace after the command has run once. It also gives the pipeline a free "what's new" check — diff manifest entries against ingested `Document` ids — without separate dedup logic.
