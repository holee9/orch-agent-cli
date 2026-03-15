"""Unit tests for SPEC-P3-004: consensus rework auto-trigger."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from scripts.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Shared fixtures (mirrors pattern from tests/unit/test_escalation.py)
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
# AC-001: rework action -> assignment written with stage=review + GitHub comment
# ---------------------------------------------------------------------------


def test_ac001_rework_writes_assignment_and_comment(tmp_path: Path) -> None:
    """AC-001: action=rework writes assignment file with stage=review and posts GitHub comment."""
    orch = _make_orchestrator(tmp_path)
    orch.github.add_comment = MagicMock()
    orch.state.write_assignment = MagicMock()
    orch.state.clear_consensus = MagicMock()
    orch.state.write_task_state = MagicMock()

    from scripts.consensus import ConsensusResult

    result = ConsensusResult(
        task_id="task-001",
        action="rework",
        ratio=0.6,
        can_proceed=False,
        re_review_count=1,
        dispersion_warning=False,
        details=[],
        computed_at="2026-03-15T00:00:00+00:00",
    )

    orch._trigger_rework(
        task_id="task-001",
        issue_number=42,
        result=result,
        last_review_agent="claude",
    )

    # Assignment written
    orch.state.write_assignment.assert_called_once()
    call_args = orch.state.write_assignment.call_args
    agent_id_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("agent_id")
    assignment_data = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("assignment")
    assert agent_id_arg == "claude"
    assert assignment_data["stage"] == "review"
    assert assignment_data["re_review_count"] == 1

    # GitHub comment posted
    orch.github.add_comment.assert_called_once()
    comment_text = orch.github.add_comment.call_args.args[1]
    assert "rework" in comment_text.lower() or "Rework" in comment_text


# ---------------------------------------------------------------------------
# AC-002: re_review_count increments correctly on second rework
# ---------------------------------------------------------------------------


def test_ac002_rereview_count_increments_correctly(tmp_path: Path) -> None:
    """AC-002: second rework (re_review_count=1, below max=2) writes assignment with correct count."""
    orch = _make_orchestrator(tmp_path)
    orch.github.add_comment = MagicMock()
    orch.state.write_assignment = MagicMock()
    orch.state.clear_consensus = MagicMock()
    orch.state.write_task_state = MagicMock()

    from scripts.consensus import ConsensusResult

    # re_review_count=1, max_rereviews=2 -> still below threshold, should assign
    result = ConsensusResult(
        task_id="task-002",
        action="rework",
        ratio=0.5,
        can_proceed=False,
        re_review_count=1,
        dispersion_warning=False,
        details=[],
        computed_at="2026-03-15T00:00:00+00:00",
    )

    orch._trigger_rework(
        task_id="task-002",
        issue_number=43,
        result=result,
        last_review_agent="claude",
    )

    call_args = orch.state.write_assignment.call_args
    assignment_data = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("assignment")
    assert assignment_data["re_review_count"] == 1


# ---------------------------------------------------------------------------
# AC-003: re_review_count >= max_rereviews -> escalate, no assignment
# ---------------------------------------------------------------------------


def test_ac003_max_rereviews_triggers_escalation(tmp_path: Path) -> None:
    """AC-003: when re_review_count >= max_rereviews, escalate and do NOT write assignment."""
    orch = _make_orchestrator(tmp_path)
    orch.github.add_comment = MagicMock()
    orch.state.write_assignment = MagicMock()
    orch.state.clear_consensus = MagicMock()
    orch.state.write_task_state = MagicMock()
    orch._create_escalation_issue = MagicMock(return_value=99)

    from scripts.consensus import ConsensusResult

    # max_rereviews=2, re_review_count=2 -> should escalate
    result = ConsensusResult(
        task_id="task-003",
        action="rework",
        ratio=0.4,
        can_proceed=False,
        re_review_count=2,
        dispersion_warning=False,
        details=[],
        computed_at="2026-03-15T00:00:00+00:00",
    )

    orch._trigger_rework(
        task_id="task-003",
        issue_number=44,
        result=result,
        last_review_agent="claude",
    )

    orch._create_escalation_issue.assert_called_once()
    orch.state.write_assignment.assert_not_called()


# ---------------------------------------------------------------------------
# AC-004: old consensus file cleared on rework
# ---------------------------------------------------------------------------


def test_ac004_consensus_cleared_on_rework(tmp_path: Path) -> None:
    """AC-004: _trigger_rework clears the consensus file via state.clear_consensus."""
    orch = _make_orchestrator(tmp_path)
    orch.github.add_comment = MagicMock()
    orch.state.write_assignment = MagicMock()
    orch.state.clear_consensus = MagicMock()
    orch.state.write_task_state = MagicMock()

    from scripts.consensus import ConsensusResult

    result = ConsensusResult(
        task_id="task-004",
        action="rework",
        ratio=0.6,
        can_proceed=False,
        re_review_count=1,
        dispersion_warning=False,
        details=[],
        computed_at="2026-03-15T00:00:00+00:00",
    )

    orch._trigger_rework(
        task_id="task-004",
        issue_number=45,
        result=result,
        last_review_agent="claude",
    )

    orch.state.clear_consensus.assert_called_once_with("task-004")


# ---------------------------------------------------------------------------
# AC-005: idempotent - same (task_id, re_review_count) -> one assignment, one comment
# ---------------------------------------------------------------------------


def test_ac005_idempotent_same_call_twice(tmp_path: Path) -> None:
    """AC-005: calling _trigger_rework twice with same task_id/re_review_count is idempotent."""
    orch = _make_orchestrator(tmp_path)
    orch.github.add_comment = MagicMock()
    orch.state.write_assignment = MagicMock()
    orch.state.clear_consensus = MagicMock()
    orch.state.write_task_state = MagicMock()

    from scripts.consensus import ConsensusResult

    result = ConsensusResult(
        task_id="task-005",
        action="rework",
        ratio=0.6,
        can_proceed=False,
        re_review_count=1,
        dispersion_warning=False,
        details=[],
        computed_at="2026-03-15T00:00:00+00:00",
    )

    orch._trigger_rework(
        task_id="task-005",
        issue_number=46,
        result=result,
        last_review_agent="claude",
    )
    orch._trigger_rework(
        task_id="task-005",
        issue_number=46,
        result=result,
        last_review_agent="claude",
    )

    assert orch.state.write_assignment.call_count == 1
    assert orch.github.add_comment.call_count == 1


# ---------------------------------------------------------------------------
# AC-006: all agents unavailable -> escalate, no assignment
# ---------------------------------------------------------------------------


def test_ac006_no_available_agent_escalates(tmp_path: Path) -> None:
    """AC-006: if rework agent is unavailable, escalate instead of writing assignment."""
    orch = _make_orchestrator(tmp_path)
    orch.github.add_comment = MagicMock()
    orch.state.write_assignment = MagicMock()
    orch.state.clear_consensus = MagicMock()
    orch.state.write_task_state = MagicMock()
    orch._create_escalation_issue = MagicMock(return_value=100)

    # Mark all agents as unavailable
    for agent in orch.agents:
        agent["available"] = False

    from scripts.consensus import ConsensusResult

    result = ConsensusResult(
        task_id="task-006",
        action="rework",
        ratio=0.6,
        can_proceed=False,
        re_review_count=1,
        dispersion_warning=False,
        details=[],
        computed_at="2026-03-15T00:00:00+00:00",
    )

    orch._trigger_rework(
        task_id="task-006",
        issue_number=47,
        result=result,
        last_review_agent="claude",
    )

    orch._create_escalation_issue.assert_called_once()
    orch.state.write_assignment.assert_not_called()
