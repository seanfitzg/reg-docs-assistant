# /track-b

Track B: the Python implementation of RegDocs Assistant (FastAPI, LangChain, LangGraph), built beside the .NET Track A over the same corpus, store, schema and eval set (`docs/ai-integration-portfolio-plan.md`).

So far it holds the **graph skeleton** (`graph.py`) and the **retriever** (`retriever.py`, ADR-0032): a custom LangChain retriever over the `chunk_embeddings` table. Given a question it embeds it with the same model and `search_query: ` prefix the Chunks were stored with (ADR-0026), runs a pgvector cosine search restricted to each Document's active Chunking Generation (ADR-0025), and returns the top-k Chunks as LangChain `Document`s.

```python
retriever = ChunkRetriever(embedding_client=OllamaEmbeddingClient(), k=5)
for document in retriever.invoke("What must a firm disclose?"):
    print(document.metadata)  # chunk_id, document_id, locator, score, chunking_strategy
```

`k` is configuration, default 5 (`DEFAULT_K`). The search is pure vector search, so it reproduces the baseline run report in `eval/runs` (ADR-0030). Hybrid search is a later, separately measured change.

`graph.py` is a LangGraph state graph with the four fixed Steps, classify → retrieve → draft → verify, and `answer_question(graph, question)` returns an Event that validates against `schema/event.schema.json`. classify and verify are stubs (model `"stub"`, verify confidence `0.0`); retrieve uses the retriever; draft prompts an injected chat model from the versioned file `prompts/draft-v1.txt`, which lists the retrieved Chunks as numbered blocks `[1]`, `[2]`, … in rank order. The model cites by number, and code resolves each `[n]` to the real Chunk's document id and locator (ADR-0010). A number with no matching Chunk is dropped from the Citations and stripped from the stored answer. Citations live in the graph's final state (`final["citations"]`), not in the Event, which the shared schema has no field for. Each node is timed with a monotonic clock and local-model Steps record cost 0. Halting Flags and the real classify/verify are later work.

## Setup

```
uv sync --all-packages              # once, from the repo root: one shared .venv for every folder
.venv/Scripts/activate              # Windows
# source .venv/bin/activate         # macOS/Linux
```

The retriever reuses `/store`'s `db` and `embed` modules (the `regdocs-store` workspace package) and needs the same prerequisites as the eval harness (`eval/README.md`): Postgres up, store loaded, Chunks embedded, and Ollama running with `nomic-embed-text` pulled.

## Running the tests

```
python -m pytest track-b/tests
```

- `test_graph.py` needs nothing running: a fake retriever and a scripted fake chat model drive the whole graph, and the resulting Event is validated against the shared schema.
- `test_draft_citations.py` needs nothing running either: a scripted fake model answers with `[n]` markers (including bad ones) and a recording fake checks the prompt it was sent.
- `test_retriever_mapping.py` needs nothing running: it covers how a database row becomes a `Document`, and the `k` default.
- `test_retriever.py` needs the Postgres container (it uses `regdocs_test`, so real data is untouched) and skips itself otherwise. It uses a fake embedding client, so Ollama isn't needed.
- `test_baseline_parity.py` is opt-in because it needs Postgres loaded and embedded plus Ollama. It runs every answerable Eval Case through the retriever at k=10 and asserts recall matches the baseline report:

```
RUN_BASELINE_PARITY=1 python -m pytest track-b/tests
```

- `test_real_draft.py` is also opt-in. It runs the real `qwen2.5:7b-instruct` (`ollama pull qwen2.5:7b-instruct`, ~4.7 GB) and checks that it writes a `[n]` marker for the supporting Chunk:

```
RUN_REAL_DRAFT=1 python -m pytest track-b/tests/test_real_draft.py
```

## Layout

Python modules live in `src/regdocs_track_b/` (`graph.py`, `retriever.py`, and `testing.py`, the fakes the graph tests share), tests in `tests/`; `prompts/` stays at the top level.

- `graph.py` — the four-node graph, Citation resolution and Event assembly.
- `prompts/` — versioned prompt files (`draft-v1.txt`); a new version is a new file.
- `retriever.py` — `ChunkRetriever` and its search SQL.
- `tests/` — as above.
