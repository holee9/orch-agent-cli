"""Tests for scripts/validate_schema.py."""

from __future__ import annotations

import pytest

from scripts.validate_schema import validate, validate_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_TASK: dict = {
    "task_id": "task-001",
    "session_id": "session-abc",
    "title": "Implement feature X",
    "stage": "implementation",
    "created_at": "2026-03-14T10:00:00Z",
}

VALID_REPORT: dict = {
    "agent_id": "reviewer-1",
    "task_id": "task-001",
    "timestamp": "2026-03-14T12:00:00Z",
    "score": 85,
    "confidence": 0.9,
    "vote": "ready",
    "blockers": [],
    "evidence": [
        {
            "type": "test_result",
            "reference": "tests/test_validate_schema.py",
            "summary": "All tests pass with 92% coverage.",
        }
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_validate_valid_task() -> None:
    """Valid task data must produce an empty error list."""
    errors = validate(VALID_TASK, "task")
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_validate_invalid_task_missing_required() -> None:
    """Task missing required fields must return a non-empty error list."""
    # Omit required fields: session_id, title, stage, created_at
    incomplete: dict = {"task_id": "task-002"}
    errors = validate(incomplete, "task")
    assert len(errors) > 0, "Expected validation errors for missing required fields"
    # At least one error should mention a missing property
    combined = " ".join(errors)
    assert any(
        field in combined for field in ("session_id", "title", "stage", "created_at")
    ), f"Expected a missing-field error, got: {errors}"


def test_validate_valid_report() -> None:
    """Valid release_readiness report must produce an empty error list."""
    errors = validate(VALID_REPORT, "release_readiness")
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_validate_invalid_report_score_range() -> None:
    """Score outside 0-100 range must produce a validation error."""
    bad_report = {**VALID_REPORT, "score": 150}
    errors = validate(bad_report, "release_readiness")
    assert len(errors) > 0, "Expected a range error for score=150"
    assert any("score" in e or "150" in e for e in errors), (
        f"Expected error mentioning 'score', got: {errors}"
    )


def test_validate_unknown_schema() -> None:
    """Passing an unknown schema name must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown schema"):
        validate({}, "nonexistent_schema")


def test_validate_file_not_found() -> None:
    """validate_file on a non-existent path must return an error list (not raise)."""
    errors = validate_file("/tmp/this_file_does_not_exist_abc123.json", "task")
    assert len(errors) == 1
    assert "not found" in errors[0].lower() or "File not found" in errors[0]
