# Chunks are immutable; re-chunking produces a fresh set, not overwrites

Reprocessing a `Document` with a new chunking strategy always produces a fresh, additional set of `Chunk` records — existing `Chunk`s are never overwritten or deleted, the same immutability rule already applied to `Event` (ADR-0001) and `Document` (ADR-0002).

This is required by `Replay`, which pins the exact chunk text a query retrieved, not just a `chunk_id`. If `Chunk`s were mutable, changing the chunking strategy later could silently repoint an old `Event`'s `chunk_id` at unrelated text, breaking `Replay` and `Agreement Check` for every query answered before the change. The cost: storage keeps every generation of Chunks (and their embeddings) for a Document indefinitely, and retrieval must always target the current/active generation rather than accidentally pulling from a stale one — which generation is "active" isn't decided yet.
