"""Integration tests for BRIEF -> process_brief -> GitHub Issue flow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.brief_parser import process_brief, scan_inbox

FULL_BRIEF_CONTENT = """\
# 통합 테스트 프로젝트

## 프로젝트
통합 테스트를 위한 샘플 프로젝트입니다.

## 배경
기존 시스템을 개선하기 위한 배경입니다.

## 목표
- 통합 테스트 구현
- E2E 검증 완료

## 범위
scripts/ 디렉토리 대상

## 제약사항
Python 3.10+ 필수

## 기술스택
Python, pytest

## 우선순위
High

## 일정
2026년 Q1
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_github() -> MagicMock:
    """Return a mock GitHub client that returns issue number 42."""
    client = MagicMock()
    client.create_issue.return_value = 42
    return client


@pytest.fixture
def inbox_with_brief(tmp_path: Path) -> tuple[Path, Path]:
    """Return (inbox_dir, brief_path) with one BRIEF file written."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    brief = inbox / "BRIEF-2026-03-14.md"
    brief.write_text(FULL_BRIEF_CONTENT, encoding="utf-8")
    return inbox, brief


# ---------------------------------------------------------------------------
# Test 1: scan_inbox finds the file, process_brief creates kickoff issue
# ---------------------------------------------------------------------------


def test_scan_inbox_finds_brief(inbox_with_brief: tuple[Path, Path]) -> None:
    """scan_inbox must detect the BRIEF file placed in inbox."""
    inbox, brief = inbox_with_brief
    found = scan_inbox(inbox)
    assert len(found) == 1
    assert found[0] == brief


def test_process_brief_creates_kickoff_issue(
    inbox_with_brief: tuple[Path, Path],
    mock_github: MagicMock,
    tmp_path: Path,
) -> None:
    """process_brief must call github.create_issue with kickoff title and labels."""
    _, brief = inbox_with_brief
    archive_dir = tmp_path / "archive"

    issue_number = process_brief(brief, mock_github, archive_dir)

    assert issue_number == 42
    mock_github.create_issue.assert_called_once()

    kwargs = mock_github.create_issue.call_args.kwargs
    assert "[Kickoff]" in kwargs["title"]
    assert "통합 테스트 프로젝트" in kwargs["title"]
    assert "type:kickoff" in kwargs["labels"]
    assert "stage:requirements" in kwargs["labels"]
    assert "status:open" in kwargs["labels"]


def test_process_brief_archives_file(
    inbox_with_brief: tuple[Path, Path],
    mock_github: MagicMock,
    tmp_path: Path,
) -> None:
    """process_brief must move the BRIEF out of inbox into archive dir."""
    _, brief = inbox_with_brief
    archive_dir = tmp_path / "archive"

    process_brief(brief, mock_github, archive_dir)

    # Original file must be gone
    assert not brief.exists(), "BRIEF file must be removed from inbox after processing"

    # Archive dir must contain exactly one file
    archived = list(archive_dir.glob("*.md"))
    assert len(archived) == 1, "Exactly one archived file expected"
    assert archived[0].name.endswith("BRIEF-2026-03-14.md")


def test_process_brief_issue_body_contains_raw_content(
    inbox_with_brief: tuple[Path, Path],
    mock_github: MagicMock,
    tmp_path: Path,
) -> None:
    """The kickoff issue body must embed the original BRIEF content."""
    _, brief = inbox_with_brief
    archive_dir = tmp_path / "archive"

    process_brief(brief, mock_github, archive_dir)

    kwargs = mock_github.create_issue.call_args.kwargs
    body = kwargs["body"]
    assert "# Kickoff Issue" in body
    assert "**Source:**" in body
    assert "Original BRIEF (Raw)" in body
    # Raw content must be present verbatim
    assert "통합 테스트 프로젝트" in body


# ---------------------------------------------------------------------------
# Test 2: Empty inbox -> no GitHub calls
# ---------------------------------------------------------------------------


def test_empty_inbox_no_github_calls(
    tmp_path: Path,
    mock_github: MagicMock,
) -> None:
    """When inbox is empty, process_brief must never be called."""
    empty_inbox = tmp_path / "inbox"
    empty_inbox.mkdir()

    found = scan_inbox(empty_inbox)
    assert found == []

    # No GitHub calls should have been made
    mock_github.create_issue.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Multiple BRIEFs in inbox -> all processed in order
# ---------------------------------------------------------------------------


def test_multiple_briefs_all_processed(
    tmp_path: Path,
    mock_github: MagicMock,
) -> None:
    """All BRIEF files in inbox must each trigger one create_issue call."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    archive_dir = tmp_path / "archive"

    for i in range(1, 4):
        (inbox / f"BRIEF-00{i}.md").write_text(
            f"# 프로젝트 {i}\n\n## 배경\n배경 {i}\n",
            encoding="utf-8",
        )

    briefs = scan_inbox(inbox)
    assert len(briefs) == 3

    for brief in briefs:
        process_brief(brief, mock_github, archive_dir)

    assert mock_github.create_issue.call_count == 3

    # All archived
    archived = list(archive_dir.glob("*.md"))
    assert len(archived) == 3
