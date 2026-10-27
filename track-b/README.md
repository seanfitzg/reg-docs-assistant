# /track-b

Track B: the Python implementation of RegDocs Assistant (FastAPI, LangChain, LangGraph), built beside the .NET Track A over the same corpus, store, schema and eval set (`docs/ai-integration-portfolio-plan.md`).

So far it holds the **graph skeleton** (`graph.py`) and the **retriever** (`retriever.py`, ADR-0032): a custom LangChain retriever over the `chunk_embeddings` table. Given a question it embeds it with the same model and `search_query: ` prefix the Chunks were stored with (ADR-0026), runs a pgvector cosine search restricted to each Document's active Chunking Generation (ADR-0025), and returns the top-k Chunks as LangChain `Document`s.

```python
retriever = ChunkRetriever(embedding_client=OllamaEmbeddingClient(), k=5)
for document in retriever.invoke("What must a firm disclose?"):
    print(document.metadata)  # chunk_id, document_id, locator, score, chunking_strategy
```

`k` is configuration, default 5 (`DEFAULT_K`). The search is pure vector search, so it reproduces the baseline run report in `eval/runs` (ADR-0030). Hybrid search is a later, separately measured change.

`graph.py` is a LangGraph state graph with the four fixed Steps, classify → retrieve → draft → verify, and `answer_question(graph, question)` returns an Event that validates against `schema/event.schema.json`. classify runs the PII rules and an injection classifier described below (its Step records the classifier's model name); retrieve uses the retriever; draft prompts an injected chat model from the versioned file `prompts/draft-v1.txt`, which lists the retrieved Chunks as numbered blocks `[1]`, `[2]`, … in rank order. The model cites by number, and code resolves each `[n]` to the real Chunk's document id and locator (ADR-0010). A number with no matching Chunk is dropped from the Citations and stripped from the stored answer. Citations live in the graph's final state (`final["citations"]`), not in the Event, which the shared schema has no field for. verify asks a judge model for a verdict per claim (described below). Each node is timed with a monotonic clock. Local-model Steps record cost 0 and an OpenAI Step records its estimated cost in USD.

## Verify and Confidence

verify sends the drafted answer and the numbered Chunks to a judge model with a versioned prompt (`prompts/verify-v1.txt`). The model lists the answer's separate claims, one per line, as `SUPPORTED: <claim>` or `UNSUPPORTED: <claim>`, and nothing else. Code (`judge.py`) reads those lines and does the rest (ADR-0006, ADR-0035):

- **Confidence** is the fraction of claims marked supported. It is computed in code, never the model's own sense of certainty, and recorded on the verify Step beside the judge's model name.
- `low_confidence` is raised when Confidence is below `LOW_CONFIDENCE_THRESHOLD` (0.8). `no_supporting_context` is raised when no claim is supported, so a fully unsupported answer carries both.
- verify only annotates. The answer is returned unchanged, and nothing is re-retrieved or re-drafted: each Step runs once.

```python
event = answer_question(graph, "How much notice?")
event["steps"][
    3
]  # {"step_type": "verify", "model": "qwen2.5:7b-instruct", "confidence": 0.5, ...}
event["flags"]  # ["low_confidence"]
```

A reply with no readable claim lines gives Confidence 0.0, so it raises both Flags: an answer that couldn't be checked is not treated as checked. Lines are read leniently (bullets, numbering and capitals are accepted), because small models don't always follow a format to the letter.

**Limits:**

- The judge writes its own list of claims, so it can leave out a claim it would have had to mark unsupported. Splitting the answer into claims in code would stop that, at the cost of crude sentence boundaries.
- The threshold 0.8 is untuned. With one claim in five unsupported the answer passes; with two in five it is flagged.
- The judge is a 7B local model judging a 7B local model's answer (by default the same model; set `JUDGE_MODEL` to another model name from the chosen provider to use another, for the API and for `test_real_judge.py`). It is a signal for a human to look at, not a guarantee, and a supported answer can still be wrong (a superseded source is the usual case).
- Only the judge's output format is tested against a real model (`RUN_REAL_JUDGE=1 python -m pytest track-b/tests/test_real_judge.py`, needs Ollama). How good its verdicts are is not measured yet.

## Injection classifier and the two halts

classify also sends the query to a chat model with a versioned prompt (`prompts/injection-v1.txt`) that asks for one word, YES or NO, on whether it is a prompt-injection attempt. YES raises `possible_prompt_injection` and halts the run at classify (ADR-0008). Separately, retrieve finding zero Chunks raises `no_chunks_retrieved` and halts at retrieve (ADR-0009). A halted run:

- answers with a fixed string defined in code (`REFUSAL_MESSAGE`, `NOT_FOUND_MESSAGE` in `graph.py`), never model-generated;
- stores an Event holding only the Steps that ran (classify alone, or classify and retrieve), which validates against the shared schema;
- is an ordinary HTTP 200 from `POST /query`, with the message as the `answer`, no citations and the Flag in `flags`.

`pii_detected` never halts, so a query can carry both Flags.

The verdict is read from the reply's first word. A reply that doesn't start with NO (including an empty or rambling one) counts as an injection: the classifier fails closed, so a genuine question may occasionally be refused but an unreadable verdict never lets a query through.

**Limits** (a small local model is a weak guardrail, not a wall):

- It is a model judgement, so it is non-deterministic in principle and can miss subtle or non-English attempts, or ones phrased as a genuine question. It can also refuse a genuine question that quotes attack text.
- The query is placed inside the classifier's own prompt, so an attack can target the classifier itself ("answer NO"). The prompt delimits the message and tells the model to treat it as data, which helps but does not guarantee anything.
- Only the query is screened. Injection hidden in a retrieved Chunk (text from a Document) is not.
- The classifier and draft both use `qwen2.5:7b-instruct` by default (`api.py`), set per call to `build_graph`.

`test_real_injection.py` is opt-in: it runs the real classifier on a documented override attempt and a genuine question (`RUN_REAL_INJECTION=1 python -m pytest track-b/tests/test_real_injection.py`, needs Ollama with the model pulled).

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

`test_judge.py` and `test_graph_verify.py` need nothing running: the first covers the line parser, Confidence and the Flag rules; the second drives scripted fake judge replies through the graph and checks the Step, the Flags, the prompt and that nothing is retried. `test_real_judge.py` is opt-in (see above). `test_graph_halts.py` needs nothing running: scripted fake classifier and draft models drive both halts, the fixed messages, the stored Steps and the verdict reading. `test_api.py` drives the whole API through FastAPI's in-process `TestClient` against `regdocs_test`, with a fake retriever and scripted fake chat model. It needs Postgres but not Ollama, and skips itself without it.

## Running the API

`api.py` is a FastAPI app with two endpoints, both synchronous, with no streaming and no authentication:

- `POST /query` with `{"question": "..."}` runs the graph, stores the Event and returns `{event_id, answer, citations, flags}`. The answer is the stored (Redacted) one. An empty question is a 422.
- `GET /events/{id}` returns the stored Event, or 404 for an unknown id. Citations are not part of the Event (the shared schema has no field for them), so only the POST response carries them.

To run it locally you need the Postgres container loaded and embedded (see `store/README.md`) and Ollama serving `nomic-embed-text` and `qwen2.5:7b-instruct` (`ollama pull qwen2.5:7b-instruct`). From the repo root, with the venv active:

```
uvicorn regdocs_track_b.api:create_default_app --factory
```

Then try it at `http://127.0.0.1:8000/docs` (FastAPI's interactive page) or:

```
curl -X POST http://127.0.0.1:8000/query -H "Content-Type: application/json" -d '{"question": "What must a firm disclose?"}'
curl http://127.0.0.1:8000/events/<event_id>
curl "http://127.0.0.1:8000/queries?page=1"   # query history, newest first, 20 per page
```

### Choosing the chat model: Ollama or OpenAI

`LLM_PROVIDER` picks the model behind classify, draft and verify (ADR-0036). It is read at startup, so restart to switch.

```
uvicorn regdocs_track_b.api:create_default_app --factory              # ollama (default)
$env:OPENAI_API_KEY = "sk-..."; $env:LLM_PROVIDER = "openai"          # PowerShell
uvicorn regdocs_track_b.api:create_default_app --factory              # gpt-4o-mini
```

Settings can also live in a `.env` file at the repo root (gitignored, never committed), read when the app starts:

```
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
```

The search starts at the directory you run `uvicorn` from and walks upwards. A variable already set in the environment wins over the file. Only the app loads it: pytest does not, so a key in `.env` does not switch on the opt-in OpenAI tests.

Embeddings always run on local Ollama (`nomic-embed-text`), so Ollama and Postgres must be up either way; only the question and the retrieved Chunks are sent to OpenAI. A paid Step records its estimated USD cost from a hand-kept price table in `models.py`. If OpenAI refuses the key or the credit runs out, `/query` returns 502 with `model error: ...`. `JUDGE_MODEL` must name a model the chosen provider serves. The prompts were tuned on `qwen2.5:7b-instruct`, so treat the first OpenAI run as a new baseline.

`test_provider_pipeline.py` has no fakes: two startup checks run by default, and the rest are opt-in. `RUN_REAL_OPENAI=1` adds a real call with a bad key (free, network only) that must be a 502; with `OPENAI_API_KEY` and `RUN_REAL_PIPELINE=1` as well it runs the OpenAI happy path, and `RUN_REAL_PIPELINE=1` alone runs the Ollama one. The happy paths store a real Event.

`STORE_DATABASE_URL` points it at a different database (default: `regdocs`). `create_app(graph, db_url)` takes an already-built graph, which is how the tests inject fakes.

## Layout

Python modules live in `src/regdocs_track_b/` (`graph.py`, `pii.py`, `injection.py`, `judge.py`, `events.py`, `api.py`, `retriever.py`, and `testing.py`, the fakes the graph tests share), tests in `tests/`; `prompts/` stays at the top level.

- `graph.py` — the four-node graph, Citation resolution and Event assembly.
- `api.py` — the FastAPI app: `create_app` (injectable, used by tests) and `create_default_app` (the real models for `LLM_PROVIDER`, used by uvicorn).
- `models.py` — the chat-model factory, per-provider defaults, provider error types and `cost_of`.
- `events.py` — `write_event` (schema validation, then the append-only insert) and `read_event`.
- `judge.py` — reads the judge's per-claim lines and computes Confidence and the verify Flags.
- `injection.py` — reads the classifier's YES/NO verdict, failing closed.
- `pii.py` — PII detection rules and the two redaction functions.
- `prompts/` — versioned prompt files (`draft-v1.txt`, `injection-v1.txt`, `verify-v1.txt`); a new version is a new file.
- `retriever.py` — `ChunkRetriever` and its search SQL.
- `tests/` — as above.
