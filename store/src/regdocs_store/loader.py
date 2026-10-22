# Loads ingestion's Document/Chunk JSON output into /store's Postgres.
#
# Deliberately a standalone step, not wired into run_pipeline (ADR-0020):
# this module never imports from /ingestion, and /store has its own
# venv/requirements.txt.
#
# documents, chunking_generations, and chunks are immutable once written
# (CONTEXT.md), so every write is either an INSERT ... ON CONFLICT DO NOTHING
# or an UPDATE of a field that's allowed to change (see phase 3) -- never a
# rewrite of core content, never a truncate/delete. Re-running only ever adds
# rows, so it can't destroy a Chunking Generation a past Replay depends on
# (ADR-0021).

import json
from pathlib import Path
from typing import Any

import psycopg

from regdocs_store.db import DEFAULT_DB_URL, upsert_immutable

# Mirrors the CHECK constraint on chunking_generations.chunking_strategy in
# store/init/001_schema.sql, and ADR-0014's list. Checked here too so a typo in
# a hand-edited manifest.json gives a clear error naming the bad value, not a
# raw CheckViolation deep in a batch insert. Update both places together.
VALID_CHUNKING_STRATEGIES = {"clause_numbered", "heading_sections", "academic_sections"}


def _document_id_from_filename(filename: str) -> str:
    # Mirrors ingestion/ids.py (ADR-0017); duplicated rather than imported to
    # keep /ingestion and /store independently runnable.
    return f"doc-{Path(filename).stem}"


def _load_manifest_strategies(manifest_path: Path) -> dict[str, str]:
    # manifest.json is the only place chunking_strategy is recorded
    # (ADR-0014): a strategy belongs to a Generation, not a Document. Builds
    # document_id -> strategy so the loader can fill in
    # chunking_generations.chunking_strategy.
    #
    # An explicit loop, not a comprehension, because it must check earlier
    # entries to catch two manifest entries for the same document.
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
    # Sorted for a deterministic load order; correctness doesn't depend on it.
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
    # A Chunking Generation isn't its own JSON file (CONTEXT.md: it only
    # appears as a bare id on Document/Chunk), so it's derived from the Chunks
    # that reference it. Keying by id also de-duplicates.
    generations: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        generation_id = chunk["chunking_generation_id"]
        document_id = chunk["document_id"]

        if document_id not in document_ids:
            # documents/ and chunks/ can drift apart if output_dir is
            # hand-edited or partially regenerated; without this check it
            # would surface as a raw foreign-key violation in phase 2.
            raise ValueError(
                f"chunk {chunk['id']!r} references document_id {document_id!r}, "
                f"which has no matching file in {output_dir / 'documents'} -- "
                "ingestion/output appears to be incomplete or corrupted"
            )

        if generation_id in generations:
            if generations[generation_id]["document_id"] != document_id:
                # ids.py derives chunking_generation_id from document_id
                # (ADR-0017), so disagreement means the output is internally
                # inconsistent, not just incomplete.
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
            # ingestion/output and manifest.json are independently
            # regenerable, so they can fall out of sync; a bare KeyError
            # wouldn't say why.
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

    # Each chunks/<doc-id>.json holds an array of Chunks for one Document;
    # extend() flattens them into one list.
    chunks: list[dict[str, Any]] = []
    for chunks_in_one_file in _read_json_files(output_dir / "chunks"):
        chunks.extend(chunks_in_one_file)

    generations = _build_generations(
        chunks, document_ids, strategy_by_document_id, output_dir
    )

    for document in documents:
        active_id = document.get("active_chunking_generation_id")
        if active_id is not None and active_id not in generations:
            # Caught before touching the database, instead of as a raw
            # foreign-key violation in phase 3.
            raise ValueError(
                f"document {document['id']!r} has active_chunking_generation_id "
                f"{active_id!r}, but no chunk in {output_dir / 'chunks'} "
                "references that generation -- ingestion/output appears to "
                "be incomplete or corrupted"
            )

    # One transaction for the whole load: any exception rolls back and
    # propagates. Unlike ingestion's per-document failure isolation
    # (ADR-0019), which exists because corrupt PDFs are ordinary input, a
    # failure here means already-validated JSON doesn't fit the schema -- a bug
    # worth stopping for.
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Must be read BEFORE phase 1 inserts anything: phase 3 only sets
            # `supersedes` on documents new this run. ANY(%s) checks
            # membership against a whole list in one query.
            incoming_document_ids = [document["id"] for document in documents]
            cur.execute(
                "SELECT id FROM documents WHERE id = ANY(%s)",
                (incoming_document_ids,),
            )
            already_loaded_document_ids = {row[0] for row in cur.fetchall()}

            # Phase 1: documents WITHOUT the two circular-reference fields
            # (supersedes, active_chunking_generation_id), which can point at
            # rows that don't exist yet on a first load. Same problem as the
            # schema (store/init/001_schema.sql), same fix: insert without
            # them, wire them up in phase 3.
            #
            # DEFERRABLE INITIALLY DEFERRED constraints would avoid the manual
            # ordering, but the schema shipped in #18 declares ordinary
            # foreign keys and changing it is out of scope.
            upsert_immutable(
                cur,
                "documents",
                ["id", "title", "publisher", "published_date", "source_url"],
                documents,
            )

            # Phase 2: chunking_generations. Every document_id was inserted in
            # phase 1 or already existed, and _build_generations checked each.
            upsert_immutable(
                cur,
                "chunking_generations",
                ["id", "document_id", "chunking_strategy"],
                list(generations.values()),
            )

            # Phase 3: fill in the two fields phase 1 left out, but not
            # symmetrically. `supersedes` is immutable (CONTEXT.md), so it's
            # set only the first time a Document is loaded -- the same
            # "original row wins" rule as upsert_immutable.
            # active_chunking_generation_id is expected to change when a
            # Document is re-chunked (ADR-0004), so it's re-applied from the
            # current JSON on every run.
            #
            # One UPDATE per document (~20), not per Chunk, so no batching.
            for document in documents:
                if document["id"] not in already_loaded_document_ids:
                    cur.execute(
                        "UPDATE documents SET supersedes = %(supersedes)s WHERE id = %(id)s",
                        {
                            "id": document["id"],
                            "supersedes": document.get("supersedes"),
                        },
                    )
                cur.execute(
                    """
                    UPDATE documents
                    SET active_chunking_generation_id = %(active_chunking_generation_id)s
                    WHERE id = %(id)s
                    """,
                    {
                        "id": document["id"],
                        # .get() because this field is genuinely optional
                        # (schema.json: absent until first chunked), unlike
                        # the required fields, which should raise if missing.
                        "active_chunking_generation_id": document.get(
                            "active_chunking_generation_id"
                        ),
                    },
                )

            # Phase 4: chunks; both foreign keys are now populated.
            upsert_immutable(
                cur,
                "chunks",
                ["id", "document_id", "chunking_generation_id", "locator", "text"],
                chunks,
            )


if __name__ == "__main__":
    import os

    repo_root = Path(__file__).parents[3]
    load_store(
        output_dir=repo_root / "ingestion" / "output",
        manifest_path=repo_root / "ingestion" / "manifest.json",
        db_url=os.environ.get("STORE_DATABASE_URL", DEFAULT_DB_URL),
    )
    print("Loaded /store from ingestion/output")
