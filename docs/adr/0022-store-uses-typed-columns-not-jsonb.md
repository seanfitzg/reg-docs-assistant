# /store uses typed columns for Document/Chunk, not JSONB

`documents`, `chunks`, and `chunking_generations` in `/store` are normal relational tables with one typed column per schema field — not JSONB blobs.

This deliberately departs from the audit-event store's design (portfolio plan): Events are stored as JSONB specifically because their shape varies by `event_type` (`QueryAnswered`, `AnswerOverridden`, `EventFlagged`, ...), so a fixed column set can't represent all of them. `Document` and `Chunk` don't have that problem — each has exactly one fixed shape, defined once in `/schema`. Retrieval and loading both need to filter and join on individual fields (`document_id`, `chunking_generation_id`, `active_chunking_generation_id`) from day one, which typed columns give directly, with Postgres enforcing foreign keys and NOT NULLs; a JSONB blob would push that validation back into application code for no benefit here.
