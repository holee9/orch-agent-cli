"""Tests for scripts/github_client.py.

All subprocess.run calls are mocked to avoid real gh CLI execution.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.github_client import GitHubClient, GitHubClientError, GitHubIssue

REPO = "owner/repo"


def _make_completed_process(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    """Build a fake subprocess.CompletedProcess-like mock."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# ---------------------------------------------------------------------------
# test_create_issue
# ---------------------------------------------------------------------------


def test_create_issue() -> None:
    """create_issue parses the issue number from the gh URL output."""
    client = GitHubClient(REPO)
    url_output = "https://github.com/owner/repo/issues/42\n"

    completed = _make_completed_process(stdout=url_output)
    with patch("subprocess.run", return_value=completed) as mock_run:
        issue_number = client.create_issue(title="My Title", body="My Body")

    assert issue_number == 42
    mock_run.assert_called_once()
    cmd_args = mock_run.call_args[0][0]
    assert cmd_args == [
        "gh", "issue", "create",
        "--title", "My Title", "--body", "My Body", "--repo", REPO,
    ]


# ---------------------------------------------------------------------------
# test_create_issue_with_labels
# ---------------------------------------------------------------------------


def test_create_issue_with_labels() -> None:
    """create_issue passes --label flag with comma-joined labels."""
    client = GitHubClient(REPO)
    url_output = "https://github.com/owner/repo/issues/7"

    with patch(
        "subprocess.run", return_value=_make_completed_process(stdout=url_output)
    ) as mock_run:
        issue_number = client.create_issue(title="T", body="B", labels=["bug", "help wanted"])

    assert issue_number == 7
    cmd_args = mock_run.call_args[0][0]
    assert "--label" in cmd_args
    label_idx = cmd_args.index("--label")
    assert cmd_args[label_idx + 1] == "bug,help wanted"
    assert cmd_args[-2:] == ["--repo", REPO]


# ---------------------------------------------------------------------------
# test_add_comment
# ---------------------------------------------------------------------------


def test_add_comment() -> None:
    """add_comment calls gh issue comment with the correct arguments."""
    client = GitHubClient(REPO)

    with patch("subprocess.run", return_value=_make_completed_process()) as mock_run:
        client.add_comment(issue_number=99, body="Great work!")

    cmd_args = mock_run.call_args[0][0]
    assert cmd_args == ["gh", "issue", "comment", "99", "--body", "Great work!", "--repo", REPO]


# ---------------------------------------------------------------------------
# test_list_issues
# ---------------------------------------------------------------------------


def test_list_issues() -> None:
    """list_issues deserialises JSON output into a list of GitHubIssue objects."""
    client = GitHubClient(REPO)
    raw = json.dumps([
        {
            "number": 1,
            "title": "First issue",
            "body": "Some body",
            "state": "OPEN",
            "labels": [{"name": "bug"}, {"name": "priority:high"}],
        },
        {
            "number": 2,
            "title": "Second issue",
            "body": "",
            "state": "OPEN",
            "labels": [],
        },
    ])

    with patch("subprocess.run", return_value=_make_completed_process(stdout=raw)):
        issues = client.list_issues()

    assert len(issues) == 2
    assert isinstance(issues[0], GitHubIssue)
    assert issues[0].number == 1
    assert issues[0].title == "First issue"
    assert issues[0].labels == ["bug", "priority:high"]
    assert issues[1].number == 2
    assert issues[1].labels == []


# ---------------------------------------------------------------------------
# test_list_issues_empty
# ---------------------------------------------------------------------------


def test_list_issues_empty() -> None:
    """list_issues returns an empty list when gh outputs nothing."""
    client = GitHubClient(REPO)

    with patch("subprocess.run", return_value=_make_completed_process(stdout="")):
        issues = client.list_issues()

    assert issues == []


# ---------------------------------------------------------------------------
# test_get_issue_with_comments
# ---------------------------------------------------------------------------


def test_get_issue_with_comments() -> None:
    """get_issue returns a GitHubIssue with comments populated."""
    client = GitHubClient(REPO)
    raw = json.dumps({
        "number": 5,
        "title": "Issue with comments",
        "body": "Body text",
        "state": "OPEN",
        "labels": [{"name": "review"}],
        "comments": [
            {"body": "First comment", "author": {"login": "alice"}},
            {"body": "Second comment", "author": {"login": "bob"}},
        ],
    })

    with patch("subprocess.run", return_value=_make_completed_process(stdout=raw)):
        issue = client.get_issue(5)

    assert issue.number == 5
    assert issue.title == "Issue with comments"
    assert issue.labels == ["review"]
    assert len(issue.comments) == 2
    assert issue.comments[0]["body"] == "First comment"
    assert issue.comments[1]["author"]["login"] == "bob"


# ---------------------------------------------------------------------------
# test_update_labels_add_and_remove
# ---------------------------------------------------------------------------


def test_update_labels_add_and_remove() -> None:
    """update_labels issues separate gh calls for add and remove operations."""
    client = GitHubClient(REPO)

    with patch("subprocess.run", return_value=_make_completed_process()) as mock_run:
        client.update_labels(issue_number=10, add=["status:done"], remove=["status:open"])

    assert mock_run.call_count == 2

    add_call_args = mock_run.call_args_list[0][0][0]
    assert add_call_args == [
        "gh", "issue", "edit", "10",
        "--add-label", "status:done",
        "--repo", REPO,
    ]

    remove_call_args = mock_run.call_args_list[1][0][0]
    assert remove_call_args == [
        "gh", "issue", "edit", "10",
        "--remove-label", "status:open",
        "--repo", REPO,
    ]


# ---------------------------------------------------------------------------
# test_gh_command_failure
# ---------------------------------------------------------------------------


def test_gh_command_failure() -> None:
    """_run_gh raises GitHubClientError when gh exits with a non-zero code."""
    client = GitHubClient(REPO)

    with patch(
        "subprocess.run",
        return_value=_make_completed_process(returncode=1, stderr="authentication required"),
    ):
        with pytest.raises(GitHubClientError, match="gh command failed"):
            client.list_issues()
