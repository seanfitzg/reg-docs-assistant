# Documents are immutable; amendments are new Documents linked by Supersedes

A `Document` is a single immutable record of one point-in-time regulatory publication — never edited in place, the same rule already applied to `Event` (ADR-0001). A regulatory amendment is ingested as a brand-new `Document` carrying a `Supersedes` link back to the one it replaces, rather than updating the existing `Document`'s content in place.

This preserves the audit trail's core guarantee: an `Event`'s `retrieved_chunks` records a `doc_id`, and because that `Document` never changes after ingestion, `doc_id` alone is always enough to recover exactly the text that was retrieved — no version number needed, no risk of a later edit silently invalidating a past `Replay`. The cost: every historical `Document` (and its Chunks and embeddings) stays in storage indefinitely, and ingestion needs an explicit step to record which prior `Document`, if any, a new one supersedes.
