# Orchestrates the ingestion pipeline: manifest entry -> extract -> clean ->
# chunk -> validate -> write. Issue #5 wired up clause_numbered end to end;
# #6 added heading_sections; #7 adds academic_sections. Each strategy module
# owns its own extraction and cleaning (clause_numbered works from plain
# per-page text; heading_sections and academic_sections both need the
# bold/font-aware layout extraction instead), exposed uniformly as a
# chunk_document(pdf_path) -> list[dict] function -- so this file only needs
# to know a strategy's *name*, never which extraction shape it needs
# internally. Registering a new strategy in CHUNKING_STRATEGIES below is the
# only change a future strategy requires here.

import json
from pathlib import Path

from ids import chunk_id, document_id_from_filename, generation_id
from strategies import academic_sections, clause_numbered, heading_sections
from validate import load_schema, validate_against_schema

# A dict used as a lookup table from a manifest's "chunking_strategy" string
# to the function that implements it -- Python functions are ordinary
# values that can be stored in a dict/passed around like any other object
# (comparable to storing C# method references in a
# Dictionary<string, Func<...>>). Each strategy's chunk_document has the
# same shape: (pdf_path: Path) -> list[dict] of {"locator", "text"}.
CHUNKING_STRATEGIES = {
    "clause_numbered": clause_numbered.chunk_document,
    "heading_sections": heading_sections.chunk_document,
    "academic_sections": academic_sections.chunk_document,
}


def load_manifest(manifest_path: Path) -> list[dict]:
    return json.loads(manifest_path.read_text())


def build_document_and_chunks(entry: dict, corpus_dir: Path) -> tuple[dict, list[dict]]:
    # "tuple[dict, list[dict]]" as a return-type hint means "a 2-tuple:
    # first item a dict, second item a list of dicts" -- Python's built-in
    # spelling for what C# would write as (Dictionary<...>, List<...>) or a
    # small record type.
    document_id = document_id_from_filename(entry["filename"])
    pdf_path = corpus_dir / entry["filename"]

    # entry["chunking_strategy"] is a plain dict lookup, same as
    # entry.get("filename") above but using [] since a missing key here
    # should be a loud error, not silently produce None -- there's no
    # sensible default chunking strategy to fall back to. An unrecognized
    # strategy name will raise a KeyError on the CHUNKING_STRATEGIES lookup
    # below; per-entry failure isolation (so one bad manifest entry can't
    # take down an entire batch) is issue #8, not this ticket.
    strategy_name = entry["chunking_strategy"]
    strategy_chunk_document = CHUNKING_STRATEGIES[strategy_name]
    raw_chunks = strategy_chunk_document(pdf_path)

    # This ticket only covers a document's first-ever ingestion, so it's
    # always generation 1 -- re-chunking an already-ingested Document into a
    # later generation (ADR-0003/0004) is later work, not covered here.
    generation_number = 1
    this_generation_id = generation_id(document_id, generation_number)

    chunks = []
    # enumerate(raw_chunks, start=1) numbers items from 1, not the default
    # 0 -- chunk_id()'s zero-padded sequence number reads more naturally
    # starting at 1 (chunk-001) than 0 (chunk-000).
    for sequence_number, raw_chunk in enumerate(raw_chunks, start=1):
        chunks.append({
            "id": chunk_id(this_generation_id, sequence_number),
            "document_id": document_id,
            "chunking_generation_id": this_generation_id,
            "locator": raw_chunk["locator"],
            "text": raw_chunk["text"],
        })

    document = {
        "id": document_id,
        "title": entry["title"],
        "publisher": entry["publisher"],
        "published_date": entry["published_date"],
        "source_url": entry["source_url"],
        "active_chunking_generation_id": this_generation_id,
    }
    # entry.get("supersedes") returns None if the key is missing or its
    # value is JSON null, without raising -- unlike entry["supersedes"],
    # which would throw a KeyError if the key were absent. document.schema.
    # json's "supersedes" is a string with minLength 1 and isn't in
    # "required", so the field must be left out entirely when there's no
    # value -- there's no valid way to write "supersedes: null" that would
    # pass validation.
    if entry.get("supersedes"):
        document["supersedes"] = entry["supersedes"]

    return document, chunks


def run_pipeline(manifest_path: Path, corpus_dir: Path, output_dir: Path) -> list[tuple[dict, list[dict]]]:
    entries = load_manifest(manifest_path)
    document_schema = load_schema("document.schema.json")
    chunk_schema = load_schema("chunk.schema.json")

    documents_dir = output_dir / "documents"
    chunks_dir = output_dir / "chunks"
    # .mkdir(parents=True, exist_ok=True) creates the directory and any
    # missing parent directories, and doesn't raise if it already exists --
    # the combination C#'s Directory.CreateDirectory(...) gives you as a
    # single call for free, but which pathlib needs both flags spelled out
    # for explicitly.
    documents_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for entry in entries:
        document, chunks = build_document_and_chunks(entry, corpus_dir)

        # Validate before writing anything -- a Document/Chunk that doesn't
        # conform to the shared schema should never reach disk as if it
        # were good output. (Skipping just this entry rather than raising
        # is issue #8's failure isolation; for this ticket's single-entry
        # manifest, raising and stopping is the correct, visible behavior.)
        validate_against_schema(document, document_schema)
        for one_chunk in chunks:
            validate_against_schema(one_chunk, chunk_schema)

        # json.dumps(..., indent=2) serializes to a pretty-printed string
        # (two-space indented) rather than one dense line -- purely for
        # human readability of the committed/inspected output, the same
        # idea as JsonSerializer.Serialize(obj, new JsonSerializerOptions
        # { WriteIndented = true }) in .NET.
        (documents_dir / f"{document['id']}.json").write_text(json.dumps(document, indent=2))
        (chunks_dir / f"{document['id']}.json").write_text(json.dumps(chunks, indent=2))

        results.append((document, chunks))

    return results
