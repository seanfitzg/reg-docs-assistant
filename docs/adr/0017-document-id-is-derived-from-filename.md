# Document id is derived from filename, not hand-assigned

A `Document`'s `id` is computed deterministically from its corpus filename (e.g. `21-new-doc.pdf` → `doc-21-new-doc`), never typed by hand in the manifest — even though the existing schema fixtures use hand-picked ids like `doc-cpc-2012`.

A derived id removes an entire class of mistake: typos, accidental duplicates, or drift between a document's filename and its id over time. It also gives the manifest-diffing mechanism (ADR-0013) a stable, known-in-advance key without needing a person to invent and remember one. Nothing about the system needs a Document id to be independently *chosen* the way the fixtures' illustrative ids are — it only needs to be stable and unique, which the corpus's existing `NN-slug.pdf` naming convention already guarantees for free. Fixtures remain hand-picked because they're illustrative test data, not pipeline output.
