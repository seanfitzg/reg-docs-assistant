# /ingestion

Turns corpus PDFs into `Document`/`Chunk` records validated against the shared schemas in `/schema` (ADR-0012: one shared pipeline, not built separately per track).

## Setup

```
python -m venv ingestion/.venv
ingestion/.venv/Scripts/activate      # Windows
# source ingestion/.venv/bin/activate # macOS/Linux
pip install -r ingestion/requirements.txt
```

Requires the corpus PDFs to be present locally (`corpus/*.pdf` — see `corpus/SOURCES.md`; not committed to git).

## Running the pipeline

```python
from pathlib import Path
from pipeline import run_pipeline

run_pipeline(Path("ingestion/manifest.json"), Path("corpus"), Path("ingestion/output"))
```

Writes one `Document` JSON file per manifest entry to `output/documents/<id>.json`, and its `Chunk` records (as a JSON array) to `output/chunks/<id>.json`. `output/` isn't committed — it's fully regenerable from the corpus PDFs plus `manifest.json`, the same relationship a projection has to the event store it's built from (ADR-0012's "Further Notes" territory, not written up as its own ADR).

## Running the tests

```
python -m pytest ingestion/tests
```

Most tests are self-contained (synthetic fixtures, or a throwaway PDF built with pymupdf itself). The end-to-end test in `test_pipeline.py` runs against the real CP54 PDF and skips itself if the corpus isn't present locally.

## Layout

- `manifest.json` — the manifest (ADR-0013): one entry per document to ingest, carrying its title/publisher/published_date/source_url/supersedes/chunking_strategy. A person edits this by hand when adding a document; the pipeline never infers this metadata from the PDF itself.
- `extract.py` — pymupdf text extraction, one string per page (chosen over pypdf after it corrupted text on the Research Technical Papers — see the session that produced ADR-0012–0019).
- `clean.py` — the automatic cleanup step (ADR-0016): strips repeated headers/footers and bare page-number lines. Document-specific cleanup (bilingual duplication, navigation chrome) is manifest-flagged instead, and isn't built yet (issue #9).
- `strategies/` — one module per chunking strategy named in the manifest (ADR-0014). Only `clause_numbered.py` exists so far; `heading_sections`/`academic_sections` are issues #6/#7.
- `ids.py` — deterministic id derivation for Document (ADR-0017), Chunking Generation, and Chunk ids — never hand-assigned.
- `validate.py` — validates pipeline output against `/schema`'s JSON Schemas before anything is written to disk.
- `pipeline.py` — wires the above together: `load_manifest`, `build_document_and_chunks` (pure construction, one manifest entry in, one Document + its Chunks out), `run_pipeline` (validates and writes output for every manifest entry).
