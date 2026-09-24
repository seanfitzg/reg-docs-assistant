-- Chunk Embedding (CONTEXT.md, ADR-0024): a vector representation of one
-- Chunk's text, produced by one specific embedding model.
--
-- A separate table keyed by (chunk_id, embedding_model), NOT a plain
-- `embedding` column on `chunks`. Trying a second embedding model later adds
-- new rows alongside the old ones instead of overwriting them -- the same
-- "old stays, new is additive" shape as Chunking Generation, and what makes
-- comparing two models' retrieval quality possible without a full re-embed.
--
-- vector(768) is pgvector's fixed-dimension column type; 768 is
-- nomic-embed-text's output size. Postgres rejects a vector of any other
-- length at INSERT time, so a wrong-size model can't silently land here.
-- A model with different dimensions needs its own table/column -- that's a
-- future schema decision, not something to build speculatively now.
CREATE TABLE chunk_embeddings (
    chunk_id         TEXT NOT NULL REFERENCES chunks (id),
    embedding_model  TEXT NOT NULL,
    embedding        vector(768) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, embedding_model)
);

-- The composite primary key's index leads with chunk_id, so it would
-- already serve "all embeddings of this Chunk" lookups in Postgres -- but
-- the spec asks for this explicit index, and it keeps that lookup
-- independent of the key's column order if the key ever changes.
--
-- Deliberately NO vector-similarity index (ivfflat/hnsw) yet: those need
-- row-count-aware tuning against a real query pattern, which only exists
-- once retrieval work begins.
CREATE INDEX idx_chunk_embeddings_chunk_id ON chunk_embeddings (chunk_id);

-- Replicate this migration into regdocs_test too (002 already created that
-- database and copied 001's schema into it, but 002 runs *before* this
-- file, so it can't have included this table).
--
-- 002 did that with `\i` on 001. That can't work here as-is: `\i` of THIS
-- file from inside itself would recurse forever. So the guard below uses a
-- psql *variable* as a "have I already done the copy?" flag:
--   :{?applied_to_test} is psql's "is this variable defined?" test, and
--   variables survive both \c (reconnect) and \i (include) within one psql
--   session. First pass: flag undefined -> set it, switch to regdocs_test,
--   re-run this same file (now the flag IS defined, so the recursive pass
--   skips the block). Result: the DDL above is written once, run twice,
--   with no second copy to keep in sync by hand.
\if :{?applied_to_test}
\else
    \set applied_to_test 1
    \c regdocs_test
    \i /docker-entrypoint-initdb.d/003_chunk_embeddings.sql
\endif
