# The verify judge lists the claims; code computes Confidence from its verdicts

`verify` asks a judge model to break the drafted answer into claims and mark each `SUPPORTED` or `UNSUPPORTED` against the retrieved Chunks, one line per claim. Code parses those lines, computes Confidence as the supported fraction, and raises `low_confidence` (below 0.8) and `no_supporting_context` (no claim supported). A reply with no readable claim lines counts as Confidence 0.0.

The model supplies verdicts, never the score. This is what CONTEXT.md means by Confidence not being the model's self-reported certainty: a model's stated confidence is poorly calibrated, while a count of per-claim verdicts is something code can compute, test with scripted replies, and later compare against human labels.

Two alternatives were weighed:

- **Splitting the answer into claims in code, then judging each.** This stops the judge from silently leaving out a claim it would have marked unsupported, which is this design's main weakness. It was rejected for now because sentence boundaries in regulatory text (clause references like "s. 3.2(a)", abbreviations) are crude to split on, and one sentence often holds several claims. If evals show the judge omitting claims, this is the fix.
- **One overall supported/unsupported verdict.** Simpler, but it gives no fraction to compute and hides which part of the answer failed.

An unreadable reply fails towards "unverified", as the injection classifier does (ADR-0008): a check that couldn't run must not look like a check that passed. The 0.8 threshold is a first guess, to be revisited once verify has evals. As ADR-0006 requires, none of this changes the pipeline: the answer is returned as drafted, flagged, and each Step runs once.
