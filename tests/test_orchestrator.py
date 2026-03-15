"""Tests for scripts/orchestrator.py.

All GitHub operations and heavy I/O are mocked. Config and agent
registry files are written to tmp_path to keep tests isolated.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from scripts.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Helpers / Shared fixtures
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
            "can_modify": ["src/", "tests/"],
            "cannot_modify": ["docs/"],
            "can_veto": False,
            "sandbox_mode": "workspace-write",
        },
        {
            "id": "gemini",
            "cli_command": "gemini",
            "display_name": "Gemini CLI",
            "base_weight": 0.25,
            "reliability": 1.0,
            "primary_stages": ["testing"],
            "secondary_stages": ["requirements", "review"],
            "can_modify": ["tests/"],
            "cannot_modify": ["src/", "docs/"],
            "can_veto": True,
            "sandbox_mode": None,
        },
    ]
}


def _write_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    """Write config.yaml and agents.json into a config/ subdir and return both paths."""
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

    # Patch the agents.json lookup (hardcoded to "config/agents.json" in source)
    with (
        patch("scripts.orchestrator.GitHubClient") as mock_gh_cls,
        patch("scripts.orchestrator.StateManager") as mock_sm_cls,
        patch("scripts.orchestrator.ConsensusEngine"),
        patch.object(
            Orchestrator,
            "_load_agents",
            return_value=MINIMAL_AGENTS["agents"],
        ),
        patch.object(
            Orchestrator,
            "check_agent_availability",
            side_effect=lambda agents: [{**a, "available": True} for a in agents],
        ),
    ):
        mock_gh_cls.return_value = MagicMock()
        mock_sm_cls.return_value = MagicMock()
        orc = Orchestrator(config_path)

    return orc


# ---------------------------------------------------------------------------
# test_orchestrator_init
# ---------------------------------------------------------------------------


def test_orchestrator_init(tmp_path: Path) -> None:
    """Orchestrator loads config and agents successfully from valid files."""
    orc = _make_orchestrator(tmp_path)

    assert orc.config["github"]["repo"] == "owner/testrepo"
    assert orc.config["consensus"]["threshold"] == 0.9
    assert len(orc.agents) == 3
    agent_ids = {a["id"] for a in orc.agents}
    assert agent_ids == {"claude", "codex", "gemini"}


# ---------------------------------------------------------------------------
# test_poll_cycle_returns_summary
# ---------------------------------------------------------------------------


def test_poll_cycle_returns_summary(tmp_path: Path) -> None:
    """poll_cycle returns a dict with all expected summary keys."""
    orc = _make_orchestrator(tmp_path)

    # Stub all sub-methods so the cycle completes without side effects
    orc.process_webhook_events = MagicMock(return_value=0)
    orc.process_inbox = MagicMock(return_value=0)
    orc.sync_github_issues = MagicMock(return_value=0)
    orc.process_completions = MagicMock(return_value=0)
    orc.check_quality_gates = MagicMock()
    orc.check_consensus_ready = MagicMock(return_value=0)
    orc.release_stale_locks = MagicMock(return_value=0)
    orc.check_session_complete = MagicMock()

    summary = orc.poll_cycle()

    expected_keys = {
        "webhook_events_processed",
        "briefs_processed",
        "issues_synced",
        "completions_processed",
        "consensus_triggered",
        "stale_released",
    }
    assert set(summary.keys()) == expected_keys


# ---------------------------------------------------------------------------
# test_process_inbox_no_briefs
# ---------------------------------------------------------------------------


def test_process_inbox_no_briefs(tmp_path: Path) -> None:
    """process_inbox returns 0 when the inbox directory has no BRIEF files."""
    orc = _make_orchestrator(tmp_path)

    # Point inbox to an empty temp dir
    orc.inbox_dir = tmp_path / "inbox"
    orc.inbox_dir.mkdir()

    with patch("scripts.orchestrator.scan_inbox", return_value=[]) as mock_scan:
        count = orc.process_inbox()

    assert count == 0
    mock_scan.assert_called_once_with(orc.inbox_dir)


# ---------------------------------------------------------------------------
# test_process_inbox_with_brief
# ---------------------------------------------------------------------------


def test_process_inbox_with_brief(tmp_path: Path) -> None:
    """process_inbox processes a single BRIEF file and returns 1."""
    orc = _make_orchestrator(tmp_path)

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    brief_file = inbox / "BRIEF-001.md"
    brief_file.write_text("# Test Brief\n\n## 목표\nDo something\n")

    orc.inbox_dir = inbox
    orc.archive_dir = tmp_path / "archive"

    fake_briefs = [brief_file]

    with (
        patch("scripts.orchestrator.scan_inbox", return_value=fake_briefs),
        patch("scripts.orchestrator.process_brief", return_value=42) as mock_process,
    ):
        count = orc.process_inbox()

    assert count == 1
    mock_process.assert_called_once_with(brief_file, orc.github, orc.archive_dir)


# ---------------------------------------------------------------------------
# test_sync_github_issues
# ---------------------------------------------------------------------------


def test_sync_github_issues(tmp_path: Path) -> None:
    """sync_github_issues caches issues locally and returns the count."""
    from scripts.github_client import GitHubIssue

    orc = _make_orchestrator(tmp_path)

    fake_issues = [
        GitHubIssue(number=1, title="Issue One", body="", state="OPEN", labels=["type:kickoff"]),
        GitHubIssue(number=2, title="Issue Two", body="", state="OPEN", labels=[]),
    ]
    orc.github.list_issues = MagicMock(return_value=fake_issues)
    orc.state.cache_issues = MagicMock()

    count = orc.sync_github_issues()

    assert count == 2
    orc.github.list_issues.assert_called_once_with(state="open")
    orc.state.cache_issues.assert_called_once()
    cached_arg = orc.state.cache_issues.call_args[0][0]
    assert len(cached_arg) == 2
    assert cached_arg[0]["number"] == 1
    assert cached_arg[0]["labels"] == ["type:kickoff"]


# ---------------------------------------------------------------------------
# test_process_completions
# ---------------------------------------------------------------------------


def test_process_completions(tmp_path: Path) -> None:
    """process_completions advances workflow and returns processed count."""
    orc = _make_orchestrator(tmp_path)

    completion = {
        "agent_id": "codex",
        "task_id": "task-001",
        "completed_at": "2026-03-14T10:00:00Z",
        "artifacts": [],
    }
    orc.state.read_completions = MagicMock(return_value=[completion])
    orc.state.clear_assignment = MagicMock()
    orc.state.clear_completion = MagicMock()
    orc._advance_workflow = MagicMock()

    count = orc.process_completions()

    assert count == 1
    orc._advance_workflow.assert_called_once_with("codex", "task-001", completion)
    orc.state.clear_assignment.assert_called_once_with("codex")
    orc.state.clear_completion.assert_called_once_with("codex", "task-001")


# ---------------------------------------------------------------------------
# test_release_stale_locks
# ---------------------------------------------------------------------------


def test_release_stale_locks(tmp_path: Path) -> None:
    """release_stale_locks clears stale assignments and returns count."""
    orc = _make_orchestrator(tmp_path)

    stale = [
        {"agent_id": "codex", "task_id": "task-001", "stage": "implementation"},
        {"agent_id": "gemini", "task_id": "task-002", "stage": "testing"},
    ]
    orc.state.get_stale_assignments = MagicMock(return_value=stale)
    orc.state.clear_assignment = MagicMock()

    count = orc.release_stale_locks()

    assert count == 2
    assert orc.state.clear_assignment.call_count == 2
    cleared_ids = {call.args[0] for call in orc.state.clear_assignment.call_args_list}
    assert cleared_ids == {"codex", "gemini"}


# ---------------------------------------------------------------------------
# test_get_next_stage
# ---------------------------------------------------------------------------


def test_get_next_stage(tmp_path: Path) -> None:
    """_get_next_stage returns correct sequential stage transitions."""
    orc = _make_orchestrator(tmp_path)

    assert orc._get_next_stage("kickoff") == "requirements"
    assert orc._get_next_stage("requirements") == "planning"
    assert orc._get_next_stage("planning") == "implementation"
    assert orc._get_next_stage("implementation") == "review"
    assert orc._get_next_stage("review") == "testing"
    assert orc._get_next_stage("testing") == "consensus"
    assert orc._get_next_stage("consensus") == "release"
    assert orc._get_next_stage("release") == "readme-sync"
    assert orc._get_next_stage("readme-sync") == "final-report"
    # Last stage has no successor
    assert orc._get_next_stage("final-report") is None
    # Unknown stage returns None
    assert orc._get_next_stage("nonexistent") is None


# ---------------------------------------------------------------------------
# test_get_primary_agent
# ---------------------------------------------------------------------------


def test_get_primary_agent(tmp_path: Path) -> None:
    """_get_primary_agent returns the correct agent id for each stage."""
    orc = _make_orchestrator(tmp_path)

    # From agents fixture: claude owns kickoff/requirements/planning/review/release
    assert orc._get_primary_agent("kickoff") == "claude"
    assert orc._get_primary_agent("planning") == "claude"
    assert orc._get_primary_agent("review") == "claude"
    assert orc._get_primary_agent("release") == "claude"

    # codex owns implementation
    assert orc._get_primary_agent("implementation") == "codex"

    # gemini owns testing
    assert orc._get_primary_agent("testing") == "gemini"

    # No agent owns consensus as primary_stage
    assert orc._get_primary_agent("consensus") is None
    # Unknown stage
    assert orc._get_primary_agent("nonexistent") is None


# ---------------------------------------------------------------------------
# test_check_consensus_ready
# ---------------------------------------------------------------------------


def test_check_consensus_ready(tmp_path: Path) -> None:
    """check_consensus_ready triggers consensus when all review reports are present."""
    orc = _make_orchestrator(tmp_path)

    # Simulate two review-stage assignments for task-001
    assignments = {
        "claude": {"stage": "review", "task_id": "task-001", "github_issue_number": 10},
        "gemini": {"stage": "review", "task_id": "task-001", "github_issue_number": 10},
    }
    # Reports from both review agents (claude + gemini have "review" in stages)
    reports = {
        "claude": {
            "agent_id": "claude",
            "task_id": "task-001",
            "score": 92,
            "vote": "ready",
            "confidence": 0.90,
        },
        "gemini": {
            "agent_id": "gemini",
            "task_id": "task-001",
            "score": 88,
            "vote": "ready",
            "confidence": 0.80,
        },
    }

    orc.state.list_assignments = MagicMock(return_value=assignments)
    orc.state.read_reports = MagicMock(return_value=reports)
    orc.state.read_consensus = MagicMock(return_value=None)
    orc.state.write_consensus = MagicMock()
    orc.github.add_comment = MagicMock()
    orc.github.update_labels = MagicMock()

    # Build a fake ConsensusResult
    from scripts.consensus import ConsensusResult

    fake_result = ConsensusResult(
        task_id="task-001",
        can_proceed=True,
        ratio=0.95,
        action="proceed",
        details=[],
        re_review_count=0,
        computed_at="2026-03-14T10:00:00Z",
    )
    orc.consensus_engine.build_votes_from_reports = MagicMock(return_value=[])
    orc.consensus_engine.compute = MagicMock(return_value=fake_result)

    triggered = orc.check_consensus_ready()

    assert triggered == 1
    orc.state.write_consensus.assert_called_once()

    # add_comment is called with a formatted markdown string
    orc.github.add_comment.assert_called_once()
    comment_args = orc.github.add_comment.call_args
    assert comment_args[0][0] == 10  # issue_number
    comment_body = comment_args[0][1]
    assert "Consensus Result" in comment_body
    assert "PASS" in comment_body
    assert "95.00%" in comment_body

    # Label update: add consensus:pass, remove status:review-needed
    orc.github.update_labels.assert_called_once_with(
        10,
        add=["consensus:pass"],
        remove=["status:review-needed"],
    )
