# Repository Guidelines

## Project Structure & Module Organization

`scripts/` contains the installable CLI modules and core logic: `orchestrator.py`, `consensus.py`, `github_client.py`, `webhook_server.py`, `dashboard.py`, and supporting utilities. Keep runtime rules and defaults in `config/`, and JSON contracts in `schemas/`. `templates/` holds files copied into target repositories, including starter agent docs and `setup.sh`. Tests live in `tests/`: top-level `test_*.py` files cover integration-style behavior, `tests/unit/` holds focused module tests, `tests/e2e/` exercises workflow scenarios, and `tests/fixtures/` stores reusable sample data. Generated state such as `.orchestra/` and `inbox/` is operational output, not source.

## Build, Test, and Development Commands

Use `python -m pip install -e ".[dev]"` for local development and `python -m pip install -e ".[dev,dashboard]"` when working on the Rich dashboard. Run `pytest` for the full suite, `pytest tests/unit -q` for fast unit checks, and `pytest tests/e2e -q` for orchestration flows. Use `pytest --cov=scripts --cov-report=term-missing` to inspect coverage on the shipped modules. Run `ruff check .` before opening a PR. Start the main daemon with `orch-agent` or `python scripts/orchestrator.py`; bootstrap labels with `python scripts/setup_labels.py owner/repo`.

## Coding Style & Naming Conventions

Target Python 3.10+ syntax, keep 4-space indentation, and stay within Ruff’s 100-character line length. Follow the existing naming patterns: `snake_case` for files, functions, and tests; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants. Prefer type hints, `pathlib.Path`, and `logging` instead of `print()`. Keep docstrings short and factual.

## Testing Guidelines

Add or update tests whenever `scripts/`, `config/`, or schema-driven behavior changes. Name files `test_<module>.py` and test functions `test_<behavior>`. Mock `gh` CLI calls and filesystem writes instead of hitting external services. Coverage currently fails below 75% in `pyproject.toml`; treat that as a floor, not a target, and cover failure paths as well as happy paths.

## Commit & Pull Request Guidelines

Recent history follows Conventional Commit prefixes such as `feat:`, `fix:`, `docs:`, and `refactor:`. Keep subjects concise and outcome-focused, for example `fix: harden webhook signature validation`. PRs should explain the orchestration scenario affected, call out any changes to `config/`, `schemas/`, or `templates/`, and list the verification commands you ran. Include sample CLI output or dashboard screenshots when changing operator-facing flows.

## Security & Configuration Tips

`gh` CLI authentication is required for live GitHub operations. Prefer environment variables such as `GITHUB_REPO` and `TARGET_PROJECT_PATH` over hard-coded local paths. Never commit `.env`, `.orchestra/`, inbox contents, or logs; they are already ignored for a reason.
