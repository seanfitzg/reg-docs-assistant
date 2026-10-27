# RegDocs Assistant

A RAG and multi-step agent system for answering questions about Irish financial-regulation documents, with every answer backed by an immutable, replayable audit trail.

It's also a portfolio project documenting how I use [Claude Code](https://claude.com/product/claude-code) to build software - see [How this was built](#how-this-was-built) below.

## The problem

Answering a question about a regulatory PDF with an LLM is easy. What's hard, and what actually matters in a regulated industry, is being able to say afterwards what was retrieved, which model answered, whether a human later overrode it, and whether asking again today gives the same substance.

Every interaction here is stored as an immutable, append-only **Event** - query, retrieved context, model/prompt version, cost, confidence, flags. Answers can be replayed and checked for drift; corrections are new events, never edits to the original. Full glossary in [`CONTEXT.md`](./CONTEXT.md), design reasoning in [`docs/adr/`](./docs/adr).

## Why dual-stack

Same architecture and event schema, built once in .NET and once in Python, both validated against one shared [`/schema`](./schema) contract - proof the design isn't tied to one language. My background is 25+ years in .NET; Python and its AI ecosystem are new ground I'm deliberately building here.

## Current status

- **[`/schema`](./schema)** - JSON Schema for `Event`, `Document`, `Chunk`, etc., with a Python test harness validating fixtures against them.
- **[`/ingestion`](./ingestion)** - turns the corpus into `Document`/`Chunk` records: PDF extraction, cleanup, three chunking strategies, deterministic ids, per-document failure isolation, schema validation on write.
- **[`/corpus`](./corpus)** - 20 public Central Bank of Ireland / CCPC documents, fully ingested (PDFs not committed; see `corpus/SOURCES.md`).
- **[`/store`](./store)** - Postgres + pgvector (via docker-compose) holding every ingested `Document`, `Chunking Generation` and `Chunk`, plus a vector embedding per active-generation Chunk. `loader.py` loads ingestion's output; `embed.py` computes embeddings with a local [Ollama](https://ollama.com) model (`nomic-embed-text`, 768 dimensions) into a `chunk_embeddings` table keyed by Chunk and model. Both are safe to re-run, and both are covered by integration tests against an isolated test database.
- **[`/eval`](./eval)** - the retrieval eval set: hand-written Eval Cases labelled by Gold Locator (`document_id` + locator), a JSON Schema for them, a test that every label exists in the ingested Chunks, and a keyword-search helper for writing cases. The harness that scores retrieval against it is next.
- **[`/track-b`](./track-b)** - the Python query pipeline (FastAPI, LangChain, LangGraph), built end to end:
  - a custom LangChain retriever over the stored embeddings;
  - a four-Step LangGraph graph, classify -> retrieve -> draft -> verify, producing numbered Citations resolved in code;
  - PII detection with Redaction, and a prompt-injection classifier, with both halts (injection, no Chunks retrieved);
  - a per-claim verify judge whose Confidence is computed in code, not by the model;
  - an append-only `events` table, with an immutability trigger, holding every Event;
  - `POST /query` and `GET /events/{id}`, plus `GET /queries`, the paged history listing the viewer uses;
  - the chat provider chosen at startup with `LLM_PROVIDER`: local Ollama (default) or OpenAI. Embeddings stay local (ADR-0036), and each Step records its real cost.
- **[`/reg-docs-viewer`](./reg-docs-viewer)** - a React/Vite UI over the API: a Query tab (answer, clickable citation markers, flags, the stored Event), and a History tab listing past questions with an event-detail popup.
- **[`/learning`](./learning)** - a self-contained HTML writeup per issue explaining what was built and the concepts behind it.
- **36 ADRs** in [`docs/adr/`](./docs/adr).

Not built yet: Track A (the .NET twin), replay and drift checks, human-override events, hybrid search, an eval of the full pipeline's answer quality (only retrieval is scored, and the verify judge's verdict quality is unmeasured), and a run of the eval set against OpenAI. This section will move as that lands.

## How this was built

- Design decisions get argued out with Claude before code is written, then recorded as ADRs - the reasoning outlives the conversation that produced it.
- Every piece of work is a GitHub issue, its own branch, its own PR. See [`docs/agents/issue-tracker.md`](./docs/agents/issue-tracker.md).
- [`CLAUDE.md`](./CLAUDE.md) sets how this project wants to be worked on: explain AI/ML concepts rather than assume them, use prior expertise (event sourcing, CQRS, regulatory reporting) as a teaching aid, comment Python tersely (the non-obvious why only) and explain concepts in conversation instead.
- The evidence is the commit history and the ADRs themselves - read `docs/adr/` in order to watch the model get sharper issue by issue.

## Layout

```
/schema      shared JSON Schema contracts (Event, Document, Chunk, ...)
/ingestion   pipeline turning corpus PDFs into Document/Chunk records
/store       Postgres + pgvector: loads Documents/Chunks, embeds Chunks
/eval        retrieval eval set (hand-written Eval Cases) + authoring tools
/track-b     Python query pipeline: LangGraph graph, FastAPI API, event store
/reg-docs-viewer  React UI: Query and History tabs
/corpus      source PDFs (not committed) + manifest
/learning    per-issue HTML writeups of what was built and why
/docs/adr    architecture decision records
/docs/agents Claude Code agent skill configuration
CONTEXT.md   domain glossary
```

Each subdirectory has its own README - start with [`schema/README.md`](./schema/README.md), [`ingestion/README.md`](./ingestion/README.md), [`store/README.md`](./store/README.md) and [`eval/README.md`](./eval/README.md) and [`track-b/README.md`](./track-b/README.md).

## Python workspace

The Python folders share one [uv](https://docs.astral.sh/uv/) workspace and one `.venv` at the repo root (ADR-0033). From the root:

```
uv sync --all-packages        # create/update .venv from uv.lock
uv run pytest                 # every folder's tests in one session
uv run pytest eval            # or just one folder
```

Each folder's README has its own run commands (`python -m regdocs_store.loader`, and so on). Tests that need Postgres or Ollama skip themselves when those aren't running.

## Running the whole ingestion process

Turns the corpus PDFs into searchable, embedded Chunks in Postgres. Prerequisites:

- the corpus PDFs in `corpus/` (see `corpus/SOURCES.md`)
- Postgres up: `docker compose up -d` in `store/`
- Ollama running with the embedding model pulled: `ollama pull nomic-embed-text`

From the repo root, with the venv active (`.venv/Scripts/activate` on Windows):

```
python scripts/reingest.py
```

That runs three steps in order, stopping at the first failure. Each can also be run on its own:

```
python -m regdocs_ingestion       # PDFs -> Document/Chunk JSON in ingestion/output/
python -m regdocs_store.loader    # that JSON -> Postgres
python -m regdocs_store.embed     # embed active-generation Chunks via Ollama
```

Re-running is safe. Ingestion regenerates `ingestion/output/` (ids are deterministic, so unchanged documents produce identical files). The loader only adds: records already in Postgres are skipped, never edited or deleted, apart from each Document's pointer to its active Chunking Generation. The embed step only computes embeddings for Chunks that don't have one yet.

So a re-run picks up new documents in the manifest and finishes any missing embeddings, but **edits to documents already in Postgres are not applied**. Changing a manifest entry's metadata (`title`, `publisher`, and so on), its `chunking_strategy`, the PDF, or the cleaning/chunking code updates the JSON in `ingestion/output/` only; the database keeps the first version it loaded. Re-chunking into a new Chunking Generation isn't built yet (generation 1 is hardcoded in `pipeline.py`), so to apply such a change today, reset the database (for example by removing the Docker volume in `store/`) and run the whole process again. Details in [`ingestion/README.md`](./ingestion/README.md) and [`store/README.md`](./store/README.md).

## Running the API and the viewer UI

Two programs run side by side: the **API** (Python, FastAPI, port 8000) does the work, and the **viewer** (React, port 5173) is a web page that talks to it. The viewer's dev server forwards anything under `/api` to the API, so the browser only ever talks to port 5173.

Prerequisites: the ingestion process above has been run (Postgres has embedded Chunks), Postgres is up (`docker compose up -d` in `store/`), Ollama is running, and the chat model is pulled (`ollama pull qwen2.5:7b-instruct`).

To use OpenAI for the chat Steps instead, set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` before starting the API (see ADR-0036). Retrieval still uses local Ollama embeddings. The default is Ollama.

**1. Start the API** (terminal 1, repo root):

```
uv run python -m uvicorn regdocs_track_b.api:create_default_app --factory
```

`uv run` uses the project's `.venv`. A bare `uvicorn` may resolve to a global Python install instead and fail with `ModuleNotFoundError: No module named 'regdocs_track_b'`; if you prefer a bare `uvicorn`, activate the venv first (`.venv\Scripts\activate`).

Why `python -m uvicorn` rather than `uv run uvicorn`: on Windows machines with Smart App Control or an Application Control policy, the generated `.venv\Scripts\uvicorn.exe` launcher is unsigned and gets blocked (`An Application Control policy has blocked this file. (os error 4551)`). Running it as a module goes through the trusted `python.exe` instead. The same applies to any other console script (`uv run python -m pytest`).

Check it at `http://127.0.0.1:8000/docs`.

**2. Start the UI** (terminal 2):

```
cd reg-docs-viewer
npm install        # first time only
npm run dev
```

Open `http://localhost:5173`. The **Query** tab runs a question and shows the answer, citations, flags and the stored Event. The **History** tab lists every question asked so far, newest first, 20 per page, each with the date it was recorded.

If the UI shows a connection error, the API isn't running; look at terminal 1. An HTTP 503 means the API can't reach Postgres (is Docker up?), and a 502 means the chat provider failed (Ollama aborted, or OpenAI refused the key or ran out of credit).

## About me

Sean Fitzgerald - full-stack engineer, 25+ years, currently at Mars Capital (Dublin). [LinkedIn](https://www.linkedin.com/in/seanfitzg/)
