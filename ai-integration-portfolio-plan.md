# Portfolio Project: Auditable RAG & Agent System (Dual-Stack)

**Positioning statement:** *A senior systems architect who proves AI-integration competence in both the enterprise .NET stack and the Python AI ecosystem, applied to a regulated-industry problem, with production-grade auditability built in from the ground up.*

This is the single artifact that answers three things a recruiter or client will ask at once:
- Can you actually build with LLMs, not just talk about them?
- Are you locked into one language/stack?
- Can you be trusted with AI in a regulated, auditable environment (fintech/financial services)?

---

## The concept, in one paragraph

You build a small system — **"RegDocs Assistant"** — that ingests public Irish financial-regulation documents (Central Bank of Ireland Consumer Protection Code, CCPC guidance, etc.) and answers natural-language questions about them using RAG and a multi-step agent. The differentiator is that **every AI action is captured as an immutable, replayable event** — what was asked, what was retrieved, what model/prompt version answered, what it cost, and whether a human overrode it. That audit trail is the artifact that turns a "chat with a PDF" tutorial into a demonstration of exactly the niche we identified: AI that a regulated business can actually trust in production.

You build the **same system twice** — once in C#/.NET, once in Python — sharing one architecture and one event schema. That's the proof you're not stack-locked.

---

## The shared spine (build this first, use it in both tracks)

### 1. Domain & data
- Corpus: 10–20 public PDFs — Central Bank of Ireland Consumer Protection Code, CCPC consumer finance guidance, or similar. Public, legally uncomplicated, and directly relevant to the Dublin fintech/financial-services market you're targeting.
- A small hand-written eval set: 15–20 question/answer pairs with the correct source passage identified. This is what lets you *measure* retrieval quality later instead of just eyeballing it — a detail that signals seniority on its own.

### 2. The event-sourced audit model (this is the actual differentiator — don't skip it)
Every interaction with the system produces an append-only event, e.g.:

```json
{
  "event_type": "QueryAnswered",
  "event_id": "uuid",
  "timestamp": "...",
  "query": "...",
  "retrieved_chunks": [{"doc_id": "...", "chunk_id": "...", "score": 0.83}],
  "model": "claude-sonnet-4-6 | gpt-4o | ...",
  "prompt_version": "v3",
  "answer": "...",
  "confidence": 0.91,
  "token_cost": {"input": 1200, "output": 340},
  "latency_ms": 850,
  "human_override": null,
  "flags": ["none"]
}
```

Store these in Postgres as JSONB in an append-only table. Both the .NET and Python implementations write to **the same table with the same schema** — that's what proves architectural portability rather than just "I wrote two demos."

From this you get, almost for free: full replay of any past answer, a queryable audit trail ("show me every answer that cited document X"), and the basis for the evaluation harness in Week 6.

### 3. Shared contracts
Define the event JSON schema and the document-chunk record schema once, in a shared `/schema` folder in the repo, and validate against it from both languages. This is a small thing that reads as very senior in a code review.

### 4. Model & infrastructure strategy — free-first, no Azure account required
No Azure account is needed to build or run this. Everything runs locally and free, with cloud kept as an optional, deferred, one-off step:

- **Chat + embeddings model:** run locally via **Ollama** or **LM Studio** — no API key, no billing, no rate limits, ideal for the iterate-fast build phase (weeks 1–6). Both expose an **OpenAI-compatible local endpoint**, so you can point the standard OpenAI connector in `Microsoft.Extensions.AI` / Semantic Kernel / LangChain at your local server's URL rather than needing a separate connector — same connector you'd use for Azure OpenAI or OpenAI direct, just a different base address. Worth trying both Ollama and LM Studio early since switching between them is just a URL and model name change.
- **Claude as the "final" model:** swap in Claude near the end (week 7–8), for the demo and the eval comparison (below). Anthropic's API doesn't speak the OpenAI wire format, so this needs a proper connector rather than the endpoint trick — check what's current and stable in Semantic Kernel/`Microsoft.Extensions.AI` when you get there. If nothing solid exists yet, a small custom `IChatClient` adapter for the Anthropic API is a good fallback, and a nice portfolio detail in its own right — it shows you understand the abstraction layer, not just a package.
- **Model routing as a production pattern:** because your event schema already logs which model answered each query, running multiple providers isn't a complication — it's a feature. Route cheap steps (classification, retrieval-relevance checks) to the free local model, and route only the final answer draft to Claude. That's a real cost-optimisation technique clients care about, not a compromise, and it plugs straight into the cost-tracking checklist item below.
- **Database:** Postgres + `pgvector` via Docker (`docker-compose`), not Azure Database for Postgres. You're already comfortable with Docker, so this is a config choice, not new learning.
- **Runtime:** everything runs via `docker-compose up` locally, orchestrated through JetBrains Rider (solid built-in Docker support, DB tools to browse the audit-event table directly, and `.http` scratch files for testing API endpoints without needing Postman).
- **Cloud deployment — optional, deferred, and cheap-to-free:** write the Bicep/IaC for how it *would* deploy to Azure Container Apps throughout the build, without ever running it — that alone demonstrates the skill in an interview or code review at zero cost. Optionally, near the very end, use Azure's one-time $200 / 30-day trial credit for a single short burst: spin it up, record the demo video, take screenshots, tear it down. Set a budget alert the moment the account is created so there's no risk of a surprise bill.

---

## Track A — .NET implementation

**Stack:** ASP.NET Core Web API · `Microsoft.Extensions.AI` (provider abstraction, pointed at Ollama/LM Studio's OpenAI-compatible endpoint, then Claude later) · Semantic Kernel (orchestration/plugins) · Microsoft Agent Framework (multi-step agent workflow — currently at Release Candidate, so expect some rough edges, which is fine, you can note that in your write-up) · Postgres + `pgvector` for embeddings, run via Docker · the audit-event table above · React front end (reuse your existing React experience) · JetBrains Rider for the whole build · Azure deployment via Bicep, written throughout, optionally run once at the end.

**What it demonstrates:** direct extension of your existing .NET seniority, current Microsoft AI tooling, and a real Azure deployment story (via IaC, optionally proven live) — this is the one to finish *first*, because it's the fastest route to a CV line that unlocks the €650–750/day .NET-plus-AI contracts.

## Track B — Python implementation

**Stack:** FastAPI · LangChain (`create_agent`, retrievers, tool definitions) · LangGraph (stateful multi-step orchestration — this is the part that will feel most natural to you, given the state-machine background) · same local-first model strategy (Ollama/LM Studio, then Claude) · same Postgres + `pgvector` via Docker · same audit-event schema · same optional/deferred Azure deployment approach.

**What it demonstrates:** that you're not stack-locked, and gives you access to the wider AI-native/startup contract market where Python is the default.

---

## Production-concerns checklist (apply to both tracks — this is what separates you from a tutorial)

- [ ] **Retrieval evaluation** — run your 15–20 question eval set through the pipeline, score retrieval accuracy, log it. Even a crude script counts.
- [ ] **Cost & token tracking** — every event records token usage; roll up a simple "cost per query" dashboard or report.
- [ ] **Latency logging** — capture and report p50/p95 response time.
- [ ] **Guardrails / prompt-injection resistance** — basic input sanitisation and a documented test of an injection attempt against your own system.
- [ ] **PII handling** — a redaction pass before anything goes into logs or events.
- [ ] **Human-in-the-loop override** — a simple UI/API action to flag or correct an answer, written back as an event (not a silent edit).
- [ ] **Observability** — OpenTelemetry tracing across the request path, even minimal.
- [ ] **CI/CD** — GitHub Actions building and testing on push; Azure deploy step optional, added only if/when you do the one-off cloud burst.
- [ ] **Tests** — unit tests for the retrieval and event-writing logic at minimum.
- [ ] **Model routing** — cheap local-model calls for classification/relevance steps, Claude reserved for the final answer draft; logged and cost-compared via the audit-event data.

You don't need all nine boxes ticked before you show this to anyone — even three or four, clearly implemented and explained, is far stronger than a bare chatbot demo.

---

## Suggested build sequence (~8 weeks, evenings/weekends around a full-time job)

Realistic pace assumption: 5–8 hours/week. If that's tight, extend to 10–12 weeks rather than cutting corners on the audit trail — that's the part doing the work for you.

| Week | Goal |
|---|---|
| 1 | Domain setup: pull the document corpus, define the shared event schema and chunk schema, stand up Postgres + pgvector via Docker, set up Ollama/LM Studio locally, write the eval Q&A set |
| 2 | Track A: basic RAG in .NET (Semantic Kernel + `Microsoft.Extensions.AI` pointed at the local model + pgvector) — plain Q&A over the docs, minimal API |
| 3 | Track A: wire in the audit-event table; every query writes an event; build a simple "replay this answer" endpoint |
| 4 | Track B: basic RAG in Python (LangChain, also pointed at the local model), writing to the **same** event table/schema as Track A |
| 5 | Add the agentic layer: multi-step workflow (classify → retrieve → verify → draft with citations) — Agent Framework in .NET, LangGraph in Python — still fully local |
| 6 | Production concerns pass: cost tracking, latency logging, guardrails, PII redaction, model routing, run the eval harness against the local model and record the numbers |
| 7 | Bring in Claude: wire up the Anthropic connector/adapter, re-run the eval harness for a local-vs-Claude comparison, adopt model routing if not already done; write the Bicep IaC and optionally do the one-off Azure deployment burst |
| 8 | Polish: README with architecture diagram, record a 3–5 min demo video (using Claude for the live run), write short posts on the hard parts (retrieval quality, cost, guardrails, and the local-vs-Claude findings) |

**If time is genuinely tight, priority order is:** Track A fully built with the audit trail (weeks 1–3, 6–7) → the eval harness and one production-concern item → *then* Track B, even in a reduced form. A finished, auditable Track A alone is already a strong, usable portfolio piece and directly serves your nearest-term goal (the .NET+AI contracts). Track B is what pushes you into "not stack-locked," so add it when you can, not necessarily before you start applying.

---

## How to present it

- **One GitHub repo**, two folders (`/dotnet`, `/python`), one shared `/schema` folder, one root README with an architecture diagram (even a simple one) showing both tracks writing to the same audit store.
- **README framing matters more than code volume** — lead with the problem (auditable AI in a regulated domain), not the tech list.
- **Two or three short write-ups** (LinkedIn articles or a personal blog) on the parts that show judgement, not just output: "What I learned evaluating RAG retrieval quality," "Building an audit trail for non-deterministic AI answers," and "Local models vs Claude: what actually changed in accuracy and cost" (using your own eval-harness numbers from Week 7). These are what a recruiter or hiring manager actually reads before a call.
- **CV/LinkedIn line:** something like *"Built a dual-stack (.NET/Python) auditable RAG and agent system for regulated-document Q&A, with full event-sourced traceability of AI decisions."* That single sentence does most of the work in getting you past a keyword screen and into a conversation.
- Update your CV and the recruiter outreach messages once Track A is live — that's the moment to send the "specialist trajectory" version of the email rather than waiting for the whole thing to be finished.
