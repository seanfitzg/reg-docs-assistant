# classify owns guardrail screening, not a separate Step

`classify` is the query's single "is this safe, and what is it" gate: it produces both the routing signal `retrieve` needs and the `pii_detected` / `possible_prompt_injection` flags, all in one pass over the raw incoming query. There is no separate guardrail Step ahead of the four named ones.

The alternative — a dedicated guardrail Step before `classify` — was rejected because both jobs read the exact same short input (the query, before any retrieval), so splitting them into two Steps means paying for two model calls over the same text rather than one. This keeps the pipeline at four Steps: `classify` (routing + guardrails on the query), `retrieve` (also produces `possibly_superseded_source`, since it already knows which Documents came back and whether any is superseded), `draft`, `verify` (produces `low_confidence` and `no_supporting_context`, per ADR-0006).
