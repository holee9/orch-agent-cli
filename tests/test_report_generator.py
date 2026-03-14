"""Tests for scripts/report_generator.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.report_generator import collect_session_data, generate_report_markdown


# ---------------------------------------------------------------------------
# test_generate_report_with_issues
# ---------------------------------------------------------------------------


def test_generate_report_with_issues() -> None:
    """generate_report_markdown produces Korean markdown with an issue list table."""
    session_data = {
        "session_id": "session-42",
        "issues": [
            {"number": 1, "title": "First task", "state": "OPEN", "labels": ["type:kickoff"]},
            {"number": 2, "title": "Second task", "state": "CLOSED", "labels": ["status:done"]},
        ],
    }

    markdown = generate_report_markdown(session_data)

    assert "session-42" in markdown
    assert "## 이슈 목록" in markdown
    assert "First task" in markdown
    assert "Second task" in markdown
    assert "type:kickoff" in markdown
    assert "status:done" in markdown
    assert "#1" in markdown
    assert "#2" in markdown
    # Report must contain Korean summary section
    assert "## 요약" in markdown
    assert "총 이슈" in markdown
    assert "2건" in markdown


# ---------------------------------------------------------------------------
# test_generate_report_with_consensus
# ---------------------------------------------------------------------------


def test_generate_report_with_consensus() -> None:
    """generate_report_markdown includes a consensus results table when present."""
    session_data = {
        "session_id": "session-99",
        "consensus_results": [
            {
                "task_id": "task-001",
                "can_proceed": True,
                "ratio": 0.95,
                "action": "proceed",
            },
            {
                "task_id": "task-002",
                "can_proceed": False,
                "ratio": 0.60,
                "action": "rework",
            },
        ],
    }

    markdown = generate_report_markdown(session_data)

    assert "## 합의 결과" in markdown
    assert "task-001" in markdown
    assert "task-002" in markdown
    # Korean translation of actions
    assert "진행" in markdown
    assert "재작업" in markdown
    # Korean pass/fail labels
    assert "통과" in markdown
    assert "실패" in markdown
    # Ratio formatted as percentage
    assert "95.0%" in markdown
    # Summary counts
    assert "합의 통과" in markdown
    assert "1건" in markdown


# ---------------------------------------------------------------------------
# test_generate_report_with_reports
# ---------------------------------------------------------------------------


def test_generate_report_with_reports() -> None:
    """generate_report_markdown renders an agent report detail table."""
    session_data = {
        "session_id": "session-77",
        "reports": {
            "task-001": {
                "claude": {
                    "agent_id": "claude",
                    "task_id": "task-001",
                    "score": 92,
                    "vote": "ready",
                    "confidence": 0.90,
                },
                "gemini": {
                    "agent_id": "gemini",
                    "task_id": "task-001",
                    "score": 88,
                    "vote": "not_ready",
                    "confidence": 0.75,
                },
            }
        },
    }

    markdown = generate_report_markdown(session_data)

    assert "## 에이전트 리포트" in markdown
    assert "task-001" in markdown
    assert "claude" in markdown
    assert "gemini" in markdown
    # Score values appear in the table
    assert "92" in markdown
    assert "88" in markdown
    # Korean vote labels
    assert "준비" in markdown
    assert "미준비" in markdown
    # Confidence rendered as percentage
    assert "90%" in markdown
    assert "75%" in markdown


# ---------------------------------------------------------------------------
# test_collect_session_data
# ---------------------------------------------------------------------------


def test_collect_session_data(tmp_path: Path) -> None:
    """collect_session_data reads consensus, reports, and completions from disk."""
    # Create the expected .orchestra/ subdirectory layout
    consensus_dir = tmp_path / "consensus"
    consensus_dir.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    completed_dir = tmp_path / "state" / "completed"
    completed_dir.mkdir(parents=True)

    # Write a consensus file
    consensus_payload = {
        "task_id": "task-001",
        "can_proceed": True,
        "ratio": 0.95,
        "action": "proceed",
    }
    (consensus_dir / "task-001.json").write_text(json.dumps(consensus_payload))

    # Write a report file (named task_id.agent_id.json)
    report_payload = {
        "task_id": "task-001",
        "agent_id": "claude",
        "score": 92,
        "vote": "ready",
        "confidence": 0.90,
    }
    (reports_dir / "task-001.claude.json").write_text(json.dumps(report_payload))

    # Write a completion file
    completion_payload = {
        "agent_id": "codex",
        "task_id": "task-001",
        "completed_at": "2026-03-14T10:00:00Z",
        "artifacts": [],
    }
    (completed_dir / "codex-task-001.json").write_text(json.dumps(completion_payload))

    result = collect_session_data("session-001", tmp_path)

    assert result["session_id"] == "session-001"
    assert "collected_at" in result

    # Consensus
    assert len(result["consensus_results"]) == 1
    assert result["consensus_results"][0]["task_id"] == "task-001"
    assert result["consensus_results"][0]["can_proceed"] is True

    # Reports: keyed by task_id -> agent_id
    assert "task-001" in result["reports"]
    assert "claude" in result["reports"]["task-001"]
    assert result["reports"]["task-001"]["claude"]["score"] == 92

    # Completions
    assert len(result["completions"]) == 1
    assert result["completions"][0]["agent_id"] == "codex"
