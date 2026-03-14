"""Tests for SPEC-P3-001: Orchestrator Stability & Observability.

AC-001/002/003: PID lock file management
AC-004/005: agents.json hot-reload
AC-006: UTC log timestamps
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from scripts.orchestrator import (
    Orchestrator,
    acquire_pid_lock,
    release_pid_lock,
)

# ---------------------------------------------------------------------------
# Shared fixtures (same pattern as test_orchestrator.py)
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
            "primary_stages": ["kickoff"],
            "secondary_stages": [],
            "can_modify": [],
            "cannot_modify": [],
            "can_veto": False,
            "sandbox_mode": None,
        }
    ]
}

UPDATED_AGENTS = {
    "agents": [
        {
            "id": "claude",
            "cli_command": "claude",
            "display_name": "Claude Code Updated",
            "base_weight": 0.50,
            "reliability": 1.0,
            "primary_stages": ["kickoff", "review"],
            "secondary_stages": [],
            "can_modify": [],
            "cannot_modify": [],
            "can_veto": False,
            "sandbox_mode": None,
        }
    ]
}


def _write_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    """Write config.yaml and agents.json, return both paths."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text(yaml.dump(MINIMAL_CONFIG))
    agents_path = config_dir / "agents.json"
    agents_path.write_text(json.dumps(MINIMAL_AGENTS))
    return config_path, agents_path


def _make_orchestrator(tmp_path: Path) -> Orchestrator:
    """Create Orchestrator with temp configs and mocked GitHub I/O."""
    config_path, agents_path = _write_fixtures(tmp_path)
    with (
        patch("scripts.orchestrator.GitHubClient") as mock_gh_cls,
        patch("scripts.orchestrator.StateManager") as mock_sm_cls,
        patch("scripts.orchestrator.ConsensusEngine"),
    ):
        mock_gh_cls.return_value = MagicMock()
        mock_sm_cls.return_value = MagicMock()
        orc = Orchestrator(config_path, agents_path=agents_path)
    return orc


# ---------------------------------------------------------------------------
# AC-001: PID file written on acquire_pid_lock
# ---------------------------------------------------------------------------


def test_acquire_pid_lock_writes_pid_file(tmp_path: Path) -> None:
    """AC-001: acquire_pid_lock writes own PID to the lock file."""
    pid_file = tmp_path / "orchestrator.pid"
    acquire_pid_lock(pid_file)
    assert pid_file.exists()
    assert int(pid_file.read_text().strip()) == os.getpid()
    # Cleanup
    release_pid_lock(pid_file)


# ---------------------------------------------------------------------------
# AC-002: acquire_pid_lock raises RuntimeError if another process holds lock
# ---------------------------------------------------------------------------


def test_acquire_pid_lock_raises_if_another_process_running(tmp_path: Path) -> None:
    """AC-002: abort if PID file exists and that process is running."""
    pid_file = tmp_path / "orchestrator.pid"
    # Write a PID that belongs to a running process (use os.getpid() itself)
    pid_file.write_text(str(os.getpid()))
    # The current process IS running — should raise
    with pytest.raises(RuntimeError, match="already running"):
        acquire_pid_lock(pid_file)


# ---------------------------------------------------------------------------
# AC-003: release_pid_lock removes the PID file
# ---------------------------------------------------------------------------


def test_release_pid_lock_removes_file(tmp_path: Path) -> None:
    """AC-003: release_pid_lock deletes the PID file."""
    pid_file = tmp_path / "orchestrator.pid"
    acquire_pid_lock(pid_file)
    assert pid_file.exists()
    release_pid_lock(pid_file)
    assert not pid_file.exists()


def test_release_pid_lock_is_idempotent(tmp_path: Path) -> None:
    """AC-003: release_pid_lock does not raise when file is absent."""
    pid_file = tmp_path / "orchestrator.pid"
    # Should not raise even if file does not exist
    release_pid_lock(pid_file)


# ---------------------------------------------------------------------------
# Stale PID detection: process not running → remove and continue
# ---------------------------------------------------------------------------


def test_acquire_pid_lock_removes_stale_pid_file(tmp_path: Path) -> None:
    """Stale PID (process not running) is removed and lock is acquired."""
    pid_file = tmp_path / "orchestrator.pid"
    # PID 999999 is almost certainly not running
    pid_file.write_text("999999")
    acquire_pid_lock(pid_file)
    assert pid_file.exists()
    assert int(pid_file.read_text().strip()) == os.getpid()
    release_pid_lock(pid_file)


# ---------------------------------------------------------------------------
# AC-004: poll_cycle reloads agents.json from disk each call
# ---------------------------------------------------------------------------


def test_poll_cycle_reloads_agents_config(tmp_path: Path) -> None:
    """AC-004: each poll_cycle call reloads agents.json from disk."""
    config_path, agents_path = _write_fixtures(tmp_path)

    with (
        patch("scripts.orchestrator.GitHubClient") as mock_gh_cls,
        patch("scripts.orchestrator.StateManager") as mock_sm_cls,
        patch("scripts.orchestrator.ConsensusEngine"),
        patch("scripts.orchestrator.scan_inbox", return_value=[]),
        patch("scripts.orchestrator.process_brief"),
    ):
        mock_gh_cls.return_value = MagicMock()
        mock_sm = MagicMock()
        mock_sm.list_active_sessions.return_value = []
        mock_sm_cls.return_value = mock_sm

        orc = Orchestrator(config_path, agents_path=agents_path)
        original_agents = orc.agents[:]

        # Update agents.json on disk
        agents_path.write_text(json.dumps(UPDATED_AGENTS))

        orc.poll_cycle()

        # Agents should reflect the updated file
        assert orc.agents != original_agents
        assert orc.agents[0]["display_name"] == "Claude Code Updated"


# ---------------------------------------------------------------------------
# AC-005: SIGHUP triggers immediate reload with log message
# ---------------------------------------------------------------------------


def test_sighup_reloads_agents_and_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """AC-005: SIGHUP causes immediate reload and logs the event."""
    config_path, agents_path = _write_fixtures(tmp_path)

    with (
        patch("scripts.orchestrator.GitHubClient") as mock_gh_cls,
        patch("scripts.orchestrator.StateManager") as mock_sm_cls,
        patch("scripts.orchestrator.ConsensusEngine"),
    ):
        mock_gh_cls.return_value = MagicMock()
        mock_sm_cls.return_value = MagicMock()
        orc = Orchestrator(config_path, agents_path=agents_path)

        # Update agents.json before sending SIGHUP
        agents_path.write_text(json.dumps(UPDATED_AGENTS))

        with caplog.at_level(logging.INFO, logger="scripts.orchestrator"):
            orc._handle_sighup(signal.SIGHUP, None)

        assert orc.agents[0]["display_name"] == "Claude Code Updated"
        assert any("reloaded" in rec.message.lower() for rec in caplog.records)


# ---------------------------------------------------------------------------
# AC-005: no-change reload does NOT log "agents config reloaded"
# ---------------------------------------------------------------------------


def test_reload_agents_no_change_skips_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-005: reload when content unchanged does not emit reload log."""
    config_path, agents_path = _write_fixtures(tmp_path)

    with (
        patch("scripts.orchestrator.GitHubClient") as mock_gh_cls,
        patch("scripts.orchestrator.StateManager") as mock_sm_cls,
        patch("scripts.orchestrator.ConsensusEngine"),
    ):
        mock_gh_cls.return_value = MagicMock()
        mock_sm_cls.return_value = MagicMock()
        orc = Orchestrator(config_path, agents_path=agents_path)

        with caplog.at_level(logging.INFO, logger="scripts.orchestrator"):
            orc._reload_agents_config()

        assert not any("reloaded" in rec.message.lower() for rec in caplog.records)


# ---------------------------------------------------------------------------
# AC-006: main() configures UTC log timestamps
# ---------------------------------------------------------------------------


def test_main_configures_utc_logging(tmp_path: Path) -> None:
    """AC-006: main() sets logging.Formatter.converter to time.gmtime."""
    import scripts.orchestrator as mod

    config_path, _ = _write_fixtures(tmp_path)

    with (
        patch("scripts.orchestrator.GitHubClient"),
        patch("scripts.orchestrator.StateManager"),
        patch("scripts.orchestrator.ConsensusEngine"),
        patch("scripts.orchestrator.Orchestrator.start"),
        patch("sys.argv", ["orchestrator", str(config_path)]),
        patch("logging.basicConfig"),
    ):
        mod.main()

    assert logging.Formatter.converter is time.gmtime


# ---------------------------------------------------------------------------
# Integration: Orchestrator.start() calls acquire/release_pid_lock
# ---------------------------------------------------------------------------


def test_start_acquires_and_releases_pid_lock(tmp_path: Path) -> None:
    """start() acquires PID lock at entry and releases in finally block."""
    orc = _make_orchestrator(tmp_path)
    pid_file = tmp_path / "test.pid"

    def _one_cycle_then_stop(*_args: object, **_kwargs: object) -> dict:
        orc.running = False
        return {}

    with (
        patch("scripts.orchestrator.PID_FILE", pid_file),
        patch("scripts.orchestrator.acquire_pid_lock") as mock_acquire,
        patch("scripts.orchestrator.release_pid_lock") as mock_release,
        patch.object(orc.state, "ensure_directories"),
        patch.object(orc, "poll_cycle", side_effect=_one_cycle_then_stop),
        patch("scripts.orchestrator.time") as mock_time,
    ):
        mock_time.sleep = MagicMock()
        orc.start()

    mock_acquire.assert_called_once_with(pid_file)
    mock_release.assert_called_once_with(pid_file)
