"""
Terminal dashboard for orch-agent-cli.

Displays agent assignments, reliability scores, recent logs, and summary counts
using rich for terminal rendering. Supports live refresh and one-shot modes.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)


class Dashboard:
    """Terminal dashboard for orch-agent-cli orchestration state."""

    def __init__(self, config_path: Path) -> None:
        """Initialize the dashboard with the given config file path.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.console = Console()

    def _load_config(self) -> dict:
        """Load and return YAML config. Returns empty dict on failure."""
        try:
            with self.config_path.open() as f:
                return yaml.safe_load(f) or {}
        except Exception as exc:
            logger.warning("Failed to load config from %s: %s", self.config_path, exc)
            return {}

    def _orchestra_path(self) -> Path:
        """Resolve the .orchestra/ base directory from config."""
        paths = self.config.get("paths", {})
        orchestra = paths.get("orchestra", ".orchestra/")
        return self.config_path.parent / orchestra

    def _list_assignments(self) -> list[dict]:
        """Read all assignment JSON files from .orchestra/state/assigned/."""
        assigned_dir = self._orchestra_path() / "state" / "assigned"
        assignments = []
        if not assigned_dir.exists():
            return assignments
        for json_file in sorted(assigned_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text())
                if "agent_id" not in data:
                    data["agent_id"] = json_file.stem
                assignments.append(data)
            except Exception as exc:
                logger.warning("Failed to read assignment %s: %s", json_file, exc)
        return assignments

    def _list_all_tasks(self) -> list[dict]:
        """Read all task JSON files from .orchestra/assignments/ (legacy path)."""
        assignments_dir = self._orchestra_path() / "assignments"
        tasks = []
        if not assignments_dir.exists():
            return tasks
        for json_file in sorted(assignments_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text())
                tasks.append(data)
            except Exception as exc:
                logger.warning("Failed to read task %s: %s", json_file, exc)
        return tasks

    def _load_reliability(self) -> dict:
        """Load agent reliability data from config/agent_reliability.json."""
        reliability_path = self.config_path.parent / "config" / "agent_reliability.json"
        try:
            return json.loads(reliability_path.read_text())
        except FileNotFoundError:
            return {}
        except Exception as exc:
            logger.warning("Failed to load reliability data: %s", exc)
            return {}

    def _recent_logs(self, n: int = 5) -> list[str]:
        """Return the last n lines from the most recent log file."""
        logs_dir = self._orchestra_path() / "logs"
        if not logs_dir.exists():
            return []
        log_files = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            return []
        try:
            lines = log_files[0].read_text().splitlines()
            return lines[-n:] if lines else []
        except Exception as exc:
            logger.warning("Failed to read log file %s: %s", log_files[0], exc)
            return []

    def _age_minutes(self, assigned_at: str) -> str:
        """Calculate age in minutes from an ISO timestamp string."""
        if not assigned_at:
            return "-"
        try:
            dt = datetime.fromisoformat(assigned_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - dt
            return str(int(delta.total_seconds() / 60))
        except (ValueError, TypeError):
            return "-"

    def _build_assignments_table(self, assignments: list[dict]) -> Table:
        """Build the active assignments table."""
        table = Table(title="Active Assignments", show_header=True, header_style="bold cyan")
        table.add_column("Agent", style="green")
        table.add_column("Task ID", style="yellow")
        table.add_column("Status / Stage")
        table.add_column("Age (min)", justify="right")

        if not assignments:
            table.add_row("-", "-", "-", "-")
        else:
            for a in assignments:
                agent_id = a.get("agent_id", "unknown")
                task_id = a.get("task_id", "-")
                stage = a.get("stage", a.get("status", "-"))
                age = self._age_minutes(a.get("assigned_at", ""))
                table.add_row(agent_id, task_id, stage, age)
        return table

    def _build_agent_status_table(self, assignments: list[dict], reliability: dict) -> Table:
        """Build the agent status table with reliability scores."""
        table = Table(title="Agent Status", show_header=True, header_style="bold magenta")
        table.add_column("Agent", style="green")
        table.add_column("Reliability Score", justify="right")
        table.add_column("Current Task")

        # Build lookup for current tasks from active assignments
        current_tasks: dict[str, str] = {
            a.get("agent_id", ""): a.get("task_id", "-") for a in assignments
        }

        # Collect agents from config + reliability data
        config_agents = set(self.config.get("agents", {}).keys())
        reliability_agents = set(reliability.keys())
        all_agents = sorted(config_agents | reliability_agents)

        if not all_agents:
            table.add_row("-", "-", "-")
        else:
            for agent in all_agents:
                agent_data = reliability.get(agent, {})
                score = agent_data.get("reliability_score", "-")
                if isinstance(score, float):
                    score_str = f"{score:.3f}"
                else:
                    score_str = str(score)
                current = current_tasks.get(agent, "-")
                table.add_row(agent, score_str, current)
        return table

    def _build_logs_panel(self, lines: list[str]) -> Panel:
        """Build the recent logs panel."""
        if lines:
            content = Text("\n".join(lines), style="dim")
        else:
            content = Text("No logs available", style="dim italic")
        return Panel(content, title="Recent Logs (last 5 lines)", border_style="blue")

    def _build_summary_panel(self) -> Panel:
        """Build the summary panel with task counts from .orchestra/assignments/."""
        tasks = self._list_all_tasks()
        active_assignments = self._list_assignments()

        open_count = 0
        in_progress_count = len(active_assignments)
        done_count = 0

        for t in tasks:
            status = t.get("status", t.get("stage", ""))
            if status in ("done", "completed", "released"):
                done_count += 1
            elif status in ("open", "pending", ""):
                open_count += 1

        content = Text()
        content.append(f"Open: {open_count}  ", style="yellow")
        content.append(f"In Progress: {in_progress_count}  ", style="cyan")
        content.append(f"Done: {done_count}", style="green")
        return Panel(content, title="Summary", border_style="green")

    def render(self) -> RenderableType:
        """Build a renderable layout with all dashboard sections.

        Returns a Layout containing:
        - Title panel
        - Assignments table
        - Agent status table
        - Recent logs panel
        - Summary panel
        """
        assignments = self._list_assignments()
        reliability = self._load_reliability()
        log_lines = self._recent_logs(5)

        layout = Layout()
        layout.split_column(
            Layout(name="title", size=3),
            Layout(name="tables", size=12),
            Layout(name="logs", size=8),
            Layout(name="summary", size=3),
        )

        layout["title"].update(
            Panel(
                Text("orch-agent-cli Dashboard", justify="center", style="bold white"),
                border_style="bright_white",
            )
        )

        layout["tables"].split_row(
            Layout(name="assignments"),
            Layout(name="agents"),
        )
        layout["tables"]["assignments"].update(self._build_assignments_table(assignments))
        layout["tables"]["agents"].update(self._build_agent_status_table(assignments, reliability))
        layout["logs"].update(self._build_logs_panel(log_lines))
        layout["summary"].update(self._build_summary_panel())

        return layout

    def run(self, refresh_seconds: int = 30) -> None:
        """Live refresh loop using rich.Live. Press Ctrl+C to exit.

        Args:
            refresh_seconds: How often to refresh the dashboard (default: 30).
        """
        try:
            with Live(self.render(), console=self.console, screen=True, refresh_per_second=1) as live:
                while True:
                    time.sleep(refresh_seconds)
                    live.update(self.render())
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Dashboard stopped.[/yellow]")

    def run_once(self) -> None:
        """Print render() once and exit. Used for --once flag and testing."""
        self.console.print(self.render())


def main() -> None:
    """CLI entry point for scripts/dashboard.py."""
    parser = argparse.ArgumentParser(description="orch-agent-cli terminal dashboard")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config YAML file (default: config.yaml)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print dashboard once and exit",
    )
    parser.add_argument(
        "--refresh",
        type=int,
        default=30,
        help="Refresh interval in seconds for live mode (default: 30)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    dashboard = Dashboard(config_path=args.config)

    if args.once:
        dashboard.run_once()
    else:
        dashboard.run(refresh_seconds=args.refresh)


if __name__ == "__main__":
    main()
