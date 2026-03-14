"""Central orchestrator daemon for orch-agent-cli.

Runs a polling loop that coordinates all agents through GitHub Issues
and local .orchestra/ state management.
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.brief_parser import process_brief, scan_inbox
from scripts.consensus import ConsensusEngine
from scripts.github_client import GitHubClient

# TODO: integrate ReliabilityTracker.update() after each assignment completion
from scripts.reliability_tracker import ReliabilityTracker  # noqa: F401
from scripts.report_generator import generate_report_markdown
from scripts.state_manager import StateManager
from scripts.validate_schema import validate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PID lock file
# ---------------------------------------------------------------------------

# @MX:NOTE: [AUTO] Global PID file path; override in tests via monkeypatch
PID_FILE = Path("/tmp/orchestrator.pid")


# @MX:ANCHOR: [AUTO] Called at daemon startup; must not allow two concurrent instances
# @MX:REASON: [AUTO] Prevents split-brain: two daemons writing conflicting state to .orchestra/
def acquire_pid_lock(pid_file: Path = PID_FILE) -> None:
    """Check/write PID lock. Raises RuntimeError if another instance is running.

    Stale PID files (process no longer alive) are removed automatically.
    """
    if pid_file.exists():
        try:
            existing_pid = int(pid_file.read_text().strip())
        except ValueError:
            pid_file.unlink(missing_ok=True)
        else:
            # Check whether that process is still alive
            try:
                os.kill(existing_pid, 0)
            except ProcessLookupError:
                # Process is gone — stale file, remove it
                pid_file.unlink(missing_ok=True)
            except PermissionError:
                # Process exists but we lack permission to signal it
                raise RuntimeError(
                    f"Orchestrator already running (PID {existing_pid})"
                ) from None
            else:
                raise RuntimeError(
                    f"Orchestrator already running (PID {existing_pid})"
                )

    try:
        fd = os.open(str(pid_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        raise RuntimeError("Orchestrator already running") from None
    else:
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)


def release_pid_lock(pid_file: Path = PID_FILE) -> None:
    """Remove PID file on exit. Safe to call even if the file is absent."""
    pid_file.unlink(missing_ok=True)


class Orchestrator:
    """Central daemon that coordinates multi-AI agent workflow."""

    def __init__(
        self,
        config_path: str | Path = "config/config.yaml",
        agents_path: str | Path | None = None,
    ):
        self.config = self._load_config(config_path)
        self._agents_path = Path(agents_path) if agents_path else Path("config/agents.json")
        self.agents = self.check_agent_availability(self._load_agents())
        self.running = False

        # Initialize components
        repo = os.environ.get("GITHUB_REPO", self.config["github"]["repo"])
        if not repo:
            raise ValueError("GITHUB_REPO not set in environment or config")

        target_path = os.environ.get(
            "TARGET_PROJECT_PATH",
            self.config["orchestrator"]["target_project_path"],
        )

        self.github = GitHubClient(repo)
        orchestra_subdir = self.config["orchestrator"]["orchestra_dir"]
        orchestra_dir = (
            Path(target_path) / orchestra_subdir if target_path else Path(orchestra_subdir)
        )
        self.state = StateManager(orchestra_dir)
        self.consensus_engine = ConsensusEngine(
            threshold=self.config["consensus"]["threshold"],
            score_ready_min=self.config["consensus"]["score_ready_min"],
            dispersion_alert_threshold=self.config["consensus"]["dispersion_alert_threshold"],
            max_rereviews=self.config["consensus"]["max_rereviews"],
        )

        # Resolve paths — prefix with target_path when set
        _base = Path(target_path) if target_path else Path(".")
        self.inbox_dir = _base / self.config["orchestrator"]["inbox_dir"]
        self.archive_dir = _base / self.config["orchestrator"]["brief_archive_dir"]

    def _load_config(self, config_path: str | Path) -> dict:
        """Load main configuration from YAML."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        with open(path) as f:
            return yaml.safe_load(f)

    def _load_agents(self) -> list[dict]:
        """Load agent registry from JSON."""
        path = self._agents_path
        if not path.exists():
            raise FileNotFoundError(f"Agent registry not found: {path}")
        with open(path) as f:
            data = json.load(f)
        return data["agents"]

    # --- CLI availability (D-004) ---

    def _check_cli_available(self, cli: str) -> bool:
        """Check whether a CLI binary is available by running `cli --version`.

        Args:
            cli: The CLI binary name (e.g. "claude", "codex").

        Returns:
            True if the command exits with code 0, False otherwise.
        """
        try:
            result = subprocess.run(
                [cli, "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check_agent_availability(self, agents: list[dict]) -> list[dict]:
        """Check CLI availability for each agent and return updated agent list.

        Each returned dict is a shallow copy of the original with an added
        ``available`` key. The original dicts are NOT mutated.
        Logs a WARNING for every agent whose CLI is unavailable.

        Args:
            agents: List of agent config dicts, each containing at least
                    ``id`` and ``cli`` fields.

        Returns:
            New list of agent dicts with ``available: bool`` added.
        """
        def _check_one(agent: dict) -> dict:
            available = self._check_cli_available(agent.get("cli", ""))
            if not available:
                logger.warning(
                    "Agent '%s' CLI '%s' is unavailable",
                    agent.get("id", ""),
                    agent.get("cli", ""),
                )
            return {**agent, "available": available}

        with ThreadPoolExecutor() as executor:
            return list(executor.map(_check_one, agents))

    def start(self) -> None:
        """Start the orchestrator daemon."""
        acquire_pid_lock(PID_FILE)
        try:
            self.running = True
            signal.signal(signal.SIGINT, self._handle_shutdown)
            signal.signal(signal.SIGTERM, self._handle_shutdown)
            signal.signal(signal.SIGHUP, self._handle_sighup)

            self.state.ensure_directories()
            interval = self.config["github"]["polling_interval_seconds"]

            logger.info("Orchestrator started. Polling every %ds.", interval)
            logger.info("Inbox: %s | Orchestra: %s", self.inbox_dir, self.state.base_dir)

            while self.running:
                try:
                    self.poll_cycle()
                except KeyboardInterrupt:
                    break
                except Exception:
                    logger.exception("Error in poll cycle")

                if self.running:
                    time.sleep(interval)

            logger.info("Orchestrator stopped.")
        finally:
            release_pid_lock(PID_FILE)

    def _handle_shutdown(self, signum: int, _frame: object) -> None:
        """Handle shutdown signals gracefully."""
        logger.info("Received signal %d, shutting down...", signum)
        # PID file released by the finally block in start()
        self.running = False

    def _handle_sighup(self, signum: int, _frame: object) -> None:
        """Handle SIGHUP: reload agents config immediately."""
        logger.info("Received SIGHUP, reloading agents config...")
        self._reload_agents_config(force_log=True)

    def _reload_agents_config(self, force_log: bool = False) -> None:
        """Reload agents.json from disk. Logs when content changed or force_log is True."""
        new_agents = self._load_agents()
        # Strip runtime-only 'available' key before comparing to avoid false positives
        def _strip_runtime(agents: list[dict]) -> list[dict]:
            return [{k: v for k, v in a.items() if k != "available"} for a in agents]
        changed = _strip_runtime(new_agents) != _strip_runtime(self.agents)
        self.agents = self.check_agent_availability(new_agents)
        if force_log or changed:
            msg = "agents config reloaded via SIGHUP" if force_log else "agents config reloaded"
            logger.info(msg)

    def poll_cycle(self) -> dict:
        """Execute one complete polling cycle. Returns a summary dict."""
        self._reload_agents_config()
        summary = {
            "briefs_processed": 0,
            "issues_synced": 0,
            "completions_processed": 0,
            "consensus_triggered": 0,
            "stale_released": 0,
        }

        summary["briefs_processed"] = self.process_inbox()
        summary["issues_synced"] = self.sync_github_issues()
        summary["completions_processed"] = self.process_completions()
        self.check_quality_gates()
        summary["consensus_triggered"] = self.check_consensus_ready()

        # Check for escalation triggers before releasing stale locks
        for trigger in self._check_escalation_triggers():
            self._create_escalation_issue(trigger["reason"], trigger)

        summary["stale_released"] = self.release_stale_locks()
        self.check_session_complete()

        logger.debug("Poll cycle summary: %s", summary)
        return summary

    # --- Phase 1: Inbox Processing ---

    def process_inbox(self) -> int:
        """Scan inbox/ for BRIEF files and create Kickoff Issues."""
        briefs = scan_inbox(self.inbox_dir)
        for brief_path in briefs:
            try:
                issue_num = process_brief(brief_path, self.github, self.archive_dir)
                logger.info("Processed BRIEF -> Issue #%d", issue_num)
                self._create_kickoff_assignment(issue_num)
            except Exception:
                logger.exception("Failed to process BRIEF: %s", brief_path)
        return len(briefs)

    def _create_kickoff_assignment(self, issue_number: int) -> None:
        """Write initial kickoff assignment for the primary kickoff agent."""
        kickoff_agent = self._get_primary_agent("kickoff")
        if not kickoff_agent:
            logger.warning("No primary agent found for kickoff stage")
            return

        task_id = f"TASK-{issue_number:03d}"
        assignment = {
            "agent_id": kickoff_agent,
            "task_id": task_id,
            "stage": "kickoff",
            "action": "analyze",
            "github_issue_number": issue_number,
            "assigned_at": datetime.now(timezone.utc).isoformat(),
            "deadline": None,
            "timeout_minutes": self.config["orchestrator"]["assignment_timeout_minutes"],
            "context": {
                "spec_path": f"docs/specs/SPEC-{issue_number:03d}.md",
                "plan_path": f"docs/plans/PLAN-{issue_number:03d}.md",
                "branch_name": f"feat/{task_id}",
            },
        }
        self.state.write_assignment(kickoff_agent, assignment)
        logger.info(
            "Created kickoff assignment: %s -> %s (Issue #%d)",
            kickoff_agent, task_id, issue_number,
        )
        self._create_task_branch(task_id)

    def _create_task_branch(self, task_id: str) -> None:
        """Create a git branch for the given task in the target project path.

        Branch name: ``feat/<task_id>``.
        Skips with WARNING if the target path is not a git repository.
        Logs WARNING (without raising) for all git errors.

        Args:
            task_id: The task identifier, e.g. "TASK-042".
        """
        target_path_str = self.config["orchestrator"].get("target_project_path", "")
        if not target_path_str:
            logger.warning("_create_task_branch: target_project_path not set, skipping")
            return

        target = Path(target_path_str)
        if not (target / ".git").exists():
            logger.warning(
                "_create_task_branch: %s is not a git repo, skipping branch creation for %s",
                target,
                task_id,
            )
            return

        branch = f"feat/{task_id}"
        try:
            result = subprocess.run(
                ["git", "switch", "-c", branch],
                cwd=target,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                stderr: str = result.stderr
                if "already exists" in stderr:
                    logger.warning(
                        "_create_task_branch: branch %r already exists for %s", branch, task_id
                    )
                else:
                    logger.warning(
                        "_create_task_branch: git switch failed for %s (rc=%d): %s",
                        task_id,
                        result.returncode,
                        stderr.strip(),
                    )
        except Exception:
            logger.warning(
                "_create_task_branch: unexpected error creating branch for %s", task_id
            )

    # --- Phase 2: GitHub Sync ---

    def sync_github_issues(self) -> int:
        """Poll GitHub for issue updates and cache locally."""
        try:
            issues = self.github.list_issues(state="open")
            issue_dicts = [
                {
                    "number": i.number,
                    "title": i.title,
                    "state": i.state,
                    "labels": i.labels,
                }
                for i in issues
            ]
            self.state.cache_issues(issue_dicts)
            return len(issue_dicts)
        except Exception:
            logger.exception("Failed to sync GitHub issues")
            return 0

    # --- Phase 3: Completion Processing ---

    def process_completions(self) -> int:
        """Read completion signals and advance workflow."""
        completions = self.state.read_completions()
        processed = 0
        for completion in completions:
            agent_id = completion.get("agent_id", "")
            task_id = completion.get("task_id", "")
            try:
                next_agent = self._advance_workflow(agent_id, task_id, completion)
                # If next stage uses the same agent, its assignment was already
                # overwritten by _advance_workflow — do NOT clear it again.
                if next_agent != agent_id:
                    self.state.clear_assignment(agent_id)
                self.state.clear_completion(agent_id, task_id)
                processed += 1
            except Exception:
                logger.exception("Failed to process completion: %s/%s", agent_id, task_id)
        return processed

    def _advance_workflow(self, agent_id: str, task_id: str, completion: dict) -> str | None:
        """Determine next stage and create assignment based on completion. Returns next agent id."""
        assignment = self.state.read_assignment(agent_id)
        if not assignment:
            logger.warning("No assignment found for completed %s/%s", agent_id, task_id)
            return

        if completion.get("status") == "error":
            logger.warning(
                "Agent %s reported error for task %s, not advancing workflow",
                agent_id, task_id,
            )
            return

        current_stage = assignment.get("stage", "")
        next_stage = self._get_next_stage(current_stage)

        if next_stage:
            next_agent = (
                self._get_primary_agent(next_stage) or self._get_secondary_agent(next_stage)
            )
            if next_agent:
                self.state.write_assignment(next_agent, {
                    "agent_id": next_agent,
                    "task_id": task_id,
                    "stage": next_stage,
                    "github_issue_number": assignment.get("github_issue_number", 0),
                    "assigned_at": completion.get("completed_at", ""),
                    "timeout_minutes": self.config["orchestrator"]["assignment_timeout_minutes"],
                    "context": {
                        "spec_path": assignment.get("context", {}).get("spec_path", ""),
                        "plan_path": assignment.get("context", {}).get("plan_path", ""),
                        "branch_name": f"feat/{task_id}",
                    },
                })
                logger.info(
                    "Advanced %s: %s -> %s (agent: %s)",
                    task_id, current_stage, next_stage, next_agent,
                )
                return next_agent
        return None

    def _get_next_stage(self, current: str) -> str | None:
        """Get the next stage in the workflow."""
        stages = [
            "kickoff", "requirements", "planning", "implementation",
            "review", "testing", "consensus", "release", "final-report",
        ]
        try:
            idx = stages.index(current)
            return stages[idx + 1] if idx + 1 < len(stages) else None
        except ValueError:
            return None

    def _get_primary_agent(self, stage: str) -> str | None:
        """Find the primary agent for a given stage."""
        for agent in self.agents:
            if stage in agent.get("primary_stages", []):
                return agent["id"]
        return None

    def _get_secondary_agent(self, stage: str) -> str | None:
        """Find the secondary agent for a given stage (fallback when no primary exists)."""
        for agent in self.agents:
            if stage in agent.get("secondary_stages", []):
                return agent["id"]
        return None

    # --- Phase 4: Quality Gates ---

    def check_quality_gates(self) -> None:
        """Validate new reports against schemas."""
        if not self.config["quality"]["validate_schemas"]:
            return

        cached = self.state.read_cached_issues()
        for issue in cached:
            labels = issue.get("labels", [])
            if "type:review" in labels:
                # Find reports for tasks in review
                task_id = self._extract_task_id(issue.get("title", ""))
                if task_id:
                    reports = self.state.read_reports(task_id)
                    for agent_id, report in reports.items():
                        errors = validate(report, "release_readiness")
                        if errors:
                            logger.warning(
                                "Report %s.%s failed validation: %s",
                                task_id, agent_id, errors,
                            )

    def _extract_task_id(self, title: str) -> str | None:
        """Extract task_id from issue title if present."""
        match = re.search(r"(task-\d{3,}(?:-[a-z]+)?)", title)
        return match.group(1) if match else None

    # --- Phase 5: Consensus ---

    def check_consensus_ready(self) -> int:
        """Trigger consensus when all review reports are collected."""
        triggered = 0
        assignments = self.state.list_assignments()

        # Find tasks in review or consensus stage
        review_tasks: dict[str, int] = {}
        review_task_agents: dict[str, str] = {}  # task_id -> agent_id
        for agent_id, assignment in assignments.items():
            if assignment.get("stage") in ("review", "consensus"):
                task_id = assignment.get("task_id", "")
                if task_id:
                    review_tasks[task_id] = assignment.get("github_issue_number", 0)
                    review_task_agents[task_id] = agent_id

        for task_id, issue_number in review_tasks.items():
            reports = self.state.read_reports(task_id)
            review_agents = [
                a["id"] for a in self.agents
                if "review" in a.get("primary_stages", []) + a.get("secondary_stages", [])
            ]

            if all(agent_id in reports for agent_id in review_agents):
                agents_config = {a["id"]: a for a in self.agents}
                votes = self.consensus_engine.build_votes_from_reports(reports, agents_config)
                existing = self.state.read_consensus(task_id)
                re_review_count = existing["re_review_count"] + 1 if existing else 0

                result = self.consensus_engine.compute(task_id, votes, re_review_count)
                self.state.write_consensus(task_id, result.to_dict())

                # Post result to GitHub
                action_text = {
                    "proceed": "PASS - Proceeding to next stage",
                    "rework": "FAIL - Rework required",
                    "escalate": "ESCALATE - Human intervention required",
                }
                self.github.add_comment(
                    issue_number,
                    f"## [Orchestrator] Consensus Result\n\n"
                    f"**Action:** {action_text.get(result.action, result.action)}\n"
                    f"**Ratio:** {result.ratio:.2%}\n"
                    f"**Can Proceed:** {result.can_proceed}\n",
                )

                if result.can_proceed:
                    self.github.update_labels(
                        issue_number, add=["consensus:pass"], remove=["status:review-needed"]
                    )
                    # Advance to release stage
                    release_agent = (
                        self._get_primary_agent("release")
                        or self._get_secondary_agent("release")
                    )
                    if release_agent:
                        consensus_agent = review_task_agents.get(task_id)
                        self.state.write_assignment(release_agent, {
                            "agent_id": release_agent,
                            "task_id": task_id,
                            "stage": "release",
                            "github_issue_number": issue_number,
                            "assigned_at": datetime.now(timezone.utc).isoformat(),
                            "timeout_minutes": self.config["orchestrator"][
                                "assignment_timeout_minutes"
                            ],
                            "context": {
                                "consensus": result.to_dict(),
                            },
                        })
                        logger.info(
                            "Advanced %s: consensus -> release (agent: %s)",
                            task_id, release_agent,
                        )
                elif result.action == "escalate":
                    self.github.update_labels(
                        issue_number, add=["escalation:human"], remove=["status:review-needed"]
                    )
                    # Create escalation issue
                    escalation_title = f"ESCALATION: Human review needed for issue #{issue_number}"
                    escalation_body = (
                        f"## Escalation Required\n\n"
                        f"Consensus engine could not reach agreement on issue #{issue_number} "
                        f"after maximum re-reviews.\n\n"
                        f"**Consensus ratio:** {result.ratio:.2%}\n"
                        f"**Action:** {result.action}\n\n"
                        f"Please review issue #{issue_number} "
                        f"and resolve the disagreement manually.\n\n"
                        f"---\n*Auto-generated by Orchestrator at "
                        f"{datetime.now(timezone.utc).isoformat()}*"
                    )
                    mention_user = self.config.get("notifications", {}).get("mention_user", "")
                    if mention_user:
                        escalation_body += f"\n\n/cc @{mention_user}"
                    try:
                        self.github.create_issue(
                            title=escalation_title,
                            body=escalation_body,
                            labels=["type:escalation", "status:human-needed", "escalation:human"],
                        )
                        logger.info("Created escalation issue for issue #%s", issue_number)
                    except Exception:
                        logger.exception("Failed to create escalation issue for #%s", issue_number)
                else:
                    self.github.update_labels(
                        issue_number, add=["consensus:fail"], remove=["status:review-needed"]
                    )

                # Clear consensus assignment to prevent re-processing on next poll
                consensus_agent = review_task_agents.get(task_id)
                if consensus_agent:
                    self.state.clear_assignment(consensus_agent)

                triggered += 1

        return triggered

    # --- Phase 5b: Escalation ---

    def _check_escalation_triggers(self) -> list[dict]:
        """Check all active assignments for escalation conditions.

        Returns:
            List of dicts with keys: agent_id, task_id, reason.
        """
        # @MX:ANCHOR: [AUTO] Escalation gate called every poll cycle
        # @MX:REASON: fan_in >= 3 (poll_cycle, tests, future alerting); triggers human intervention
        timeout = self.config["orchestrator"]["assignment_timeout_minutes"]
        stale = self.state.get_stale_assignments(timeout)
        triggers = []
        for assignment in stale:
            triggers.append(
                {
                    "agent_id": assignment.get("agent_id", ""),
                    "task_id": assignment.get("task_id", ""),
                    "reason": (
                        f"Assignment exceeded timeout of {timeout} minutes"
                    ),
                }
            )
        return triggers

    def _create_escalation_issue(self, reason: str, context: dict) -> int | None:
        """Create a GitHub escalation issue.

        Args:
            reason: Human-readable description of why escalation was triggered.
            context: Dict with agent_id, task_id, and any additional details.

        Returns:
            The new GitHub issue number, or None on failure.
        """
        agent_id = context.get("agent_id", "unknown")
        task_id = context.get("task_id", "unknown")
        title = f"ESCALATION: Timeout for agent={agent_id} task={task_id}"
        body = (
            f"## Escalation: Assignment Timeout\n\n"
            f"**Reason:** {reason}\n\n"
            f"**Agent:** {agent_id}\n"
            f"**Task:** {task_id}\n\n"
            f"The assignment has exceeded the configured timeout. "
            f"Please investigate and reassign or resolve manually.\n\n"
            f"---\n*Auto-generated by Orchestrator at "
            f"{datetime.now(timezone.utc).isoformat()}*"
        )
        mention_user = self.config.get("notifications", {}).get("mention_user", "")
        if mention_user:
            body += f"\n\n/cc @{mention_user}"
        try:
            issue_num = self.github.create_issue(
                title=title,
                body=body,
                labels=["type:escalation", "status:human-needed"],
            )
            logger.info(
                "Created escalation issue #%s for %s/%s", issue_num, agent_id, task_id
            )
            return issue_num
        except Exception:
            logger.exception(
                "Failed to create escalation issue for %s/%s", agent_id, task_id
            )
            return None

    # --- Phase 6: Stale Lock Release ---

    def release_stale_locks(self) -> int:
        """Release assignments that have exceeded the timeout."""
        timeout = self.config["orchestrator"]["assignment_timeout_minutes"]
        stale = self.state.get_stale_assignments(timeout)
        for assignment in stale:
            agent_id = assignment.get("agent_id", "")
            task_id = assignment.get("task_id", "")
            logger.warning("Releasing stale assignment: %s/%s", agent_id, task_id)
            self.state.clear_assignment(agent_id)
        return len(stale)

    # --- Phase 7: Session Completion ---

    def check_session_complete(self) -> None:
        """Check if all tasks are done and generate Final Report."""
        cached = self.state.read_cached_issues()
        if not cached:
            return

        # Check if any kickoff issues exist and all are done
        kickoff_issues = [i for i in cached if "type:kickoff" in i.get("labels", [])]
        if not kickoff_issues:
            return

        all_done = all("status:done" in i.get("labels", []) for i in kickoff_issues)
        if not all_done:
            return

        # Generate Final Report
        session_id = f"session-{kickoff_issues[0].get('number', 0)}"
        existing = self.state.read_consensus(session_id)
        if existing:
            return  # Already generated

        try:
            report_md = generate_report_markdown({
                "session_id": session_id,
                "issues": cached,
            })
            mention = self.config["github"]["mention_user"]
            issue_num = self.github.create_issue(
                title=f"[Final Report] {session_id}",
                body=report_md + (f"\n\ncc {mention}" if mention else ""),
                labels=["type:report", "status:done"],
            )
            logger.info("Created Final Report: Issue #%d", issue_num)
        except Exception:
            logger.exception("Failed to generate Final Report")


def main() -> None:
    """CLI entry point for the orchestrator."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/config.yaml"

    # Setup logging with UTC timestamps (AC-006)
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    try:
        orchestrator = Orchestrator(config_path)
        orchestrator.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception:
        logger.exception("Orchestrator failed to start")
        sys.exit(1)


if __name__ == "__main__":
    main()
