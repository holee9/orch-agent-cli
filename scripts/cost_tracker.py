"""Agent cost tracking module.

Records API call token usage and estimates USD cost per agent.
Persists data to a JSON file for cross-session accumulation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# @MX:ANCHOR: [AUTO] Primary cost tracking interface; called after each API call
# @MX:REASON: fan_in >= 3 (orchestrator, tests, future dashboard); drives cost reporting

# Default cost rates per 1,000 tokens (USD)
_INPUT_COST_PER_1K: float = 0.003
_OUTPUT_COST_PER_1K: float = 0.015


class CostTracker:
    """Tracks API call token usage and estimated cost per agent."""

    def __init__(self, data_path: str | Path = "config/agent_costs.json") -> None:
        """Initialize CostTracker with a persistent JSON store.

        Args:
            data_path: Path to the JSON file for persisting cost data.
        """
        self.path = Path(data_path)

    def _load(self) -> dict:
        """Load cost data from disk. Returns initial scaffold if file missing."""
        if not self.path.exists():
            return {"agents": {}, "total_calls": 0}
        with self.path.open() as f:
            return json.load(f)

    def _save(self, data: dict) -> None:
        """Persist cost data to disk."""
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as f:
            json.dump(data, f, indent=2)

    def _estimate_cost(self, tokens_in: int, tokens_out: int, _model: str) -> float:
        """Estimate USD cost for a single API call.

        Uses default rates for unknown models:
          - Input:  $0.003 / 1K tokens
          - Output: $0.015 / 1K tokens

        Args:
            tokens_in: Number of input tokens consumed.
            tokens_out: Number of output tokens generated.
            model: Model name (currently unused; reserved for future per-model rates).

        Returns:
            Estimated cost in USD.
        """
        input_cost = (tokens_in / 1000.0) * _INPUT_COST_PER_1K
        output_cost = (tokens_out / 1000.0) * _OUTPUT_COST_PER_1K
        return input_cost + output_cost

    def record(
        self,
        agent_id: str,
        tokens_in: int,
        tokens_out: int,
        model: str = "unknown",
    ) -> None:
        """Record an API call's token usage for the given agent.

        Args:
            agent_id: Agent identifier (e.g. "claude", "codex").
            tokens_in: Number of input tokens consumed.
            tokens_out: Number of output tokens generated.
            model: Model name used for the call.
        """
        cost = self._estimate_cost(tokens_in, tokens_out, model)
        data = self._load()

        agents = data.setdefault("agents", {})
        if agent_id not in agents:
            agents[agent_id] = {
                "tokens_in": 0,
                "tokens_out": 0,
                "estimated_cost_usd": 0.0,
                "call_count": 0,
            }

        agent = agents[agent_id]
        agent["tokens_in"] += tokens_in
        agent["tokens_out"] += tokens_out
        agent["estimated_cost_usd"] += cost
        agent["call_count"] += 1

        data["total_calls"] = data.get("total_calls", 0) + 1

        self._save(data)
        logger.info(
            "CostTracker: %s tokens_in=%d tokens_out=%d cost=$%.6f",
            agent_id,
            tokens_in,
            tokens_out,
            cost,
        )

    def get_summary(self, agent_id: str | None = None) -> dict:
        """Return aggregated cost summary.

        Args:
            agent_id: If provided, return data only for that agent.
                      If None, return totals across all agents.

        Returns:
            Dict with keys: tokens_in, tokens_out, estimated_cost_usd, call_count.
        """
        data = self._load()
        agents = data.get("agents", {})

        if agent_id is not None:
            agent_data = agents.get(agent_id, {})
            return {
                "tokens_in": agent_data.get("tokens_in", 0),
                "tokens_out": agent_data.get("tokens_out", 0),
                "estimated_cost_usd": agent_data.get("estimated_cost_usd", 0.0),
                "call_count": agent_data.get("call_count", 0),
            }

        # Aggregate across all agents
        total_in = sum(a.get("tokens_in", 0) for a in agents.values())
        total_out = sum(a.get("tokens_out", 0) for a in agents.values())
        total_cost = sum(a.get("estimated_cost_usd", 0.0) for a in agents.values())
        total_calls = sum(a.get("call_count", 0) for a in agents.values())

        return {
            "tokens_in": total_in,
            "tokens_out": total_out,
            "estimated_cost_usd": total_cost,
            "call_count": total_calls,
        }
