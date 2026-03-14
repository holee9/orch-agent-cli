"""Multi-target orchestrator for orch-agent-cli.

Extends the single-target Orchestrator to support multiple target projects
simultaneously. Each target runs its own StateManager and ConsensusEngine
independently with no cross-target state sharing.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import yaml

from scripts.consensus import ConsensusEngine
from scripts.state_manager import StateManager

logger = logging.getLogger(__name__)


class MultiOrchestrator:
    """Orchestrates multiple target projects simultaneously.

    Each target project operates with its own StateManager and ConsensusEngine.
    No state is shared between targets.
    """

    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        """Initialize MultiOrchestrator from a config file.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.targets = self._load_targets()

    def _load_config(self) -> dict[str, Any]:
        """Load YAML configuration from disk.

        Returns:
            Parsed configuration dictionary.
        """
        with self.config_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def _load_targets(self) -> list[dict[str, Any]]:
        """Read the ``targets`` list from config.

        Each item may have:
        - ``path`` (required): filesystem path to the target project
        - ``name`` (optional): human-readable identifier; defaults to the
          basename of ``path``
        - ``orchestra_dir`` (optional): subdirectory for state; defaults to
          ``.orchestra``

        Returns:
            List of normalised target dicts.
        """
        raw: list[dict[str, Any]] = self.config.get("targets") or []
        normalised: list[dict[str, Any]] = []
        for item in raw:
            target: dict[str, Any] = dict(item)
            target.setdefault("orchestra_dir", ".orchestra")
            if "name" not in target:
                target["name"] = Path(target["path"]).name
            normalised.append(target)
        return normalised

    # ------------------------------------------------------------------
    # Per-target helpers
    # ------------------------------------------------------------------

    def _make_components(
        self, target: dict[str, Any]
    ) -> tuple[StateManager, ConsensusEngine]:
        """Build StateManager and ConsensusEngine for a single target.

        Args:
            target: Normalised target dict from ``_load_targets``.

        Returns:
            A (StateManager, ConsensusEngine) tuple.
        """
        orchestra_path = Path(target["path"]) / target["orchestra_dir"]
        state_manager = StateManager(base_dir=orchestra_path)

        consensus_cfg = self.config.get("consensus", {})
        consensus_engine = ConsensusEngine(
            threshold=consensus_cfg.get("threshold", 0.9),
        )
        return state_manager, consensus_engine

    def _run_target(self, target: dict[str, Any]) -> dict[str, Any]:
        """Execute one polling cycle for a single target.

        Args:
            target: Normalised target dict.

        Returns:
            Result dict with keys ``target``, ``status``, and optionally
            ``error``.
        """
        name: str = target["name"]
        logger.info("Running polling cycle for target '%s'", name)
        try:
            state_manager, _consensus_engine = self._make_components(target)
            state_manager.ensure_directories()
            return {
                "target": name,
                "status": "ok",
                "state_manager": str(state_manager.base_dir),
            }
        except Exception:
            logger.exception("Error during polling cycle for target '%s'", name)
            return {"target": name, "status": "error"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self) -> dict[str, dict[str, Any]]:
        """Run one polling cycle for every configured target.

        Returns:
            Mapping of ``target_name -> result_dict`` for each target.
        """
        results: dict[str, dict[str, Any]] = {}
        for target in self.targets:
            result = self._run_target(target)
            results[target["name"]] = result
        logger.info(
            "Polling cycle complete: %d target(s) processed", len(results)
        )
        return results

    def run(self, interval_seconds: int | None = None) -> None:
        """Run a continuous polling loop for all targets.

        Args:
            interval_seconds: Seconds to wait between polling cycles.
                Reads ``orchestrator.polling_interval_seconds`` from config
                when *None*. Falls back to 60 if not configured.
        """
        if interval_seconds is None:
            interval_seconds = int(
                self.config.get("orchestrator", {}).get(
                    "polling_interval_seconds", 60
                )
            )

        logger.info(
            "Starting MultiOrchestrator with %d target(s), interval=%ds",
            len(self.targets),
            interval_seconds,
        )

        while True:
            self.run_once()
            logger.debug("Sleeping %d seconds before next cycle", interval_seconds)
            time.sleep(interval_seconds)
