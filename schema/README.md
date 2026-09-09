# /schema

JSON Schema definitions for RegDocs Assistant's shared domain model (`Event`, `Document`, `Chunk`, and related shapes — see `CONTEXT.md` and `docs/adr/`), validated against fixture payloads by a Python test harness.

This directory is a shared contract both Track A (.NET) and Track B (Python) implementations validate against. The schema and fixture files themselves are plain JSON — only the test harness that validates them is Python (a deliberate learning choice, see `docs/adr/0011-schema-validation-harness-is-python.md`).

## Setup

```
python -m venv schema/.venv
schema/.venv/Scripts/activate      # Windows
# source schema/.venv/bin/activate # macOS/Linux
pip install -r schema/requirements.txt
```

## Running the tests

```
pytest schema/tests
```

Exit code `0` means every fixture validated as expected; a non-zero exit code means at least one didn't.

## Layout

- `fixtures/<name>/schema.json` — one JSON Schema.
- `fixtures/<name>/valid.json`, `fixtures/<name>/invalid.json` (or similarly named) — example payloads asserted to pass or fail validation against that schema.
- `tests/test_<name>.py` — the pytest file validating that schema's fixtures.

`fixtures/trivial/` is a throwaway example proving the harness itself works end-to-end; it's not part of the real domain model.
