# /eval

The retrieval eval set: hand-written **Eval Cases**, each labelled with the **Gold Locators** where its answer lives (`CONTEXT.md`), used to *measure* retrieval quality rather than eyeball it. Design in ADR-0027 to ADR-0030.

This folder holds the dataset, the tooling for authoring it (#29), the match rule that decides whether a retrieved Chunk is a hit (#30), and the harness that runs retrieval over the dataset and writes a run report (#32).

## Setup

```
uv sync --all-packages              # once, from the repo root: one shared .venv for every folder
.venv/Scripts/activate              # Windows
# source .venv/bin/activate         # macOS/Linux
```

Authoring and validating cases reads `ingestion/output/`, not Postgres, so Docker isn't needed for that. That folder is gitignored, so run the ingestion pipeline first (`ingestion/README.md`). Only the harness (`run_eval.py`) needs Postgres and Ollama.

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
python -m regdocs_eval.find_locator "key information document"
python -m regdocs_eval.find_locator "fitness probity" --doc doc-10-cp160-fitness-and-probity-regime
```

Every word must appear in a Chunk, but not necessarily next to each other, and matching ignores case. Only active-generation Chunks are searched, since those are the only ones retrieval can return. This is keyword search, so it matches words rather than meaning. That's deliberate: comparing it with the harness's embedding search later shows the difference between the two.

## Running the eval harness

`run_eval.py` embeds every case's question, runs a top-10 similarity search over the stored Chunk Embeddings, scores each case with the match rule, prints a summary table, and writes a report to `runs/`.

Prerequisites, in order (details in `store/README.md`):

1. Postgres up: `docker compose up -d` from `store/`.
2. The store loaded: `python -m regdocs_store.loader`.
3. Chunks embedded: `python -m regdocs_store.embed`, with Ollama running and `nomic-embed-text` pulled.

Then:

```
python -m regdocs_eval.run_eval
```

- Each question is sent as `"search_query: <question>"`, the query half of ADR-0026's asymmetric prefix. Chunks were stored with `"search_document: "`.
- The search is exact (no vector index), restricted to each Document's active Chunking Generation (ADR-0025).
- Recall@1/3/5/10 and MRR are computed over answerable cases only, overall and by `phrasing` and `category`. Unanswerable cases record their top-1 similarity instead (ADR-0029).
- The report is written to `runs/<UTC timestamp>-<model>.json` and never overwrites an existing one. It pins the embedding model, query prefix, k, `dataset_version` and every Document's active Chunking Generation, so reports are only compared like-for-like (ADR-0030).
- Env vars: `STORE_DATABASE_URL` and `OLLAMA_HOST`, as for `regdocs_store.embed`.

The earliest report in `runs/` is the **baseline**: the score the later .NET retriever must reproduce on the same embeddings.

## Running the tests

```
python -m pytest eval/tests
```

`test_run_eval.py` is the harness's integration test. It runs against the isolated `regdocs_test` database with hand-built vectors and a fake embedding client, so it needs Postgres but not Ollama, and skips if Postgres isn't reachable.

`test_dataset.py` is the safety net while writing cases. Run it after every edit. It checks `dataset.json` against the schema, checks that case ids are unique, and checks that every Gold Locator (and superseded locator) exists **exactly** in the ingested active Chunks. That exact check is only there to catch typos. Whether a *retrieved* Chunk counts as a hit is a separate, structure-aware rule (`match.py`, ADR-0028). The locator check skips if `ingestion/output/` isn't present.

## Layout

Python modules live in `src/regdocs_eval/` (so `run_eval.py` below is `regdocs_eval.run_eval`), tests in `tests/`; `dataset.json` and `runs/` stay at the top level.

- `dataset.json`: the Eval Cases.
- `corpus.py`: loads active-generation Chunks from `ingestion/output/`.
- `check_dataset.py`: `find_problems()`, the relational checks the JSON Schema can't express.
- `match.py`: `locator_matches()` and `case_hit()`, the Gold Locator match rule (ADR-0028). Anything it can't parse raises instead of scoring a silent miss.
- `find_locator.py`: the keyword-search authoring helper.
- `run_eval.py`: the eval harness. `run_eval()` returns a report and `write_report()` saves it. It reuses `regdocs_store.db` and `regdocs_store.embed`.
- `runs/`: committed run reports, one immutable file per run.
- `tests/`: unit tests against small fixture copies of ingestion output (`tests/fixtures/`), plus `test_dataset.py` for the real dataset and `test_run_eval.py` for the harness.
