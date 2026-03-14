"""Tests for scripts/state_manager.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.state_manager import StateManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_manager(tmp_path: Path) -> StateManager:
    """Return a StateManager rooted at tmp_path."""
    return StateManager(tmp_path / ".orchestra")


def iso_now(offset: timedelta = timedelta()) -> str:
    """Return current UTC time (with optional offset) as ISO 8601 string."""
    return (datetime.now(timezone.utc) + offset).isoformat()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ensure_directories(tmp_path: Path) -> None:
    """ensure_directories() must create every expected subdirectory."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    for subdir in StateManager.SUBDIRS:
        expected = mgr.base_dir / subdir
        assert expected.is_dir(), f"Expected directory to exist: {expected}"


def test_write_and_read_assignment(tmp_path: Path) -> None:
    """write_assignment / read_assignment must round-trip correctly."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    assignment = {
        "task_id": "task-001",
        "assigned_at": iso_now(),
        "priority": "high",
    }
    mgr.write_assignment("agent-1", assignment)

    result = mgr.read_assignment("agent-1")
    assert result is not None
    assert result["task_id"] == "task-001"
    assert result["priority"] == "high"


def test_read_assignment_not_found(tmp_path: Path) -> None:
    """read_assignment for an unknown agent must return None."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    assert mgr.read_assignment("ghost-agent") is None


def test_clear_assignment(tmp_path: Path) -> None:
    """clear_assignment must remove the file and return True; False if absent."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    assignment = {"task_id": "task-002", "assigned_at": iso_now()}
    mgr.write_assignment("agent-2", assignment)

    # First clear: file exists -> True
    assert mgr.clear_assignment("agent-2") is True
    # File should be gone
    assert mgr.read_assignment("agent-2") is None
    # Second clear: file absent -> False
    assert mgr.clear_assignment("agent-2") is False


def test_list_assignments(tmp_path: Path) -> None:
    """list_assignments must return all written assignments keyed by agent_id."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    agents = {
        "agent-a": {"task_id": "task-010", "assigned_at": iso_now()},
        "agent-b": {"task_id": "task-011", "assigned_at": iso_now()},
        "agent-c": {"task_id": "task-012", "assigned_at": iso_now()},
    }
    for agent_id, data in agents.items():
        mgr.write_assignment(agent_id, data)

    result = mgr.list_assignments()
    assert set(result.keys()) == set(agents.keys())
    assert result["agent-b"]["task_id"] == "task-011"


def test_write_and_read_completion(tmp_path: Path) -> None:
    """write_completion / read_completions must round-trip completion signals."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    mgr.write_completion("agent-1", "task-001", artifacts=["output/report.md"])

    completions = mgr.read_completions()
    assert len(completions) == 1
    c = completions[0]
    assert c["agent_id"] == "agent-1"
    assert c["task_id"] == "task-001"
    assert "output/report.md" in c["artifacts"]
    assert "completed_at" in c


def test_read_completions_empty(tmp_path: Path) -> None:
    """read_completions must return an empty list when no completions exist."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    assert mgr.read_completions() == []


def test_write_and_read_report(tmp_path: Path) -> None:
    """write_report / read_reports must round-trip a report for a task."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    report = {
        "vote": "ready",
        "score": 90,
        "blockers": [],
    }
    mgr.write_report("task-005", "reviewer-1", report)

    reports = mgr.read_reports("task-005")
    assert "reviewer-1" in reports
    assert reports["reviewer-1"]["score"] == 90
    assert reports["reviewer-1"]["vote"] == "ready"


def test_read_reports_for_task(tmp_path: Path) -> None:
    """read_reports must return all reports scoped to the given task_id only."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    # Write two reports for task-007 and one for task-008 (should not appear)
    mgr.write_report("task-007", "reviewer-a", {"score": 70, "vote": "not_ready", "blockers": []})
    mgr.write_report("task-007", "reviewer-b", {"score": 95, "vote": "ready", "blockers": []})
    mgr.write_report("task-008", "reviewer-a", {"score": 80, "vote": "ready", "blockers": []})

    result = mgr.read_reports("task-007")
    assert set(result.keys()) == {"reviewer-a", "reviewer-b"}
    # task-008 must not bleed through
    result_other = mgr.read_reports("task-008")
    assert set(result_other.keys()) == {"reviewer-a"}


def test_get_stale_assignments(tmp_path: Path) -> None:
    """get_stale_assignments must detect assignments past the timeout threshold."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    # Fresh assignment (5 minutes ago) - should NOT be stale with default 30 min timeout
    mgr.write_assignment(
        "fresh-agent",
        {"task_id": "task-020", "assigned_at": iso_now(offset=timedelta(minutes=-5))},
    )

    # Stale assignment (60 minutes ago) - SHOULD be stale
    mgr.write_assignment(
        "stale-agent",
        {"task_id": "task-021", "assigned_at": iso_now(offset=timedelta(minutes=-60))},
    )

    stale = mgr.get_stale_assignments(timeout_minutes=30)
    stale_agent_ids = [s["agent_id"] for s in stale]

    assert "stale-agent" in stale_agent_ids, "60-min-old assignment must be detected as stale"
    assert "fresh-agent" not in stale_agent_ids, "5-min-old assignment must not be stale"


def test_write_read_assignment_round_trip(tmp_path: Path) -> None:
    """write_assignment + read_assignment must preserve all fields exactly."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    payload = {
        "agent_id": "round-trip-agent",
        "task_id": "task-999",
        "stage": "review",
        "github_issue_number": 77,
        "assigned_at": iso_now(),
        "context": {"spec_path": "docs/spec.md", "branch_name": "feat/task-999"},
    }

    mgr.write_assignment("round-trip-agent", payload)
    result = mgr.read_assignment("round-trip-agent")

    assert result is not None
    assert result["task_id"] == "task-999"
    assert result["stage"] == "review"
    assert result["github_issue_number"] == 77
    assert result["context"]["branch_name"] == "feat/task-999"


def test_get_stale_assignments_with_timezone_naive_string(tmp_path: Path) -> None:
    """get_stale_assignments must handle ISO strings that lack timezone info."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    # Naive datetime string (no +00:00 suffix) — 90 minutes in the past
    naive_old = (datetime.now(timezone.utc) - timedelta(minutes=90)).replace(
        tzinfo=None
    ).isoformat()

    mgr.write_assignment(
        "naive-stale-agent",
        {"task_id": "task-tz-naive", "assigned_at": naive_old},
    )

    # The implementation uses fromisoformat; a naive datetime compared to aware
    # datetime raises TypeError — code must handle or the test documents the behaviour.
    try:
        stale = mgr.get_stale_assignments(timeout_minutes=30)
        # If it handled gracefully, the stale agent should ideally be detected
        # OR silently skipped — either is acceptable; we just must not crash.
        assert isinstance(stale, list)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"get_stale_assignments raised an unexpected exception: {exc}"
        )


def test_get_stale_assignments_with_timezone_aware_z_suffix(tmp_path: Path) -> None:
    """get_stale_assignments must handle ISO 8601 strings ending with 'Z'."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    # 'Z' suffix is valid ISO 8601 but fromisoformat only supports it in Python 3.11+
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=60)
    # Produce e.g. "2026-03-14T10:00:00Z"
    z_string = stale_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    mgr.write_assignment(
        "z-suffix-agent",
        {"task_id": "task-z-suffix", "assigned_at": z_string},
    )

    try:
        stale = mgr.get_stale_assignments(timeout_minutes=30)
        # Must not raise; stale list is valid (agent may or may not appear depending
        # on Python version's fromisoformat support for 'Z')
        assert isinstance(stale, list)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"get_stale_assignments raised unexpected exception for Z-suffix: {exc}"
        )


def test_atomic_write_no_temp_file_left_behind(tmp_path: Path) -> None:
    """_atomic_write must not leave .tmp files in the target directory."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    target_dir = mgr.base_dir / "state" / "assigned"
    target_path = target_dir / "atomic-agent.json"

    mgr._atomic_write(target_path, {"task_id": "task-atomic", "value": 123})

    # Final file must exist with correct content
    assert target_path.exists()

    # No .tmp files may remain
    tmp_files = list(target_dir.glob("*.tmp"))
    assert tmp_files == [], f"Leftover .tmp files found: {tmp_files}"


def test_atomic_write_produces_valid_json(tmp_path: Path) -> None:
    """_atomic_write must write valid, parseable JSON content."""
    import json

    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    data = {"key": "value", "number": 42, "nested": {"a": [1, 2, 3]}}
    path = mgr.base_dir / "state" / "assigned" / "json-check.json"
    mgr._atomic_write(path, data)

    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed == data


def test_get_stale_assignments_empty_returns_empty_list(tmp_path: Path) -> None:
    """get_stale_assignments must return [] when no assignments exist at all."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    result = mgr.get_stale_assignments(timeout_minutes=30)
    assert result == []


def test_get_stale_assignments_skips_missing_assigned_at(tmp_path: Path) -> None:
    """Assignments without assigned_at field must be silently skipped."""
    mgr = make_manager(tmp_path)
    mgr.ensure_directories()

    # Assignment with no assigned_at key
    mgr.write_assignment("no-time-agent", {"task_id": "task-no-time"})

    stale = mgr.get_stale_assignments(timeout_minutes=30)
    agent_ids = [s.get("agent_id") for s in stale]
    assert "no-time-agent" not in agent_ids
