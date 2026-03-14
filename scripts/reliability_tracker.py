"""Reliability tracker for agent performance scoring.

Maintains a persistent JSON store of per-agent reliability scores,
updated after each assignment outcome.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# @MX:ANCHOR: [AUTO] Central scoring interface called by orchestrator after every completion
# @MX:REASON: fan_in >= 3 (orchestrator, tests, future dashboard); score drives agent selection


class ReliabilityTracker:
    """Tracks and persists agent reliability scores."""

    SCORE_DELTA: dict[str, float] = {
        "success": 0.05,
        "failure": -0.1,
        "timeout": -0.15,
    }
    SCORE_MIN: float = 0.1
    SCORE_MAX: float = 1.0

    def __init__(self, reliability_path: Path) -> None:
        self.path = Path(reliability_path)

    def load(self) -> dict:
        """Load reliability data from disk. Returns empty scaffold if file missing."""
        if not self.path.exists():
            return {
                "agents": {},
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        with self.path.open() as f:
            return json.load(f)

    def save(self, data: dict) -> None:
        """Persist reliability data to disk."""
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as f:
            json.dump(data, f, indent=2)

    def update(self, agent_id: str, outcome: str) -> float:
        """Apply outcome delta to agent score and persist. Returns new score.

        Args:
            agent_id: Agent identifier (e.g. "claude", "codex", "gemini").
            outcome: One of "success", "failure", "timeout".

        Returns:
            The updated score, clamped to [SCORE_MIN, SCORE_MAX].
        """
        delta = self.SCORE_DELTA.get(outcome, 0.0)
        data = self.load()

        agents = data.setdefault("agents", {})
        if agent_id not in agents:
            agents[agent_id] = {"score": 1.0, "history": [], "total_tasks": 0}

        agent = agents[agent_id]
        new_score = max(self.SCORE_MIN, min(self.SCORE_MAX, agent["score"] + delta))
        agent["score"] = new_score
        agent["history"].append(
            {
                "outcome": outcome,
                "delta": delta,
                "score_after": new_score,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        agent["total_tasks"] = agent.get("total_tasks", 0) + 1

        self.save(data)
        logger.info(
            "ReliabilityTracker: %s %s -> score=%.3f", agent_id, outcome, new_score
        )
        return new_score

    def record_deployment(self, agent_id: str, success: bool) -> float:
        """Adjust agent score based on deployment outcome and persist. Returns new score.

        Args:
            agent_id: Agent identifier (e.g. "claude", "codex", "gemini").
            success: True for deployment success (+0.03), False for failure (-0.20).

        Returns:
            The updated score, clamped to [SCORE_MIN, SCORE_MAX].
        """
        delta = 0.03 if success else -0.20
        data = self.load()

        agents = data.setdefault("agents", {})
        if agent_id not in agents:
            agents[agent_id] = {"score": 1.0, "history": [], "total_tasks": 0}

        agent = agents[agent_id]
        new_score = max(self.SCORE_MIN, min(self.SCORE_MAX, agent["score"] + delta))
        agent["score"] = new_score
        agent["history"].append(
            {
                "outcome": "deployment_success" if success else "deployment_failure",
                "delta": delta,
                "score_after": new_score,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        self.save(data)
        outcome_label = "deployment_success" if success else "deployment_failure"
        logger.info(
            "ReliabilityTracker: %s %s -> score=%.3f", agent_id, outcome_label, new_score
        )
        return new_score

    def get_score(self, agent_id: str) -> float:
        """Return current score for agent_id, defaulting to 1.0 if unknown."""
        data = self.load()
        return data.get("agents", {}).get(agent_id, {}).get("score", 1.0)
