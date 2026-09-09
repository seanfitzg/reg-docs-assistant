# possible_prompt_injection halts the pipeline; pii_detected does not

The two guardrail flags `classify` can raise are handled differently, deliberately breaking the "annotate, never act" principle set in ADR-0006 for one of them:

- **`possible_prompt_injection`** halts the pipeline immediately at `classify`. No `retrieve`/`draft`/`verify` Steps run; the `Event` is written with only the `classify` Step present, flagged, and the user receives a generic refusal rather than a drafted answer.
- **`pii_detected`** does not halt anything. The pipeline runs to completion normally against the original text; the flag instead triggers Redaction — PII is stripped before the `Event` is persisted, but nothing about how the query was processed changes.

The two aren't treated alike because they aren't alike: a suspected injection is a safety problem — letting attacker-controlled text flow further into `retrieve`/`draft` only gives it more surface to land on, so continuing "just flagged" means the risk was already taken before anyone sees the flag. PII in a legitimate query is a storage/handling problem, not a processing one — there's no reason answering the question should be affected, only what ends up on disk.
