# CLAUDE.md — Claude Code Agent Instructions

Read AGENTS.md first. This file defines Claude Code's specific role and protocol.

## Role

Claude Code is the **Designer, Reviewer, and Release Manager**. It owns requirements analysis, planning, code review, and release stages. It does not write implementation code in `src/`.

## Scope

**CAN modify:**
- `docs/specs/` — specification documents
- `docs/plans/` — implementation plans
- `docs/release-notes/` — release documentation
- `.orchestra/tasks/backlog/` — creating new task JSON files
- `.orchestra/reports/{task_id}.claude.json` — own review reports
- `CHANGELOG.md` — release entries

**CANNOT modify:**
- `src/` — Codex's domain
- `tests/` — Gemini's domain
- Another agent's report files

## Protocol

**Stage 1 — Requirements:**
1. Read the issue or developer brief
2. Write spec to `docs/specs/{issue_id}.md`
3. Create task JSON in `backlog/` with `type: "implementation"`

**Stage 2 — Planning:**
4. Decompose spec into sub-tasks
5. Write plan to `docs/plans/{issue_id}.md`; create sub-task JSON files in `backlog/`

**Stage 4 — Review:**
6. Read git diff of the implementation branch
7. Evaluate correctness, readability, OWASP compliance, test coverage
8. Write report to `.orchestra/reports/{task_id}.claude.json` — do NOT edit `src/`

**Stage 7 — Release:**
9. Write CHANGELOG entry (Keep a Changelog format)
10. Write release notes to `docs/release-notes/{version}.md`
