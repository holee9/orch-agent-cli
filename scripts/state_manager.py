"""State management for .orchestra/ directory."""

from __future__ import annotations

import json
import logging
import os
import re as _re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_SAFE_ID_PATTERN = _re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,63}$')


def _validate_id(value: str, field_name: str) -> None:
    """Validate that an ID is safe to use as a filename component."""
    if not _SAFE_ID_PATTERN.match(value):
        raise ValueError(
            f"Invalid {field_name}: '{value}'. "
            "Only alphanumeric characters, hyphens, and underscores allowed."
        )


class StateManager:
    """Manages .orchestra/ state directory for agent coordination."""

    SUBDIRS = [
        "state/assigned",
        "state/completed",
        "cache",
        "reports",
        "logs",
        "consensus",
    ]

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def ensure_directories(self) -> None:
        """Create .orchestra/ directory tree if it doesn't exist."""
        for subdir in self.SUBDIRS:
            (self.base_dir / subdir).mkdir(parents=True, exist_ok=True)
        logger.info("Ensured .orchestra/ directory structure at %s", self.base_dir)

    # --- Assignment Operations ---

    def write_assignment(self, agent_id: str, assignment: dict) -> Path:
        """Write assignment file for an agent. Uses atomic rename for safety."""
        _validate_id(agent_id, "agent_id")
        path = self.base_dir / "state" / "assigned" / f"{agent_id}.json"
        self._atomic_write(path, assignment)
        logger.info("Wrote assignment for %s: task %s", agent_id, assignment.get("task_id"))
        return path

    def read_assignment(self, agent_id: str) -> dict | None:
        """Read an agent's current assignment. Returns None if no assignment."""
        _validate_id(agent_id, "agent_id")
        path = self.base_dir / "state" / "assigned" / f"{agent_id}.json"
        return self._read_json(path)

    def clear_assignment(self, agent_id: str) -> bool:
        """Remove an agent's assignment file. Returns True if file existed."""
        _validate_id(agent_id, "agent_id")
        path = self.base_dir / "state" / "assigned" / f"{agent_id}.json"
        if path.exists():
            path.unlink()
            logger.info("Cleared assignment for %s", agent_id)
            return True
        return False

    def list_assignments(self) -> dict[str, dict]:
        """List all current assignments. Returns {agent_id: assignment_data}."""
        assigned_dir = self.base_dir / "state" / "assigned"
        result = {}
        if assigned_dir.exists():
            for f in assigned_dir.glob("*.json"):
                data = self._read_json(f)
                if data:
                    result[f.stem] = data
        return result

    # --- Completion Signal Operations ---

    def write_completion(
        self, agent_id: str, task_id: str, artifacts: list[str] | None = None
    ) -> Path:
        """Write a completion signal file."""
        _validate_id(agent_id, "agent_id")
        _validate_id(task_id, "task_id")
        filename = f"{agent_id}-{task_id}.json"
        path = self.base_dir / "state" / "completed" / filename
        data = {
            "agent_id": agent_id,
            "task_id": task_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": artifacts or [],
        }
        self._atomic_write(path, data)
        logger.info("Wrote completion signal: %s completed %s", agent_id, task_id)
        return path

    def read_completions(self) -> list[dict]:
        """Read all pending completion signals."""
        completed_dir = self.base_dir / "state" / "completed"
        results = []
        if completed_dir.exists():
            for f in sorted(completed_dir.glob("*.json")):
                data = self._read_json(f)
                if data:
                    results.append(data)
        return results

    def clear_completion(self, agent_id: str, task_id: str) -> bool:
        """Remove a processed completion signal."""
        _validate_id(agent_id, "agent_id")
        _validate_id(task_id, "task_id")
        filename = f"{agent_id}-{task_id}.json"
        path = self.base_dir / "state" / "completed" / filename
        if path.exists():
            path.unlink()
            return True
        return False

    # --- Report Operations ---

    def write_report(self, task_id: str, agent_id: str, report: dict) -> Path:
        """Write an agent's review report."""
        _validate_id(task_id, "task_id")
        _validate_id(agent_id, "agent_id")
        path = self.base_dir / "reports" / f"{task_id}.{agent_id}.json"
        self._atomic_write(path, report)
        logger.info("Wrote report: %s.%s", task_id, agent_id)
        return path

    def read_reports(self, task_id: str) -> dict[str, dict]:
        """Read all reports for a task. Returns {agent_id: report_data}."""
        _validate_id(task_id, "task_id")
        reports_dir = self.base_dir / "reports"
        result = {}
        if reports_dir.exists():
            for f in reports_dir.glob(f"{task_id}.*.json"):
                # Extract agent_id from filename: task_id.agent_id.json
                agent_id = f.stem.split(".", 1)[1] if "." in f.stem else f.stem
                data = self._read_json(f)
                if data:
                    result[agent_id] = data
        return result

    # --- Consensus Operations ---

    def write_consensus(self, task_id: str, result: dict) -> Path:
        """Store consensus result."""
        _validate_id(task_id, "task_id")
        path = self.base_dir / "consensus" / f"{task_id}.json"
        self._atomic_write(path, result)
        logger.info("Wrote consensus for %s: %s", task_id, result.get("action"))
        return path

    def read_consensus(self, task_id: str) -> dict | None:
        """Read consensus result for a task."""
        _validate_id(task_id, "task_id")
        path = self.base_dir / "consensus" / f"{task_id}.json"
        return self._read_json(path)

    def clear_consensus(self, task_id: str) -> bool:
        """Remove the consensus file for a task. Returns True if file existed."""
        _validate_id(task_id, "task_id")
        path = self.base_dir / "consensus" / f"{task_id}.json"
        if path.exists():
            path.unlink()
            logger.info("Cleared consensus for %s", task_id)
            return True
        return False

    # --- Cache Operations ---

    def cache_issues(self, issues: list[dict]) -> Path:
        """Cache GitHub issues locally."""
        path = self.base_dir / "cache" / "issues.json"
        data = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "issues": issues,
        }
        self._atomic_write(path, data)
        return path

    def read_cached_issues(self) -> list[dict]:
        """Read cached issues. Returns empty list if no cache."""
        path = self.base_dir / "cache" / "issues.json"
        data = self._read_json(path)
        return data.get("issues", []) if data else []

    # --- Stale Detection ---

    def get_stale_assignments(self, timeout_minutes: int = 30) -> list[dict]:
        """Find assignments that have exceeded the timeout."""
        stale = []
        now = datetime.now(timezone.utc)
        for agent_id, assignment in self.list_assignments().items():
            assigned_at_str = assignment.get("assigned_at")
            if not assigned_at_str:
                continue
            try:
                assigned_at = datetime.fromisoformat(
                    assigned_at_str.replace("Z", "+00:00")
                )
                # Normalize both to UTC-aware for safe comparison
                if assigned_at.tzinfo is None:
                    assigned_at = assigned_at.replace(tzinfo=timezone.utc)
                if (now - assigned_at).total_seconds() > timeout_minutes * 60:
                    stale.append({**assignment, "agent_id": agent_id})
            except (ValueError, TypeError):
                logger.warning("Invalid assigned_at for %s: %s", agent_id, assigned_at_str)
        return stale

    # --- Internal Helpers ---

    def _atomic_write(self, path: Path, data: dict) -> None:
        """Write JSON file atomically using temp file + rename."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _read_json(self, path: Path) -> dict | None:
        """Read JSON file safely. Returns None if file doesn't exist or is invalid."""
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s", path, e)
            return None
