"""Tests for kickoff assignment creation in scripts/orchestrator.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from scripts.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Fixtures
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
        {
            "id": "codex",
            "cli_command": "codex",
            "display_name": "Codex CLI",
            "base_weight": 0.35,
            "reliability": 1.0,
            "primary_stages": ["implementation"],
            "secondary_stages": ["testing"],
            "can_modify": ["src/"],
            "cannot_modify": ["docs/"],
            "can_veto": False,
            "sandbox_mode": "workspace-write",
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
    ):
        orch = Orchestrator(config_path=config_path, agents_path=agents_path)
    return orch


# ---------------------------------------------------------------------------
# Tests: _create_kickoff_assignment
# ---------------------------------------------------------------------------


def test_create_kickoff_assignment_writes_claude(tmp_path: Path) -> None:
    """_create_kickoff_assignment writes assignment for primary kickoff agent (claude)."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()

    orch._create_kickoff_assignment(issue_number=1)

    orch.state.write_assignment.assert_called_once()
    agent_id, assignment = orch.state.write_assignment.call_args[0]
    assert agent_id == "claude"
    assert assignment["task_id"] == "TASK-001"
    assert assignment["stage"] == "kickoff"
    assert assignment["action"] == "analyze"
    assert assignment["github_issue_number"] == 1


def test_create_kickoff_assignment_task_id_padded(tmp_path: Path) -> None:
    """task_id is zero-padded to 3 digits."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()

    orch._create_kickoff_assignment(issue_number=42)

    _, assignment = orch.state.write_assignment.call_args[0]
    assert assignment["task_id"] == "TASK-042"
    assert assignment["context"]["spec_path"] == "docs/specs/SPEC-042.md"
    assert assignment["context"]["branch_name"] == "feat/TASK-042"


def test_create_kickoff_assignment_no_kickoff_agent(tmp_path: Path) -> None:
    """When no agent handles kickoff stage, write_assignment is not called."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    agents_path = config_dir / "agents.json"
    config_path.write_text(yaml.dump(MINIMAL_CONFIG))
    # Agents with no kickoff stage
    agents_path.write_text(json.dumps({
        "agents": [{
            "id": "codex",
            "cli_command": "codex",
            "display_name": "Codex CLI",
            "base_weight": 0.35,
            "reliability": 1.0,
            "primary_stages": ["implementation"],
            "secondary_stages": [],
            "can_modify": ["src/"],
            "cannot_modify": [],
            "can_veto": False,
            "sandbox_mode": None,
        }]
    }))

    with (
        patch("scripts.orchestrator.GitHubClient"),
        patch("scripts.orchestrator.StateManager"),
        patch("scripts.orchestrator.ConsensusEngine"),
    ):
        orch = Orchestrator(config_path=config_path, agents_path=agents_path)

    orch.state.write_assignment = MagicMock()
    orch._create_kickoff_assignment(issue_number=1)
    orch.state.write_assignment.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: process_inbox integration
# ---------------------------------------------------------------------------


def test_process_inbox_creates_kickoff_assignment(tmp_path: Path) -> None:
    """process_inbox creates GitHub Issue AND writes kickoff assignment."""
    orch = _make_orchestrator(tmp_path)

    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    brief = inbox_dir / "BRIEF-001.md"
    brief.write_text("# Test BRIEF\n\n## Summary\nTest task.\n")
    orch.inbox_dir = inbox_dir

    orch.state.write_assignment = MagicMock()

    with patch("scripts.orchestrator.process_brief", return_value=7) as mock_brief:
        count = orch.process_inbox()

    assert count == 1
    mock_brief.assert_called_once()
    orch.state.write_assignment.assert_called_once()
    agent_id, assignment = orch.state.write_assignment.call_args[0]
    assert agent_id == "claude"
    assert assignment["github_issue_number"] == 7
    assert assignment["stage"] == "kickoff"


def test_process_inbox_empty_inbox(tmp_path: Path) -> None:
    """process_inbox with no BRIEFs returns 0 and writes no assignments."""
    orch = _make_orchestrator(tmp_path)

    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    orch.inbox_dir = inbox_dir
    orch.state.write_assignment = MagicMock()

    with patch("scripts.orchestrator.process_brief") as mock_brief:
        count = orch.process_inbox()

    assert count == 0
    mock_brief.assert_not_called()
    orch.state.write_assignment.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: path resolution with target_project_path
# ---------------------------------------------------------------------------


def test_inbox_dir_uses_target_project_path(tmp_path: Path) -> None:
    """inbox_dir and archive_dir are resolved relative to target_project_path."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    agents_path = config_dir / "agents.json"

    target = tmp_path / "my-target-project"
    config = {**MINIMAL_CONFIG}
    config["orchestrator"] = {
        **MINIMAL_CONFIG["orchestrator"],
        "target_project_path": str(target),
    }
    config_path.write_text(yaml.dump(config))
    agents_path.write_text(json.dumps(MINIMAL_AGENTS))

    with (
        patch("scripts.orchestrator.GitHubClient"),
        patch("scripts.orchestrator.StateManager"),
        patch("scripts.orchestrator.ConsensusEngine"),
    ):
        orch = Orchestrator(config_path=config_path, agents_path=agents_path)

    assert orch.inbox_dir == target / "inbox/"
    assert orch.archive_dir == target / "docs/briefs/"


def test_inbox_dir_without_target_project_path(tmp_path: Path) -> None:
    """When target_project_path is empty, paths are relative to CWD."""
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
    ):
        orch = Orchestrator(config_path=config_path, agents_path=agents_path)

    assert orch.inbox_dir == Path(".") / "inbox/"
    assert orch.archive_dir == Path(".") / "docs/briefs/"
