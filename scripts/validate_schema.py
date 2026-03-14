"""JSON schema validation utility for orch-agent-cli."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from jsonschema import Draft7Validator, ValidationError

logger = logging.getLogger(__name__)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

# Map of schema names to filenames
SCHEMA_REGISTRY: dict[str, str] = {
    "task": "task.schema.json",
    "release_readiness": "release_readiness.schema.json",
    "assignment": "assignment.schema.json",
    "consensus": "consensus.schema.json",
}


def load_schema(schema_name: str) -> dict:
    """Load a JSON schema by name from the schemas/ directory."""
    filename = SCHEMA_REGISTRY.get(schema_name)
    if not filename:
        raise ValueError(
            f"Unknown schema: {schema_name}. Available: {list(SCHEMA_REGISTRY.keys())}"
        )

    schema_path = SCHEMA_DIR / filename
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path) as f:
        return json.load(f)


def validate(data: dict, schema_name: str) -> list[str]:
    """Validate data against a named schema.

    Returns a list of validation error messages. Empty list means valid.
    """
    schema = load_schema(schema_name)
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return [_format_error(e) for e in errors]


def validate_or_raise(data: dict, schema_name: str) -> None:
    """Validate data against a named schema. Raises ValidationError if invalid."""
    errors = validate(data, schema_name)
    if errors:
        raise ValidationError(
            f"Validation failed for schema '{schema_name}':\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def validate_file(file_path: str | Path, schema_name: str) -> list[str]:
    """Validate a JSON file against a named schema."""
    path = Path(file_path)
    if not path.exists():
        return [f"File not found: {path}"]

    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON in {path}: {e}"]

    return validate(data, schema_name)


def _format_error(error: ValidationError) -> str:
    """Format a validation error into a readable string."""
    path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
    return f"{path}: {error.message}"
