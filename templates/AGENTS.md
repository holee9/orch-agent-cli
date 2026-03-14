# Common Agent Protocol

Shared communication and execution rules for all agents in the multi-AI orchestration system (Claude Code, Codex CLI, Gemini CLI).

## Communication Protocol

### Polling and State Management

All agents poll `.orchestra/state/assigned/{agent_id}.json` every 60-120 seconds with random jitter to avoid thundering herd. Poll timeout is 180 seconds; treat non-responsive assignments as stale.

State file schema:
```json
{
  "agent_id": "claude|codex|gemini",
  "task_id": "TASK-001",
  "action": "analyze|implement|test|review",
  "spec_path": "docs/specs/SPEC-XXX.md",
  "plan_path": "docs/plans/PLAN-XXX.md",
  "assigned_at": "2026-03-14T10:30:00Z",
  "deadline": "2026-03-14T12:30:00Z",
  "context": { /* task-specific context */ }
}
```

### GitHub Issue Comments

All GitHub Issue comments MUST be in English. Comment format is mandatory:

```
## [Agent: {agent_id}] {Action} Result

**Verdict:** {ready|not_ready|approved|needs_revision|blocked}
**Confidence:** {0.0-1.0}
**Findings:**
- Finding 1
- Finding 2

**Blockers:** (if any)
- Blocker 1
```

Verdicts by action:
- analyze/fact-check: approved | needs_revision
- implement: (internal only, no GitHub comment)
- test: ready | not_ready
- review: ready | not_ready | blocked

### Completion Signal

Upon task completion, write to `.orchestra/state/completed/{agent_id}-{task_id}.json`:

```json
{
  "agent_id": "claude",
  "task_id": "TASK-001",
  "completed_at": "2026-03-14T11:45:00Z",
  "status": "success",
  "report_path": ".orchestra/reports/TASK-001.claude.json"
}
```

## File Scope Enforcement

### By Development Stage

**Stage 1 (Specification)** - No code modifications
- Claude writes SPEC files to `docs/specs/`
- No agent modifies `src/` or `tests/`

**Stage 2 (Planning)** - No code modifications
- Claude writes PLAN files to `docs/plans/`
- No agent modifies `src/` or `tests/`

**Stage 3 (Implementation)** - Codex only
- Codex modifies `src/` with sandboxed `codex exec --sandbox workspace-write`
- Claude and Gemini do NOT modify `src/`
- No agent modifies `tests/` or `docs/specs/` or `docs/plans/`

**Stage 4 (Review)** - No code modifications
- Claude reads `src/` and `tests/`, generates review report
- Gemini reads `src/` for security analysis
- NO agent modifies `src/` or `tests/`

**Stage 5 (Testing)** - Gemini and Codex only
- Gemini writes tests to `tests/`
- Codex creates test fixtures in `tests/conftest.py`
- Claude does NOT modify `tests/`

**Stage 7 (Release)** - Claude only
- Claude writes CHANGELOG.md and release notes
- Codex and Gemini do NOT modify release files

## Report Schema Compliance

All reports MUST validate against `release_readiness.schema.json` before writing.

### File Naming Convention

Report path format: `.orchestra/reports/{task_id}.{agent_id}.json`

Examples:
- `.orchestra/reports/TASK-001.claude.json`
- `.orchestra/reports/TASK-001.codex.json`
- `.orchestra/reports/TASK-001.gemini.json`

### Required Fields (All Reports)

Every report MUST contain:
- `agent_id`: "claude" | "codex" | "gemini"
- `task_id`: "TASK-XXX" (matches assignment)
- `timestamp`: ISO 8601 datetime when report generated
- `score`: integer 0-100 (normalized quality metric)
- `confidence`: float 0.0-1.0 (agent certainty level)
- `vote`: "ready" | "not_ready" | "approved" | "needs_revision" | "blocked"
- `blockers`: string[] (blockers preventing progression)
- `evidence`: object[] (supporting findings with source references)

### Evidence Structure

Each evidence object contains:
```json
{
  "source": "file path or rule reference",
  "finding": "description of finding",
  "severity": "critical|warning|info",
  "line_numbers": [42, 43, 44]
}
```

### Full Report Example

```json
{
  "agent_id": "claude",
  "task_id": "TASK-001",
  "timestamp": "2026-03-14T11:45:00Z",
  "score": 85,
  "confidence": 0.92,
  "vote": "ready",
  "blockers": [],
  "evidence": [
    {
      "source": "src/auth/jwt.py:line 42",
      "finding": "JWT validation uses standard library signature checks",
      "severity": "info",
      "line_numbers": [42]
    }
  ]
}
```

## Prohibitions (Hard Rules)

### Git and CI

- NEVER bypass CI hooks or force-push to main/master
- NEVER skip pre-commit hooks with --no-verify
- NEVER skip GPG signing with --no-gpg-sign unless explicitly authorized
- NEVER run `git push --force` (escalate to human if needed)

### Secrets and Security

- NEVER commit secrets, API keys, or credentials
- NEVER store passwords in code or config files
- NEVER push .env files or sensitive credentials to repository
- Fail immediately if secrets are detected in staged changes

### Report Integrity

- NEVER modify another agent's report file
- NEVER falsify confidence scores or evidence
- NEVER remove blockers without resolving root cause
- NEVER post GitHub comments without agent attribution [Agent: {id}]

### Language and Communication

- NEVER post non-English GitHub comments (translate if needed)
- NEVER use ambiguous verdicts (use exact: ready|not_ready|approved|needs_revision|blocked)
- NEVER comment without structured format (Verdict/Confidence/Findings/Blockers)

### Code Scope

- NEVER modify code outside assigned stage
- NEVER modify test files during implementation (Stage 3)
- NEVER modify docs/specs/ or docs/plans/ after approval
- NEVER modify .orchestra/config/ files

## Validation Checklist

Before each agent completes a task:

- [ ] All GitHub comments are in English
- [ ] GitHub comment follows [Agent: {id}] {Action} format
- [ ] Report file path matches `.orchestra/reports/{task_id}.{agent_id}.json`
- [ ] Report validates against `release_readiness.schema.json`
- [ ] All required fields present (agent_id, task_id, timestamp, score, confidence, vote, blockers, evidence)
- [ ] Confidence score is float 0.0-1.0 (not integer)
- [ ] Score is integer 0-100
- [ ] Vote is one of: ready|not_ready|approved|needs_revision|blocked
- [ ] Evidence array contains source, finding, severity, line_numbers
- [ ] No secrets or API keys in report
- [ ] Completion signal written to `.orchestra/state/completed/{agent_id}-{task_id}.json`
- [ ] No CI hooks bypassed
- [ ] No force-pushes to main/master
- [ ] File modifications respect stage scope enforcement
- [ ] All blockers have clear root causes or recovery paths

---

**Version:** 1.0.0
**Updated:** 2026-03-14
**All Agents:** Claude Code, Codex CLI, Gemini CLI
