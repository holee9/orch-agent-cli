"""Tests for SPEC-P3-002: CLI availability check and branch auto-creation.

AC-001 to AC-003: CLI availability check (_check_cli_available, check_agent_availability)
AC-004 to AC-006: Branch auto-creation (_create_task_branch)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import yaml

from scripts.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Shared fixtures (reuse pattern from test_orchestrator.py)
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
            "cli": "claude",
            "cli_command": "claude --dangerously-skip-permissions",
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
            "cli": "codex",
            "cli_command": "codex",
            "display_name": "Codex CLI",
            "base_weight": 0.35,
            "reliability": 1.0,
            "primary_stages": ["implementation"],
            "secondary_stages": ["testing"],
            "can_modify": ["src/", "tests/"],
            "cannot_modify": ["docs/"],
            "can_veto": False,
            "sandbox_mode": "workspace-write",
        },
    ]
}


def _write_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    """Write config.yaml and agents.json into a config/ subdir."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    config_path = config_dir / "config.yaml"
    config_path.write_text(yaml.dump(MINIMAL_CONFIG))

    agents_path = config_dir / "agents.json"
    agents_path.write_text(json.dumps(MINIMAL_AGENTS))

    return config_path, agents_path


def _make_orchestrator(tmp_path: Path) -> Orchestrator:
    """Create an Orchestrator with temp configs and all GitHub I/O mocked."""
    config_path, _ = _write_fixtures(tmp_path)

    with (
        patch("scripts.orchestrator.GitHubClient") as mock_gh_cls,
        patch("scripts.orchestrator.StateManager") as mock_sm_cls,
        patch("scripts.orchestrator.ConsensusEngine"),
        patch.object(
            Orchestrator,
            "_load_agents",
            return_value=MINIMAL_AGENTS["agents"],
        ),
    ):
        mock_gh_cls.return_value = MagicMock()
        mock_sm_cls.return_value = MagicMock()
        orc = Orchestrator(config_path)

    return orc


# ---------------------------------------------------------------------------
# AC-001: _check_cli_available
# ---------------------------------------------------------------------------


def test_check_cli_available_returns_true_when_exit_zero(tmp_path: Path) -> None:
    """_check_cli_available returns True when CLI exits with code 0."""
    orc = _make_orchestrator(tmp_path)

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = orc._check_cli_available("claude")

    assert result is True
    mock_run.assert_called_once_with(
        ["claude", "--version"],
        capture_output=True,
        timeout=5,
    )


def test_check_cli_available_returns_false_when_nonzero_exit(tmp_path: Path) -> None:
    """_check_cli_available returns False when CLI exits with non-zero code."""
    orc = _make_orchestrator(tmp_path)

    mock_result = MagicMock()
    mock_result.returncode = 1

    with patch("subprocess.run", return_value=mock_result):
        result = orc._check_cli_available("codex")

    assert result is False


def test_check_cli_available_returns_false_on_file_not_found(tmp_path: Path) -> None:
    """_check_cli_available returns False when CLI binary is not found."""
    orc = _make_orchestrator(tmp_path)

    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = orc._check_cli_available("nonexistent-cli")

    assert result is False


def test_check_cli_available_returns_false_on_timeout(tmp_path: Path) -> None:
    """_check_cli_available returns False when CLI check times out."""
    orc = _make_orchestrator(tmp_path)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("nonexistent-cli", 5)):
        result = orc._check_cli_available("slow-cli")

    assert result is False


# ---------------------------------------------------------------------------
# AC-002: check_agent_availability
# ---------------------------------------------------------------------------


def test_check_agent_availability_marks_available_agents(tmp_path: Path) -> None:
    """check_agent_availability adds available=True for agents whose CLI exits 0."""
    orc = _make_orchestrator(tmp_path)

    agents = [
        {"id": "claude", "cli": "claude"},
        {"id": "codex", "cli": "codex"},
    ]

    def fake_check(cli: str) -> bool:
        return cli == "claude"

    with patch.object(orc, "_check_cli_available", side_effect=fake_check):
        result = orc.check_agent_availability(agents)

    assert result[0]["available"] is True
    assert result[1]["available"] is False


def test_check_agent_availability_does_not_mutate_original(tmp_path: Path) -> None:
    """check_agent_availability does not mutate the original agents list dicts."""
    orc = _make_orchestrator(tmp_path)

    original = {"id": "claude", "cli": "claude"}
    agents = [original]

    with patch.object(orc, "_check_cli_available", return_value=True):
        result = orc.check_agent_availability(agents)

    # Original dict should not have been mutated
    assert "available" not in original
    # Result is a new list with updated dicts
    assert result[0]["available"] is True
    assert result[0] is not original


def test_check_agent_availability_preserves_existing_fields(tmp_path: Path) -> None:
    """check_agent_availability preserves all existing agent fields."""
    orc = _make_orchestrator(tmp_path)

    agents = [
        {
            "id": "claude",
            "cli": "claude",
            "display_name": "Claude Code",
            "base_weight": 0.40,
        }
    ]

    with patch.object(orc, "_check_cli_available", return_value=True):
        result = orc.check_agent_availability(agents)

    assert result[0]["id"] == "claude"
    assert result[0]["cli"] == "claude"
    assert result[0]["display_name"] == "Claude Code"
    assert result[0]["base_weight"] == 0.40
    assert result[0]["available"] is True


# ---------------------------------------------------------------------------
# AC-003: check_agent_availability called in __init__ and stored in self.agents
# ---------------------------------------------------------------------------


def test_init_calls_check_agent_availability(tmp_path: Path) -> None:
    """Orchestrator.__init__ calls check_agent_availability after _load_agents."""
    config_path, _ = _write_fixtures(tmp_path)

    loaded_agents = MINIMAL_AGENTS["agents"]

    with (
        patch("scripts.orchestrator.GitHubClient") as mock_gh_cls,
        patch("scripts.orchestrator.StateManager") as mock_sm_cls,
        patch("scripts.orchestrator.ConsensusEngine"),
        patch.object(Orchestrator, "_load_agents", return_value=loaded_agents),
        patch.object(
            Orchestrator,
            "check_agent_availability",
            return_value=[{**a, "available": True} for a in loaded_agents],
        ) as mock_check,
    ):
        mock_gh_cls.return_value = MagicMock()
        mock_sm_cls.return_value = MagicMock()
        orc = Orchestrator(config_path)

    mock_check.assert_called_once_with(loaded_agents)
    # self.agents should be the result from check_agent_availability
    assert all(a.get("available") is True for a in orc.agents)


def test_init_agents_json_not_modified(tmp_path: Path) -> None:
    """Orchestrator.__init__ does NOT write back to agents.json on disk."""
    config_path, agents_path = _write_fixtures(tmp_path)

    original_content = agents_path.read_bytes()

    with (
        patch("scripts.orchestrator.GitHubClient") as mock_gh_cls,
        patch("scripts.orchestrator.StateManager") as mock_sm_cls,
        patch("scripts.orchestrator.ConsensusEngine"),
        patch.object(
            Orchestrator,
            "_load_agents",
            return_value=MINIMAL_AGENTS["agents"],
        ),
        patch("subprocess.run") as mock_run,
    ):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        mock_gh_cls.return_value = MagicMock()
        mock_sm_cls.return_value = MagicMock()
        Orchestrator(config_path)

    # agents.json should not have changed on disk
    assert agents_path.read_bytes() == original_content


def test_init_logs_warning_for_unavailable_agent(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Orchestrator.__init__ logs WARNING for each agent whose CLI is unavailable."""
    import logging

    config_path, _ = _write_fixtures(tmp_path)

    def fake_check(cli: str) -> bool:
        return cli == "claude"

    with (
        patch("scripts.orchestrator.GitHubClient") as mock_gh_cls,
        patch("scripts.orchestrator.StateManager") as mock_sm_cls,
        patch("scripts.orchestrator.ConsensusEngine"),
        patch.object(Orchestrator, "_load_agents", return_value=MINIMAL_AGENTS["agents"]),
        patch.object(Orchestrator, "_check_cli_available", side_effect=fake_check),
        caplog.at_level(logging.WARNING, logger="scripts.orchestrator"),
    ):
        mock_gh_cls.return_value = MagicMock()
        mock_sm_cls.return_value = MagicMock()
        Orchestrator(config_path)

    # codex CLI is unavailable — warning must include agent id and cli name
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("codex" in msg for msg in warning_messages)
    assert any("codex" in msg for msg in warning_messages)


# ---------------------------------------------------------------------------
# AC-004: _create_task_branch method signature and basic call
# ---------------------------------------------------------------------------


def test_create_task_branch_calls_git_switch(tmp_path: Path) -> None:
    """_create_task_branch runs git switch -c <branch> in target_project_path."""
    orc = _make_orchestrator(tmp_path)

    # Create a fake git repo
    target = tmp_path / "target_project"
    target.mkdir()
    (target / ".git").mkdir()

    orc.config["orchestrator"]["target_project_path"] = str(target)

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        orc._create_task_branch("TASK-001")

    mock_run.assert_called_once_with(
        ["git", "switch", "-c", "feat/TASK-001"],
        cwd=target,
        capture_output=True,
        text=True,
        timeout=5,
    )


# ---------------------------------------------------------------------------
# AC-005: _create_task_branch error handling
# ---------------------------------------------------------------------------


def test_create_task_branch_skips_if_not_git_repo(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """_create_task_branch skips with WARNING if target is not a git repo."""
    import logging

    orc = _make_orchestrator(tmp_path)

    target = tmp_path / "not_a_repo"
    target.mkdir()
    # No .git directory

    orc.config["orchestrator"]["target_project_path"] = str(target)

    with (
        patch("subprocess.run") as mock_run,
        caplog.at_level(logging.WARNING, logger="scripts.orchestrator"),
    ):
        orc._create_task_branch("TASK-001")

    mock_run.assert_not_called()
    assert any("not a git repo" in msg.lower() or "git" in msg.lower() for msg in [r.message for r in caplog.records])


def test_create_task_branch_warns_on_already_exists(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """_create_task_branch logs WARNING (no error) when branch already exists."""
    import logging

    orc = _make_orchestrator(tmp_path)

    target = tmp_path / "repo"
    target.mkdir()
    (target / ".git").mkdir()

    orc.config["orchestrator"]["target_project_path"] = str(target)

    mock_result = MagicMock()
    mock_result.returncode = 128
    mock_result.stderr = "fatal: a branch named 'feat/TASK-001' already exists"

    with (
        patch("subprocess.run", return_value=mock_result),
        caplog.at_level(logging.WARNING, logger="scripts.orchestrator"),
    ):
        orc._create_task_branch("TASK-001")

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("already exists" in msg.lower() or "TASK-001" in msg for msg in warnings)


def test_create_task_branch_warns_on_other_nonzero(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """_create_task_branch logs WARNING with stderr on other non-zero return codes."""
    import logging

    orc = _make_orchestrator(tmp_path)

    target = tmp_path / "repo"
    target.mkdir()
    (target / ".git").mkdir()

    orc.config["orchestrator"]["target_project_path"] = str(target)

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "error: some git error"

    with (
        patch("subprocess.run", return_value=mock_result),
        caplog.at_level(logging.WARNING, logger="scripts.orchestrator"),
    ):
        orc._create_task_branch("TASK-001")

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) >= 1


def test_create_task_branch_does_not_raise_on_errors(tmp_path: Path) -> None:
    """_create_task_branch never raises exceptions — all errors are WARNING only."""
    orc = _make_orchestrator(tmp_path)

    target = tmp_path / "repo"
    target.mkdir()
    (target / ".git").mkdir()

    orc.config["orchestrator"]["target_project_path"] = str(target)

    with patch("subprocess.run", side_effect=Exception("unexpected error")):
        # Must not raise
        orc._create_task_branch("TASK-001")


# ---------------------------------------------------------------------------
# AC-006: _create_task_branch called from _create_kickoff_assignment
# ---------------------------------------------------------------------------


def test_create_kickoff_assignment_calls_create_task_branch(tmp_path: Path) -> None:
    """_create_kickoff_assignment calls _create_task_branch(task_id) at end."""
    orc = _make_orchestrator(tmp_path)

    orc.state.write_assignment = MagicMock()

    with patch.object(orc, "_create_task_branch") as mock_branch:
        orc._create_kickoff_assignment(42)

    mock_branch.assert_called_once_with("TASK-042")


def test_create_kickoff_assignment_branch_uses_correct_task_id_format(tmp_path: Path) -> None:
    """_create_kickoff_assignment passes zero-padded task_id to _create_task_branch."""
    orc = _make_orchestrator(tmp_path)
    orc.state.write_assignment = MagicMock()

    with patch.object(orc, "_create_task_branch") as mock_branch:
        orc._create_kickoff_assignment(7)

    mock_branch.assert_called_once_with("TASK-007")
