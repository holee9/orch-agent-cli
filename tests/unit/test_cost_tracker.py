"""Unit tests for scripts/cost_tracker.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.cost_tracker import CostTracker


def test_record_creates_entry(tmp_path: Path) -> None:
    """First record call for an agent should create a new dict entry."""
    tracker = CostTracker(tmp_path / "costs.json")

    tracker.record("claude", tokens_in=500, tokens_out=200)

    summary = tracker.get_summary("claude")
    assert summary["tokens_in"] == 500
    assert summary["tokens_out"] == 200
    assert summary["call_count"] == 1
    assert summary["estimated_cost_usd"] > 0.0


def test_record_accumulates(tmp_path: Path) -> None:
    """Second record for the same agent should add to existing totals."""
    tracker = CostTracker(tmp_path / "costs.json")

    tracker.record("claude", tokens_in=1000, tokens_out=500)
    tracker.record("claude", tokens_in=200, tokens_out=100)

    summary = tracker.get_summary("claude")
    assert summary["tokens_in"] == 1200
    assert summary["tokens_out"] == 600
    assert summary["call_count"] == 2


def test_get_summary_all(tmp_path: Path) -> None:
    """get_summary() with no agent_id should return totals across all agents."""
    tracker = CostTracker(tmp_path / "costs.json")

    tracker.record("claude", tokens_in=1000, tokens_out=500)
    tracker.record("codex", tokens_in=800, tokens_out=300)

    summary = tracker.get_summary()
    assert summary["tokens_in"] == 1800
    assert summary["tokens_out"] == 800
    assert summary["call_count"] == 2
    assert summary["estimated_cost_usd"] > 0.0


def test_get_summary_agent(tmp_path: Path) -> None:
    """get_summary('claude') should return only claude's data."""
    tracker = CostTracker(tmp_path / "costs.json")

    tracker.record("claude", tokens_in=1000, tokens_out=500)
    tracker.record("codex", tokens_in=9999, tokens_out=9999)

    summary = tracker.get_summary("claude")
    assert summary["tokens_in"] == 1000
    assert summary["tokens_out"] == 500
    assert summary["call_count"] == 1


def test_estimate_cost(tmp_path: Path) -> None:
    """_estimate_cost(1000, 500, 'unknown') should equal $0.003 + $0.0075 = $0.0105."""
    tracker = CostTracker(tmp_path / "costs.json")

    cost = tracker._estimate_cost(1000, 500, "unknown")

    assert cost == pytest.approx(0.003 + 0.0075)
