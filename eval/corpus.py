# Reads the ingested corpus from ingestion/output/ -- the JSON projection
# ingestion writes (ADR-0012), regenerable and gitignored -- rather than
# from Postgres, so the eval set can be authored and validated without
# Docker running.

import json
from pathlib import Path

# Path(__file__) is this file's own path; .parent twice climbs eval/ -> repo
# root. Resolving from the file rather than the current working directory
# means the default works no matter which folder a script is run from.
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "ingestion" / "output"


def load_active_chunks(output_dir: Path = DEFAULT_OUTPUT_DIR) -> list[dict]:
    """Every Chunk belonging to its Document's active Chunking Generation.

    Only active-generation Chunks are retrieval candidates (and the only
    ones embedded, ADR-0025), so they're the only ones a Gold Locator can
    meaningfully point at.
    """
    # Every documents/*.json file, parsed. [expr for item in iterable] is a
    # list comprehension -- like .Select(...).ToList(). sorted() makes the
    # file order (and so every result below) stable across operating
    # systems, since glob order isn't guaranteed.
    documents = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((output_dir / "documents").glob("*.json"))]
    # A lookup of document_id -> active generation id. {key: value for item
    # in iterable} is a dict comprehension -- like
    # .ToDictionary(d => d.Id, d => d.ActiveGen).
    active_generation = {d["id"]: d["active_chunking_generation_id"] for d in documents}

    chunks = []
    for path in sorted((output_dir / "chunks").glob("*.json")):
        # Each chunks/*.json file is a JSON array of Chunk objects.
        for chunk in json.loads(path.read_text(encoding="utf-8")):
            # .get() returns None instead of raising KeyError for a missing
            # key -- so a Chunk whose Document file is somehow absent is
            # treated as inactive (skipped) rather than crashing.
            if active_generation.get(chunk["document_id"]) == chunk["chunking_generation_id"]:
                chunks.append(chunk)
    return chunks
