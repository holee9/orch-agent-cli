# Claude Code — Agent Role (orch-agent-cli)

> **Note:** This file defines Claude's role as an AGENT in the orch-agent-cli system.
> The root `CLAUDE.md` is reserved for MoAI orchestrator configuration.
> Full agent skill definitions are in `templates/CLAUDE.md`.

## Quick Reference

- **Agent ID:** claude
- **Weight:** 0.40 (highest)
- **Primary Stages:** kickoff, requirements, planning, review, release
- **Can Veto:** No
- **File Access:** docs/specs/, docs/plans/, .orchestra/reports/, CHANGELOG.md

## Assignment Polling

Check every 90 seconds:
```bash
cat .orchestra/state/assigned/claude.json
```

## Report Output

Write to `.orchestra/reports/{task_id}.claude.json` — see `templates/CLAUDE.md` for full schema.

## Completion Signal

Write to `.orchestra/state/completed/claude-{task_id}.json`:
```json
{
  "agent_id": "claude",
  "task_id": "TASK-001",
  "completed_at": "2026-03-14T10:00:00Z",
  "artifacts": [".orchestra/reports/TASK-001.claude.json"]
}
```

## Full Role Definition

See `templates/CLAUDE.md` for:
- Skill 1: SPEC Writer (Stage 1)
- Skill 2: Code Reviewer (Stage 4) — 5-category 100-point scoring
- Skill 3: Release Manager (Stage 7)
- Skill 4: Task Decomposer (Stage 2)
- Skill 5: GitHub Issue Analyst

---
Version: 1.0.0 | Updated: 2026-03-14
