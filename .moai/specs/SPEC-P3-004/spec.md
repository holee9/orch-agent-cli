# SPEC-P3-004: Consensus FAIL 후 자동 재할당 (Re-review Auto-Trigger)

## Metadata

| Field | Value |
|-------|-------|
| SPEC-ID | SPEC-P3-004 |
| Created | 2026-03-15 |
| Status | approved |
| Priority | P2 |
| Issue | TBD |

## Summary

3차 E2E 검증(2026-03-15)에서 발견된 구조적 갭: consensus 엔진이 `rework` 판정을 내린 후 오케스트레이터가 자동으로 에이전트에게 재할당하지 않아 파이프라인이 중단됨.

현재 동작: consensus → rework → **파이프라인 정지** (수동 주입 필요)
목표 동작: consensus → rework → orchestrator가 `re_review_count` 증가 후 이전 단계 에이전트에게 자동 재할당

## Problem Analysis

3차 검증 TASK-008 실행 중 확인된 현상:
1. consensus FAIL (ratio=0.26 < 0.90) → `action=rework` 기록
2. 오케스트레이터는 다음 poll에서 rework 상태를 감지했으나 **재할당 로직 없음**
3. `re_review_count` 증가 없이 상태 그대로 유지
4. 수동으로 `re_review_count=1`, claude 할당 파일 작성 후 진행

## Requirements (EARS Format)

### 자동 재할당

**REQ-001**: WHEN the consensus engine returns `action=rework` for a TASK, the orchestrator SHALL increment `re_review_count` by 1 and assign the task back to the primary review agent (the agent that submitted the most recent review report).

**REQ-002**: WHEN re-assigning for rework, the orchestrator SHALL write an assignment file for the target agent at `.orchestra/state/assigned/<agent_id>.json` with `stage=review` and `re_review_count=<n>`.

**REQ-003**: WHEN the orchestrator assigns a rework task, it SHALL post a comment on the GitHub Issue explaining the rework trigger (ratio, dispersion, re_review_count).

**REQ-004**: WHEN `re_review_count >= max_rereviews` (configured in `config.yaml`), the orchestrator SHALL NOT attempt another rework and instead escalate to human via `_create_escalation_issue()`.

**REQ-005**: WHEN a rework assignment is created, the orchestrator SHALL update the task state to `status=rework` in `.orchestra/state/tasks/<task_id>.json`.

### 재할당 대상 결정

**REQ-006**: The orchestrator SHALL determine the rework target agent as follows:
1. Primary: the agent assigned to the most recent `review` stage
2. Fallback: the agent with the highest `base_weight` in `config/agents.json`

**REQ-007**: IF the rework target agent is marked `available: false` in the runtime registry, the orchestrator SHALL select the next available agent by base_weight descending.

### 상태 일관성

**REQ-008**: WHEN rework assignment is written, the orchestrator SHALL clear the previous consensus result from `.orchestra/state/consensus/` to prevent stale data.

**REQ-009**: The re-assignment MUST be idempotent: calling the rework trigger twice for the same (task_id, re_review_count) SHALL produce only one assignment file.

## Acceptance Criteria

### AC-001: 자동 재할당 — rework 판정 후 assignment 생성
- Given: consensus returns `action=rework` for TASK-010
- When: orchestrator processes on next poll
- Then: `.orchestra/state/assigned/<primary_agent>.json` exists with `stage=review`, `re_review_count=1`
- And: GitHub Issue receives a rework comment

### AC-002: re_review_count 누적
- Given: rework occurs twice for TASK-010
- When: orchestrator processes second rework
- Then: assignment contains `re_review_count=2`

### AC-003: max_rereviews 초과 → escalate
- Given: `re_review_count=2`, `max_rereviews=2`
- When: consensus returns rework again
- Then: `_create_escalation_issue()` called, no new review assignment created

### AC-004: 이전 consensus 상태 초기화
- Given: previous consensus file exists for TASK-010
- When: rework assignment is written
- Then: old consensus file is removed or overwritten with `status=rework`

### AC-005: 멱등성 — 동일 rework 2회 호출
- Given: `_trigger_rework(task_id="TASK-010", re_review_count=1)` called twice
- When: second call
- Then: only one assignment file exists, GitHub comment posted once

### AC-006: 가용 에이전트 없음 → escalate
- Given: all agents are `available: false`
- When: rework assignment is attempted
- Then: escalation issue created, no assignment written

## Technical Approach

### New Method: `_trigger_rework(task_id, consensus_result)`

```
orchestrator._trigger_rework(task_id, consensus_result):
  1. Read current re_review_count from consensus result
  2. new_count = re_review_count + 1
  3. If new_count > max_rereviews: call _create_escalation_issue(), return
  4. Determine rework_agent (last review agent or highest base_weight)
  5. If rework_agent unavailable: call _create_escalation_issue(), return
  6. Write assignment file for rework_agent (stage=review, re_review_count=new_count)
  7. Clear old consensus file
  8. Update task state to rework
  9. Post GitHub comment with rework details
```

### Integration Point

In `orchestrator.py`, the existing consensus processing block:
```python
if result.action == "rework":
    # TODO (SPEC-P3-004): trigger re-assignment instead of stopping
    pass
```
→ Replace `pass` with `self._trigger_rework(task_id, result)`

### Files to Modify

| File | Change |
|------|--------|
| `scripts/orchestrator.py` | Add `_trigger_rework()` method; integrate into consensus processing loop |
| `scripts/state_manager.py` | Add `clear_consensus(task_id)` and `write_task_rework_status(task_id, count)` helpers |
| `tests/unit/test_rework_trigger.py` | Unit tests for AC-001 through AC-006 |

## Dependencies

- SPEC-P3-003 completed (escalation dedup guard must exist)
- `_create_escalation_issue()` with `_escalated_task_keys` dedup already implemented

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Infinite rework loop | `max_rereviews` hard cap → escalate |
| Duplicate assignments if poll races | Idempotency check (REQ-009) |
| Wrong agent re-assigned | Fallback chain (REQ-006, REQ-007) |
| Stale consensus data | Clear on rework (REQ-008) |
