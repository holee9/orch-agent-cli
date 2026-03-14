"""BRIEF file parser for orch-agent-cli.

Scans inbox/ directory for BRIEF-*.md files, parses Korean content,
performs structural English translation, and creates GitHub Kickoff Issues.
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_BRIEF_SIZE = 1_048_576  # 1MB


def _is_safe_path(path: Path, base_dir: Path) -> bool:
    """Verify path is within base_dir and is not a symlink."""
    try:
        resolved = path.resolve()
        base_resolved = base_dir.resolve()
        return resolved.is_relative_to(base_resolved) and not path.is_symlink()
    except (OSError, ValueError):
        return False


# Expected BRIEF sections (Korean headers -> English keys)
SECTION_MAP: dict[str, str] = {
    "프로젝트": "project",
    "배경": "background",
    "목표": "objectives",
    "범위": "scope",
    "제약사항": "constraints",
    "기술스택": "tech_stack",
    "참고자료": "references",
    "우선순위": "priority",
    "일정": "timeline",
}


def scan_inbox(inbox_dir: str | Path) -> list[Path]:
    """Find BRIEF-*.md files in the inbox directory.

    Returns sorted list of BRIEF file paths.
    """
    inbox = Path(inbox_dir)
    if not inbox.exists():
        logger.debug("Inbox directory does not exist: %s", inbox)
        return []
    briefs = []
    for f in sorted(inbox.glob("BRIEF-*.md")):
        if not _is_safe_path(f, inbox):
            logger.warning("Skipping unsafe path in inbox: %s", f)
            continue
        briefs.append(f)
    if briefs:
        logger.info("Found %d BRIEF file(s) in inbox", len(briefs))
    return briefs


def parse_brief(path: str | Path) -> dict:
    """Parse a BRIEF markdown file into structured sections.

    Extracts content under ## headers, mapping Korean headers to English keys.
    Returns dict with 'raw_title', 'sections', 'source_path', and 'raw_content'.
    """
    path = Path(path)
    if path.stat().st_size > MAX_BRIEF_SIZE:
        raise ValueError(
            f"BRIEF file too large: {path.stat().st_size} bytes (max {MAX_BRIEF_SIZE})"
        )
    content = path.read_text(encoding="utf-8")

    result: dict = {
        "raw_title": "",
        "sections": {},
        "source_path": str(path),
        "raw_content": content,
    }

    # Extract title from first # header
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if title_match:
        result["raw_title"] = title_match.group(1).strip()

    # Extract sections under ## headers
    section_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(section_pattern.finditer(content))

    for i, match in enumerate(matches):
        header = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()

        # Map Korean header to English key
        key = _map_header(header)
        result["sections"][key] = {
            "original_header": header,
            "content": body,
        }

    return result


def _map_header(header: str) -> str:
    """Map a Korean section header to an English key."""
    for korean, english in SECTION_MAP.items():
        if korean in header:
            return english
    # Fallback: use the header as-is (lowercased, spaces to underscores)
    return re.sub(r"\s+", "_", header.lower())


def translate_to_english(brief_data: dict) -> dict:
    """Perform structural translation of BRIEF data.

    This does basic header translation and formatting.
    Full translation is delegated to Claude via the Kickoff Issue.
    """
    translated = {
        "title": brief_data["raw_title"],
        "sections": {},
    }

    for key, section in brief_data["sections"].items():
        translated["sections"][key] = {
            "header": key.replace("_", " ").title(),
            "content": section["content"],
            "original_header": section["original_header"],
        }

    return translated


def format_kickoff_issue(brief_data: dict) -> tuple[str, str]:
    """Format parsed BRIEF data into a GitHub Kickoff Issue (title, body).

    The issue body includes both original Korean and English structure.
    """
    title = f"[Kickoff] {brief_data['raw_title']}"

    translated = translate_to_english(brief_data)

    lines = [
        "# Kickoff Issue",
        "",
        f"**Source:** `{Path(brief_data['source_path']).name}`",
        f"**Created:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
    ]

    # Add translated sections
    for _key, section in translated["sections"].items():
        lines.append(f"## {section['header']}")
        if section["original_header"] != section["header"]:
            lines.append(f"*Original: {section['original_header']}*")
        lines.append("")
        lines.append(section["content"])
        lines.append("")

    # Add raw content as reference
    lines.extend([
        "---",
        "",
        "<details>",
        "<summary>Original BRIEF (Raw)</summary>",
        "",
        "```markdown",
        brief_data["raw_content"],
        "```",
        "",
        "</details>",
    ])

    body = "\n".join(lines)
    return title, body


def archive_brief(brief_path: str | Path, archive_dir: str | Path) -> Path:
    """Move processed BRIEF file to archive directory.

    Adds timestamp prefix to prevent name collisions.
    Returns the new archive path.
    """
    brief_path = Path(brief_path)
    archive = Path(archive_dir)

    base_dir = brief_path.parent
    if not _is_safe_path(brief_path, base_dir):
        raise ValueError(f"Unsafe brief path: {brief_path}")
    if brief_path.stat().st_size > MAX_BRIEF_SIZE:
        raise ValueError(
            f"BRIEF file too large for archiving: "
            f"{brief_path.stat().st_size} bytes (max {MAX_BRIEF_SIZE})"
        )

    archive.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive_name = f"{timestamp}-{brief_path.name}"
    dest = archive / archive_name

    shutil.move(str(brief_path), str(dest))
    logger.info("Archived BRIEF: %s -> %s", brief_path, dest)
    return dest


def process_brief(path: str | Path, github_client, archive_dir: str | Path) -> int:
    """Full BRIEF processing pipeline.

    1. Parse BRIEF file
    2. Format Kickoff Issue
    3. Create GitHub Issue with labels
    4. Archive the BRIEF file

    Returns the created issue number.
    """
    logger.info("Processing BRIEF: %s", path)

    brief_data = parse_brief(path)
    title, body = format_kickoff_issue(brief_data)

    issue_number = github_client.create_issue(
        title=title,
        body=body,
        labels=["type:kickoff", "stage:requirements", "status:open"],
    )
    logger.info("Created Kickoff Issue #%d: %s", issue_number, title)

    archive_brief(path, archive_dir)

    return issue_number
