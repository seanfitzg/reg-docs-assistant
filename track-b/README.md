# /track-b

Track B: the Python implementation of RegDocs Assistant (FastAPI, LangChain, LangGraph), built beside the .NET Track A over the same corpus, store, schema and eval set (`docs/ai-integration-portfolio-plan.md`).

So far it holds the **retriever** (`retriever.py`, ADR-0032): a custom LangChain retriever over the `chunk_embeddings` table. Given a question it embeds it with the same model and `search_query: ` prefix the Chunks were stored with (ADR-0026), runs a pgvector cosine search restricted to each Document's active Chunking Generation (ADR-0025), and returns the top-k Chunks as LangChain `Document`s.

```python
retriever = ChunkRetriever(embedding_client=OllamaEmbeddingClient(), k=5)
for document in retriever.invoke("What must a firm disclose?"):
    print(document.metadata)  # chunk_id, document_id, locator, score, chunking_strategy
```

`k` is configuration, default 5 (`DEFAULT_K`). The search is pure vector search, so it reproduces the baseline run report in `eval/runs` (ADR-0030). Hybrid search is a later, separately measured change.

## Setup

```
python -m venv track-b/.venv
track-b/.venv/Scripts/activate      # Windows
# source track-b/.venv/bin/activate # macOS/Linux
pip install -r track-b/requirements.txt
```

The retriever reuses `/store`'s `db.py` and `embed.py` (by path, not as a package) and needs the same prerequisites as the eval harness (`eval/README.md`): Postgres up, store loaded, Chunks embedded, and Ollama running with `nomic-embed-text` pulled.

## Running the tests

```
python -m pytest track-b/tests
```

- `test_retriever_mapping.py` needs nothing running: it covers how a database row becomes a `Document`, and the `k` default.
- `test_retriever.py` needs the Postgres container (it uses `regdocs_test`, so real data is untouched) and skips itself otherwise. It uses a fake embedding client, so Ollama isn't needed.
- `test_baseline_parity.py` is opt-in because it needs Postgres loaded and embedded plus Ollama. It runs every answerable Eval Case through the retriever at k=10 and asserts recall matches the baseline report:

```
RUN_BASELINE_PARITY=1 python -m pytest track-b/tests
```

## Layout

- `retriever.py` — `ChunkRetriever` and its search SQL.
- `tests/` — as above.
