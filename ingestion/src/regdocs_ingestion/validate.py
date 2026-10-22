# Validates pipeline output against the shared JSON Schemas in /schema.
#
# Mirrors regdocs_schema.testing (a plain jsonschema.validate() silently
# skips "format" keywords like "date"/"uri" unless a FormatChecker is passed).
# Not imported from there so ingestion needn't depend on a test-support module;
# schema/ stays the shared spine, and ingestion is one more independent
# consumer of it.

import json
from pathlib import Path

import jsonschema

FORMAT_CHECKER = jsonschema.FormatChecker()

SCHEMA_DIR = Path(__file__).parents[3] / "schema"


def load_schema(schema_filename: str) -> dict:
    return json.loads((SCHEMA_DIR / schema_filename).read_text())


def validate_against_schema(payload: dict, schema: dict) -> None:
    # Raises jsonschema.exceptions.ValidationError on failure.
    jsonschema.validate(instance=payload, schema=schema, format_checker=FORMAT_CHECKER)
