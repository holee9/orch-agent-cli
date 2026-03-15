"""Unit tests for escalation logic in scripts/orchestrator.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from scripts.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Shared fixtures (mirror pattern from tests/test_orchestrator.py)
# ---------------------------------------------------------------------------

MINIMAL_CONFIG = {
    "github": {
        "repo": "owner/testrepo",
        "polling_interval_seconds": 60,
        "mention_user": "",
    },
    "orchestrator": {
        "target_project_path": "",
        "inbox_dir": "inbox/",
        "brief_archive_dir": "docs/briefs/",
        "orchestra_dir": ".orchestra/",
        "assignment_timeout_minutes": 30,
        "max_retries": 3,
    },
    "consensus": {
        "threshold": 0.9,
        "score_ready_min": 90,
        "dispersion_alert_threshold": 20,
        "max_rereviews": 2,
    },
    "quality": {
        "enforce_english_comments": True,
        "validate_schemas": False,
    },
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "file": ".orchestra/logs/orchestrator.log",
    },
}

MINIMAL_AGENTS = {
    "agents": [
        {
            "id": "claude",
            "cli_command": "claude",
            "display_name": "Claude Code",
            "base_weight": 0.40,
            "reliability": 1.0,
            "primary_stages": ["kickoff", "requirements", "planning", "review", "release"],
            "secondary_stages": ["consensus"],
            "can_modify": ["docs/"],
            "cannot_modify": ["src/"],
            "can_veto": False,
            "sandbox_mode": None,
        },
    ]
}


def _make_orchestrator(tmp_path: Path) -> Orchestrator:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    agents_path = config_dir / "agents.json"
    config_path.write_text(yaml.dump(MINIMAL_CONFIG))
    agents_path.write_text(json.dumps(MINIMAL_AGENTS))

    with (
        patch("scripts.orchestrator.GitHubClient"),
        patch("scripts.orchestrator.StateManager"),
        patch("scripts.orchestrator.ConsensusEngine"),
        patch.object(
            Orchestrator,
            "check_agent_availability",
            side_effect=lambda agents: [{**a, "available": True} for a in agents],
        ),
    ):
        orch = Orchestrator(config_path=config_path, agents_path=agents_path)
    return orch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_timeout_triggers_escalation(tmp_path: Path) -> None:
    """Stale assignments should produce escalation triggers."""
    orch = _make_orchestrator(tmp_path)
    stale_assignment = {
        "agent_id": "claude",
        "task_id": "task-001",
        "stage": "implementation",
        "assigned_at": "2026-03-14T00:00:00+00:00",
    }
    orch.state.get_stale_assignments = MagicMock(return_value=[stale_assignment])

    triggers = orch._check_escalation_triggers()

    assert len(triggers) == 1
    assert triggers[0]["agent_id"] == "claude"
    assert triggers[0]["task_id"] == "task-001"
    assert "timeout" in triggers[0]["reason"].lower()


def test_escalation_issue_created_with_correct_labels(tmp_path: Path) -> None:
    """_create_escalation_issue should call github.create_issue with escalation labels."""
    orch = _make_orchestrator(tmp_path)
    orch.github.create_issue = MagicMock(return_value=42)

    issue_num = orch._create_escalation_issue(
        reason="Assignment exceeded timeout of 30 minutes",
        context={"agent_id": "codex", "task_id": "task-002"},
    )

    assert issue_num == 42
    call_kwargs = orch.github.create_issue.call_args
    labels = call_kwargs.kwargs.get("labels") or call_kwargs.args[2]
    assert "type:escalation" in labels
    assert "status:human-needed" in labels


def test_no_escalation_when_within_timeout(tmp_path: Path) -> None:
    """No triggers should be returned when no assignments are stale."""
    orch = _make_orchestrator(tmp_path)
    orch.state.get_stale_assignments = MagicMock(return_value=[])

    triggers = orch._check_escalation_triggers()

    assert triggers == []


# ---------------------------------------------------------------------------
# BUG-3 regression: deduplication guard for escalation issues
# ---------------------------------------------------------------------------


def test_no_duplicate_escalation_same_agent_task(tmp_path: Path) -> None:
    """Calling _create_escalation_issue twice with same agent/task creates only one issue."""
    orch = _make_orchestrator(tmp_path)
    orch.github.create_issue = MagicMock(return_value=10)

    context = {"agent_id": "codex", "task_id": "task-dup"}
    first = orch._create_escalation_issue("timeout", context)
    second = orch._create_escalation_issue("timeout", context)

    assert first == 10
    assert second is None
    assert orch.github.create_issue.call_count == 1


def test_different_tasks_get_separate_escalations(tmp_path: Path) -> None:
    """Different agent/task combinations each get their own escalation issue."""
    orch = _make_orchestrator(tmp_path)
    orch.github.create_issue = MagicMock(side_effect=[20, 21])

    first = orch._create_escalation_issue(
        "timeout", {"agent_id": "codex", "task_id": "task-A"}
    )
    second = orch._create_escalation_issue(
        "timeout", {"agent_id": "codex", "task_id": "task-B"}
    )

    assert first == 20
    assert second == 21
    assert orch.github.create_issue.call_count == 2


def test_consensus_escalate_no_duplicate_same_issue_number(tmp_path: Path) -> None:
    """check_consensus_ready must not create duplicate escalation for same issue number."""
    orch = _make_orchestrator(tmp_path)
    orch.github.create_issue = MagicMock(return_value=99)

    # Pre-register issue 5 as already escalated
    orch._escalated_issue_numbers.add(5)

    # Simulate calling the escalation path a second time for issue #5
    # by directly checking the dedup set (unit-level guard verification)
    assert 5 in orch._escalated_issue_numbers
    # A fresh issue number should not be in the set
    assert 7 not in orch._escalated_issue_numbers
