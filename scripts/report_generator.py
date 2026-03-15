"""Final Report generator for orch-agent-cli.

Generates Korean-language final reports summarizing the orchestration session,
including all task results, consensus outcomes, and agent contributions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import NotRequired, TypedDict

logger = logging.getLogger(__name__)


class ReportData(TypedDict):
    """Expected shape for data passed to generate_report_markdown().

    Two accepted forms:
    - Form A (orchestrator mode): includes 'consensus_results', 'reports', 'completions'
      as produced by collect_session_data().
    - Form B (simple mode): includes 'issues' as a flat list of issue dicts.
    Both forms require 'session_id'.
    """
    session_id: str
    target_repo: NotRequired[str]
    completed_issues: NotRequired[list[dict]]
    consensus_results: NotRequired[list[dict]]
    reports: NotRequired[dict[str, dict]]
    issues: NotRequired[list[dict]]
    duration_seconds: NotRequired[float]
    agent_stats: NotRequired[dict]


def collect_session_data(
    session_id: str,
    state_base_dir: str | Path,
) -> dict:
    """Aggregate all results for a session from .orchestra/ state.

    Collects consensus results, reports, and completion signals.
    """
    base = Path(state_base_dir)

    data: dict = {
        "session_id": session_id,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "consensus_results": [],
        "reports": {},
        "completions": [],
    }

    # Collect consensus results
    consensus_dir = base / "consensus"
    if consensus_dir.exists():
        for f in sorted(consensus_dir.glob("*.json")):
            try:
                with open(f) as fh:
                    data["consensus_results"].append(json.load(fh))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read consensus file %s: %s", f, e)

    # Collect reports
    reports_dir = base / "reports"
    if reports_dir.exists():
        for f in sorted(reports_dir.glob("*.json")):
            try:
                with open(f) as fh:
                    report = json.load(fh)
                    task_id = report.get("task_id", f.stem.split(".")[0])
                    agent_id = report.get("agent_id", f.stem.split(".")[-1])
                    data["reports"].setdefault(task_id, {})[agent_id] = report
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read report file %s: %s", f, e)

    # Collect completions
    completed_dir = base / "state" / "completed"
    if completed_dir.exists():
        for f in sorted(completed_dir.glob("*.json")):
            try:
                with open(f) as fh:
                    data["completions"].append(json.load(fh))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read completion file %s: %s", f, e)

    return data


def generate_report_markdown(session_data: ReportData | dict) -> str:
    """Generate a Korean-language final report in Markdown format.

    Accepts two data shapes (backward compatible):
    - Form A (orchestrator mode): dict from collect_session_data() containing
      'consensus_results' (list), 'reports' (dict), and 'completions' (list).
    - Form B (simple mode): dict with 'session_id' and 'issues' (list of issue dicts).

    Args:
        session_data: Either a ReportData-shaped dict from collect_session_data(),
                      or a simple dict with 'session_id' and 'issues' keys.

    Returns:
        Markdown string for the final report.
    """
    session_id = session_data.get("session_id", "unknown")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# 최종 보고서: {session_id}",
        "",
        f"**생성일시:** {now}",
        "",
        "---",
        "",
    ]

    # Summary section
    lines.extend([
        "## 요약",
        "",
    ])

    # --- Form A (orchestrator mode): consensus_results / reports present ---
    # --- Form B (simple mode):       issues list present ---
    # Both forms may coexist; sections are rendered when their keys are present.

    # If we have consensus results
    consensus_results = session_data.get("consensus_results", [])
    if consensus_results:
        passed = sum(1 for c in consensus_results if c.get("can_proceed"))
        failed = sum(1 for c in consensus_results if not c.get("can_proceed"))
        lines.extend([
            f"- **합의 통과:** {passed}건",
            f"- **합의 실패:** {failed}건",
            "",
        ])

    # If we have issues (simple mode from orchestrator)
    issues = session_data.get("issues", [])
    if issues:
        lines.extend([
            f"- **총 이슈:** {len(issues)}건",
            "",
        ])

    # Consensus details
    if consensus_results:
        lines.extend([
            "## 합의 결과",
            "",
            "| 태스크 | 결과 | 비율 | 조치 |",
            "|--------|------|------|------|",
        ])
        for result in consensus_results:
            task_id = result.get("task_id", "?")
            can_proceed = "통과" if result.get("can_proceed") else "실패"
            ratio = f"{result.get('ratio', 0):.1%}"
            action_map = {"proceed": "진행", "rework": "재작업", "escalate": "에스컬레이션"}
            action = action_map.get(result.get("action", ""), result.get("action", "?"))
            lines.append(f"| {task_id} | {can_proceed} | {ratio} | {action} |")
        lines.append("")

    # Agent reports
    reports = session_data.get("reports", {})
    if reports:
        lines.extend([
            "## 에이전트 리포트",
            "",
        ])
        for task_id, agent_reports in reports.items():
            lines.append(f"### {task_id}")
            lines.append("")
            lines.append("| 에이전트 | 점수 | 투표 | 신뢰도 |")
            lines.append("|----------|------|------|--------|")
            for agent_id, report in agent_reports.items():
                score = report.get("score", "?")
                vote_map = {"ready": "준비", "not_ready": "미준비", "veto": "거부"}
                vote = vote_map.get(report.get("vote", ""), report.get("vote", "?"))
                confidence = f"{report.get('confidence', 0):.0%}"
                lines.append(f"| {agent_id} | {score} | {vote} | {confidence} |")
            lines.append("")

    # Issue list
    if issues:
        lines.extend([
            "## 이슈 목록",
            "",
            "| # | 제목 | 상태 | 라벨 |",
            "|---|------|------|------|",
        ])
        for issue in issues:
            num = issue.get("number", "?")
            title = issue.get("title", "?")
            state = issue.get("state", "?")
            labels = ", ".join(issue.get("labels", []))
            lines.append(f"| #{num} | {title} | {state} | {labels} |")
        lines.append("")

    lines.extend([
        "---",
        "",
        "*이 보고서는 orch-agent-cli 오케스트레이터에 의해 자동 생성되었습니다.*",
    ])

    return "\n".join(lines)


class ReportGenerator:
    """Generates Markdown final reports from completed workflow data in .orchestra/."""

    def __init__(self, config_path: Path, agents_path: Path) -> None:
        """Initialize with paths to config and agent registry files.

        Args:
            config_path: Path to config YAML file.
            agents_path: Path to agents.json registry.
        """
        self._config_path = Path(config_path)
        self._agents_path = Path(agents_path)
        self._config = self._load_config()
        self._agents = self._load_agents()

        target_path = self._config.get("orchestrator", {}).get("target_project_path", "")
        orchestra_subdir = self._config.get("orchestrator", {}).get("orchestra_dir", ".orchestra")
        if target_path:
            self._orchestra_dir = Path(target_path) / orchestra_subdir
        else:
            self._orchestra_dir = Path(orchestra_subdir)

    def generate(self, spec_id: str) -> Path:
        """Collect workflow data and write a Markdown final report.

        Args:
            spec_id: Identifier for the spec/session (e.g. "SPEC-001").

        Returns:
            Path to the written report file.
        """
        data = self._collect_workflow_data(spec_id)
        markdown = self._format_markdown(data)

        reports_dir = self._orchestra_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"{spec_id}-final-report.md"
        report_path.write_text(markdown, encoding="utf-8")
        logger.info("Final report written: %s", report_path)
        return report_path

    def _load_config(self) -> dict:
        if not self._config_path.exists():
            logger.warning("Config not found: %s — using defaults", self._config_path)
            return {}
        import yaml
        with open(self._config_path) as f:
            return yaml.safe_load(f) or {}

    def _load_agents(self) -> list[dict]:
        if not self._agents_path.exists():
            logger.warning("Agents registry not found: %s — using empty list", self._agents_path)
            return []
        with open(self._agents_path) as f:
            data = json.load(f)
        return data.get("agents", [])

    def _collect_workflow_data(self, spec_id: str) -> dict:
        """Collect all available workflow artefacts for spec_id from .orchestra/.

        Args:
            spec_id: The spec/session identifier.

        Returns:
            Dictionary with keys: spec_id, timestamp, agents, consensus, release_readiness.
        """
        data: dict = {
            "spec_id": spec_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents": self._agents,
            "consensus": None,
            "release_readiness": None,
        }

        consensus_path = self._orchestra_dir / "consensus" / f"{spec_id}.json"
        if consensus_path.exists():
            try:
                with open(consensus_path) as f:
                    data["consensus"] = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read consensus file %s: %s", consensus_path, e)
        else:
            logger.warning("Consensus file not found: %s", consensus_path)

        readiness_path = self._orchestra_dir / "reports" / f"{spec_id}-readiness.json"
        if readiness_path.exists():
            try:
                with open(readiness_path) as f:
                    data["release_readiness"] = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read readiness file %s: %s", readiness_path, e)
        else:
            logger.warning("Readiness file not found: %s — using defaults", readiness_path)

        return data

    def _format_markdown(self, data: dict) -> str:
        """Render collected workflow data as a Markdown report.

        Args:
            data: Dict with keys spec_id, timestamp, agents, consensus, release_readiness.

        Returns:
            Markdown string for the final report.
        """
        spec_id = data.get("spec_id", "unknown")
        timestamp = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        consensus = data.get("consensus") or {}
        readiness = data.get("release_readiness") or {}
        agents: list[dict] = data.get("agents") or []

        final_decision = consensus.get("action", "N/A")
        can_proceed = consensus.get("can_proceed", False)

        lines: list[str] = []

        # 1. Executive Summary
        lines += [
            "# Final Report",
            "",
            "## 1. Executive Summary",
            "",
            "| Field | Value |",
            "| ----- | ----- |",
            f"| Spec ID | `{spec_id}` |",
            f"| Timestamp | {timestamp} |",
            f"| Final Decision | **{final_decision.upper()}** |",
            f"| Can Proceed | {'Yes' if can_proceed else 'No'} |",
            "",
        ]

        # 2. Agent Contributions
        lines += ["## 2. Agent Contributions", ""]
        if agents:
            lines += ["| Agent ID | Role | Primary Stages |", "| -------- | ---- | -------------- |"]  # noqa: E501
            for agent in agents:
                agent_id = agent.get("id", "unknown")
                role = agent.get("role", "—")
                primary = ", ".join(agent.get("primary_stages", []))
                lines.append(f"| {agent_id} | {role} | {primary} |")
        else:
            lines.append("_No agent data available._")
        lines.append("")

        # 3. Consensus Result
        lines += ["## 3. Consensus Result", ""]
        if consensus:
            ratio = consensus.get("ratio", 0.0)
            re_review = consensus.get("re_review_count", 0)
            vetoed_by = consensus.get("vetoed_by")
            dispersion = consensus.get("dispersion_warning", False)

            lines += [
                f"- **Action:** {final_decision}",
                f"- **Ratio:** {ratio:.2%}",
                f"- **Re-review count:** {re_review}",
            ]
            if vetoed_by:
                lines.append(f"- **Vetoed by:** {vetoed_by}")
            if dispersion:
                lines.append("- **Dispersion warning:** Yes — scores diverged significantly")

            details: list[dict] = consensus.get("details", [])
            if details:
                lines += [
                    "",
                    "### Agent Votes",
                    "",
                    "| Agent | Score | Vote | Confidence | Effective Weight |",
                    "| ----- | ----- | ---- | ---------- | ---------------- |",
                ]
                for d in details:
                    lines.append(
                        f"| {d.get('agent_id')} | {d.get('score')} | {d.get('vote')} "
                        f"| {d.get('confidence')} | {d.get('effective_weight')} |"
                    )
        else:
            lines.append("_No consensus data available._")
        lines.append("")

        # 4. Release Readiness
        lines += ["## 4. Release Readiness", ""]
        test_coverage = readiness.get("test_coverage", "N/A")
        security_passed = readiness.get("security_scan_passed", False)
        release_notes = readiness.get("release_notes_ready", False)
        lines += [
            f"- **Test Coverage:** {test_coverage}",
            f"- **Security Scan Passed:** {'Yes' if security_passed else 'No'}",
            f"- **Release Notes Ready:** {'Yes' if release_notes else 'No'}",
            "",
        ]

        # 5. Recommendations
        lines += ["## 5. Recommendations", ""]
        recommendations: list[str] = []

        if not can_proceed:
            if final_decision == "escalate":
                recommendations.append(
                    "Human review is required — consensus could not be reached after maximum re-reviews."  # noqa: E501
                )
            else:
                recommendations.append(
                    "Address rework items identified by agents before proceeding."
                )

        if readiness:
            if not readiness.get("security_scan_passed", True):
                recommendations.append("Run security scan and resolve all findings before release.")
            if not readiness.get("release_notes_ready", True):
                recommendations.append("Prepare release notes before publishing.")
            cov = readiness.get("test_coverage")
            if isinstance(cov, (int, float)) and cov < 0.85:
                recommendations.append(
                    f"Increase test coverage to >= 85% (current: {cov:.0%})."
                )

        if consensus.get("dispersion_warning"):
            recommendations.append(
                "Investigate score dispersion — agents disagree significantly on quality."
            )

        if recommendations:
            for rec in recommendations:
                lines.append(f"- {rec}")
        else:
            lines.append("_No action required — all quality gates passed._")
        lines.append("")

        return "\n".join(lines)


def create_final_report_issue(
    session_id: str,
    markdown: str,
    github_client,
    mention_user: str = "",
) -> int:
    """Create a Final Report GitHub Issue.

    Returns the issue number.
    """
    body = markdown
    if mention_user:
        body += f"\n\ncc {mention_user}"

    issue_number = github_client.create_issue(
        title=f"[Final Report] {session_id}",
        body=body,
        labels=["type:report", "status:done"],
    )
    logger.info("Created Final Report Issue #%d for %s", issue_number, session_id)
    return issue_number
