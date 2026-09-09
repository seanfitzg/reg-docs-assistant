# Events are never edited — corrections and annotations are new events

The audit trail's value rests on Events being genuinely immutable. No Event, once written, is ever updated in place — this applies uniformly to every kind of after-the-fact action, not just one of them:

- A human **override** of a query's answer is its own new `AnswerOverridden` Event, referencing the original `QueryAnswered` Event by id.
- A human **flagging** an Event for attention after the fact is its own new `EventFlagged` Event, referencing the original by id — not an edit to the original's `flags` array.

In both cases, "the current state" (the effective answer, the current set of flags) is a derived view, computed by folding all Events for a given query id, not a stored field anywhere. This follows the event-sourcing pattern (append-only log, current state derived by folding events) rather than a mutable audit-log-with-fields approach, because a mutable field on a record described as "immutable" is exactly the kind of contradiction a careful reader would flag. There is no `human_override` field and no post-write mutation of `flags` on `QueryAnswered` — an early draft schema had a `human_override` field, but it has no purpose once corrections are their own Event.

Automated flags (`low_confidence`, `no_supporting_context`, `pii_detected`, `possible_prompt_injection`, `possibly_superseded_source`) are the one exception that isn't really an exception: they're computed *at* write time, as part of producing the answer, so they safely belong on the original Event from birth. Only flags added *later* — `human_flagged` — need their own Event, because only they happen after the original write.
