import json
from pathlib import Path

import jsonschema
import pytest

# The folder holding the sample JSON files these tests validate against.
TRIVIAL_FIXTURES = Path(__file__).parent.parent / "fixtures" / "trivial"


def load(name):
    return json.loads((TRIVIAL_FIXTURES / name).read_text())


def test_valid_fixture_passes_validation():
    schema = load("schema.json")
    payload = load("valid.json")

    # Returns nothing on success and raises on failure, so "no exception" is
    # the pass condition.
    jsonschema.validate(instance=payload, schema=schema)


def test_invalid_fixture_fails_validation():
    schema = load("schema.json")
    payload = load("invalid.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=payload, schema=schema)
