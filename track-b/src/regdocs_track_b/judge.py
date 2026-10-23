# verify's judge (issue #47, ADR-0006, ADR-0035): the model only gives a verdict
# per claim; Confidence and the Flags are computed here, never taken from the
# model's own sense of certainty.

import re
from dataclasses import dataclass

# Below this fraction of supported claims, the answer is flagged. Not tuned
# against any data yet: it is the first thing to revisit once verify has evals.
LOW_CONFIDENCE_THRESHOLD = 0.8

# One claim per line. Small models add bullets, numbering and capitals, so the
# prefix and the case are forgiven; anything else on a line is not a verdict.
CLAIM_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])?\s*(SUPPORTED|UNSUPPORTED)\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class ClaimVerdict:
    claim: str
    supported: bool


def parse_verdicts(reply: str) -> list[ClaimVerdict]:
    verdicts = []
    for found in CLAIM_LINE.finditer(reply):
        supported = found.group(1).upper() == "SUPPORTED"
        verdicts.append(ClaimVerdict(found.group(2), supported))
    return verdicts


def confidence_of(verdicts: list[ClaimVerdict]) -> float:
    """The fraction of claims the judge found supported.

    No verdicts is 0.0: a reply that can't be read leaves the answer
    unverified, which must not look like a clean bill of health.
    """
    if not verdicts:
        return 0.0
    supported = 0
    for verdict in verdicts:
        if verdict.supported:
            supported += 1
    return supported / len(verdicts)


def flags_for(confidence: float) -> list[str]:
    flags = []
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        flags.append("low_confidence")
    # Nothing at all was supported: the answer strayed wholly beyond the Chunks.
    if confidence == 0.0:
        flags.append("no_supporting_context")
    return flags
