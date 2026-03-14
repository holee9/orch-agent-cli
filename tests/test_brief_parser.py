"""Tests for the brief_parser module in scripts/brief_parser.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.brief_parser import (
    archive_brief,
    format_kickoff_issue,
    parse_brief,
    scan_inbox,
    translate_to_english,
)

# ---------------------------------------------------------------------------
# Sample BRIEF content fixture (Korean headers)
# ---------------------------------------------------------------------------

SAMPLE_BRIEF_CONTENT = """\
# 오케스트레이션 CLI 개선 프로젝트

## 프로젝트
멀티 AI 에이전트 오케스트레이션 CLI 도구를 개선합니다.

## 배경
현재 CLI는 단일 에이전트만 지원하여 복잡한 작업을 처리하기 어렵습니다.

## 목표
- 멀티 에이전트 지원 추가
- 합의 엔진 구현
- 자동화된 워크플로우 생성

## 범위
scripts/ 디렉토리의 핵심 모듈을 대상으로 합니다.

## 제약사항
Python 3.10 이상 지원 필수.

## 기술스택
Python, pytest, GitHub Actions

## 참고자료
- docs/v3-plan.md
- README.md

## 우선순위
High

## 일정
2026년 Q1 완료 목표
"""

MINIMAL_BRIEF_CONTENT = """\
# 간단한 BRIEF

## 배경
배경 설명입니다.
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_inbox(tmp_path: Path) -> Path:
    """Return a temporary inbox directory."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return inbox


@pytest.fixture
def tmp_archive(tmp_path: Path) -> Path:
    """Return a temporary archive directory (not yet created)."""
    return tmp_path / "archive"


@pytest.fixture
def sample_brief_file(tmp_inbox: Path) -> Path:
    """Write a well-formed BRIEF file to the inbox and return its path."""
    brief_path = tmp_inbox / "BRIEF-001.md"
    brief_path.write_text(SAMPLE_BRIEF_CONTENT, encoding="utf-8")
    return brief_path


# ---------------------------------------------------------------------------
# Test 1: scan_inbox finds BRIEF-*.md files
# ---------------------------------------------------------------------------


def test_scan_inbox_finds_briefs(tmp_inbox: Path) -> None:
    (tmp_inbox / "BRIEF-001.md").write_text("# test", encoding="utf-8")
    (tmp_inbox / "BRIEF-002.md").write_text("# test", encoding="utf-8")
    (tmp_inbox / "README.md").write_text("not a brief", encoding="utf-8")

    result = scan_inbox(tmp_inbox)

    assert len(result) == 2
    names = [p.name for p in result]
    assert "BRIEF-001.md" in names
    assert "BRIEF-002.md" in names
    assert "README.md" not in names


# ---------------------------------------------------------------------------
# Test 2: scan_inbox returns empty list for empty or missing directory
# ---------------------------------------------------------------------------


def test_scan_inbox_empty(tmp_path: Path) -> None:
    # Non-existent directory
    missing = tmp_path / "no_such_inbox"
    assert scan_inbox(missing) == []

    # Existing but empty directory
    empty = tmp_path / "empty_inbox"
    empty.mkdir()
    assert scan_inbox(empty) == []


# ---------------------------------------------------------------------------
# Test 3: parse_brief parses all sections from a well-formed BRIEF
# ---------------------------------------------------------------------------


def test_parse_brief_full(sample_brief_file: Path) -> None:
    data = parse_brief(sample_brief_file)

    assert data["raw_title"] == "오케스트레이션 CLI 개선 프로젝트"
    assert str(sample_brief_file) == data["source_path"]
    assert SAMPLE_BRIEF_CONTENT == data["raw_content"]

    sections = data["sections"]
    # All nine Korean sections should be mapped to English keys
    expected_keys = {
        "project",
        "background",
        "objectives",
        "scope",
        "constraints",
        "tech_stack",
        "references",
        "priority",
        "timeline",
    }
    assert expected_keys == set(sections.keys())

    # Spot-check one section
    assert "멀티 에이전트 지원 추가" in sections["objectives"]["content"]
    assert sections["objectives"]["original_header"] == "목표"


# ---------------------------------------------------------------------------
# Test 4: parse_brief handles BRIEF with some sections missing
# ---------------------------------------------------------------------------


def test_parse_brief_missing_sections(tmp_path: Path) -> None:
    brief = tmp_path / "BRIEF-minimal.md"
    brief.write_text(MINIMAL_BRIEF_CONTENT, encoding="utf-8")

    data = parse_brief(brief)

    assert data["raw_title"] == "간단한 BRIEF"
    sections = data["sections"]
    # Only the 배경 (background) section should be present
    assert "background" in sections
    assert len(sections) == 1


# ---------------------------------------------------------------------------
# Test 5: parse_brief extracts title from the first # header
# ---------------------------------------------------------------------------


def test_parse_brief_title(tmp_path: Path) -> None:
    content = "# My BRIEF Title\n\n## 배경\nSome content.\n"
    brief = tmp_path / "BRIEF-title.md"
    brief.write_text(content, encoding="utf-8")

    data = parse_brief(brief)

    assert data["raw_title"] == "My BRIEF Title"


# ---------------------------------------------------------------------------
# Test 6: translate_to_english produces English keys and section headers
# ---------------------------------------------------------------------------


def test_translate_to_english(sample_brief_file: Path) -> None:
    brief_data = parse_brief(sample_brief_file)
    translated = translate_to_english(brief_data)

    assert translated["title"] == "오케스트레이션 CLI 개선 프로젝트"

    sections = translated["sections"]
    # All keys must be English (no Korean characters)
    for key in sections:
        assert all(ord(c) < 0xAC00 or ord(c) > 0xD7A3 for c in key), (
            f"Key '{key}' contains Korean characters"
        )

    # Header value should be title-cased English
    assert sections["background"]["header"] == "Background"
    assert sections["tech_stack"]["header"] == "Tech Stack"

    # Original Korean header must be preserved
    assert sections["background"]["original_header"] == "배경"

    # Content must be passed through unchanged
    assert sections["background"]["content"] == brief_data["sections"]["background"]["content"]


# ---------------------------------------------------------------------------
# Test 7: format_kickoff_issue produces valid title and body markdown
# ---------------------------------------------------------------------------


def test_format_kickoff_issue(sample_brief_file: Path) -> None:
    brief_data = parse_brief(sample_brief_file)
    title, body = format_kickoff_issue(brief_data)

    # Title
    assert title.startswith("[Kickoff]")
    assert "오케스트레이션 CLI 개선 프로젝트" in title

    # Body must be a non-empty string of markdown
    assert isinstance(body, str)
    assert len(body) > 0

    # Structural checks on body content
    assert "# Kickoff Issue" in body
    assert "**Source:**" in body
    assert "**Created:**" in body
    assert "Original BRIEF (Raw)" in body
    assert "```markdown" in body

    # Section headers should appear in body
    assert "## Background" in body
    assert "## Objectives" in body


# ---------------------------------------------------------------------------
# Test 8: archive_brief moves file to archive dir with timestamp prefix
# ---------------------------------------------------------------------------


def test_archive_brief(sample_brief_file: Path, tmp_archive: Path) -> None:
    original_name = sample_brief_file.name  # "BRIEF-001.md"

    dest = archive_brief(sample_brief_file, tmp_archive)

    # Original file must no longer exist
    assert not sample_brief_file.exists()

    # Destination must exist in archive dir
    assert dest.exists()
    assert dest.parent == tmp_archive

    # Destination name must end with the original file name
    assert dest.name.endswith(original_name)

    # Destination name must have a timestamp prefix (format: YYYYMMDD-HHMMSS-)
    prefix = dest.name.replace(original_name, "")
    assert len(prefix) > 0, "Expected timestamp prefix before original filename"
    # Rough check: prefix contains digits and a hyphen
    assert any(c.isdigit() for c in prefix)
