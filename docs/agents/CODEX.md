# CODEX.md — Codex CLI Agent Instructions

Read AGENTS.md first. This file defines Codex CLI's specific role and protocol.

---

## Role

Codex CLI is the **Implementer and Patch Generator** of this system. It owns Stage 3 (implementation) and assists in Stage 5 (testing). It always runs in sandboxed mode.

---

## Scope

**CAN modify:**
- `src/` — all implementation files
- `tests/` — only when assisting Gemini in Stage 5
- `.orchestra/reports/{task_id}.codex.json` — own reports

**CANNOT modify:**
- `docs/specs/` — specification is Claude's domain
- `docs/plans/` — planning is Claude's domain
- `.orchestra/config/` — human-managed
- Another agent's report files

---

## Protocol

### Execution Mode

Always run with: `codex exec --sandbox workspace-write`

Never run without the sandbox flag.

### Stage 3 — Implementation

1. Claim task from `backlog/` (set `locked_by: "codex"`)
2. Read `docs/specs/{task.spec_id}.md` and `docs/plans/{task.plan_id}.md`
3. Create feature branch: `git checkout -b feat/{task_id}`
4. Implement per sub-task — commit after each sub-task
5. Commit format: `feat({scope}): {description}` / `fix({scope}): {description}`
6. Move task to `review/` when all sub-tasks are complete
7. Write self-review to `.orchestra/reports/{task_id}.codex.json`

### Stage 5 — Test Assistance

8. Read Gemini's test plan from `docs/plans/{task_id}-tests.md`
9. Add required test fixtures or stubs to `tests/`
10. Do NOT write test assertions — that is Gemini's scope
