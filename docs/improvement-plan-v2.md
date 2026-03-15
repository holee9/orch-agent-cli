# Phase 3 개선 계획 (improvement-plan-v2.md)

**작성일**: 2026-03-15
**기반**: validation-report-v2.md의 검증 결과

---

## 성공 결과 보호 전략 (성공한 결과 보호)

각 검증된 성공 항목에 대해 미래의 회귀를 방지하는 테스트/가드 수립.

### 1. 4-터미널 파이프라인 보호

**성공 항목**: T1 (Orchestrator) → T2 (Planner) → T3 (Developer) → T4 (Tester) 역할 분리 완전 검증

**회귀 방지 전략**:
- E2E 통합 테스트 추가: `tests/e2e/test_4terminal_pipeline.py`
- 테스트 내용:
  - GitHub Issue 생성 → webhook 감지 → TASK 생성
  - TASK 자동 할당 (claude, codex, gemini 중 선택)
  - 각 에이전트 역할 순차 실행 검증
  - 최종 결과물(코드, 테스트, 리뷰) 존재 확인
- 실행: CI/CD 파이프라인에서 매 커밋마다 실행
- 목표: 100% 파이프라인 완료율

---

### 2. GitHub Issue 트리거 보호

**성공 항목**: GitHub Issue → webhook → agent 자동 할당 파이프라인 작동

**회귀 방지 전략**:
- Webhook 이벤트 포맷 문서화: `docs/webhook-event-format.md`
  - 예상 JSON 스키마
  - 필수 필드 및 선택 필드
  - 테스트 이벤트 샘플
- Unit test: `tests/unit/test_webhook_processor.py`
  - 웹훅 페이로드 검증
  - TASK 생성 로직 검증
  - 에이전트 할당 로직 검증
- 모니터링: 웹훅 처리 성공률 추적

---

### 3. Phase 3 기능 보호 (PID lock, hot-reload, UTC 타임스탬프)

**성공 항목**: 모든 Phase 3 기능이 정상 작동

**회귀 방지 전략**:

기존 unit test 활용:
- `tests/unit/test_multi_orchestrator.py` ← PID lock 테스트
- `tests/unit/test_reliability_tracker.py` ← hot-reload 테스트
- `tests/unit/test_webhook_server.py` ← UTC 타임스탬프 테스트

추가 필요 사항:
- 각 테스트 케이스에 명시적 Phase 3 기능 검증 코멘트 추가
- CI/CD 체크: Phase 3 기능 테스트 실패 시 병합 차단

---

### 4. 에이전트 역할 분리 보호

**성공 항목**: 4개 에이전트가 명확히 분리된 역할 수행

**회귀 방지 전략**:
- `agents.json`에서 `primary_stages` 설정 고정
  - Planner: plan, review
  - Developer: implement
  - Tester: test
  - 중복 할당 금지
- Schema validation test: `tests/unit/test_agents_schema.py` 추가
  - agents.json 스키마 검증
  - primary_stages 중복 검사
  - 역할 누락 검사
- 위반 시: 배포 전 자동 거부

---

## 개선 계획 (P1 ~ P6)

### P1 — BUG-1 수정: setup_labels.py 누락 레이블

**상태**: ✅ 완료됨

**완료 내용**:
- GitHub에 3개 레이블 수동 생성:
  - `consensus:escalate`
  - `status:human-needed`
  - `type:escalation`
- `setup_labels.py` 업데이트 완료

**추가 작업**:
- 테스트 추가: `tests/unit/test_setup_labels.py`
  - `setup_labels.py`의 LABELS 리스트에 3개 레이블 포함 확인
  - `orchestrator.py`에서 참조하는 모든 레이블이 LABELS에 존재하는지 검증
  - 누락된 레이블 자동 감지

**예상 시간**: 1시간
**우선순위**: P1 (회귀 방지)

---

### P2 — BUG-2 수정: 오프라인 환경 빌드 톨러런스

**문제**: `golang.org/x/crypto` 모듈 다운로드 차단 → 불필요한 점수 분산 → 상향 보고

**근본 원인**: 빌드 환경 검증 없이 Codex 실행

**해결 방안 A (권장)**: 빌드 환경 사전 검사

1. `build_env_check()` 함수 추가: `src/orchestrator/core/checkers.py`
   - Go 프록시 접근성 검사 (`curl -s https://proxy.golang.org/...`)
   - 의존성 캐시 확인
   - 오프라인 모드 감지

2. Codex 실행 전 검사:
   - 결과 `build_verified: true/false` 저장

3. Completion signal에 포함:
   ```json
   {
     "agent": "codex",
     "build_verified": false,
     "reason": "go proxy blocked"
   }
   ```

4. Consensus에서 점수 분산 계산:
   ```python
   if completion["build_verified"] == false:
     dispersion_threshold = 30  # 기본값 20에서 상향
   ```

**해결 방안 B**: 임계값 상향

- `config.yaml`에서 `consensus.dispersion_alert_threshold` 값 조정
- 20 → 30으로 변경
- (방안 A보다 덜 선호: 근본 원인 미해결)

**선택**: **방안 A 권장**

**구현 파일**:
- `src/orchestrator/core/checkers.py` (새 파일)
- `src/orchestrator/tasks/completion.py` (수정)
- `src/orchestrator/consensus/consensus.py` (수정)

**테스트**:
- Unit test: `tests/unit/test_build_env_check.py`
  - 프록시 차단 시뮬레이션
  - build_verified 플래그 검증
  - Consensus 점수 분산 재계산 검증

**SPEC**: SPEC-P3-003
**우선순위**: P2 (빌드 안정성)
**예상 시간**: 2시간

---

### P3 — BUG-3 수정: Escalation 이슈 중복 생성

**문제**: 동일 Issue에 대해 중복 상향 보고 이슈 #6, #7 생성

**근본 원인**: `_create_escalation_issue()` 함수에 중복 방지 로직 없음

**해결 방안**: Deduplication 로직 추가

1. `_create_escalation_issue()` 함수 수정 위치:
   - `src/orchestrator/integrations/github_client.py`

2. 구현:
   ```python
   def _create_escalation_issue(issue_number, reason):
       # 기존 열린 상향 이슈 검색
       query = f'label:type:escalation in:open "Issue #{issue_number}"'
       existing = self.search_issues(query)

       if existing:
           logger.warning(f"Escalation issue already exists for #{issue_number}")
           return existing[0].number

       # 신규 생성
       title = f"[ESCALATION] Issue #{issue_number}"
       body = f"Consensus score dispersion threshold exceeded.\n\n{reason}"
       return self.create_issue(title, body, labels=["type:escalation"])
   ```

3. 검사 조건:
   - Issue 번호 매칭
   - `type:escalation` 레이블 포함
   - Status: open만 고려
   - 이미 존재하면 로깅만 하고 반환

**테스트**:
- Unit test: `tests/unit/test_escalation_dedup.py`
  - 첫 번째 상향: 신규 이슈 생성 ✅
  - 두 번째 상향: 기존 이슈 반환, 신규 생성 안 함 ✅
  - 닫힌 상향 이슈: 신규 생성 ✅

**SPEC**: SPEC-P3-003
**우선순위**: P1 (GitHub 계정 혼란 방지)
**예상 시간**: 1.5시간

---

### P4 — Zombie 프로세스 정리

**문제**: 이전 세션에서 T 상태(stopped) orchestrator 9개 발견

**원인**: PID lock이 중지된 프로세스를 정리하지 않음

**해결 방안**: 시작 시 기존 프로세스 종료

1. `start_t1.sh` 수정:
   ```bash
   # PID lock 생성 전에 기존 T-state 프로세스 정리
   pkill -f "python.*orchestrator" || true

   # 또는 더 세밀하게:
   ps aux | grep orchestrator | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true
   ```

2. Pre-flight check 추가:
   - `.orchestra/pid/` 디렉토리의 stale PID 파일 정리
   - 해당 PID 프로세스 존재 확인
   - 존재하지 않으면 PID 파일 삭제

**구현 파일**: `scripts/start_t1.sh`

**테스트**: Manual test (자동화 불가)

**우선순위**: P2 (리소스 정리)
**예상 시간**: 1시간

---

### P5 — 웹훅 경로 문서화

**문제**: 코드와 문서의 웹훅 경로 불일치

**해결 방안**: 명확한 문서화

1. 문서 작성: `docs/webhook-event-format.md`
   - 웹훅 이벤트 JSON 스키마
   - 파일 경로: `.orchestra/cache/webhook_events/`
   - 예제 이벤트 JSON
   - 테스트 이벤트 생성 방법

2. README 업데이트:
   - Quick Start 섹션에 웹훅 설정 추가
   - Deployment 가이드에 웹훅 경로 명시

3. 배포 가이드 추가:
   - `.orchestra/cache/webhook_events/` 디렉토리 생성 확인
   - 파일 권한 설정 (0755)

**우선순위**: P3 (배포 명확성)
**예상 시간**: 1시간

---

### P6 — 로그 파일 분리

**문제**: Live orchestrator와 pytest가 동일 로그 파일에 기록 → 출력 혼란

**해결 방안**: 환경별 로그 경로 분리

1. CLI 인자 추가:
   ```bash
   python -m orch_agent_cli.orchestrator --log-file /path/to/custom.log
   ```

2. 또는 환경변수:
   ```bash
   export ORCHESTRATOR_LOG_FILE=/custom/path/orchestrator.log
   orchestrator start
   ```

3. 또는 자동 분리 (권장):
   - Live orchestrator: `.orchestra/logs/orchestrator-live.log`
   - Pytest: `.orchestra/logs/orchestrator-test.log`
   - 로깅 설정에서 실행 모드 감지

**구현 파일**: `src/orchestrator/core/logging.py`

**우선순위**: P3 (디버깅 편의성)
**예상 시간**: 1.5시간

---

## 우선순위 매트릭스

| 이슈 | 우선순위 | 난이도 | 영향도 | 예상 시간 |
|------|---------|--------|--------|---------|
| BUG-1 (레이블) | P1 | Low | Critical | 1h |
| BUG-3 (중복) | P1 | Low | High | 1.5h |
| BUG-2 (오프라인) | P2 | Medium | Medium | 2h |
| Zombie 정리 | P2 | Low | Medium | 1h |
| 웹훅 문서화 | P3 | Low | Low | 1h |
| 로그 분리 | P3 | Medium | Low | 1.5h |

---

## 실행 순서

### Phase 3 Sprint

**Week 1**:
1. P1 BUG-1 수정 + 테스트 ✅
2. P1 BUG-3 수정 + 테스트
3. P2 BUG-2 수정 + 테스트

**Week 2**:
4. P2 Zombie 정리
5. P3 웹훅 문서화
6. P3 로그 분리

**총 예상 시간**: 9.5시간
**예상 완료**: 2026-03-22

---

## 테스트 계획

### Unit Test 추가

```
tests/unit/
  ├── test_setup_labels.py          (P1)
  ├── test_escalation_dedup.py      (P1)
  ├── test_build_env_check.py       (P2)
  └── test_agents_schema.py         (P4)
```

### E2E Test 추가

```
tests/e2e/
  └── test_4terminal_pipeline.py    (보호 전략 1)
```

### Manual Test

- Zombie 프로세스 정리 (P4)
- 웹훅 이벤트 처리 (P5)

---

## 회귀 방지 검리스트

- [ ] P1 BUG-1 레이블 테스트 추가
- [ ] P1 BUG-3 중복 방지 테스트 추가
- [ ] P2 BUG-2 빌드 환경 검사 테스트 추가
- [ ] Phase 3 기능 테스트 명시 업데이트
- [ ] E2E 4-터미널 파이프라인 테스트 추가
- [ ] agents.json 스키마 검증 테스트 추가
- [ ] CI/CD 파이프라인에 모든 테스트 추가
- [ ] 배포 전 모든 테스트 통과 확인

---

## 성공 지표

| 지표 | 목표 | 현재 | 목표 달성 일정 |
|------|------|------|----------------|
| BUG-1 수정율 | 100% | 100% | ✅ 완료 |
| BUG-2 수정율 | 100% | 0% | 2026-03-17 |
| BUG-3 수정율 | 100% | 0% | 2026-03-16 |
| E2E 파이프라인 성공율 | 100% | 88% (분산 이슈로 상향 보고) | 2026-03-22 |
| 회귀 테스트 추가 | 6개 이상 | 0개 | 2026-03-22 |
| Phase 3 안정성 | 100% | 100% | ✅ 유지 |

---

## 결론

Phase 3 E2E 검증에서 4-터미널 파이프라인과 GitHub Issue 트리거가 성공적으로 작동함을 확인했습니다.

BUG-1은 이미 해결되었고, BUG-2와 BUG-3는 즉시 수정해야 할 중대 항목입니다.

이 개선 계획을 따르면 2026-03-22까지 모든 Phase 3 기능이 안정적으로 작동하며, 회귀 테스트를 통해 미래의 안정성이 보장될 것입니다.

