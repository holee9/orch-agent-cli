"""Secret scan automation module.

Scans text, files, and directories for common secret patterns
such as GitHub tokens, AWS keys, API keys, and private key markers.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Compiled secret detection patterns
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "github_token",
        re.compile(r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}"),
    ),
    (
        "api_key",
        re.compile(r'(?i)api[_-]?key["\']?\s*[:=]\s*["\']?[A-Za-z0-9+/]{20,}'),
    ),
    (
        "aws_key",
        re.compile(r"AKIA[0-9A-Z]{16}"),
    ),
    (
        "private_key",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
]

# Directories to skip during recursive scanning
_SKIP_DIRS: frozenset[str] = frozenset({".git", ".venv"})


def scan_text(text: str) -> list[dict]:
    """Scan a string for secret patterns.

    Args:
        text: The text content to scan.

    Returns:
        List of dicts with keys: type, match, start, end.
        Returns an empty list when no secrets are found.
    """
    results: list[dict] = []
    for secret_type, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            results.append(
                {
                    "type": secret_type,
                    "match": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return results


def scan_file(path: str | Path) -> list[dict]:
    """Scan a single file for secret patterns.

    Args:
        path: Path to the file to scan.

    Returns:
        List of dicts with keys: type, match, start, end, file.
        Returns an empty list when no secrets are found.
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.warning("secret_scan: cannot read file %s", file_path)
        return []

    findings = scan_text(text)
    for finding in findings:
        finding["file"] = str(file_path)

    if findings:
        logger.warning(
            "secret_scan: %d secret(s) found in %s", len(findings), file_path
        )
    return findings


def scan_directory(
    directory: str | Path,
    extensions: list[str] | None = None,
) -> list[dict]:
    """Recursively scan a directory for secret patterns.

    Skips `.git/` and `.venv/` subdirectories automatically.

    Args:
        directory: Root directory to scan.
        extensions: Optional list of file extensions to include (e.g. [".py", ".env"]).
                    When None, all files are scanned.

    Returns:
        Aggregated list of findings from all scanned files.
    """
    root = Path(directory)
    results: list[dict] = []

    for file_path in root.rglob("*"):
        # Skip non-files
        if not file_path.is_file():
            continue

        # Skip excluded directories (check every component of the relative path)
        relative = file_path.relative_to(root)
        if any(part in _SKIP_DIRS for part in relative.parts):
            continue

        # Filter by extension when requested
        if extensions is not None and file_path.suffix not in extensions:
            continue

        results.extend(scan_file(file_path))

    return results
