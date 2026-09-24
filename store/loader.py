# Loads ingestion's Document/Chunk JSON output into /store's Postgres.
#
# Deliberately a standalone step, not wired into ingestion/pipeline.py's
# run_pipeline (ADR-0020) -- this module never imports anything from
# /ingestion, and /store has its own venv/requirements.txt, so it can run
# (and be tested) independently of the pipeline that produced its input.
#
# documents, chunking_generations, and chunks are each defined in
# CONTEXT.md as immutable once written -- so every write here is either an
# INSERT ... ON CONFLICT DO NOTHING or an UPDATE restricted to a field
# that's genuinely allowed to change (see load_store's phase 3), never a
# rewrite of a row's core content, and never a truncate/delete. Re-running
# this loader after ingestion/output changes only ever adds rows; it can
# never destroy a Chunking Generation a past Replay still depends on
# (ADR-0021).

import json
from pathlib import Path
from typing import Any

import psycopg

from db import DEFAULT_DB_URL, upsert_immutable

# Mirrors the closed set store/init/001_schema.sql's CHECK constraint on
# chunking_generations.chunking_strategy enforces, and ADR-0014's own list.
# Checked here too, before anything reaches the database, purely so a typo
# in a hand-edited manifest.json produces a clear Python error naming the
# bad value -- rather than a raw Postgres CheckViolation surfacing deep
# inside a batch insert with no context. If a fourth strategy is ever
# added, update it in both places.
VALID_CHUNKING_STRATEGIES = {"clause_numbered", "heading_sections", "academic_sections"}


def _document_id_from_filename(filename: str) -> str:
    # Mirrors ingestion/ids.py's document_id_from_filename (ADR-0017) --
    # duplicated as this one line rather than importing across
    # /ingestion and /store's independent venvs, which would couple two
    # folders that are deliberately kept separately runnable.
    return f"doc-{Path(filename).stem}"


def _load_manifest_strategies(manifest_path: Path) -> dict[str, str]:
    # ingestion/manifest.json is the *only* place chunking_strategy is
    # recorded (ADR-0014) -- it never made it onto the Document or Chunk
    # JSON schemas themselves, since a strategy belongs to a Generation, not
    # permanently to a Document. This builds a document_id -> strategy
    # lookup so the loader can fill in chunking_generations.chunking_strategy,
    # which nothing in ingestion/output alone can supply.
    #
    # Written as an explicit loop rather than a dict comprehension (compare
    # _read_json_files below, which uses one) because it needs to *inspect*
    # what's already been collected on each iteration, to catch a manifest
    # with two entries for the same document -- a comprehension builds its
    # result in one expression with no opportunity to check prior entries
    # as it goes.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    strategies: dict[str, str] = {}
    for entry in manifest:
        document_id = _document_id_from_filename(entry["filename"])
        if document_id in strategies:
            raise ValueError(
                f"manifest.json has more than one entry for filename "
                f"{entry['filename']!r} (document_id {document_id!r}) -- "
                "each document should appear exactly once"
            )
        chunking_strategy = entry["chunking_strategy"]
        if chunking_strategy not in VALID_CHUNKING_STRATEGIES:
            raise ValueError(
                f"manifest.json's entry for {entry['filename']!r} has "
                f"chunking_strategy {chunking_strategy!r}, which isn't one "
                f"of {sorted(VALID_CHUNKING_STRATEGIES)}"
            )
        strategies[document_id] = chunking_strategy
    return strategies


def _read_json_files(directory: Path) -> list[dict[str, Any]]:
    # A list comprehension: "for each path in this sorted list of files,
    # produce one parsed-JSON value, collected into a new list." The LINQ
    # equivalent is paths.Select(path => ParseJson(path)).ToList(). sorted()
    # makes load order deterministic -- helpful for reproducing a run,
    # though it has no effect on correctness since every write below is
    # either an upsert or an idempotent UPDATE.
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


def _build_generations(
    chunks: list[dict[str, Any]],
    document_ids: set[str],
    strategy_by_document_id: dict[str, str],
    output_dir: Path,
) -> dict[str, dict[str, Any]]:
    # Chunking Generation isn't its own JSON file anywhere in ingestion's
    # output (CONTEXT.md: it only ever appears as a bare id on Document/
    # Chunk) -- so it's derived here from the Chunks that reference it. A
    # dict keyed by chunking_generation_id both derives the set of distinct
    # Generations and de-duplicates automatically (a Generation with 50
    # Chunks would otherwise be "seen" 50 times).
    generations: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        generation_id = chunk["chunking_generation_id"]
        document_id = chunk["document_id"]

        if document_id not in document_ids:
            # documents/ and chunks/ are two separate sets of files
            # (ingestion/README.md) -- nothing stops them drifting apart if
            # output_dir is ever hand-edited or partially regenerated. A
            # chunk pointing at a document_id with no matching
            # documents/<id>.json file would otherwise only surface as a
            # raw foreign-key violation once phase 2 tries to insert it.
            raise ValueError(
                f"chunk {chunk['id']!r} references document_id {document_id!r}, "
                f"which has no matching file in {output_dir / 'documents'} -- "
                "ingestion/output appears to be incomplete or corrupted"
            )

        if generation_id in generations:
            if generations[generation_id]["document_id"] != document_id:
                # Every chunk claiming the same chunking_generation_id must
                # agree on which Document that Generation belongs to --
                # ids.py derives chunking_generation_id from document_id
                # (ADR-0017), so two different answers here means
                # ingestion/output itself is internally inconsistent, not
                # just incomplete.
                raise ValueError(
                    f"chunk {chunk['id']!r} claims chunking_generation_id "
                    f"{generation_id!r} belongs to document {document_id!r}, "
                    "but another chunk for the same generation claims "
                    f"document {generations[generation_id]['document_id']!r} "
                    "-- ingestion/output is internally inconsistent"
                )
            continue

        try:
            chunking_strategy = strategy_by_document_id[document_id]
        except KeyError as exc:
            # A bare `strategy_by_document_id[document_id]` would raise a
            # KeyError naming only the id, with nothing pointing at *why*
            # it's missing. ingestion/output and manifest.json are
            # independently regenerable (ingestion/README.md), so nothing
            # guarantees they stay in sync with each other -- this
            # re-raises with that explanation attached, so a future "it
            # crashed, why?" doesn't start from a bare id.
            raise ValueError(
                f"chunk {chunk['id']!r} references document_id {document_id!r}, "
                f"which has no chunking_strategy entry in manifest.json -- "
                "ingestion/output and manifest.json appear to have drifted "
                "out of sync; re-run ingestion's pipeline against the "
                "current manifest.json"
            ) from exc

        generations[generation_id] = {
            "id": generation_id,
            "document_id": document_id,
            "chunking_strategy": chunking_strategy,
        }
    return generations


def load_store(output_dir: Path, manifest_path: Path, db_url: str) -> None:
    """Load ingestion's Document/Chunk output into /store's Postgres.

    output_dir: ingestion's output folder (containing documents/ and chunks/).
    manifest_path: ingestion/manifest.json, read only for chunking_strategy.
    db_url: a psycopg-style connection string, e.g. DEFAULT_DB_URL above.

    Safe to call repeatedly against unchanged or extended output -- see
    upsert_immutable's docstring for exactly what "safe" means here.
    """
    strategy_by_document_id = _load_manifest_strategies(manifest_path)

    documents = _read_json_files(output_dir / "documents")
    document_ids = {document["id"] for document in documents}

    # Each chunks/<doc-id>.json file holds a JSON *array* of Chunk records
    # for one Document (ingestion/README.md) -- _read_json_files parses
    # each file into one Python list, so this loop's variable is itself a
    # list; .extend() folds each file's Chunks into the one running
    # `chunks` list, rather than ending up with a list of lists.
    chunks: list[dict[str, Any]] = []
    for chunks_in_one_file in _read_json_files(output_dir / "chunks"):
        chunks.extend(chunks_in_one_file)

    generations = _build_generations(chunks, document_ids, strategy_by_document_id, output_dir)

    for document in documents:
        active_id = document.get("active_chunking_generation_id")
        if active_id is not None and active_id not in generations:
            # Caught here, before touching the database, rather than
            # letting phase 3 below hit this as a raw foreign-key
            # violation with no explanation of which document/field caused
            # it.
            raise ValueError(
                f"document {document['id']!r} has active_chunking_generation_id "
                f"{active_id!r}, but no chunk in {output_dir / 'chunks'} "
                "references that generation -- ingestion/output appears to "
                "be incomplete or corrupted"
            )

    # `with psycopg.connect(...) as conn:` wraps the whole load in one
    # transaction: a clean exit commits, but if anything below raises, the
    # transaction rolls back and the exception propagates -- nothing is
    # left half-written, and the failure surfaces loudly (a Python
    # traceback, non-zero exit) rather than being swallowed. This is a
    # deliberate departure from ingestion's own per-document failure
    # isolation (ADR-0019): that isolation exists because a *corrupt PDF*
    # is expected, ordinary input; a failure here means already-validated
    # JSON somehow doesn't fit the schema, which is a bug worth stopping
    # the whole run over, not skipping past.
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Which documents already exist has to be known BEFORE phase 1
            # inserts anything -- phase 3 needs it to decide whether a
            # Document's `supersedes` is safe to set (only on a document
            # that's genuinely new this run; see phase 3's own comment for
            # why). "= ANY(%s)" is psycopg's way of checking column
            # membership against a whole Python list in one round trip,
            # the SQL equivalent of C#'s `list.Contains(...)` used as a
            # LINQ `Where` predicate, rather than one query per id.
            cur.execute(
                "SELECT id FROM documents WHERE id = ANY(%s)",
                ([document["id"] for document in documents],),
            )
            already_loaded_document_ids = {row[0] for row in cur.fetchall()}

            # Phase 1: documents, WITHOUT their two circular-reference
            # fields (supersedes, active_chunking_generation_id). Both can
            # point at rows that don't exist in the table yet on a first
            # load -- supersedes at another Document not yet inserted,
            # active_chunking_generation_id at a Chunking Generation that
            # doesn't exist until phase 2 below. Same circular-reference
            # problem /store's schema itself has (see
            # store/init/001_schema.sql's comments) -- resolved the same
            # way: insert the row first with the circular fields left out
            # entirely, then wire them up once every table involved
            # actually has rows in it (phase 3).
            #
            # An alternative would be Postgres DEFERRABLE INITIALLY
            # DEFERRED constraints, which let the database itself defer an
            # FK check until commit instead of requiring this kind of
            # manual phase ordering in application code. Not used here
            # because /store's schema (already shipped in #18) declares
            # these foreign keys as ordinary, non-deferrable constraints --
            # switching would mean reopening and re-migrating already-merged
            # schema work, out of scope for this loader.
            upsert_immutable(
                cur,
                "documents",
                ["id", "title", "publisher", "published_date", "source_url"],
                documents,
            )

            # Phase 2: chunking_generations. Every document_id referenced
            # here was just inserted in phase 1 (or already existed), and
            # _build_generations already checked each one has a matching
            # Document, so the foreign key holds.
            upsert_immutable(
                cur,
                "chunking_generations",
                ["id", "document_id", "chunking_strategy"],
                list(generations.values()),
            )

            # Phase 3: now that every Document and every Chunking Generation
            # exists, go back and fill in the two fields phase 1 left out --
            # but NOT symmetrically. `supersedes` is exactly as immutable as
            # a Document's title/publisher/etc once written (CONTEXT.md), so
            # it's only ever set the *first* time a Document is loaded --
            # skipped entirely for a document already in
            # already_loaded_document_ids, the same "original row wins"
            # rule upsert_immutable applies elsewhere. `active_chunking_
            # generation_id` is different: which Generation is *active* is
            # expected to change over a Document's lifetime (ADR-0004: it
            # moves when a Document is re-chunked), so it's always
            # re-applied from the current JSON, on every run, for every
            # document -- there's no "first write wins" for a pointer
            # that's meant to be updatable.
            #
            # Only 20 documents exist today, so one UPDATE per document
            # (not per Chunk) is a handful of round trips, not thousands --
            # unlike upsert_immutable's executemany over Chunks, this
            # hasn't needed batching.
            for document in documents:
                if document["id"] not in already_loaded_document_ids:
                    cur.execute(
                        "UPDATE documents SET supersedes = %(supersedes)s WHERE id = %(id)s",
                        {"id": document["id"], "supersedes": document.get("supersedes")},
                    )
                cur.execute(
                    """
                    UPDATE documents
                    SET active_chunking_generation_id = %(active_chunking_generation_id)s
                    WHERE id = %(id)s
                    """,
                    {
                        "id": document["id"],
                        # .get(...) rather than [...] here, deliberately --
                        # unlike chunk["id"]/chunk["document_id"] elsewhere
                        # in this file, which are *required* fields that
                        # should raise if somehow missing,
                        # active_chunking_generation_id is genuinely
                        # optional on a Document (schema.json: absent until
                        # a Document has been chunked at least once), so
                        # .get() returning None for a missing key is the
                        # correct behaviour here, not a shortcut around
                        # error handling.
                        "active_chunking_generation_id": document.get(
                            "active_chunking_generation_id"
                        ),
                    },
                )

            # Phase 4: chunks. Both foreign keys they need (documents,
            # chunking_generations) are now fully populated.
            upsert_immutable(
                cur,
                "chunks",
                ["id", "document_id", "chunking_generation_id", "locator", "text"],
                chunks,
            )


if __name__ == "__main__":
    import os

    repo_root = Path(__file__).parent.parent
    load_store(
        output_dir=repo_root / "ingestion" / "output",
        manifest_path=repo_root / "ingestion" / "manifest.json",
        db_url=os.environ.get("STORE_DATABASE_URL", DEFAULT_DB_URL),
    )
    print("Loaded /store from ingestion/output")
