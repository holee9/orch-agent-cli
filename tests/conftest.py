"""Shared pytest fixtures for all orchestrator tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=False)
def mock_cli_subprocess(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-in fixture: mock scripts.orchestrator.subprocess.run for a single test.

    Use this fixture explicitly in tests that need subprocess.run mocked but
    cannot patch check_agent_availability at the Orchestrator level.

    Most tests should instead patch Orchestrator.check_agent_availability directly
    inside _make_orchestrator() to avoid masking real logic in _check_cli_available.

    Skipped for tests marked with @pytest.mark.real_subprocess.
    """
    if request.node.get_closest_marker("real_subprocess"):
        return

    cli_ok: MagicMock = MagicMock()
    cli_ok.returncode = 0
    cli_ok.stderr = ""
    cli_ok.stdout = "mock-cli v0.0.0"

    monkeypatch.setattr("scripts.orchestrator.subprocess.run", lambda *a, **kw: cli_ok)
