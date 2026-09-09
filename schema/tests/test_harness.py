import json
from pathlib import Path

import jsonschema
import pytest

TRIVIAL_FIXTURES = Path(__file__).parent.parent / "fixtures" / "trivial"


def load(name):
    return json.loads((TRIVIAL_FIXTURES / name).read_text())


def test_valid_fixture_passes_validation():
    schema = load("schema.json")
    payload = load("valid.json")

    jsonschema.validate(instance=payload, schema=schema)


def test_invalid_fixture_fails_validation():
    schema = load("schema.json")
    payload = load("invalid.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=payload, schema=schema)
