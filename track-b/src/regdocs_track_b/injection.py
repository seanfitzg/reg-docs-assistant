# Reading the injection classifier's verdict (issue #46, ADR-0008).

import re


def reads_as_injection(verdict: str) -> bool:
    """True unless the model's reply starts with NO.

    The prompt asks for one word, but small models add punctuation or a
    sentence. Only the first word counts. A reply that is neither YES nor NO
    fails closed, as an injection: a halted genuine question is a visible,
    recoverable annoyance, while a missed attack is not.
    """
    words = re.findall(r"[A-Za-z]+", verdict)
    if words and words[0].lower() == "no":
        return False
    return True
