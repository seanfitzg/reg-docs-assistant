-- Schema for /store's Postgres instance. Runs automatically on first
-- container start (Postgres images execute every *.sql file found in
-- /docker-entrypoint-initdb.d, in filename order -- this is the only file
-- today, numbered so a second migration file would have an obvious place
-- to slot in later, per ADR-0020/0021/0022).

-- pgvector isn't used by any column yet (no embeddings column until a
-- follow-up issue picks an embedding model), but the extension is enabled
-- now so the image never needs to change later -- just a migration to add
-- the column, not a base-image swap.
CREATE EXTENSION IF NOT EXISTS vector;

-- Document (CONTEXT.md): an immutable record of one point-in-time
-- regulatory publication. Columns mirror /schema/document.schema.json.
--
-- active_chunking_generation_id points at whichever Chunking Generation
-- retrieval should currently search against (ADR-0004). It can't carry a
-- foreign key yet: chunking_generations (which it would reference) doesn't
-- exist until the next CREATE TABLE below. The constraint is added
-- separately once that table exists -- see the ALTER TABLE after it.
CREATE TABLE documents (
    id                             TEXT PRIMARY KEY,
    title                          TEXT NOT NULL,
    publisher                      TEXT NOT NULL,
    published_date                 DATE NOT NULL,
    source_url                     TEXT NOT NULL,
    active_chunking_generation_id  TEXT,
    supersedes                     TEXT REFERENCES documents (id)
);

-- Chunking Generation (CONTEXT.md, ADR-0021): the full set of Chunks
-- produced by one run of a chunking strategy over a Document. Not modelled
-- in /schema's JSON Schemas at all -- it only ever appears there as a bare
-- id referenced by Document/Chunk. Here it gets a real table so the
-- domain's own rules (a Document points at exactly one active Generation;
-- earlier Generations are never deleted, only superseded as "active") are
-- enforced by a foreign key, not just documented in prose.
--
-- chunking_strategy is CHECKed against the closed set ADR-0014 already
-- mandates at the manifest level (clause_numbered, heading_sections,
-- academic_sections) -- the same "constraints, not prose" reasoning this
-- file applies everywhere else, so a bad strategy name can't reach this
-- table even once a loader/direct-insert writes here without going
-- through ingestion's own dict-lookup guard.
CREATE TABLE chunking_generations (
    id                  TEXT PRIMARY KEY,
    document_id         TEXT NOT NULL REFERENCES documents (id),
    chunking_strategy   TEXT NOT NULL CHECK (
                             chunking_strategy IN (
                                 'clause_numbered',
                                 'heading_sections',
                                 'academic_sections'
                             )
                         ),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A plain FK on chunking_generations.id alone isn't enough to guarantee a
-- Generation actually belongs to the Document it's the *active* one for --
-- id is a global primary key, so it doesn't rule out pointing at a
-- Generation that belongs to some other Document. This UNIQUE constraint
-- gives (document_id, id) a distinct identity to pair against, which the
-- two composite foreign keys below both reference.
ALTER TABLE chunking_generations
    ADD CONSTRAINT uq_chunking_generations_document_id_id
    UNIQUE (document_id, id);

-- Now that chunking_generations exists, documents.active_chunking_generation_id
-- can finally get its foreign key -- the circular reference (a Document
-- points at its active Generation; a Generation points back at its
-- Document) can only be wired up in this order, one direction at a time.
--
-- This is a COMPOSITE key on (id, active_chunking_generation_id), matched
-- against chunking_generations (document_id, id) -- not just a plain FK on
-- active_chunking_generation_id alone. A plain FK would only prove the
-- pointed-to Generation exists *somewhere*, not that it belongs to *this*
-- Document; pairing documents.id into the same constraint forces the
-- match to be for this Document specifically. NULL is allowed (no active
-- Generation yet) since Postgres skips a multi-column FK check (MATCH
-- SIMPLE, the default) whenever any one of its columns is NULL.
ALTER TABLE documents
    ADD CONSTRAINT fk_documents_active_chunking_generation
    FOREIGN KEY (id, active_chunking_generation_id)
    REFERENCES chunking_generations (document_id, id);

-- Chunk (CONTEXT.md): an immutable retrieval/citation unit derived from a
-- Document. Columns mirror /schema/chunk.schema.json. No embedding column
-- yet -- deferred to the follow-up embeddings issue (ADR-0022 explains why
-- this is typed columns rather than the JSONB shape the audit-event store
-- uses).
--
-- Same composite-key reasoning as documents' active-pointer FK above:
-- document_id and chunking_generation_id each have their own plain FK (so
-- either one, read alone, still says something meaningful), but the
-- composite FK is what actually stops a Chunk from claiming a
-- Generation that belongs to a different Document than the Chunk itself
-- claims -- the failure mode the plain FKs alone can't catch.
CREATE TABLE chunks (
    id                      TEXT PRIMARY KEY,
    document_id             TEXT NOT NULL REFERENCES documents (id),
    chunking_generation_id  TEXT NOT NULL REFERENCES chunking_generations (id),
    locator                 TEXT NOT NULL,
    text                    TEXT NOT NULL,
    CONSTRAINT fk_chunks_document_chunking_generation
        FOREIGN KEY (document_id, chunking_generation_id)
        REFERENCES chunking_generations (document_id, id)
);

-- Retrieval's whole reason to exist is querying by these foreign keys
-- (which Chunks belong to a Document, which Generation is active) -- these
-- indexes support that from the start rather than being added reactively
-- once queries are slow. Primary keys are already indexed automatically;
-- these cover the foreign key columns, which Postgres does not index by
-- default.
CREATE INDEX idx_chunking_generations_document_id ON chunking_generations (document_id);
CREATE INDEX idx_chunks_document_id ON chunks (document_id);
CREATE INDEX idx_chunks_chunking_generation_id ON chunks (chunking_generation_id);
