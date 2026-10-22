# Rule-based PII detection and Redaction (issue #43, ADR-0008).
#
# classify detects PII in the query once; those matches both raise the
# pii_detected Flag and drive Redaction, so the Flag and the stored
# placeholders can't disagree. Detection is deterministic rules, not a model:
# it catches structured identifiers only. Names and addresses in free text are
# out of reach, which the Track B README documents.

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiMatch:
    kind: str
    start: int
    end: int
    text: str


def luhn_valid(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def mod97_valid(iban: str) -> bool:
    rearranged = iban[4:] + iban[:4]
    number = ""
    for char in rearranged:
        if char.isdigit():
            number += char
        else:
            # A=10 ... Z=35, as the IBAN standard defines the check.
            number += str(ord(char) - 55)
    return int(number) % 97 == 1


# The PPSN check letter: weighted digit sum mod 23, indexed into this string.
PPSN_CHECK_LETTERS = "WABCDEFGHIJKLMNOPQRSTUV"


def ppsn_valid(ppsn: str) -> bool:
    total = 0
    for digit, weight in zip(ppsn[:7], range(8, 1, -1)):
        total += int(digit) * weight
    # An optional second letter is weighted 9 (A=1 ... I=9); W counts as 0.
    if len(ppsn) == 9 and ppsn[8].upper() != "W":
        total += (ord(ppsn[8].upper()) - 64) * 9
    return PPSN_CHECK_LETTERS[total % 23] == ppsn[7].upper()


def _is_iban(text: str) -> bool:
    compact = text.replace(" ", "")
    return 15 <= len(compact) <= 34 and mod97_valid(compact)


def _is_card(text: str) -> bool:
    digits = re.sub(r"[ -]", "", text)
    return 13 <= len(digits) <= 19 and luhn_valid(digits)


# (kind, pattern, optional checksum). Order is precedence: a span claimed by an
# earlier rule is not re-read by a later one, so an IBAN's digits are never
# also reported as a phone number.
RULES = [
    (
        "IBAN",
        re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"),
        _is_iban,
    ),
    ("CARD", re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"), _is_card),
    ("PPSN", re.compile(r"\b\d{7}[A-Wa-w][A-Ia-iWw]?\b"), ppsn_valid),
    (
        "EMAIL",
        re.compile(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
        ),
        None,
    ),
    # Irish formats only: +353 / 00353 / a leading 0, then an area or mobile
    # prefix and the subscriber number. The prefix can't start with 0, which
    # keeps zero-padded reference numbers out.
    (
        "PHONE",
        re.compile(
            r"(?<![\w+])\(?(?:\+353[\s-]?|00353[\s-]?|0)\(?[1-9]\d?\)?"
            r"[\s-]?\d{3}[\s-]?\d{3,4}(?!\d)"
        ),
        None,
    ),
]


def _overlaps(found: re.Match, other: PiiMatch) -> bool:
    return found.start() < other.end and other.start < found.end()


def detect_pii(text: str) -> list[PiiMatch]:
    """Return the PII found in `text`, in order of appearance, non-overlapping."""
    accepted = []
    for kind, pattern, is_valid in RULES:
        for found in pattern.finditer(text):
            if is_valid is not None and not is_valid(found.group(0)):
                continue
            overlaps = False
            for other in accepted:
                if _overlaps(found, other):
                    overlaps = True
            if not overlaps:
                accepted.append(
                    PiiMatch(kind, found.start(), found.end(), found.group(0))
                )
    accepted.sort(key=lambda match: match.start)
    return accepted


def placeholder(kind: str) -> str:
    return f"[REDACTED:{kind}]"


def redact_query(text: str, matches: list[PiiMatch]) -> str:
    """Replace each detected span in the query where it was found."""
    pieces = []
    position = 0
    for match in matches:
        pieces.append(text[position : match.start])
        pieces.append(placeholder(match.kind))
        position = match.end
    pieces.append(text[position:])
    return "".join(pieces)


def redact_answer(answer: str, matches: list[PiiMatch]) -> str:
    """Replace the answer's echoes of values detected in the query.

    The answer is not scanned itself: only PII the user supplied is redacted,
    so an address the model quotes from a Chunk (a regulator's contact email)
    survives. The cost is that PII the model invents or reformats is missed.
    """
    kind_by_text = {}
    for match in matches:
        kind_by_text[match.text] = match.kind
    # Longest first, so a value that contains another is replaced whole.
    for text in sorted(kind_by_text, key=len, reverse=True):
        replacement = placeholder(kind_by_text[text])
        # Whole values only: a value inside a longer word or number isn't an echo.
        pattern = r"(?<!\w)" + re.escape(text) + r"(?!\w)"
        answer = re.sub(pattern, lambda found: replacement, answer)
    return answer
