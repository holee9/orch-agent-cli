"""Tests for the ConsensusEngine in scripts/consensus.py."""

from __future__ import annotations

import pytest

from scripts.consensus import AgentVote, ConsensusEngine, ConsensusResult

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

AGENTS_CONFIG = [
    {"id": "claude", "base_weight": 0.40, "reliability": 1.0},
    {"id": "codex", "base_weight": 0.35, "reliability": 1.0},
    {"id": "gemini", "base_weight": 0.25, "reliability": 1.0},
]


def _make_vote(
    agent_id: str,
    vote: str = "ready",
    score: int = 95,
    confidence: float = 1.0,
    base_weight: float = 0.40,
    reliability: float = 1.0,
) -> AgentVote:
    """Helper to construct an AgentVote with sensible defaults."""
    return AgentVote(
        agent_id=agent_id,
        score=score,
        vote=vote,
        confidence=confidence,
        base_weight=base_weight,
        reliability=reliability,
    )


@pytest.fixture
def engine() -> ConsensusEngine:
    """Default ConsensusEngine with threshold=0.9."""
    return ConsensusEngine(
        threshold=0.9,
        score_ready_min=90,
        dispersion_alert_threshold=20,
        max_rereviews=2,
    )


@pytest.fixture
def all_ready_votes() -> list[AgentVote]:
    """Three agents all voting ready with high scores."""
    return [
        _make_vote("claude", vote="ready", score=95, base_weight=0.40),
        _make_vote("codex", vote="ready", score=92, base_weight=0.35),
        _make_vote("gemini", vote="ready", score=91, base_weight=0.25),
    ]


# ---------------------------------------------------------------------------
# Test 1: All agents vote ready -> proceed
# ---------------------------------------------------------------------------


def test_consensus_pass(engine: ConsensusEngine, all_ready_votes: list[AgentVote]) -> None:
    result = engine.compute("TASK-001", all_ready_votes)

    assert result.can_proceed is True
    assert result.action == "proceed"
    assert result.ratio == pytest.approx(1.0)
    assert result.vetoed_by is None
    assert result.task_id == "TASK-001"


# ---------------------------------------------------------------------------
# Test 2: Mixed votes below threshold -> rework
# ---------------------------------------------------------------------------


def test_consensus_fail_low_ratio(engine: ConsensusEngine) -> None:
    votes = [
        _make_vote("claude", vote="ready", score=92, base_weight=0.40),
        _make_vote("codex", vote="not_ready", score=60, base_weight=0.35),
        _make_vote("gemini", vote="not_ready", score=55, base_weight=0.25),
    ]

    result = engine.compute("TASK-002", votes)

    # Only claude (weight 0.40) voted ready out of total 1.0 -> ratio = 0.40 < 0.9
    assert result.can_proceed is False
    assert result.action == "rework"
    assert result.ratio == pytest.approx(0.40)
    assert result.vetoed_by is None


# ---------------------------------------------------------------------------
# Test 3: One agent vetoes -> immediate rework, vetoed_by set
# ---------------------------------------------------------------------------


def test_consensus_veto(engine: ConsensusEngine) -> None:
    votes = [
        _make_vote("claude", vote="ready", score=95, base_weight=0.40),
        _make_vote("codex", vote="ready", score=93, base_weight=0.35),
        _make_vote("gemini", vote="veto", score=30, base_weight=0.25),
    ]

    result = engine.compute("TASK-003", votes)

    assert result.can_proceed is False
    assert result.action == "rework"
    assert result.vetoed_by == "gemini"
    # Veto is caught before ratio computation, so ratio stays at 0.0
    assert result.ratio == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test 4: Scores differ by >20pts -> dispersion_warning=True
# ---------------------------------------------------------------------------


def test_consensus_dispersion_warning(engine: ConsensusEngine) -> None:
    votes = [
        _make_vote("claude", vote="ready", score=95, base_weight=0.40),
        _make_vote("codex", vote="ready", score=92, base_weight=0.35),
        # 95 - 70 = 25 > 20 -> dispersion warning
        _make_vote("gemini", vote="not_ready", score=70, base_weight=0.25),
    ]

    result = engine.compute("TASK-004", votes)

    assert result.dispersion_warning is True


def test_consensus_no_dispersion_warning(engine: ConsensusEngine) -> None:
    """Scores within 20 pts should not trigger the warning."""
    votes = [
        _make_vote("claude", vote="ready", score=95, base_weight=0.40),
        _make_vote("codex", vote="ready", score=90, base_weight=0.35),
        _make_vote("gemini", vote="ready", score=82, base_weight=0.25),
    ]

    result = engine.compute("TASK-004b", votes)

    # 95 - 82 = 13 which is <= 20
    assert result.dispersion_warning is False


# ---------------------------------------------------------------------------
# Test 5: re_review_count > max_rereviews -> escalate
# ---------------------------------------------------------------------------


def test_consensus_escalation(engine: ConsensusEngine, all_ready_votes: list[AgentVote]) -> None:
    # engine.max_rereviews is 2; passing re_review_count=2 triggers escalation
    result = engine.compute("TASK-005", all_ready_votes, re_review_count=2)

    assert result.action == "escalate"
    assert result.can_proceed is False
    # Escalation is checked before ratio threshold, so re_review_count is preserved
    assert result.re_review_count == 2


# ---------------------------------------------------------------------------
# Test 6: No votes -> rework with ratio 0
# ---------------------------------------------------------------------------


def test_consensus_empty_votes(engine: ConsensusEngine) -> None:
    result = engine.compute("TASK-006", [])

    assert result.can_proceed is False
    assert result.action == "rework"
    assert result.ratio == pytest.approx(0.0)
    assert result.details == []


# ---------------------------------------------------------------------------
# Test 7: effective_weight = base_weight * reliability * confidence
# ---------------------------------------------------------------------------


def test_effective_weight_calculation() -> None:
    vote = AgentVote(
        agent_id="claude",
        score=90,
        vote="ready",
        confidence=0.8,
        base_weight=0.40,
        reliability=0.9,
    )

    expected = 0.40 * 0.9 * 0.8  # 0.288
    assert vote.effective_weight == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Test 8: build_votes_from_reports constructs AgentVote list correctly
# ---------------------------------------------------------------------------


def test_build_votes_from_reports(engine: ConsensusEngine) -> None:
    reports = {
        "claude": {"score": 95, "vote": "ready", "confidence": 1.0},
        "codex": {"score": 88, "vote": "ready", "confidence": 0.9},
        "gemini": {"score": 72, "vote": "not_ready", "confidence": 0.85},
    }

    votes = engine.build_votes_from_reports(reports, AGENTS_CONFIG)

    assert len(votes) == 3

    claude_vote = next(v for v in votes if v.agent_id == "claude")
    assert claude_vote.score == 95
    assert claude_vote.vote == "ready"
    assert claude_vote.confidence == pytest.approx(1.0)
    assert claude_vote.base_weight == pytest.approx(0.40)
    assert claude_vote.reliability == pytest.approx(1.0)

    gemini_vote = next(v for v in votes if v.agent_id == "gemini")
    assert gemini_vote.vote == "not_ready"


def test_build_votes_from_reports_unknown_agent_skipped(engine: ConsensusEngine) -> None:
    """Reports from unknown agents should be silently skipped."""
    reports = {
        "unknown_agent": {"score": 90, "vote": "ready", "confidence": 1.0},
        "claude": {"score": 95, "vote": "ready", "confidence": 1.0},
    }

    votes = engine.build_votes_from_reports(reports, AGENTS_CONFIG)

    assert len(votes) == 1
    assert votes[0].agent_id == "claude"


# ---------------------------------------------------------------------------
# Test 9: ConsensusResult.to_dict serialization round-trip
# ---------------------------------------------------------------------------


def test_consensus_result_to_dict(engine: ConsensusEngine, all_ready_votes: list[AgentVote]) -> None:
    result = engine.compute("TASK-009", all_ready_votes)
    d = result.to_dict()

    assert d["task_id"] == "TASK-009"
    assert d["can_proceed"] is True
    assert d["action"] == "proceed"
    assert isinstance(d["ratio"], float)
    assert isinstance(d["details"], list)
    assert len(d["details"]) == 3
    assert isinstance(d["computed_at"], str)
    # Optional keys should be absent when not set
    assert "vetoed_by" not in d
    assert "dispersion_warning" not in d


def test_consensus_result_to_dict_includes_optional_fields() -> None:
    """to_dict must include vetoed_by and dispersion_warning when set."""
    result = ConsensusResult(
        task_id="TASK-009b",
        can_proceed=False,
        ratio=0.0,
        action="rework",
        details=[],
        re_review_count=0,
        computed_at="2026-03-14T00:00:00+00:00",
        vetoed_by="gemini",
        dispersion_warning=True,
    )

    d = result.to_dict()

    assert d["vetoed_by"] == "gemini"
    assert d["dispersion_warning"] is True


# ---------------------------------------------------------------------------
# Test 10: Degraded mode - only 2 of 3 agents report, still computes
# ---------------------------------------------------------------------------


def test_consensus_degraded_mode(engine: ConsensusEngine) -> None:
    """Consensus should still work when only a subset of agents vote."""
    votes = [
        _make_vote("claude", vote="ready", score=94, base_weight=0.40),
        _make_vote("codex", vote="ready", score=91, base_weight=0.35),
        # gemini is absent
    ]

    result = engine.compute("TASK-010", votes)

    # total weight = 0.75, ready weight = 0.75 -> ratio = 1.0 >= 0.9
    assert result.can_proceed is True
    assert result.action == "proceed"
    assert result.ratio == pytest.approx(1.0)
    assert len(result.details) == 2
