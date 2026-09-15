# Validates pipeline output against the shared JSON Schemas in /schema.
#
# This mirrors schema/tests/support.py (same FormatChecker reasoning: a
# plain jsonschema.validate() call silently skips "format" keywords like
# "date"/"uri" unless a FormatChecker is passed explicitly). It isn't
# imported from schema/tests directly, though, because ingestion/ is a
# separate component with its own virtual environment and dependencies
# (schema/'s venv has no reason to carry pymupdf, and vice versa) -- schema/
# stays the "shared spine" both future tracks depend on, ingestion is one
# more independent consumer of it, not an extension of its test suite.

import json
from pathlib import Path

import jsonschema

FORMAT_CHECKER = jsonschema.FormatChecker()

SCHEMA_DIR = Path(__file__).parent.parent / "schema"


def load_schema(schema_filename: str) -> dict:
    return json.loads((SCHEMA_DIR / schema_filename).read_text())


def validate_against_schema(payload: dict, schema: dict) -> None:
    # Raises jsonschema.exceptions.ValidationError on failure; returns
    # nothing on success, the same "no news is good news" shape as
    # schema/tests/support.py's validate().
    jsonschema.validate(instance=payload, schema=schema, format_checker=FORMAT_CHECKER)
