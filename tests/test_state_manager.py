"""Tests for scripts/state_manager.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

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
