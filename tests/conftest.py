"""Shared pytest fixtures for all orchestrator tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_cli_subprocess(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-mock scripts.orchestrator.subprocess.run for all tests.

    Prevents _check_cli_available() from spawning real processes during
    Orchestrator.__init__(). Tests that need to assert on subprocess behaviour
    can override via their own patch("scripts.orchestrator.subprocess.run").

    Skipped for tests marked with @pytest.mark.real_subprocess.
    """
    if request.node.get_closest_marker("real_subprocess"):
        return

    cli_ok: MagicMock = MagicMock()
    cli_ok.returncode = 0
    cli_ok.stderr = ""
    cli_ok.stdout = "mock-cli v0.0.0"

    monkeypatch.setattr("scripts.orchestrator.subprocess.run", lambda *a, **kw: cli_ok)
