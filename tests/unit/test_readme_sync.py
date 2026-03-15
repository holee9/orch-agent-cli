"""Unit tests for SPEC-P3-005: readme-sync stage auto-trigger."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import yaml

from scripts.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Shared fixtures (mirrors pattern from tests/unit/test_rework.py)
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
            "primary_stages": [
                "kickoff", "requirements", "planning", "review", "release",
                "readme-sync", "final-report",
            ],
            "secondary_stages": ["consensus"],
            "can_modify": ["docs/", "README.md"],
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
# TC-001: _get_next_stage("release") returns "readme-sync"
# ---------------------------------------------------------------------------


def test_tc001_get_next_stage_after_release(tmp_path: Path) -> None:
    """TC-001: _get_next_stage('release') must return 'readme-sync'."""
    orch = _make_orchestrator(tmp_path)
    result = orch._get_next_stage("release")
    assert result == "readme-sync"


# ---------------------------------------------------------------------------
# TC-002: _get_next_stage("readme-sync") returns "final-report"
# ---------------------------------------------------------------------------


def test_tc002_get_next_stage_after_readme_sync(tmp_path: Path) -> None:
    """TC-002: _get_next_stage('readme-sync') must return 'final-report'."""
    orch = _make_orchestrator(tmp_path)
    result = orch._get_next_stage("readme-sync")
    assert result == "final-report"


# ---------------------------------------------------------------------------
# TC-003: _get_primary_agent("readme-sync") returns "claude"
# ---------------------------------------------------------------------------


def test_tc003_primary_agent_for_readme_sync(tmp_path: Path) -> None:
    """TC-003: _get_primary_agent('readme-sync') must return 'claude'."""
    orch = _make_orchestrator(tmp_path)
    result = orch._get_primary_agent("readme-sync")
    assert result == "claude"


# ---------------------------------------------------------------------------
# TC-004: _trigger_readme_sync creates assignment with brief_path and target_project_path
# ---------------------------------------------------------------------------


def test_tc004_trigger_readme_sync_writes_assignment(tmp_path: Path) -> None:
    """TC-004: _trigger_readme_sync writes assignment containing brief_path and target_project_path."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()

    prev_context = {
        "brief_path": "/path/to/brief.md",
        "target_project_path": str(tmp_path),
    }
    orch._trigger_readme_sync("task-001", 42, prev_context)

    assert orch.state.write_assignment.call_count == 1
    args, _kwargs = orch.state.write_assignment.call_args
    assignment = args[1]
    assert assignment["stage"] == "readme-sync"
    assert assignment["brief_path"] == "/path/to/brief.md"
    assert assignment["target_project_path"] == str(tmp_path)
    assert "instructions" in assignment
    assert "append" in assignment["instructions"].lower()
    assert "git_commit_cmd" in assignment
    assert "readme-sync" in assignment["git_commit_cmd"]


# ---------------------------------------------------------------------------
# TC-005: Calling _trigger_readme_sync twice with same task_id -> write_assignment called only once
# ---------------------------------------------------------------------------


def test_tc005_trigger_readme_sync_idempotency(tmp_path: Path) -> None:
    """TC-005: Calling _trigger_readme_sync twice with same task_id writes assignment only once."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()

    prev_context = {
        "brief_path": "/path/to/brief.md",
        "target_project_path": str(tmp_path),
    }
    orch._trigger_readme_sync("task-001", 42, prev_context)
    orch._trigger_readme_sync("task-001", 42, prev_context)

    assert orch.state.write_assignment.call_count == 1


# ---------------------------------------------------------------------------
# TC-006: Missing target_project_path -> logs warning, no raise, write_assignment NOT called
# ---------------------------------------------------------------------------


def test_tc006_trigger_readme_sync_missing_target_path(tmp_path: Path) -> None:
    """TC-006: When target_project_path is missing from context, logs warning and does NOT call write_assignment."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()

    prev_context = {
        "brief_path": "/path/to/brief.md",
        # target_project_path intentionally absent
    }

    # Must not raise
    orch._trigger_readme_sync("task-002", 99, prev_context)

    orch.state.write_assignment.assert_not_called()


# ---------------------------------------------------------------------------
# TC-007: _advance_workflow when release stage completes -> readme-sync assignment created
# ---------------------------------------------------------------------------


def test_tc007_advance_workflow_release_triggers_readme_sync(tmp_path: Path) -> None:
    """TC-007: _advance_workflow on release completion triggers readme-sync assignment."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()
    orch.state.read_assignment = MagicMock(return_value={
        "agent_id": "claude",
        "task_id": "task-001",
        "stage": "release",
        "github_issue_number": 42,
        "context": {
            "brief_path": "/briefs/brief.md",
            "target_project_path": str(tmp_path),
        },
    })

    completion = {
        "status": "success",
        "task_id": "task-001",
        "completed_at": "2026-03-15T00:00:00Z",
    }

    orch._advance_workflow("claude", "task-001", completion)

    # write_assignment should have been called for readme-sync
    assert orch.state.write_assignment.call_count >= 1
    calls_stages = [
        call_args[0][1].get("stage")
        for call_args in orch.state.write_assignment.call_args_list
    ]
    assert "readme-sync" in calls_stages


# ---------------------------------------------------------------------------
# TC-008: _trigger_readme_sync success -> github.add_comment() called once
# ---------------------------------------------------------------------------


def test_tc008_trigger_readme_sync_calls_add_comment(tmp_path: Path) -> None:
    """TC-008: _trigger_readme_sync success -> github.add_comment() called once with issue_number."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()
    orch.github.add_comment = MagicMock()

    prev_context = {
        "brief_path": "/b.md",
        "target_project_path": str(tmp_path),
    }
    orch._trigger_readme_sync("task-008", 55, prev_context)

    assert orch.github.add_comment.call_count == 1
    call_args = orch.github.add_comment.call_args
    assert 55 in call_args[0] or call_args[1].get("issue_number") == 55


# ---------------------------------------------------------------------------
# TC-SEC-01: Shell metacharacters in task_id are escaped in git_commit_cmd
# ---------------------------------------------------------------------------


def test_tc_sec01_git_cmd_escapes_task_id(tmp_path: Path) -> None:
    """TC-SEC-01: task_id with shell metacharacters must be quoted in git_commit_cmd."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()
    orch.github.add_comment = MagicMock()
    # Use tmp_path (exists) for target_project_path so W1 passes
    prev_context = {
        "brief_path": "/b.md",
        "target_project_path": str(tmp_path),
        # task_id with injection attempt passed separately
    }
    malicious_task_id = "task; rm -rf /"
    orch._trigger_readme_sync(malicious_task_id, 1, prev_context)
    assert orch.state.write_assignment.call_count == 1
    args = orch.state.write_assignment.call_args[0]
    cmd = args[1]["git_commit_cmd"]
    # shlex.quote wraps dangerous content in single quotes
    assert "rm -rf" not in cmd.split("'")[0]  # not unquoted
    # The whole commit message arg must be quoted
    assert "'" in cmd


# ---------------------------------------------------------------------------
# TC-SEC-02: Shell metacharacters in target_project_path are rejected (W1)
# ---------------------------------------------------------------------------


def test_tc_sec02_malicious_target_path_rejected(tmp_path: Path) -> None:
    """TC-SEC-02: target_project_path that is not a valid directory must be rejected."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()
    prev_context = {
        "brief_path": "/b.md",
        "target_project_path": "/tmp; rm -rf /; echo",
    }
    orch._trigger_readme_sync("task-sec2", 1, prev_context)
    orch.state.write_assignment.assert_not_called()


# ---------------------------------------------------------------------------
# TC-SEC-03: Non-existent target_project_path is rejected (W1)
# ---------------------------------------------------------------------------


def test_tc_sec03_nonexistent_target_path_rejected(tmp_path: Path) -> None:
    """TC-SEC-03: A non-existent target_project_path must be rejected before write_assignment."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()
    prev_context = {
        "brief_path": "/b.md",
        "target_project_path": "/nonexistent/path/xxx_does_not_exist",
    }
    orch._trigger_readme_sync("task-sec3", 1, prev_context)
    orch.state.write_assignment.assert_not_called()


# ---------------------------------------------------------------------------
# TC-PERF-01: Duplicate calls don't duplicate comments (C2 verification)
# ---------------------------------------------------------------------------


def test_tc_perf01_duplicate_calls_no_duplicate_comments(tmp_path: Path) -> None:
    """TC-PERF-01: Calling _trigger_readme_sync twice with same task_id posts comment only once."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock()
    orch.github.add_comment = MagicMock()
    ctx = {"brief_path": "/b.md", "target_project_path": str(tmp_path)}
    orch._trigger_readme_sync("task-dup", 1, ctx)
    orch._trigger_readme_sync("task-dup", 1, ctx)
    assert orch.github.add_comment.call_count == 1


# ---------------------------------------------------------------------------
# TC-QUAL-01: Unexpected exceptions propagate through specific exception guard (C3)
# ---------------------------------------------------------------------------


def test_tc_qual01_unexpected_exception_propagates(tmp_path: Path) -> None:
    """TC-QUAL-01: KeyboardInterrupt must not be swallowed by the specific exception handler."""
    orch = _make_orchestrator(tmp_path)
    orch.state.write_assignment = MagicMock(side_effect=KeyboardInterrupt)
    ctx = {"brief_path": "/b.md", "target_project_path": str(tmp_path)}
    with pytest.raises(KeyboardInterrupt):
        orch._trigger_readme_sync("task-exc", 1, ctx)
