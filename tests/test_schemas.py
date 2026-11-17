"""Every JSON schema under schema/ is itself a valid JSON Schema (Draft 2020-12 unless it declares another)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, validators

SCHEMAS = sorted((Path(__file__).resolve().parents[1] / "schema").glob("*.json"))


def test_schema_files_are_found():
    assert len(SCHEMAS) >= 10


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_schema_file_is_a_valid_json_schema(path):
    schema = json.loads(path.read_text())
    cls = validators.validator_for(schema, default=Draft202012Validator)
    cls.check_schema(schema)
