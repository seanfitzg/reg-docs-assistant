# Orchestrates the ingestion pipeline: manifest entry -> extract -> clean ->
# chunk -> validate -> write. Issue #5 wired up clause_numbered end to end;
# #6 added heading_sections; #7 added academic_sections; #8 added per-document
# failure isolation (ADR-0019); #9 added manifest-flagged cleanup (ADR-0016);
# #13 generalised that cleanup away from hardcoded document text.
# Each strategy module owns its own extraction and cleaning, exposed uniformly
# as chunk_document(pdf_path, cleanup_flags) -> list[dict], so this file only
# needs a strategy's *name*. Registering a new strategy in CHUNKING_STRATEGIES
# is the only change a future strategy requires here.

import json
import logging
from pathlib import Path

from regdocs_ingestion.ids import chunk_id, document_id_from_filename, generation_id
from regdocs_ingestion.strategies import (
    academic_sections,
    clause_numbered,
    heading_sections,
)
from regdocs_ingestion.validate import load_schema, validate_against_schema

# Used by run_pipeline() to surface a failed document's filename and reason
# (ADR-0019) without halting the rest of the batch.
logger = logging.getLogger(__name__)

# Lookup from a manifest's "chunking_strategy" string to its implementation.
# Each has the shape (pdf_path, cleanup_flags: list[dict] | None) ->
# list[dict] of {"locator", "text"}.
CHUNKING_STRATEGIES = {
    "clause_numbered": clause_numbered.chunk_document,
    "heading_sections": heading_sections.chunk_document,
    "academic_sections": academic_sections.chunk_document,
}


def load_manifest(manifest_path: Path) -> list[dict]:
    # encoding is explicit because the default on Windows is commonly cp1252,
    # which would silently mangle real non-ASCII manifest text (since #13, a
    # cleanup flag's "start_heading" can be "Réamhrá") instead of raising.
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def build_document_and_chunks(entry: dict, corpus_dir: Path) -> tuple[dict, list[dict]]:
    document_id = document_id_from_filename(entry["filename"])
    pdf_path = corpus_dir / entry["filename"]

    # [] not .get(): there's no sensible default chunking strategy, so a
    # missing key should fail loudly. An unrecognized strategy name raises a
    # KeyError below, and a recognized one that finds nothing raises too --
    # run_pipeline catches both per entry (ADR-0019, issue #8), so one bad
    # entry can't take down the batch.
    strategy_name = entry["chunking_strategy"]
    strategy_chunk_document = CHUNKING_STRATEGIES[strategy_name]
    # Defaults to [] since most entries set no flags (ADR-0016, issue #9).
    # Passed to every strategy, whether or not it acts on them.
    cleanup_flags = entry.get("cleanup_flags", [])
    raw_chunks = strategy_chunk_document(pdf_path, cleanup_flags)

    # A declared strategy that matches nothing (e.g. zero clause numbers in a
    # clause_numbered document) is almost certainly the wrong strategy tag,
    # not an empty document (ADR-0019); writing a Document with zero Chunks
    # would defeat declaring the strategy explicitly (ADR-0014). Raising lets
    # run_pipeline handle it like any extraction error.
    if not raw_chunks:
        raise ValueError(
            f"{strategy_name!r} strategy found no chunks in {entry['filename']!r} "
            "-- check that this is the right chunking_strategy for this document"
        )

    # First-ever ingestion is always generation 1; re-chunking into later
    # generations (ADR-0003/0004) is later work.
    generation_number = 1
    this_generation_id = generation_id(document_id, generation_number)

    chunks = []
    # Starts at 1 so ids read chunk-001, not chunk-000.
    for sequence_number, raw_chunk in enumerate(raw_chunks, start=1):
        chunks.append(
            {
                "id": chunk_id(this_generation_id, sequence_number),
                "document_id": document_id,
                "chunking_generation_id": this_generation_id,
                "locator": raw_chunk["locator"],
                "text": raw_chunk["text"],
            }
        )

    document = {
        "id": document_id,
        "title": entry["title"],
        "publisher": entry["publisher"],
        "published_date": entry["published_date"],
        "source_url": entry["source_url"],
        "active_chunking_generation_id": this_generation_id,
    }
    # document.schema.json's "supersedes" has minLength 1 and isn't required,
    # so when there's no value the field must be omitted -- "supersedes: null"
    # would fail validation.
    if entry.get("supersedes"):
        document["supersedes"] = entry["supersedes"]

    return document, chunks


def run_pipeline(
    manifest_path: Path, corpus_dir: Path, output_dir: Path
) -> list[tuple[dict, list[dict]]]:
    entries = load_manifest(manifest_path)
    document_schema = load_schema("document.schema.json")
    chunk_schema = load_schema("chunk.schema.json")

    documents_dir = output_dir / "documents"
    chunks_dir = output_dir / "chunks"
    documents_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for entry in entries:
        # Computed outside the try: the except block's cleanup needs these
        # even if the failure happens before `document` exists.
        document_id = document_id_from_filename(entry["filename"])
        document_path = documents_dir / f"{document_id}.json"
        chunks_path = chunks_dir / f"{document_id}.json"

        # Any failure in the chain (corrupt PDF, strategy found nothing,
        # schema violation, partial write) is caught, logged with the filename
        # and reason, and skipped, rather than halting the batch (ADR-0019,
        # issue #8). The broad `except Exception` is deliberate: at the batch
        # boundary every failure is "isolate it and move on".
        try:
            document, chunks = build_document_and_chunks(entry, corpus_dir)

            # Validate before writing, so nonconforming output never reaches
            # disk as if it were good.
            validate_against_schema(document, document_schema)
            for one_chunk in chunks:
                validate_against_schema(one_chunk, chunk_schema)

            # Two separate writes, not atomic: if the second fails, the except
            # block removes whichever file was written, so a mid-write failure
            # never leaves an orphaned Document without its Chunks file
            # (ADR-0019).
            document_path.write_text(json.dumps(document, indent=2))
            chunks_path.write_text(json.dumps(chunks, indent=2))

            results.append((document, chunks))
        except Exception as error:
            document_path.unlink(missing_ok=True)
            chunks_path.unlink(missing_ok=True)

            # exc_info records the traceback without re-raising.
            logger.error(
                "Skipping %s: %s",
                entry.get("filename", "<unknown>"),
                error,
                exc_info=True,
            )

    return results
