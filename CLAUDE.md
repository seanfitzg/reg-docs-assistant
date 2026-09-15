## Purpose & working style

This project exists so the owner (an experienced .NET developer, new to AI/ML) can **learn AI by doing**, primarily for job-search purposes. Skill growth is the actual goal — a working system is the by-product, not the point. Don't optimise for "get it built fast."

- Explain concepts as you go, especially anything AI/ML-specific (RAG, embeddings, model behavior, agent patterns, evals, etc.) — don't assume familiarity, and don't skip the explanation just because a decision seems obvious to you.
- Analogies to things the owner already knows (.NET, event sourcing/CQRS, DDD, TDD/BDD) are a teaching aid, not a shortcut — use them to build intuition, then still explain the AI-specific mechanics in full rather than stopping at "it's basically like X."
- When making design decisions together (e.g. via `/grill-with-docs`), don't just state a recommendation — explain the trade-off so the owner can reason to their own answer, then confirm understanding before locking it in.
- Python code should be commented more heavily than usual — line-by-line where the syntax or library usage itself is unfamiliar territory (per "Genuinely new territory" below), not just for non-obvious *why*. This is a deliberate exception to normal terse-comment style, for learning purposes. Applies to Python specifically; other languages here (C#, TS) follow normal comment discipline.

## Owner background

Sean Fitzgerald — full-stack software engineer, 25+ years experience, currently at Mars Capital (Dublin). LinkedIn: https://www.linkedin.com/in/seanfitzg/. Full CV: `CV-SeanFitzgerald-March2026.docx.pdf` in repo root.

**Already deep expertise here — lean on these as analogies, but still explain the AI-specific parts in full:**
- Event sourcing & CQRS: won a Google Excellence Award (2013) for a thesis on "State Machine Design, Persistence and Code Generation using a Visual Workbench, Event Sourcing and CQRS." Also built a CQRS/nServiceBus exposure-calculation engine at Renaissance Re. Home turf.
- Regulatory/compliance reporting systems: led SEC Rule 13F-2 short-position disclosure reporting at Bank of America — large-scale batch jobs, rules engines, aggregation over huge datasets, directly analogous to this project's regulatory domain.
- TDD/BDD discipline: nUnit, Moq, SpecFlow, Cucumber, throughout career; strong opinions on maintainability and CI/CD.
- Deep .NET (ASP.NET, WCF, ADO.NET, Windows Forms through modern .NET Core) and solid React/Angular/Node/TypeScript/GraphQL.
- Already dabbling at the edges of AI tooling: AI-assisted coding, Spec-Driven Development/SpecKit, Playwright + MCP for AI-generated E2E tests. Aware of these concepts, not a stranger to "AI in the dev workflow" generally — the gap is AI/ML fundamentals themselves, not AI tooling as a concept.

**Genuinely new territory — explain these in full:**
- AI/ML fundamentals: RAG, embeddings/retrieval, model non-determinism & temperature, LLM-as-judge, agent orchestration patterns, prompt versioning, evals.
- Python and its AI ecosystem: no Python on the CV at all (career is C#/.NET + JS/TS). Track B of the plan (FastAPI, LangChain, LangGraph) is new language *and* new domain simultaneously — don't assume Python fluency either.

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (uses the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
