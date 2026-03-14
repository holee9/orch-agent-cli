"""Unit tests for scripts/secret_scan.py."""

from __future__ import annotations

from pathlib import Path

from scripts.secret_scan import scan_directory, scan_file, scan_text

# ---------------------------------------------------------------------------
# scan_text tests
# ---------------------------------------------------------------------------


def test_scan_text_finds_github_token() -> None:
    """scan_text should detect a ghp_ GitHub personal access token."""
    token = "ghp_" + "A" * 36
    text = f"Authorization: Bearer {token}"

    results = scan_text(text)

    assert len(results) == 1
    assert results[0]["type"] == "github_token"
    assert results[0]["match"] == token


def test_scan_text_finds_aws_key() -> None:
    """scan_text should detect an AKIA AWS access key."""
    aws_key = "AKIA" + "A0Z1B2C3D4E5F6G7"
    text = f"AWS_ACCESS_KEY_ID={aws_key}"

    results = scan_text(text)

    assert len(results) == 1
    assert results[0]["type"] == "aws_key"
    assert results[0]["match"] == aws_key


def test_scan_text_no_secrets() -> None:
    """scan_text should return an empty list for clean text."""
    text = "This is a perfectly normal configuration file with no secrets."

    results = scan_text(text)

    assert results == []


# ---------------------------------------------------------------------------
# scan_file tests
# ---------------------------------------------------------------------------


def test_scan_file(tmp_path: Path) -> None:
    """scan_file should find a secret written to a real file."""
    token = "ghp_" + "B" * 36
    secret_file = tmp_path / "config.env"
    secret_file.write_text(f"GITHUB_TOKEN={token}\n")

    results = scan_file(secret_file)

    assert len(results) == 1
    assert results[0]["type"] == "github_token"
    assert results[0]["file"] == str(secret_file)


# ---------------------------------------------------------------------------
# scan_directory tests
# ---------------------------------------------------------------------------


def test_scan_directory(tmp_path: Path) -> None:
    """scan_directory should find secrets in 1 of 2 files."""
    token = "ghp_" + "C" * 36
    (tmp_path / "secrets.env").write_text(f"GITHUB_TOKEN={token}\n")
    (tmp_path / "clean.txt").write_text("nothing to see here\n")

    results = scan_directory(tmp_path)

    assert len(results) == 1
    assert results[0]["type"] == "github_token"


def test_scan_directory_skips_venv(tmp_path: Path) -> None:
    """scan_directory must not scan files inside a .venv/ subdirectory."""
    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    token = "ghp_" + "D" * 36
    (venv_dir / "secrets.py").write_text(f"TOKEN = '{token}'\n")

    results = scan_directory(tmp_path)

    assert results == []
