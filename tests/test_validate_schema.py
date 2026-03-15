"""Tests for scripts/validate_schema.py."""

from __future__ import annotations

import pytest

from scripts.validate_schema import validate, validate_file

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_TASK: dict = {
    "id": "task-001",
    "type": "implementation",
    "status": "open",
    "assigned_to": "codex",
    "priority": "P1",
    "title": "Implement feature X",
    "description": "Implement the core feature X as described in SPEC-001.",
    "created_at": "2026-03-14T10:00:00Z",
    "updated_at": "2026-03-14T10:00:00Z",
    "blocks": [],
    "blocked_by": [],
}

VALID_REPORT: dict = {
    "spec_id": "SPEC-001",
    "version": "1.0.0",
    "timestamp": "2026-03-14T12:00:00Z",
    "consensus_result": {"status": "approved", "score": 0.85},
    "agent_votes": [
        {"agent_id": "claude", "vote": "approve", "weight": 3, "rationale": "Code quality is high."},  # noqa: E501
        {"agent_id": "codex", "vote": "approve", "weight": 2, "rationale": "Tests pass."},
    ],
    "overall_score": 0.85,
    "veto_applied": False,
    "test_coverage": 0.92,
    "security_scan_passed": True,
    "release_notes_ready": True,
    "final_decision": "release",
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
    # Only provide title; omit required fields: id, type, status, assigned_to, etc.
    incomplete: dict = {"title": "task-002"}
    errors = validate(incomplete, "task")
    assert len(errors) > 0, "Expected validation errors for missing required fields"
    combined = " ".join(errors)
    assert any(
        field in combined for field in ("id", "type", "status", "assigned_to")
    ), f"Expected a missing-field error, got: {errors}"


def test_validate_valid_report() -> None:
    """Valid release_readiness report must produce an empty error list."""
    errors = validate(VALID_REPORT, "release_readiness")
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_validate_invalid_report_score_range() -> None:
    """overall_score outside 0-1 range must produce a validation error."""
    bad_report = {**VALID_REPORT, "overall_score": 1.5}
    errors = validate(bad_report, "release_readiness")
    assert len(errors) > 0, "Expected a range error for overall_score=1.5"
    assert any("overall_score" in e or "1.5" in e for e in errors), (
        f"Expected error mentioning 'overall_score', got: {errors}"
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
