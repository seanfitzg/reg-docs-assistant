# Document tracks its active Chunking Generation via a pointer field

A `Document` carries `active_chunking_generation_id`, naming which Chunking Generation retrieval should search against. Set at ingestion and updated only when a Document is deliberately reprocessed with a new chunking strategy.

This was chosen over an `is_active` flag on each Chunk/generation record: a single pointer on `Document` is one field to keep consistent, versus a flag that could — through a bug in the reprocessing step — end up true on more than one generation at once, or false on all of them. Earlier generations stay in storage untouched (ADR-0003), simply excluded from retrieval by not being the pointed-to generation.
