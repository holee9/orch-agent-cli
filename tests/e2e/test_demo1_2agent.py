"""E2E tests for Demo 1: 2-Agent (Claude+Codex) Collaboration Loop.

Tests the core workflow:
- BRIEF file detection and assignment creation
- Weighted consensus (Claude weight=3, Codex weight=2)
- Veto override behavior
- .orchestra/cache/ directory writability
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
import yaml

from scripts.brief_parser import scan_inbox
from scripts.consensus import AgentVote, ConsensusEngine
from scripts.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Shared config/agent fixtures matching the 2-agent Demo 1 setup
# ---------------------------------------------------------------------------

DEMO1_CONFIG = {
    "github": {
        "repo": "owner/demo-repo",
        "polling_interval_seconds": 60,
        "mention_user": "",
    },
    "orchestrator": {
        "target_project_path": "",
        "inbox_dir": "",          # overridden per-test via tmp_path
        "brief_archive_dir": "",  # overridden per-test via tmp_path
        "orchestra_dir": "",      # overridden per-test via tmp_path
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
    "notifications": {},
}

DEMO1_AGENTS = {
    "agents": [
        {
            "id": "claude",
            "cli_command": "claude",
            "display_name": "Claude Code",
            "base_weight": 0.60,  # weight=3 (normalized)
            "reliability": 1.0,
            "primary_stages": ["kickoff", "requirements", "planning", "review", "release"],
            "secondary_stages": ["implementation"],
        },
        {
            "id": "codex",
            "cli_command": "codex",
            "display_name": "OpenAI Codex",
            "base_weight": 0.40,  # weight=2 (normalized)
            "reliability": 1.0,
            "primary_stages": ["implementation", "testing"],
            "secondary_stages": ["review"],
        },
    ]
}


def _write_config(tmp_path: Path, inbox: Path, archive: Path, orchestra: Path) -> Path:
    """Write a config.yaml to tmp_path with paths filled in."""
    cfg = {**DEMO1_CONFIG}
    cfg["orchestrator"] = {
        **DEMO1_CONFIG["orchestrator"],
        "inbox_dir": str(inbox),
        "brief_archive_dir": str(archive),
        "orchestra_dir": str(orchestra),
        "target_project_path": str(tmp_path),
    }
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(cfg))
    return config_file


def _write_agents(tmp_path: Path) -> Path:
    """Write agents.json to tmp_path."""
    agents_file = tmp_path / "agents.json"
    agents_file.write_text(json.dumps(DEMO1_AGENTS))
    return agents_file


def _make_orchestrator(tmp_path: Path) -> Orchestrator:
    """Build an Orchestrator wired to tmp_path directories."""
    inbox = tmp_path / "inbox"
    archive = tmp_path / "archive"
    orchestra = tmp_path / ".orchestra"
    inbox.mkdir(parents=True)
    archive.mkdir(parents=True)

    config_file = _write_config(tmp_path, inbox, archive, orchestra)
    agents_file = _write_agents(tmp_path)

    with patch("scripts.orchestrator.GitHubClient") as mock_gh_cls:
        mock_gh = MagicMock()
        mock_gh_cls.return_value = mock_gh
        orch = Orchestrator(config_path=config_file, agents_path=agents_file)
        orch.github = mock_gh  # keep reference for assertions

    return orch


# ---------------------------------------------------------------------------
# Test 1: BRIEF file detected → assignment created
# ---------------------------------------------------------------------------

def test_brief_detected_creates_assignment(tmp_path: Path) -> None:
    """A BRIEF-*.md placed in inbox/ must be picked up by scan_inbox."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    brief_file = inbox / "BRIEF-test.md"
    brief_file.write_text(
        "# Demo Test Task\n\n## 배경\nBackground content.\n\n## 목표\nObjective content.\n",
        encoding="utf-8",
    )

    found = scan_inbox(inbox)

    assert len(found) == 1, f"Expected 1 BRIEF file, got {len(found)}"
    assert found[0].name == "BRIEF-test.md"


def test_brief_detected_and_processed_creates_issue(tmp_path: Path) -> None:
    """process_inbox() must call github.create_issue for each BRIEF found."""
    orch = _make_orchestrator(tmp_path)
    inbox = Path(orch.inbox_dir)

    brief_file = inbox / "BRIEF-demo1.md"
    brief_file.write_text(
        "# Demo 1 Task\n\n## 배경\nIntegration test brief.\n\n## 목표\nCreate issue.\n",
        encoding="utf-8",
    )
    mock_github = cast(MagicMock, orch.github)
    mock_github.create_issue.return_value = 42

    count = orch.process_inbox()

    assert count == 1
    mock_github.create_issue.assert_called_once()
    call_kwargs = mock_github.create_issue.call_args
    assert "Kickoff" in (call_kwargs.kwargs.get("title") or call_kwargs.args[0])


# ---------------------------------------------------------------------------
# Test 2: Weighted approval — Claude(weight=3) + Codex(weight=2) both approve
# ---------------------------------------------------------------------------

def test_consensus_weighted_approve() -> None:
    """Claude(0.60) + Codex(0.40) both vote ready → approved, ratio >= threshold."""
    engine = ConsensusEngine(threshold=0.5, score_ready_min=90, dispersion_alert_threshold=20, max_rereviews=2)

    votes = [
        AgentVote(agent_id="claude", score=95, vote="ready", confidence=1.0, base_weight=0.60, reliability=1.0),
        AgentVote(agent_id="codex",  score=92, vote="ready", confidence=1.0, base_weight=0.40, reliability=1.0),
    ]

    result = engine.compute("task-001", votes, re_review_count=0)

    assert result.can_proceed is True
    assert result.action == "proceed"
    assert result.ratio >= 0.5
    assert result.vetoed_by is None


# ---------------------------------------------------------------------------
# Test 3: Weighted rejection — Claude(weight=3) rejects, Codex(weight=2) approves
# ---------------------------------------------------------------------------

def test_consensus_weighted_reject() -> None:
    """Claude(0.60) votes not_ready, Codex(0.40) votes ready → rejected by weight majority."""
    engine = ConsensusEngine(threshold=0.5, score_ready_min=90, dispersion_alert_threshold=20, max_rereviews=2)

    votes = [
        AgentVote(agent_id="claude", score=60, vote="not_ready", confidence=1.0, base_weight=0.60, reliability=1.0),
        AgentVote(agent_id="codex",  score=92, vote="ready",     confidence=1.0, base_weight=0.40, reliability=1.0),
    ]

    result = engine.compute("task-002", votes, re_review_count=0)

    assert result.can_proceed is False
    assert result.action == "rework"
    # Codex weight=0.40 out of total 1.0 → ratio=0.40, below threshold=0.50
    assert result.ratio < 0.5


# ---------------------------------------------------------------------------
# Test 4: Veto overrides all other votes
# ---------------------------------------------------------------------------

def test_consensus_veto_overrides() -> None:
    """A single veto vote must result in rejection regardless of other votes."""
    engine = ConsensusEngine(threshold=0.5, score_ready_min=90, dispersion_alert_threshold=20, max_rereviews=2)

    # Claude votes ready, Codex vetoes — veto must win
    votes = [
        AgentVote(agent_id="claude", score=95, vote="ready", confidence=1.0, base_weight=0.60, reliability=1.0),
        AgentVote(agent_id="codex",  score=30, vote="veto",  confidence=1.0, base_weight=0.40, reliability=1.0),
    ]

    result = engine.compute("task-003", votes, re_review_count=0)

    assert result.can_proceed is False
    assert result.vetoed_by == "codex"


def test_consensus_veto_by_claude_overrides() -> None:
    """Claude veto must also result in rejection even if Codex votes ready."""
    engine = ConsensusEngine(threshold=0.5, score_ready_min=90, dispersion_alert_threshold=20, max_rereviews=2)

    votes = [
        AgentVote(agent_id="claude", score=20, vote="veto",  confidence=1.0, base_weight=0.60, reliability=1.0),
        AgentVote(agent_id="codex",  score=95, vote="ready", confidence=1.0, base_weight=0.40, reliability=1.0),
    ]

    result = engine.compute("task-004", votes, re_review_count=0)

    assert result.can_proceed is False
    assert result.vetoed_by == "claude"


# ---------------------------------------------------------------------------
# Test 5: .orchestra/cache/ directory is writable
# ---------------------------------------------------------------------------

def test_orchestra_cache_created(tmp_path: Path) -> None:
    """Orchestrator must ensure .orchestra/cache/ is writable."""
    orch = _make_orchestrator(tmp_path)
    orch.state.ensure_directories()

    cache_dir = Path(orch.state.base_dir) / "cache"
    assert cache_dir.exists(), f".orchestra/cache/ not created: {cache_dir}"
    assert cache_dir.is_dir()

    test_file = cache_dir / "test-cache-entry.json"
    test_file.write_text(json.dumps({"agent": "claude", "task": "task-001"}))
    assert test_file.exists()
    assert json.loads(test_file.read_text())["agent"] == "claude"


def test_orchestra_assignments_dir_writable(tmp_path: Path) -> None:
    """Orchestrator must ensure .orchestra/state/assigned/ is writable."""
    orch = _make_orchestrator(tmp_path)
    orch.state.ensure_directories()

    assignments_dir = Path(orch.state.base_dir) / "state" / "assigned"
    assert assignments_dir.exists(), f".orchestra/state/assigned/ not created: {assignments_dir}"

    test_assignment = {
        "agent_id": "claude",
        "task_id": "task-001",
        "stage": "kickoff",
        "github_issue_number": 1,
        "assigned_at": "2026-03-14T00:00:00Z",
        "timeout_minutes": 30,
        "context": {},
    }
    assignment_file = assignments_dir / "claude.json"
    assignment_file.write_text(json.dumps(test_assignment))
    assert assignment_file.exists()
