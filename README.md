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
- **19 ADRs** in [`docs/adr/`](./docs/adr).

Not built yet: retrieval, the agent pipeline (classify -> retrieve -> draft -> verify), the audit-event store, and both application tracks. This section will move as that lands.

## How this was built

- Design decisions get argued out with Claude before code is written, then recorded as ADRs - the reasoning outlives the conversation that produced it.
- Every piece of work is a GitHub issue, its own branch, its own PR. See [`docs/agents/issue-tracker.md`](./docs/agents/issue-tracker.md).
- [`CLAUDE.md`](./CLAUDE.md) sets how this project wants to be worked on: explain AI/ML concepts rather than assume them, use prior expertise (event sourcing, CQRS, regulatory reporting) as a teaching aid, comment Python more heavily than usual since it's new territory.
- The evidence is the commit history and the ADRs themselves - read `docs/adr/` in order to watch the model get sharper issue by issue.

## Layout

```
/schema      shared JSON Schema contracts (Event, Document, Chunk, ...)
/ingestion   pipeline turning corpus PDFs into Document/Chunk records
/corpus      source PDFs (not committed) + manifest
/docs/adr    architecture decision records
/docs/agents Claude Code agent skill configuration
CONTEXT.md   domain glossary
```

Each subdirectory has its own README - start with [`schema/README.md`](./schema/README.md) and [`ingestion/README.md`](./ingestion/README.md).

## About me

Sean Fitzgerald - full-stack engineer, 25+ years, currently at Mars Capital (Dublin). [LinkedIn](https://www.linkedin.com/in/seanfitzg/)
