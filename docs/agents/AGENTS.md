# AGENTS.md — Common Rules for All Agents

Shared protocol loaded by every agent in this repository.

## Role

All agents collaborate via the `.orchestra/` directory as a shared task board. Each agent operates autonomously within its defined scope and reports outcomes in a standard format.

## Scope

**CAN modify:**
- Files within your assigned stage scope (see per-agent docs)
- `.orchestra/tasks/` — task state transitions only
- `.orchestra/reports/` — your own report files only
- `.orchestra/logs/` — append-only

**CANNOT modify:**
- Another agent's report files
- `.orchestra/config/` — human-managed
- `.orchestra/consensus/` — orchestrator-managed
- CI/CD pipeline files (`.github/`, `Makefile`, etc.)

## Protocol

1. **Claim**: Read `backlog/` → pick lowest-numbered task → set `locked_by` atomically (rename to `in_progress/`)
2. **Execute**: Work only within permitted directories; commit per sub-task using conventional commit format
3. **Report**: Write `.orchestra/reports/{task_id}.{agent_id}.json` — schema: `{ task_id, agent_id, status, findings[], verdict, timestamp }`
4. **Close**: Move task to `review/` (implementation) or `done/` (review complete)
5. **Escalate**: After 2 failed review loops → append to `.orchestra/logs/escalations.log` and halt for human resolution

**Hard prohibitions:**
- Never bypass CI hooks (`--no-verify`, force-push to protected branches)
- Never commit secrets or API keys
- Never move a task to `done/` without a consensus record in `.orchestra/consensus/`
