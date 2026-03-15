"""Unit tests for scripts/report_generator.py ReportGenerator class."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from scripts.report_generator import ReportGenerator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def minimal_config(tmp_path: Path) -> Path:
    """Write a minimal config.yaml and return its path."""
    config = tmp_path / "config.yaml"
    config.write_text(
        "orchestrator:\n"
        "  orchestra_dir: .orchestra\n"
        "consensus:\n"
        "  threshold: 0.9\n"
        "  score_ready_min: 90\n"
        "  dispersion_alert_threshold: 20\n"
        "  max_rereviews: 2\n",
        encoding="utf-8",
    )
    return config


@pytest.fixture()
def minimal_agents(tmp_path: Path) -> Path:
    """Write a minimal agents.json and return its path."""
    agents_file = tmp_path / "agents.json"
    agents_file.write_text(
        json.dumps({
            "agents": [
                {"id": "agent-claude", "role": "architect", "primary_stages": ["review", "release"]},  # noqa: E501
                {"id": "agent-codex", "role": "implementer", "primary_stages": ["implementation"]},
            ]
        }),
        encoding="utf-8",
    )
    return agents_file


@pytest.fixture()
def generator(tmp_path: Path, minimal_config: Path, minimal_agents: Path) -> ReportGenerator:
    """Return a ReportGenerator wired to tmp_path as its orchestra root."""
    gen = ReportGenerator(config_path=minimal_config, agents_path=minimal_agents)
    # Override orchestra dir to point into tmp_path
    gen._orchestra_dir = tmp_path / ".orchestra"
    return gen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_consensus(orchestra_dir: Path, spec_id: str, data: dict) -> None:
    consensus_dir = orchestra_dir / "consensus"
    consensus_dir.mkdir(parents=True, exist_ok=True)
    (consensus_dir / f"{spec_id}.json").write_text(json.dumps(data), encoding="utf-8")


def _write_readiness(orchestra_dir: Path, spec_id: str, data: dict) -> None:
    reports_dir = orchestra_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{spec_id}-readiness.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateCreatesReportFile:
    """test_generate_creates_report_file: report file is created at correct path."""

    def test_file_is_created(self, generator: ReportGenerator, tmp_path: Path) -> None:
        spec_id = "SPEC-001"
        orchestra_dir = tmp_path / ".orchestra"

        _write_consensus(orchestra_dir, spec_id, {
            "task_id": spec_id,
            "can_proceed": True,
            "ratio": 0.95,
            "action": "proceed",
            "details": [],
            "re_review_count": 0,
            "computed_at": "2026-01-01T00:00:00+00:00",
        })
        _write_readiness(orchestra_dir, spec_id, {
            "test_coverage": 0.90,
            "security_scan_passed": True,
            "release_notes_ready": True,
        })

        report_path = generator.generate(spec_id)

        assert report_path.exists(), "Report file should be created"
        assert report_path.name == f"{spec_id}-final-report.md"
        content = report_path.read_text(encoding="utf-8")
        assert spec_id in content
        assert "Final Report" in content

    def test_return_value_is_path(self, generator: ReportGenerator, tmp_path: Path) -> None:
        spec_id = "SPEC-002"
        report_path = generator.generate(spec_id)
        assert isinstance(report_path, Path)


class TestGenerateWithMissingReadinessFile:
    """test_generate_with_missing_readiness_file: no raise when readiness JSON absent."""

    def test_does_not_raise(self, generator: ReportGenerator) -> None:
        spec_id = "SPEC-003"
        # Deliberately do NOT write readiness file
        report_path = generator.generate(spec_id)
        assert report_path.exists()

    def test_logs_warning(
        self, generator: ReportGenerator, caplog: pytest.LogCaptureFixture
    ) -> None:
        spec_id = "SPEC-004"
        with caplog.at_level(logging.WARNING, logger="scripts.report_generator"):
            generator.generate(spec_id)
        assert any("readiness" in msg.lower() or "Readiness" in msg for msg in caplog.messages), (
            "Expected a warning about missing readiness file"
        )

    def test_report_contains_na_for_missing_data(
        self, generator: ReportGenerator
    ) -> None:
        spec_id = "SPEC-005"
        report_path = generator.generate(spec_id)
        content = report_path.read_text(encoding="utf-8")
        assert "N/A" in content


class TestFormatMarkdownContainsSections:
    """test_format_markdown_contains_sections: all five report sections present."""

    def test_all_sections_present(self, generator: ReportGenerator) -> None:
        data = {
            "spec_id": "SPEC-TEST",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "agents": [
                {"id": "agent-a", "role": "reviewer", "primary_stages": ["review"]},
            ],
            "consensus": {
                "task_id": "SPEC-TEST",
                "can_proceed": True,
                "ratio": 0.95,
                "action": "proceed",
                "details": [
                    {
                        "agent_id": "agent-a",
                        "score": 95,
                        "vote": "ready",
                        "confidence": 0.9,
                        "effective_weight": 0.297,
                    }
                ],
                "re_review_count": 0,
                "computed_at": "2026-01-01T00:00:00+00:00",
            },
            "release_readiness": {
                "test_coverage": 0.88,
                "security_scan_passed": True,
                "release_notes_ready": True,
            },
        }

        md = generator._format_markdown(data)

        assert "## 1. Executive Summary" in md
        assert "## 2. Agent Contributions" in md
        assert "## 3. Consensus Result" in md
        assert "## 4. Release Readiness" in md
        assert "## 5. Recommendations" in md

    def test_executive_summary_contains_spec_id(self, generator: ReportGenerator) -> None:
        data = {
            "spec_id": "MY-SPEC-99",
            "agents": [],
            "consensus": None,
            "release_readiness": None,
        }
        md = generator._format_markdown(data)
        assert "MY-SPEC-99" in md

    def test_recommendations_all_pass(self, generator: ReportGenerator) -> None:
        data = {
            "spec_id": "SPEC-OK",
            "agents": [],
            "consensus": {
                "can_proceed": True,
                "action": "proceed",
                "ratio": 1.0,
                "re_review_count": 0,
                "details": [],
            },
            "release_readiness": {
                "test_coverage": 0.90,
                "security_scan_passed": True,
                "release_notes_ready": True,
            },
        }
        md = generator._format_markdown(data)
        assert "No action required" in md

    def test_veto_shown_in_consensus(self, generator: ReportGenerator) -> None:
        data = {
            "spec_id": "SPEC-VETO",
            "agents": [],
            "consensus": {
                "can_proceed": False,
                "action": "rework",
                "ratio": 0.0,
                "re_review_count": 0,
                "details": [],
                "vetoed_by": "agent-gemini",
            },
            "release_readiness": None,
        }
        md = generator._format_markdown(data)
        assert "agent-gemini" in md
        assert "Vetoed by" in md
