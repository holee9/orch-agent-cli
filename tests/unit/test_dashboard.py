"""Unit tests for scripts/dashboard.py."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


def _write_config(path: Path, orchestra_dir: str = ".orchestra/") -> Path:
    """Write a minimal config.yaml to path and return it."""
    config = {
        "orchestrator": {"polling_interval_seconds": 60},
        "agents": {"claude": {"weight": 3}, "codex": {"weight": 2}},
        "paths": {"orchestra": orchestra_dir},
    }
    config_file = path / "config.yaml"
    config_file.write_text(yaml.dump(config))
    return config_file


class TestDashboardRendersWithoutError:
    """Dashboard renders a layout with valid config and empty orchestra dir."""

    def test_dashboard_renders_without_error(self, tmp_path: Path) -> None:
        """run_once() should not raise even with an empty project directory."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        dashboard = Dashboard(config_path=config_file)
        # run_once() prints to console; should complete without any exception
        dashboard.run_once()

    def test_render_returns_renderable(self, tmp_path: Path) -> None:
        """render() should return a rich RenderableType."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        dashboard = Dashboard(config_path=config_file)
        result = dashboard.render()
        # rich Layout is a RenderableType
        assert result is not None

    def test_dashboard_with_assignment_files(self, tmp_path: Path) -> None:
        """render() includes assignment data when files are present."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        # Create an assignment file
        assigned_dir = tmp_path / ".orchestra" / "state" / "assigned"
        assigned_dir.mkdir(parents=True)
        assignment = {
            "agent_id": "claude",
            "task_id": "TASK-001",
            "stage": "review",
            "assigned_at": "2026-03-14T10:00:00Z",
        }
        (assigned_dir / "claude.json").write_text(json.dumps(assignment))

        dashboard = Dashboard(config_path=config_file)
        assignments = dashboard._list_assignments()
        assert len(assignments) == 1
        assert assignments[0]["task_id"] == "TASK-001"

    def test_dashboard_with_reliability_data(self, tmp_path: Path) -> None:
        """_load_reliability() returns data when agent_reliability.json exists."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        reliability = {
            "claude": {"reliability_score": 0.95, "total_tasks": 10},
            "codex": {"reliability_score": 0.80, "total_tasks": 5},
        }
        (config_dir / "agent_reliability.json").write_text(json.dumps(reliability))

        dashboard = Dashboard(config_path=config_file)
        data = dashboard._load_reliability()
        assert data["claude"]["reliability_score"] == 0.95
        assert data["codex"]["reliability_score"] == 0.80


class TestDashboardHandlesMissingOrchestraDir:
    """Dashboard does not raise when .orchestra/ directories are absent."""

    def test_dashboard_handles_missing_orchestra_dir(self, tmp_path: Path) -> None:
        """run_once() should not raise when .orchestra/ does not exist."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        # Intentionally do NOT create any .orchestra/ subdirectories
        dashboard = Dashboard(config_path=config_file)
        # Should complete gracefully
        dashboard.run_once()

    def test_list_assignments_returns_empty_when_missing(self, tmp_path: Path) -> None:
        """_list_assignments() returns [] when assigned dir is absent."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        dashboard = Dashboard(config_path=config_file)
        assert dashboard._list_assignments() == []

    def test_recent_logs_returns_empty_when_missing(self, tmp_path: Path) -> None:
        """_recent_logs() returns [] when logs dir is absent."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        dashboard = Dashboard(config_path=config_file)
        assert dashboard._recent_logs() == []

    def test_load_reliability_returns_empty_when_missing(self, tmp_path: Path) -> None:
        """_load_reliability() returns {} when file is absent."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        dashboard = Dashboard(config_path=config_file)
        assert dashboard._load_reliability() == {}

    def test_summary_panel_with_no_tasks(self, tmp_path: Path) -> None:
        """_build_summary_panel() should not raise when no task files exist."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        dashboard = Dashboard(config_path=config_file)
        panel = dashboard._build_summary_panel()
        assert panel is not None

    def test_age_minutes_with_invalid_timestamp(self, tmp_path: Path) -> None:
        """_age_minutes() returns '-' for invalid or empty timestamps."""
        from scripts.dashboard import Dashboard

        config_file = _write_config(tmp_path)
        dashboard = Dashboard(config_path=config_file)
        assert dashboard._age_minutes("") == "-"
        assert dashboard._age_minutes("not-a-date") == "-"

    def test_dashboard_missing_config_file(self, tmp_path: Path) -> None:
        """Dashboard handles a missing config file gracefully."""
        from scripts.dashboard import Dashboard

        missing = tmp_path / "nonexistent.yaml"
        dashboard = Dashboard(config_path=missing)
        # Config should be empty dict, not raise
        assert dashboard.config == {}
        # run_once should still complete without error
        dashboard.run_once()
