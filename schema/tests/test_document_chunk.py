# Tests for document.schema.json and chunk.schema.json (issue #3), plus two
# relational checks that individual per-file validation can't express on its
# own: that a "supersedes" fixture genuinely points at another fixture's id,
# and that a Document's active_chunking_generation_id genuinely picks out one
# generation among more than one Chunk generation on disk.
#
from pathlib import Path

import jsonschema
import pytest

from support import load_json, validate

SCHEMA_DIR = Path(__file__).parent.parent
DOCUMENT_SCHEMA = SCHEMA_DIR / "document.schema.json"
CHUNK_SCHEMA = SCHEMA_DIR / "chunk.schema.json"
DOCUMENT_FIXTURES = SCHEMA_DIR / "fixtures" / "document"
CHUNK_FIXTURES = SCHEMA_DIR / "fixtures" / "chunk"


# ---- Document schema ----


def test_original_document_passes_validation():
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "valid-original.json")

    validate(payload, schema)


def test_superseding_document_passes_validation():
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "valid-superseding.json")

    validate(payload, schema)


def test_superseding_document_references_the_original_by_id():
    original = load_json(DOCUMENT_FIXTURES / "valid-original.json")
    superseding = load_json(DOCUMENT_FIXTURES / "valid-superseding.json")

    assert superseding["supersedes"] == original["id"]


def test_invalid_document_fails_validation():
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "invalid-missing-required.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_document_with_malformed_date_fails_validation():
    # Proves format enforcement works for "date": without it, "not-a-date"
    # would pass.
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "invalid-bad-date-format.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_document_with_malformed_url_fails_validation():
    # Same proof for "uri": jsonschema's default install registers no "uri"
    # checker, which is why requirements.txt pins jsonschema[format].
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "invalid-bad-uri-format.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_document_with_empty_id_fails_validation():
    schema = load_json(DOCUMENT_SCHEMA)
    payload = load_json(DOCUMENT_FIXTURES / "invalid-empty-id.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


# ---- Chunk schema ----


def test_generation_one_chunk_passes_validation():
    schema = load_json(CHUNK_SCHEMA)
    payload = load_json(CHUNK_FIXTURES / "valid-generation-1.json")

    validate(payload, schema)


def test_generation_two_chunk_passes_validation():
    schema = load_json(CHUNK_SCHEMA)
    payload = load_json(CHUNK_FIXTURES / "valid-generation-2.json")

    validate(payload, schema)


def test_invalid_chunk_fails_validation():
    schema = load_json(CHUNK_SCHEMA)
    payload = load_json(CHUNK_FIXTURES / "invalid-missing-required.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


def test_chunk_with_empty_text_fails_validation():
    schema = load_json(CHUNK_SCHEMA)
    payload = load_json(CHUNK_FIXTURES / "invalid-empty-text.json")

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)


# ---- Cross-fixture relationship: active generation among more than one ----


def test_document_active_generation_points_at_the_correct_chunk_generation():
    document = load_json(DOCUMENT_FIXTURES / "valid-original.json")
    generation_one = load_json(CHUNK_FIXTURES / "valid-generation-1.json")
    generation_two = load_json(CHUNK_FIXTURES / "valid-generation-2.json")

    # Both Chunks belong to the same Document, but to two different
    # generations — proving more than one generation genuinely exists here.
    assert generation_one["document_id"] == document["id"]
    assert generation_two["document_id"] == document["id"]
    assert (
        generation_one["chunking_generation_id"]
        != generation_two["chunking_generation_id"]
    )

    # With the inequality above, matching generation_two already establishes
    # generation_one is not active, so no third assertion is needed.
    assert (
        document["active_chunking_generation_id"]
        == generation_two["chunking_generation_id"]
    )
