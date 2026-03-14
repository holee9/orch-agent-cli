"""Weighted consensus engine for orch-agent-cli.

Implements the consensus algorithm from the v3 plan:
- Weighted voting with reliability and confidence factors
- Veto mechanism (Gemini-exclusive)
- Score dispersion detection
- Re-review escalation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class AgentVote:
    """Represents a single agent's vote in the consensus."""
    agent_id: str
    score: int
    vote: str  # ready, not_ready, veto
    confidence: float
    base_weight: float
    reliability: float = 1.0

    @property
    def effective_weight(self) -> float:
        return self.base_weight * self.reliability * self.confidence


@dataclass
class ConsensusResult:
    """Result of the consensus computation."""
    task_id: str
    can_proceed: bool
    ratio: float
    action: str  # proceed, rework, escalate
    details: list[dict]
    re_review_count: int
    computed_at: str
    vetoed_by: str | None = None
    dispersion_warning: bool = False

    def to_dict(self) -> dict:
        result = {
            "task_id": self.task_id,
            "can_proceed": self.can_proceed,
            "ratio": round(self.ratio, 4),
            "action": self.action,
            "details": self.details,
            "re_review_count": self.re_review_count,
            "computed_at": self.computed_at,
        }
        if self.vetoed_by:
            result["vetoed_by"] = self.vetoed_by
        if self.dispersion_warning:
            result["dispersion_warning"] = True
        return result


class ConsensusEngine:
    """Computes consensus from agent reports using weighted voting."""

    def __init__(
        self,
        threshold: float = 0.9,
        score_ready_min: int = 90,
        dispersion_alert_threshold: int = 20,
        max_rereviews: int = 2,
    ):
        self.threshold = threshold
        self.score_ready_min = score_ready_min
        self.dispersion_alert_threshold = dispersion_alert_threshold
        self.max_rereviews = max_rereviews

    def compute(
        self,
        task_id: str,
        votes: list[AgentVote],
        re_review_count: int = 0,
    ) -> ConsensusResult:
        """Run the consensus algorithm on collected votes.

        Algorithm:
        1. Check for vetoes (immediate FAIL)
        2. Compute effective weights and ready ratio
        3. Check score dispersion
        4. Check re-review escalation
        5. Determine action: proceed / rework / escalate
        """
        now = datetime.now(timezone.utc).isoformat()

        if not votes:
            return ConsensusResult(
                task_id=task_id,
                can_proceed=False,
                ratio=0.0,
                action="rework",
                details=[],
                re_review_count=re_review_count,
                computed_at=now,
            )

        # Step 1: Check vetoes
        for vote in votes:
            if vote.vote == "veto":
                logger.warning("VETO by %s on task %s", vote.agent_id, task_id)
                return ConsensusResult(
                    task_id=task_id,
                    can_proceed=False,
                    ratio=0.0,
                    action="rework",
                    details=self._build_details(votes),
                    re_review_count=re_review_count,
                    computed_at=now,
                    vetoed_by=vote.agent_id,
                )

        # Step 2: Compute effective weights and ratio
        total_weight = sum(v.effective_weight for v in votes)
        ready_weight = sum(v.effective_weight for v in votes if v.vote == "ready")
        ratio = ready_weight / total_weight if total_weight > 0 else 0.0

        # Step 3: Check score dispersion
        scores = [v.score for v in votes]
        dispersion = max(scores) - min(scores)
        dispersion_warning = dispersion > self.dispersion_alert_threshold

        if dispersion_warning:
            logger.warning(
                "Score dispersion alert for %s: %d points (max=%d, min=%d)",
                task_id, dispersion, max(scores), min(scores),
            )

        # Step 4: Determine action
        if re_review_count >= self.max_rereviews:
            action = "escalate"
            can_proceed = False
            logger.warning("Escalating %s: exceeded max re-reviews (%d)", task_id, re_review_count)
        elif ratio >= self.threshold:
            action = "proceed"
            can_proceed = True
            logger.info("Consensus PASS for %s: ratio=%.4f", task_id, ratio)
        else:
            action = "rework"
            can_proceed = False
            logger.info("Consensus FAIL for %s: ratio=%.4f < %.2f", task_id, ratio, self.threshold)

        return ConsensusResult(
            task_id=task_id,
            can_proceed=can_proceed,
            ratio=ratio,
            action=action,
            details=self._build_details(votes),
            re_review_count=re_review_count,
            computed_at=now,
            dispersion_warning=dispersion_warning,
        )

    def build_votes_from_reports(
        self,
        reports: dict[str, dict],
        agents_config: list[dict],
    ) -> list[AgentVote]:
        """Build AgentVote list from report data and agent configuration.

        Args:
            reports: {agent_id: report_data} from state_manager.read_reports()
            agents_config: list of agent config dicts from agents.json
        """
        agent_lookup = {a["id"]: a for a in agents_config}
        votes = []
        for agent_id, report in reports.items():
            agent_cfg = agent_lookup.get(agent_id)
            if not agent_cfg:
                logger.warning("Unknown agent in report: %s", agent_id)
                continue
            votes.append(AgentVote(
                agent_id=agent_id,
                score=report["score"],
                vote=report["vote"],
                confidence=report["confidence"],
                base_weight=agent_cfg["base_weight"],
                reliability=agent_cfg.get("reliability", 1.0),
            ))
        return votes

    def _build_details(self, votes: list[AgentVote]) -> list[dict]:
        """Build per-agent detail records for the consensus result."""
        return [
            {
                "agent_id": v.agent_id,
                "score": v.score,
                "vote": v.vote,
                "confidence": v.confidence,
                "effective_weight": round(v.effective_weight, 4),
            }
            for v in votes
        ]
