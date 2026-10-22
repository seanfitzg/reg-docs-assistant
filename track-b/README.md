# /track-b

Track B: the Python implementation of RegDocs Assistant (FastAPI, LangChain, LangGraph), built beside the .NET Track A over the same corpus, store, schema and eval set (`docs/ai-integration-portfolio-plan.md`).

So far it holds the **graph skeleton** (`graph.py`) and the **retriever** (`retriever.py`, ADR-0032): a custom LangChain retriever over the `chunk_embeddings` table. Given a question it embeds it with the same model and `search_query: ` prefix the Chunks were stored with (ADR-0026), runs a pgvector cosine search restricted to each Document's active Chunking Generation (ADR-0025), and returns the top-k Chunks as LangChain `Document`s.

```python
retriever = ChunkRetriever(embedding_client=OllamaEmbeddingClient(), k=5)
for document in retriever.invoke("What must a firm disclose?"):
    print(document.metadata)  # chunk_id, document_id, locator, score, chunking_strategy
```

`k` is configuration, default 5 (`DEFAULT_K`). The search is pure vector search, so it reproduces the baseline run report in `eval/runs` (ADR-0030). Hybrid search is a later, separately measured change.

`graph.py` is a LangGraph state graph with the four fixed Steps, classify → retrieve → draft → verify, and `answer_question(graph, question)` returns an Event that validates against `schema/event.schema.json`. verify is a stub (model `"stub"`, confidence `0.0`); classify runs the PII rules described below (model `"rules"`), and its prompt-injection half is still unbuilt; retrieve uses the retriever; draft prompts an injected chat model from the versioned file `prompts/draft-v1.txt`, which lists the retrieved Chunks as numbered blocks `[1]`, `[2]`, … in rank order. The model cites by number, and code resolves each `[n]` to the real Chunk's document id and locator (ADR-0010). A number with no matching Chunk is dropped from the Citations and stripped from the stored answer. Citations live in the graph's final state (`final["citations"]`), not in the Event, which the shared schema has no field for. Each node is timed with a monotonic clock and local-model Steps record cost 0. The halting Flags and the real verify are later work.

## PII detection and Redaction

classify scans the query with deterministic rules (`pii.py`) and returns the matched spans. Any match raises `pii_detected`, which does not halt the run (ADR-0008): retrieve, draft and verify still see the original text. After the run, `answer_question` replaces the matches in the Event's `query` and `answer` with typed placeholders such as `[REDACTED:EMAIL]`, before the Event is returned for validation. The Flag and the placeholders come from the same matches, so they can't disagree. Retrieved Chunk text pinned on the retrieve Step is never redacted: it is public source text, not user input.

```python
event = answer_question(graph, "My email is jane@x.ie, how much notice?")
event["query"]  # "My email is [REDACTED:EMAIL], how much notice?"
event["flags"]  # ["pii_detected"]
```

Detected kinds: `EMAIL`, `PHONE`, `IBAN`, `PPSN`, `CARD`.

**Limits** (rule-based detection catches structured identifiers, not meaning):

- Names and postal addresses in free text are not detected. "John Murphy of 12 Main Street" passes through unchanged. Finding those needs a named-entity model, which is a separate piece of work.
- Phone numbers are Irish formats only (`+353`, `00353` or a leading `0`). Foreign, freephone (`1800`) and premium-rate numbers are missed, and a reference number shaped like an Irish number (a `0`, then a non-zero digit and eight or so more) can be a false positive.
- Card numbers, IBANs and PPSNs must pass their checksum (Luhn, mod-97, the PPSN check letter), which cuts false positives but means an identifier with a typo is treated as ordinary text.
- The answer is redacted by replacing exact echoes of values found in the query. PII the model writes that the user never supplied is not scanned for, and an echo the model reformats (`0871234567` for `087 123 4567`) is missed. Echoes are matched as whole values, so `jane@x.ieee` is left alone. Scanning the answer itself would also redact addresses quoted from Chunks, such as a regulator's contact email.

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
- `test_pii.py` and `test_graph_pii.py` need nothing running: the first covers each detection rule, its checksums and the two redaction functions; the second drives a query with PII through the graph with a fake model and checks the Flag, the stored placeholders, that draft saw the original text, and that Chunk text is untouched.
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

## Storing Events

`events.py` has `write_event(event, db_url)`: it validates the Event against the schema for its `event_type`, then appends it to the `events` table (`store/init/004_events.sql`, ADR-0031). An Event that fails validation, or has an unknown `event_type`, raises and writes nothing. `recorded_at` is stamped by the database. The table rejects `UPDATE` and `DELETE`, so Redaction must already have happened: pass the Event `answer_question` returns, never a hand-built one with raw user text.

```python
event = answer_question(graph, "My email is jane@x.ie, how much notice?")
write_event(event, DB_URL)  # stores "My email is [REDACTED:EMAIL], ..."
```

`test_events.py` needs the Postgres container and skips itself otherwise.

## Layout

Python modules live in `src/regdocs_track_b/` (`graph.py`, `pii.py`, `events.py`, `retriever.py`, and `testing.py`, the fakes the graph tests share), tests in `tests/`; `prompts/` stays at the top level.

- `graph.py` — the four-node graph, Citation resolution and Event assembly.
- `events.py` — `write_event`: schema validation, then the append-only insert.
- `pii.py` — PII detection rules and the two redaction functions.
- `prompts/` — versioned prompt files (`draft-v1.txt`); a new version is a new file.
- `retriever.py` — `ChunkRetriever` and its search SQL.
- `tests/` — as above.
