"""Startup smoke tests for Orchestrator init with real config files.

These tests verify that Orchestrator.__init__ runs without crashing when
loaded with the actual config/agents.json. They act as a contract test:
if any required field is missing or misnamed, these tests fail immediately
rather than at runtime in production.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.orchestrator import Orchestrator

# Absolute path to project root — smoke tests require real config files
_PROJECT_ROOT = Path(__file__).parent.parent


def _make_orch_no_avail_check() -> Orchestrator:
    """Create Orchestrator with real config files, skipping CLI availability check."""
    with (
        patch("scripts.orchestrator.GitHubClient"),
        patch("scripts.orchestrator.StateManager"),
        patch("scripts.orchestrator.ConsensusEngine"),
        patch.object(
            Orchestrator,
            "check_agent_availability",
            side_effect=lambda agents: [{**a, "available": False} for a in agents],
        ),
    ):
        orch = Orchestrator(config_path=_PROJECT_ROOT / "config" / "config.yaml")
    return orch


def test_init_with_real_agents_json() -> None:
    """Orchestrator initializes without crash using real config files.

    If this test fails, it means Orchestrator.__init__ crashes before any
    business logic runs — likely a missing field or schema mismatch.
    """
    orch = _make_orch_no_avail_check()
    assert orch.agents is not None
    assert len(orch.agents) > 0


def test_agents_have_cli_command_field() -> None:
    """All agents loaded from agents.json have the 'cli_command' field.

    This test would have caught the 'cli' vs 'cli_command' key mismatch
    that slipped through 3 rounds of code review.
    """
    agents_path = _PROJECT_ROOT / "config" / "agents.json"
    with open(agents_path) as f:
        data = json.load(f)
    for agent in data["agents"]:
        assert "cli_command" in agent, (
            f"Agent '{agent.get('id', '?')}' missing 'cli_command' field. "
            f"Found keys: {list(agent.keys())}"
        )
        assert "cli" not in agent, (
            f"Agent '{agent.get('id', '?')}' has deprecated 'cli' key — "
            f"rename to 'cli_command'"
        )


def test_check_cli_available_empty_string_returns_false() -> None:
    """_check_cli_available with empty string returns False without raising."""
    orch = _make_orch_no_avail_check()
    assert orch._check_cli_available("") is False


@pytest.mark.real_subprocess
def test_check_cli_available_permission_error_returns_false() -> None:
    """PermissionError from subprocess is caught and returns False."""
    orch = _make_orch_no_avail_check()
    with patch("scripts.orchestrator.subprocess.run", side_effect=PermissionError):
        result = orch._check_cli_available("some-cli")
    assert result is False
