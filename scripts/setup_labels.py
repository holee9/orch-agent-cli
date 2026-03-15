"""GitHub label bootstrap for orch-agent-cli.

Creates all required labels for the multi-AI orchestration workflow.
Run once per target repository to set up the label taxonomy.
"""

from __future__ import annotations

import argparse
import logging
import sys

from scripts.github_client import GitHubClient

logger = logging.getLogger(__name__)

# Label taxonomy for the orchestration workflow
LABELS: list[dict[str, str]] = [
    # Routing labels (which agent handles this)
    {"name": "agent:claude", "color": "7B68EE", "description": "Assigned to Claude Code"},
    {"name": "agent:codex", "color": "FF6347", "description": "Assigned to Codex CLI"},
    {"name": "agent:gemini", "color": "4169E1", "description": "Assigned to Gemini CLI"},
    {"name": "agent:orchestrator", "color": "2E8B57", "description": "Handled by orchestrator"},
    # Type labels
    {"name": "type:kickoff", "color": "FBCA04", "description": "Kickoff issue from BRIEF"},
    {"name": "type:spec", "color": "C5DEF5", "description": "SPEC document"},
    {"name": "type:plan", "color": "BFD4F2", "description": "Implementation plan"},
    {"name": "type:implementation", "color": "0E8A16", "description": "Implementation task"},
    {"name": "type:review", "color": "D93F0B", "description": "Code review"},
    {"name": "type:test", "color": "5319E7", "description": "Test task"},
    {"name": "type:release", "color": "006B75", "description": "Release preparation"},
    {"name": "type:report", "color": "1D76DB", "description": "Final report"},
    # Status labels
    {"name": "status:open", "color": "EDEDED", "description": "Open and ready for work"},
    {"name": "status:in-progress", "color": "FEF2C0", "description": "Currently being worked on"},
    {"name": "status:review-needed", "color": "F9D0C4", "description": "Awaiting review"},
    {"name": "status:blocked", "color": "E4E669", "description": "Blocked by dependency"},
    {"name": "status:done", "color": "0E8A16", "description": "Completed"},
    # Stage labels
    {"name": "stage:requirements", "color": "D4C5F9", "description": "Stage 1: Requirements"},
    {"name": "stage:planning", "color": "C2E0C6", "description": "Stage 2: Planning"},
    {"name": "stage:implementation", "color": "FEF2C0", "description": "Stage 3: Implementation"},
    {"name": "stage:review", "color": "F9D0C4", "description": "Stage 4: Review"},
    {"name": "stage:testing", "color": "D4C5F9", "description": "Stage 5: Testing"},
    {"name": "stage:consensus", "color": "C5DEF5", "description": "Stage 6: Consensus"},
    {"name": "stage:release", "color": "BFD4F2", "description": "Stage 7: Release"},
    # Priority labels
    {"name": "priority:critical", "color": "B60205", "description": "Critical priority"},
    {"name": "priority:high", "color": "D93F0B", "description": "High priority"},
    {"name": "priority:medium", "color": "FBCA04", "description": "Medium priority"},
    {"name": "priority:low", "color": "0E8A16", "description": "Low priority"},
    # Special labels
    {"name": "consensus:pass", "color": "0E8A16", "description": "Consensus reached - proceed"},
    {"name": "consensus:fail", "color": "B60205", "description": "Consensus failed - rework"},
    {"name": "consensus:veto", "color": "D93F0B", "description": "Vetoed by security review"},
    {"name": "consensus:escalate", "color": "B60205", "description": "Consensus escalated to human review"},
    {"name": "escalation:human", "color": "B60205", "description": "Requires human intervention"},
    {"name": "status:human-needed", "color": "E11D48", "description": "Human intervention required"},
    {"name": "type:escalation", "color": "E11D48", "description": "Escalation issue requiring human decision"},
]


def setup_labels(repo: str) -> int:
    """Create all orchestration labels in the target repo.

    Returns the number of labels successfully created.
    """
    client = GitHubClient(repo)
    logger.info("Setting up %d labels for %s", len(LABELS), repo)
    client.create_labels(LABELS)
    logger.info("Label setup complete for %s", repo)
    return len(LABELS)


def main() -> None:
    """CLI entry point for label setup."""
    parser = argparse.ArgumentParser(
        description="Bootstrap GitHub labels for orch-agent-cli orchestration"
    )
    parser.add_argument("repo", help="GitHub repository (owner/repo)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        count = setup_labels(args.repo)
        print(f"Successfully set up {count} labels for {args.repo}")
    except Exception as e:
        logger.error("Label setup failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
