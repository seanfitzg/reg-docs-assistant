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

Most tests are self-contained (synthetic fixtures, or a throwaway PDF built with pymupdf itself). The end-to-end tests in `test_pipeline.py` run against the real CP54/DP8 PDFs and skip themselves if the corpus isn't present locally.

## Layout

- `manifest.json` — the manifest (ADR-0013): one entry per document to ingest, carrying its title/publisher/published_date/source_url/supersedes/chunking_strategy. A person edits this by hand when adding a document; the pipeline never infers this metadata from the PDF itself.
- `extract.py` — pymupdf text extraction. Two functions, for the two shapes chunking strategies need: `extract_pages` returns plain per-page text (used by `clause_numbered`); `extract_pages_with_headings` returns each page's lines with font-weight info (`is_heading`, true when every span on a line is bold), needed by `heading_sections` since a heading has no numbered marker a plain-text regex could find — bold is the only signal that distinguishes it from an ordinary sentence. (pymupdf itself was chosen over pypdf after it corrupted text on the Research Technical Papers — see the session that produced ADR-0012–0019.)
- `clean.py` — the automatic cleanup step (ADR-0016): strips repeated headers/footers and page-number lines (bare, or "Page N"-prefixed). Two variants share the same underlying rule, for the same two shapes `extract.py` produces. Document-specific cleanup (bilingual duplication, navigation chrome) is manifest-flagged instead, and isn't built yet (issue #9).
- `strategies/` — one module per chunking strategy named in the manifest (ADR-0014), each exposing the same `chunk_document(pdf_path) -> list[dict]` shape regardless of what extraction/cleaning it needs internally. `clause_numbered.py` (issue #5) and `heading_sections.py` (issue #6) exist so far; `academic_sections` is issue #7. `heading_sections.py` has a documented known limitation: a cover-page title or other spurious bold line can be misdetected as a real section heading, sweeping front matter into its chunk text — not fixed yet, flagged for a follow-up decision rather than an unreviewed heuristic.
- `ids.py` — deterministic id derivation for Document (ADR-0017), Chunking Generation, and Chunk ids — never hand-assigned.
- `validate.py` — validates pipeline output against `/schema`'s JSON Schemas before anything is written to disk.
- `pipeline.py` — wires the above together: `load_manifest`, `build_document_and_chunks` (pure construction, one manifest entry in, one Document + its Chunks out, dispatching to whichever strategy's `chunk_document` the entry names), `run_pipeline` (validates and writes output for every manifest entry).
