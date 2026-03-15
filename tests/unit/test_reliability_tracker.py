"""Unit tests for scripts/reliability_tracker.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.reliability_tracker import ReliabilityTracker

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_update_success_increases_score(tmp_path: Path) -> None:
    """A 'success' outcome should increase the agent score by SCORE_DELTA['success']."""
    path = tmp_path / "reliability.json"
    tracker = ReliabilityTracker(path)

    # Seed a known starting score
    tracker.save(
        {
            "agents": {"claude": {"score": 0.8, "history": [], "total_tasks": 5}},
            "last_updated": "2026-01-01T00:00:00+00:00",
        }
    )

    new_score = tracker.update("claude", "success")

    assert new_score == pytest.approx(0.8 + ReliabilityTracker.SCORE_DELTA["success"])


def test_update_failure_decreases_score(tmp_path: Path) -> None:
    """A 'failure' outcome should decrease the agent score by |SCORE_DELTA['failure']|."""
    path = tmp_path / "reliability.json"
    tracker = ReliabilityTracker(path)

    tracker.save(
        {
            "agents": {"codex": {"score": 0.6, "history": [], "total_tasks": 3}},
            "last_updated": "2026-01-01T00:00:00+00:00",
        }
    )

    new_score = tracker.update("codex", "failure")

    assert new_score == pytest.approx(0.6 + ReliabilityTracker.SCORE_DELTA["failure"])


def test_score_clamped_to_min_max(tmp_path: Path) -> None:
    """Scores must never exceed SCORE_MAX or drop below SCORE_MIN."""
    path = tmp_path / "reliability.json"
    tracker = ReliabilityTracker(path)

    # Test lower clamp: score near min with a timeout penalty
    tracker.save(
        {
            "agents": {"gemini": {"score": 0.1, "history": [], "total_tasks": 0}},
            "last_updated": "2026-01-01T00:00:00+00:00",
        }
    )
    low_score = tracker.update("gemini", "timeout")
    assert low_score >= ReliabilityTracker.SCORE_MIN

    # Test upper clamp: score at max with a success bonus
    tracker.save(
        {
            "agents": {"gemini": {"score": 1.0, "history": [], "total_tasks": 0}},
            "last_updated": "2026-01-01T00:00:00+00:00",
        }
    )
    high_score = tracker.update("gemini", "success")
    assert high_score <= ReliabilityTracker.SCORE_MAX


def test_record_deployment_success(tmp_path: Path) -> None:
    """record_deployment(success=True) should increase score by 0.03."""
    path = tmp_path / "reliability.json"
    tracker = ReliabilityTracker(path)

    tracker.save(
        {
            "agents": {"claude": {"score": 0.7, "history": [], "total_tasks": 2}},
            "last_updated": "2026-01-01T00:00:00+00:00",
        }
    )

    new_score = tracker.record_deployment("claude", success=True)

    assert new_score == pytest.approx(0.7 + 0.03)


def test_record_deployment_failure(tmp_path: Path) -> None:
    """record_deployment(success=False) should decrease score by 0.20."""
    path = tmp_path / "reliability.json"
    tracker = ReliabilityTracker(path)

    tracker.save(
        {
            "agents": {"codex": {"score": 0.8, "history": [], "total_tasks": 3}},
            "last_updated": "2026-01-01T00:00:00+00:00",
        }
    )

    new_score = tracker.record_deployment("codex", success=False)

    assert new_score == pytest.approx(0.8 - 0.20)


def test_record_deployment_clamp_min(tmp_path: Path) -> None:
    """record_deployment failure must never push score below SCORE_MIN (0.1)."""
    path = tmp_path / "reliability.json"
    tracker = ReliabilityTracker(path)

    tracker.save(
        {
            "agents": {"gemini": {"score": 0.15, "history": [], "total_tasks": 1}},
            "last_updated": "2026-01-01T00:00:00+00:00",
        }
    )

    new_score = tracker.record_deployment("gemini", success=False)

    assert new_score >= ReliabilityTracker.SCORE_MIN


def test_persistence_load_save(tmp_path: Path) -> None:
    """Scores written by update() must be readable by a fresh tracker instance."""
    path = tmp_path / "reliability.json"
    tracker = ReliabilityTracker(path)

    tracker.update("claude", "success")
    tracker.update("claude", "success")

    # Re-instantiate to verify persistence
    tracker2 = ReliabilityTracker(path)
    score = tracker2.get_score("claude")

    expected = min(
        ReliabilityTracker.SCORE_MAX,
        1.0 + 2 * ReliabilityTracker.SCORE_DELTA["success"],
    )
    assert score == pytest.approx(expected)

    # History must contain two entries
    data = tracker2.load()
    assert len(data["agents"]["claude"]["history"]) == 2
    assert data["agents"]["claude"]["total_tasks"] == 2
