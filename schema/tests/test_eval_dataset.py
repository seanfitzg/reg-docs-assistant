# Tests for eval-dataset.schema.json (issue #29): the shape of the retrieval
# eval set in eval/dataset.json (ADR-0027, ADR-0029).
#
# Relational checks the schema can't express (unique case ids, Gold Locators
# that really exist in the ingested Chunks) live in eval/, not here, since
# they need the corpus rather than just the file's shape.

from pathlib import Path

import jsonschema
import pytest

from regdocs_schema.testing import load_json, validate

SCHEMA_DIR = Path(__file__).parent.parent
EVAL_DATASET_SCHEMA = SCHEMA_DIR / "eval-dataset.schema.json"
FIXTURES = SCHEMA_DIR / "fixtures" / "eval-dataset"


@pytest.mark.parametrize(
    "fixture_name",
    [
        # One case per category, including a supersession case with
        # superseded_locators and an unanswerable case with none.
        "valid-mixed-categories.json",
        # The committed starting point before any Eval Cases are written.
        "valid-empty-seed.json",
    ],
)
def test_valid_dataset_passes_validation(fixture_name):
    schema = load_json(EVAL_DATASET_SCHEMA)
    payload = load_json(FIXTURES / fixture_name)

    validate(payload, schema)


@pytest.mark.parametrize(
    "fixture_name",
    [
        # Unanswerable means the corpus has no answer, so there's nothing
        # to point at -- a Gold Locator here is a contradiction.
        "invalid-unanswerable-with-gold-locators.json",
        # The reverse: an answerable case must say where its answer lives,
        # or the harness has nothing to score it against.
        "invalid-answerable-without-gold-locators.json",
        # Every answerable case carries a verbatim quote for human
        # sanity-checking (ADR-0027).
        "invalid-answerable-without-answer-quote.json",
        # Closed vocabulary: only lexical | paraphrase (ADR-0029).
        "invalid-unknown-phrasing.json",
        # A supersession case must record the older Document's equivalent,
        # or it's indistinguishable from a single_passage case.
        "invalid-supersession-without-superseded-locators.json",
        # Case ids are q01, q02, ... so reports sort and read cleanly.
        "invalid-malformed-case-id.json",
    ],
)
def test_invalid_dataset_fails_validation(fixture_name):
    schema = load_json(EVAL_DATASET_SCHEMA)
    payload = load_json(FIXTURES / fixture_name)

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(payload, schema)
