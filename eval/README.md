# /eval

The retrieval eval set: hand-written **Eval Cases**, each labelled with the **Gold Locators** where its answer lives (`CONTEXT.md`), used to *measure* retrieval quality rather than eyeball it. Design in ADR-0027 to ADR-0030.

So far this folder holds the dataset and the tooling for authoring it (#29). The locator match rule (#30) and the harness that runs retrieval and writes reports (#32) come next.

## Setup

```
python -m venv eval/.venv
eval/.venv/Scripts/activate      # Windows
# source eval/.venv/bin/activate # macOS/Linux
pip install -r eval/requirements.txt
```

Everything here reads `ingestion/output/`, not Postgres, so Docker isn't needed. That folder is gitignored, so run the ingestion pipeline first (`ingestion/README.md`).

## Writing Eval Cases

Cases go in `dataset.json`, whose shape is defined by `schema/eval-dataset.schema.json`:

```json
{
  "id": "q01",
  "question": "…",
  "phrasing": "lexical",
  "category": "single_passage",
  "gold_locators": [{ "document_id": "doc-04-…", "locator": "3.12" }],
  "answer_quote": "verbatim text from the source"
}
```

- `phrasing` is `lexical` (reuses the passage's wording) or `paraphrase` (deliberately doesn't). Aim for roughly half of each. Recall is reported separately for each, to expose lexical overlap bias (ADR-0029).
- `category` is `single_passage`, `multi_locator`, `supersession` (also needs `superseded_locators`, pointing at the older Document) or `unanswerable` (empty `gold_locators` and no `answer_quote`).
- Bump `dataset_version` whenever the cases change. Every eval run report records it (ADR-0030).

To find the exact locator for a passage, search by keyword:

```
python eval/find_locator.py "key information document"
python eval/find_locator.py "fitness probity" --doc doc-10-cp160-fitness-and-probity-regime
```

Every word must appear in a Chunk, but not necessarily next to each other, and matching ignores case. Only active-generation Chunks are searched, since those are the only ones retrieval can return. This is keyword search, so it matches words rather than meaning. That's deliberate: comparing it with the harness's embedding search later shows the difference between the two.

## Running the tests

```
python -m pytest eval/tests
```

`test_dataset.py` is the safety net while writing cases. Run it after every edit. It checks `dataset.json` against the schema, checks that case ids are unique, and checks that every Gold Locator (and superseded locator) exists **exactly** in the ingested active Chunks. That exact check is only there to catch typos. Whether a *retrieved* Chunk counts as a hit is a separate, structure-aware rule (ADR-0028). The locator check skips if `ingestion/output/` isn't present.

## Layout

- `dataset.json`: the Eval Cases.
- `corpus.py`: loads active-generation Chunks from `ingestion/output/`.
- `check_dataset.py`: `find_problems()`, the relational checks the JSON Schema can't express.
- `find_locator.py`: the keyword-search authoring helper.
- `tests/`: unit tests against small fixture copies of ingestion output (`tests/fixtures/`), plus `test_dataset.py` for the real dataset.
