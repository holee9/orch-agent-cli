"""P4 regression: shell script syntax and zombie-cleanup logic validation."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


def test_start_t1_sh_syntax_valid() -> None:
    """start_t1.sh must pass bash -n syntax check."""
    result = subprocess.run(
        ["bash", "-n", str(SCRIPTS_DIR / "start_t1.sh")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Syntax error in start_t1.sh:\n{result.stderr}"


def test_start_t1_sh_contains_zombie_cleanup() -> None:
    """start_t1.sh must contain pgrep-based zombie/stale process cleanup."""
    content = (SCRIPTS_DIR / "start_t1.sh").read_text()
    assert "pgrep" in content, "start_t1.sh must use pgrep for process detection"
    assert "kill -9" in content, "start_t1.sh must kill stopped/zombie processes"


def test_start_t2_sh_syntax_valid() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPTS_DIR / "start_t2.sh")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Syntax error in start_t2.sh:\n{result.stderr}"


def test_start_t3_sh_syntax_valid() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPTS_DIR / "start_t3.sh")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Syntax error in start_t3.sh:\n{result.stderr}"


def test_start_t4_sh_syntax_valid() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPTS_DIR / "start_t4.sh")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Syntax error in start_t4.sh:\n{result.stderr}"
