# SPEC-P3-002: CLI 가용성 체크 및 브랜치 자동 생성

## Metadata

| Field | Value |
|-------|-------|
| SPEC-ID | SPEC-P3-002 |
| Created | 2026-03-15 |
| Status | approved |
| Priority | P3/P4 |
| issue_number | 0 |

## Summary

D-004: orchestrator 시작 시 AI agent CLI 가용성 자동 체크 및 미설치 시 경고/비활성화.
D-005: 오케스트레이터가 TASK 시작 시 feat/TASK-NNN 브랜치를 타겟 프로젝트에 직접 생성.

## Requirements (EARS Format)

### D-004 — CLI 가용성 체크

**REQ-001**: WHEN the orchestrator starts, it SHALL check whether each agent's CLI is available by running `<cli> --version` (e.g., `claude --version`, `codex --version`, `gemini --version`).

**REQ-002**: IF an agent's CLI is unavailable, the orchestrator SHALL log a WARNING with the agent name and the missing CLI, and mark that agent as `available: false` in the runtime agent registry (without modifying agents.json on disk).

**REQ-003**: IF all primary agents for a workflow stage are unavailable, the orchestrator SHALL log an ERROR and raise a RuntimeError during startup.

**REQ-004**: WHEN a CLI check is performed, the system SHALL treat any non-zero exit code or FileNotFoundError as "unavailable".

### D-005 — 브랜치 자동 생성

**REQ-005**: WHEN a kickoff assignment is created for a new TASK, the orchestrator SHALL create a `feat/TASK-NNN` branch in the target project directory using `git checkout -b feat/TASK-NNN` (or `git switch -c feat/TASK-NNN`).

**REQ-006**: IF the branch already exists, the orchestrator SHALL log a WARNING and skip branch creation (do not fail).

**REQ-007**: IF the target project path is not a git repository, the orchestrator SHALL log a WARNING and skip branch creation.

**REQ-008**: WHEN branch creation succeeds, the orchestrator SHALL log the branch name created.

## Acceptance Criteria

### AC-001: CLI check — available agent passes
- Given: `claude --version` exits with code 0
- When: orchestrator starts
- Then: claude agent is marked available, no warning emitted

### AC-002: CLI check — unavailable agent logs warning
- Given: `codex --version` returns non-zero or FileNotFoundError
- When: orchestrator starts
- Then: WARNING logged mentioning "codex" and "unavailable"
- And: codex agent marked `available: false` in runtime registry

### AC-003: CLI check — does not modify agents.json on disk
- Given: an agent CLI is unavailable
- When: orchestrator starts
- Then: `config/agents.json` on disk is NOT modified

### AC-004: Branch creation — success path
- Given: target project is a git repo, branch `feat/TASK-004` does not exist
- When: kickoff assignment for issue #4 is created
- Then: branch `feat/TASK-004` is created in target project
- And: log entry contains "feat/TASK-004"

### AC-005: Branch creation — existing branch skipped
- Given: branch `feat/TASK-004` already exists
- When: kickoff assignment for issue #4 is created
- Then: WARNING logged, no error raised, orchestrator continues

### AC-006: Branch creation — non-git directory skipped
- Given: target project path exists but is not a git repo
- When: kickoff assignment is created
- Then: WARNING logged, no error raised

## Technical Approach

### Files to Modify

- `scripts/orchestrator.py`
  - Add `check_agent_availability(agents: list[dict]) -> list[dict]` module-level function
  - Call in `Orchestrator.__init__()` after `_load_agents()`
  - Add `_create_task_branch(task_id: str) -> None` instance method
  - Call in `_create_kickoff_assignment()` after writing assignment

### Key Implementation Notes

**CLI check:**
```python
import subprocess
def _check_cli(cli: str) -> bool:
    try:
        result = subprocess.run([cli, "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
```

**Branch creation:**
```python
import subprocess
def _create_task_branch(self, task_id: str) -> None:
    target = Path(self.config["orchestrator"]["target_project_path"])
    if not (target / ".git").exists():
        logger.warning("Target is not a git repo, skipping branch creation")
        return
    branch = f"feat/{task_id}"
    result = subprocess.run(["git", "switch", "-c", branch], cwd=target, capture_output=True, text=True)
    if result.returncode != 0 and "already exists" in result.stderr:
        logger.warning("Branch %s already exists, skipping", branch)
    elif result.returncode != 0:
        logger.warning("Branch creation failed: %s", result.stderr.strip())
    else:
        logger.info("Created branch: %s", branch)
```

### Files to Create

- `tests/test_orchestrator_env.py` — TDD tests for all ACs above

## Out of Scope

- D-006: my-login session cookie (target project, separate repo)
- Automatic agent reassignment when primary unavailable (future SPEC)
