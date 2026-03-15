"""Unit tests for MultiOrchestrator (P3-T06)."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.multi_orchestrator import MultiOrchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Write a YAML config file and return its path."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump(data), encoding="utf-8")
    return cfg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_load_targets_empty(tmp_path: Path) -> None:
    """When no 'targets' key exists in config, _load_targets returns []."""
    cfg = _write_config(tmp_path, {"orchestrator": {"polling_interval_seconds": 30}})
    mo = MultiOrchestrator(config_path=cfg)
    assert mo.targets == []


def test_load_targets_single(tmp_path: Path) -> None:
    """Config with one target entry returns a list with exactly 1 item."""
    project = tmp_path / "my-project"
    project.mkdir()
    data = {
        "targets": [
            {"path": str(project), "name": "proj-a", "orchestra_dir": ".orchestra"}
        ]
    }
    cfg = _write_config(tmp_path, data)
    mo = MultiOrchestrator(config_path=cfg)
    assert len(mo.targets) == 1
    assert mo.targets[0]["name"] == "proj-a"


def test_load_targets_multiple(tmp_path: Path) -> None:
    """Config with 2 target entries returns a list with 2 items."""
    p1 = tmp_path / "proj1"
    p2 = tmp_path / "proj2"
    p1.mkdir()
    p2.mkdir()
    data = {
        "targets": [
            {"path": str(p1), "name": "project-1"},
            {"path": str(p2), "name": "project-2"},
        ]
    }
    cfg = _write_config(tmp_path, data)
    mo = MultiOrchestrator(config_path=cfg)
    assert len(mo.targets) == 2
    names = {t["name"] for t in mo.targets}
    assert names == {"project-1", "project-2"}


def test_load_targets_default_orchestra_dir(tmp_path: Path) -> None:
    """An item without 'orchestra_dir' defaults to '.orchestra'."""
    project = tmp_path / "bare-project"
    project.mkdir()
    data = {"targets": [{"path": str(project)}]}
    cfg = _write_config(tmp_path, data)
    mo = MultiOrchestrator(config_path=cfg)
    assert len(mo.targets) == 1
    assert mo.targets[0]["orchestra_dir"] == ".orchestra"


def test_run_once_no_targets(tmp_path: Path) -> None:
    """run_once() with no configured targets returns an empty dict."""
    cfg = _write_config(tmp_path, {})
    mo = MultiOrchestrator(config_path=cfg)
    result = mo.run_once()
    assert result == {}
