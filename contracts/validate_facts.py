import json
from jsonschema import validate, ValidationError
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "system_facts_schema.json"

def validate_system_facts(facts: dict):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    try:
        validate(instance=facts, schema=schema)
    except ValidationError as e:
        raise RuntimeError(
            f"System facts contract violation: {e.message}"
        )
