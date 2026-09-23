-- A second database, entirely for store/tests, so running the test suite
-- can never wipe out real data loaded into `regdocs` via `python
-- store/loader.py`. Postgres images only auto-create the one database
-- named by POSTGRES_DB (store/docker-compose.yml's `regdocs`) -- this file
-- creates a second one by hand, runs once on the container's first start
-- alongside 001_schema.sql, same docker-entrypoint-initdb.d mechanism
-- (store/README.md).
CREATE DATABASE regdocs_test;

-- \c is a psql meta-command (not SQL itself) that switches the current
-- session's connection to the named database -- everything below this
-- line runs against regdocs_test, not regdocs.
\c regdocs_test

-- \i re-runs another file's statements verbatim, in the connection \c just
-- switched to -- so regdocs_test ends up with the exact same schema as
-- regdocs, without a second, separately-maintained copy of the DDL to
-- keep in sync by hand.
\i /docker-entrypoint-initdb.d/001_schema.sql
