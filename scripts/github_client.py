"""GitHub CLI (gh) wrapper for orch-agent-cli.

All GitHub API interactions go through this module.
Uses subprocess to call `gh` CLI, which handles authentication natively.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GitHubIssue:
    """Represents a GitHub issue."""
    number: int
    title: str
    body: str
    state: str
    labels: list[str] = field(default_factory=list)
    comments: list[dict] = field(default_factory=list)


class GitHubClientError(Exception):
    """Raised when a gh CLI command fails."""


class GitHubClient:
    """Gateway for all GitHub operations via gh CLI."""

    def __init__(self, repo: str):
        """Initialize with owner/repo string."""
        self.repo = repo

    def _run_gh(self, args: list[str], input_text: str | None = None) -> str:
        """Execute a gh CLI command and return stdout.

        Raises GitHubClientError on non-zero exit code.
        """
        cmd = ["gh"] + args + ["--repo", self.repo]
        logger.debug("Running: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input=input_text,
                timeout=30,
            )
        except subprocess.TimeoutExpired as e:
            raise GitHubClientError(f"gh command timed out: {' '.join(cmd)}") from e
        except FileNotFoundError as e:
            raise GitHubClientError("gh CLI not found. Install from https://cli.github.com/") from e

        if result.returncode != 0:
            raise GitHubClientError(
                f"gh command failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> int:
        """Create a GitHub issue. Returns the issue number."""
        args = ["issue", "create", "--title", title, "--body", body]
        if labels:
            args.extend(["--label", ",".join(labels)])
        output = self._run_gh(args)
        # gh issue create outputs the URL, extract issue number from it
        # e.g., https://github.com/owner/repo/issues/42
        try:
            return int(output.rstrip("/").split("/")[-1])
        except (ValueError, IndexError) as e:
            raise GitHubClientError(f"Could not parse issue number from: {output}") from e

    def add_comment(self, issue_number: int, body: str) -> None:
        """Post a comment on an issue."""
        self._run_gh(["issue", "comment", str(issue_number), "--body", body])

    def list_issues(
        self,
        labels: list[str] | None = None,
        state: str = "open",
        limit: int = 100,
    ) -> list[GitHubIssue]:
        """Query issues with optional label and state filters."""
        args = [
            "issue", "list",
            "--state", state,
            "--limit", str(limit),
            "--json", "number,title,body,state,labels",
        ]
        if labels:
            for label in labels:
                args.extend(["--label", label])
        output = self._run_gh(args)
        if not output:
            return []
        raw_issues = json.loads(output)
        return [
            GitHubIssue(
                number=issue["number"],
                title=issue["title"],
                body=issue.get("body", ""),
                state=issue["state"],
                labels=[lbl["name"] for lbl in issue.get("labels", [])],
            )
            for issue in raw_issues
        ]

    def get_issue(self, issue_number: int) -> GitHubIssue:
        """Get a single issue with its comments."""
        # Get issue details
        output = self._run_gh([
            "issue", "view", str(issue_number),
            "--json", "number,title,body,state,labels,comments",
        ])
        data = json.loads(output)
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body", ""),
            state=data["state"],
            labels=[lbl["name"] for lbl in data.get("labels", [])],
            comments=data.get("comments", []),
        )

    def update_labels(
        self,
        issue_number: int,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> None:
        """Add and/or remove labels from an issue."""
        if add:
            self._run_gh([
                "issue", "edit", str(issue_number),
                "--add-label", ",".join(add),
            ])
        if remove:
            try:
                self._run_gh([
                    "issue", "edit", str(issue_number),
                    "--remove-label", ",".join(remove),
                ])
            except GitHubClientError as e:
                if "not found" in str(e):
                    logger.debug("Label(s) not found on issue #%s, skipping remove: %s", issue_number, remove)  # noqa: E501
                else:
                    raise

    def close_issue(self, issue_number: int, comment: str | None = None) -> None:
        """Close an issue with an optional closing comment."""
        if comment:
            self.add_comment(issue_number, comment)
        self._run_gh(["issue", "close", str(issue_number)])

    def create_labels(self, labels: list[dict]) -> None:
        """Bulk create labels. Each dict needs 'name', 'color', 'description'.

        Skips labels that already exist (gh exits non-zero for duplicates).
        """
        for label in labels:
            try:
                self._run_gh([
                    "label", "create", label["name"],
                    "--color", label["color"],
                    "--description", label.get("description", ""),
                    "--force",
                ])
            except GitHubClientError as e:
                logger.warning("Could not create label '%s': %s", label["name"], e)
