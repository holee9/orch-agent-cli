"""Final Report generator for orch-agent-cli.

Generates Korean-language final reports summarizing the orchestration session,
including all task results, consensus outcomes, and agent contributions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


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


def generate_report_markdown(session_data: dict) -> str:
    """Generate a Korean-language final report in Markdown format.

    Args:
        session_data: Either from collect_session_data() or a simple dict
                      with 'session_id' and 'issues' keys.
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
