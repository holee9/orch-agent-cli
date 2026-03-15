# SPEC-P3-003: BUG-2 / BUG-3 / P4 수정 및 검증 테스트

## Metadata

| Field | Value |
|-------|-------|
| SPEC-ID | SPEC-P3-003 |
| Created | 2026-03-15 |
| Status | completed |
| Priority | P1 |
| Commits | cea7159, f3b19b0, df02c83 |

## Summary

2차 E2E 검증(2026-03-15)에서 발견된 버그 3건 수정 및 P4(좀비 프로세스 정리) 개선.

- **BUG-2**: `environment_constrained` 에이전트의 점수가 consensus 분산(dispersion) 계산에 포함되어 오탐 발생
- **BUG-3**: `_create_escalation_issue()` 동일 agent/task에 대해 escalation GitHub Issue 중복 생성
- **P4**: `start_t1.sh` 재시작 시 T/Z 상태의 좀비/중지 프로세스를 정리하지 않음

## Requirements (EARS Format)

### BUG-2 — 환경 제약 에이전트 분산 오탐 수정

**REQ-001**: WHEN computing score dispersion for consensus, the system SHALL exclude votes with `environment_constrained=True` from the dispersion calculation, using only unconstrained votes when at least 2 unconstrained votes exist.

**REQ-002**: IF all votes are environment-constrained, the system SHALL fall back to using all votes for dispersion calculation (no division by zero or empty list).

**REQ-003**: WHEN `build_votes_from_reports()` reads agent reports, it SHALL propagate the `environment_constrained` flag from the report dict to the `AgentVote` dataclass.

**REQ-004**: Environment-constrained votes SHALL still participate in the voting ratio calculation (weight included, vote type counted).

### BUG-3 — 중복 에스컬레이션 이슈 방지

**REQ-005**: WHEN `_create_escalation_issue()` is called with the same `(agent_id, task_id)` combination a second time, the system SHALL return `None` and NOT call `github.create_issue` again.

**REQ-006**: The `Orchestrator.__init__` SHALL initialize `_escalated_task_keys: set[str]` to prevent duplicate escalation tracking.

**REQ-007**: WHEN creating a consensus escalation issue, the system SHALL check `_escalated_issue_numbers` before calling `github.create_issue` to prevent duplicate issues for the same issue number.

### P4 — 좀비 프로세스 자동 정리

**REQ-008**: WHEN `start_t1.sh` starts and finds an existing `python.*scripts.orchestrator` process, it SHALL check the process state via `ps -o state=`.

**REQ-009**: IF the process state is `T` (stopped) or `Z` (zombie), the script SHALL kill it with `kill -9` and continue startup.

**REQ-010**: IF the process state is running (not T or Z), the script SHALL print an error message and exit with code 1 to protect the running instance.

## Acceptance Criteria

### AC-001: BUG-2 — constrained 제외 후 분산 정상 계산
- Given: Claude(score=55, constrained=True), Codex(88), Gemini(95)
- When: `engine.compute()` is called
- Then: `dispersion_warning` is False (unconstrained dispersion = 95-88 = 7 ≤ 20)
- And: log contains "excluding environment-constrained agents ['claude']"

### AC-002: BUG-2 — constrained 투표도 ratio 포함
- Given: Claude(constrained, not_ready), Codex+Gemini(ready)
- When: `engine.compute()` is called
- Then: ratio = (Codex_weight + Gemini_weight) / total_weight < 1.0

### AC-003: BUG-2 — 전원 constrained fallback
- Given: All votes have `environment_constrained=True`
- When: `engine.compute()` is called
- Then: no exception raised; dispersion uses all votes

### AC-004: BUG-3 — 동일 agent/task 2회 호출 dedup
- Given: `_create_escalation_issue("timeout", {"agent_id":"codex", "task_id":"task-001"})` called twice
- When: second call
- Then: returns None, `github.create_issue` called exactly once

### AC-005: BUG-3 — 다른 task 별도 escalation 생성
- Given: task-A and task-B with same agent
- When: each is escalated
- Then: `github.create_issue` called twice, each returns distinct issue number

### AC-006: P4 — SIGSTOP 프로세스 kill 후 소멸
- Given: a `sleep 30` process in T state
- When: cleanup logic runs
- Then: process is killed and no longer visible in `ps`

## Implementation Files

| File | Change |
|------|--------|
| `scripts/consensus.py` | `AgentVote.environment_constrained: bool = False`; dispersion excludes constrained votes |
| `scripts/orchestrator.py` | `_escalated_task_keys: set[str]`; dedup in `_create_escalation_issue()`; `_escalated_issue_numbers: set[int]` in consensus path |
| `scripts/start_t1.sh` | pgrep-based zombie/stale process cleanup block before orchestrator start |
| `tests/test_consensus.py` | Tests T11–T14: BUG-2 regression coverage |
| `tests/unit/test_escalation.py` | 3 BUG-3 regression tests |
| `tests/unit/test_shell_scripts.py` | P4: bash syntax check + zombie cleanup logic content check |
| `scripts/verify_fixes.py` | Live verification script (16 scenarios) |

## Verification Results

### Unit Tests
- BUG-2: 4 tests added (T11–T14) — all passing ✅
- BUG-3: 3 tests added — all passing ✅
- P4: 4 tests added — all passing ✅

### Live Pipeline (3차 E2E 검증, 2026-03-15, TASK-008 on holee9/orch-test-target)

| Bug | Live Evidence | Status |
|-----|--------------|--------|
| BUG-2 | Log: `excluding environment-constrained agents ['claude']` at 09:18:51 | ✅ CONFIRMED |
| BUG-3 | Issue #8 → only escalation #9 created (vs #6+#7 before fix) | ✅ CONFIRMED |
| P4 | `verify_fixes.py` 16/16 pass; `bash -n` syntax check pass | ✅ CONFIRMED |

### Structural Gap Discovered

After consensus FAIL, the orchestrator has no logic to automatically re-assign the task for re-review.
Currently requires manual intervention (write assignment file directly).
→ Tracked in **SPEC-P3-004**.
