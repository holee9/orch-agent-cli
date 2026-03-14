# Multi-AI CLI Agent Orchestration — 구현 계획서

> **문서 버전:** v2.0  
> **작성일:** 2026-03-14  
> **기반 문서:** orche-agent.md (초안)  
> **운영 형태:** 다중 터미널에서 개별 실행되는 CLI 에이전트의 협업 오케스트레이션

---

## 목차

1. [운영 개념](#1-운영-개념)
2. [오케스트레이션 아키텍처](#2-오케스트레이션-아키텍처)
3. [제품개발 프로세스별 에이전트 운영](#3-제품개발-프로세스별-에이전트-운영)
4. [Phase별 구현 계획 및 체크리스트](#4-phase별-구현-계획-및-체크리스트)
5. [핵심 컴포넌트 상세 설계](#5-핵심-컴포넌트-상세-설계)
6. [잠재적 문제점 및 해소 방안](#6-잠재적-문제점-및-해소-방안)
7. [데모 시나리오](#7-데모-시나리오)
8. [부록: 워크플로우 다이어그램](#8-부록-워크플로우-다이어그램)

---

## 1. 운영 개념

### 1.1 핵심 전제

이 시스템은 GitHub Actions 같은 CI/CD 파이프라인 안에서 에이전트를 자동 호출하는 구조가 **아니다**.

**현실:** 개발자가 다중 터미널 창을 열고, 각 터미널에서 CLI 에이전트(Claude Code, Codex CLI, Gemini CLI)를 직접 실행한다. 각 에이전트는 동일한 Git 리포지토리를 작업 컨텍스트로 공유하며, 제품개발 프로세스(요구사항 → 설계 → 구현 → 리뷰 → 테스트 → 릴리스)의 각 단계에서 역할을 분담한다.

```
개발자 워크스테이션
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Terminal 1 (Claude Code)    Terminal 2 (Codex CLI)         │
│  ┌───────────────────────┐   ┌───────────────────────┐     │
│  │ $ claude              │   │ $ codex               │     │
│  │ > /review PR #42      │   │ > implement task-003  │     │
│  │ > write spec for...   │   │ > generate patch...   │     │
│  │                       │   │                       │     │
│  └───────────────────────┘   └───────────────────────┘     │
│                                                             │
│  Terminal 3 (Gemini CLI)     Terminal 4 (Orchestrator)      │
│  ┌───────────────────────┐   ┌───────────────────────┐     │
│  │ $ gemini              │   │ $ python orche.py     │     │
│  │ > enhance tests for   │   │ [watching task board]  │     │
│  │ > analyze coverage... │   │ [collecting reports]   │     │
│  │                       │   │ [computing consensus]  │     │
│  └───────────────────────┘   └───────────────────────┘     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Shared Git Repository (local)           │   │
│  │  /project-root                                       │   │
│  │  ├── src/          ← 에이전트들이 동시에 읽고 씀     │   │
│  │  ├── .orchestra/   ← 오케스트레이션 상태/태스크 보드  │   │
│  │  └── docs/         ← 스펙, 플랜, 리포트              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 CI/CD 자동화와의 관계

| 구분 | 역할 | 비고 |
|------|------|------|
| CLI 에이전트 (본 문서 범위) | 요구사항 분석, 설계, 구현, 리뷰, 테스트 작성 | 개발자가 터미널에서 직접 운영 |
| CI/CD (GitHub Actions 등) | 빌드, 린트, 보안 스캔, 배포 | 에이전트 작업 결과물을 검증하는 **별도 파이프라인** |

에이전트는 코드를 작성하고 리뷰하고 테스트를 만드는 **개발 참여자**이다. CI/CD는 그 결과물을 검증하는 **품질 게이트**이다. 이 둘은 분리된다.

### 1.3 에이전트 프로파일

| 에이전트 | CLI 도구 | 실행 방식 | 핵심 역할 |
|----------|----------|-----------|-----------|
| **Claude Code** | `claude` | 터미널 인터랙티브 / `claude -p` 비대화 | 설계자 + 리뷰어 + 릴리스 매니저 |
| **Codex CLI** | `codex` | `codex exec --sandbox workspace-write` | 구현자 + 패치 생성기 |
| **Gemini CLI** | `gemini` | 터미널 인터랙티브 / API 호출 | 테스트 강화 + 팩트체커 (Red Team) |

---

## 2. 오케스트레이션 아키텍처

### 2.1 파일 시스템 기반 태스크 보드

에이전트 간 협업은 **공유 리포지토리 내 `.orchestra/` 디렉토리**를 통해 이루어진다. 외부 서비스 의존 없이 파일 시스템 + Git만으로 상태를 관리한다.

```
.orchestra/
├── config/
│   ├── agents.json              # 에이전트 등록 및 가중치
│   ├── consensus.json           # 합의 임계값, 분산 한도
│   └── process.json             # 개발 프로세스 단계 정의
├── tasks/
│   ├── backlog/                 # 대기 중인 태스크
│   │   └── task-001.json
│   ├── in_progress/             # 에이전트가 작업 중
│   │   └── task-002.json        # locked_by: "codex"
│   ├── review/                  # 리뷰 대기
│   │   └── task-003.json
│   └── done/                    # 완료
│       └── task-000.json
├── reports/                     # 에이전트 평가 리포트
│   ├── task-003.claude.json
│   ├── task-003.codex.json
│   └── task-003.gemini.json
├── consensus/                   # 합의 결과
│   └── task-003.consensus.json
└── logs/                        # 에이전트 활동 로그
    ├── claude.log
    ├── codex.log
    └── gemini.log
```

### 2.2 태스크 라이프사이클

```
                    오케스트레이터 또는 개발자가 태스크 생성
                                    │
                                    ▼
┌──────────┐    에이전트가     ┌──────────────┐    작업 완료     ┌──────────┐
│ backlog/ │───────────────▶│ in_progress/ │────────────────▶│ review/  │
│          │    태스크 잠금    │ locked_by:   │    결과물 커밋    │          │
└──────────┘    (claim)       │ "codex"      │                  └────┬─────┘
                              └──────────────┘                       │
                                                          다른 에이전트가 리뷰
                                                          리포트 작성
                                                                     │
                                                                     ▼
                                                              ┌──────────┐
                                                              │  done/   │
                                                              │          │
                                                              └──────────┘
```

### 2.3 오케스트레이터의 역할

오케스트레이터(`scripts/orchestrator.py`)는 별도 터미널에서 상시 실행되는 경량 프로세스이다.

**하는 일:**
- `.orchestra/tasks/` 디렉토리를 감시 (file watcher)
- 태스크 상태 전이 검증 (올바른 순서로 이동했는지)
- `review/`에 도착한 태스크에 대해 리뷰 에이전트 지정
- 모든 리포트가 도착하면 `consensus.py` 실행
- 합의 결과를 `.orchestra/consensus/`에 기록
- 개발자에게 터미널 알림 (또는 파일 기반 알림)

**하지 않는 일:**
- 에이전트를 직접 실행하거나 종료하지 않음
- 코드를 수정하지 않음
- 배포하지 않음

### 2.4 에이전트 간 통신 메커니즘

```
Claude Code ──┐                          ┌── Claude Code
(spec 작성)   │    .orchestra/tasks/     │   (리뷰 수행)
              ├───▶ task-003.json ◀──────┤
Codex CLI ────┘    (파일 시스템이        └── Gemini CLI
(구현 수행)         메시지 버스 역할)         (테스트 작성)

동기화: Git commit + push (또는 로컬 file watch)
충돌 방지: 태스크 잠금 (locked_by 필드)
```

각 에이전트는 독립적으로 실행되며, 다음 두 가지 방법으로 태스크를 인지한다:

1. **Polling:** 에이전트의 CLAUDE.md / CODEX.md에 "작업 전 `.orchestra/tasks/backlog/`를 확인하라"는 지시
2. **Watch:** 오케스트레이터가 특정 에이전트에게 태스크를 할당하면, 해당 에이전트의 로그 파일에 알림 기록

---

## 3. 제품개발 프로세스별 에이전트 운영

### 3.1 프로세스 흐름과 에이전트 배치

```
제품개발 프로세스          담당 에이전트              실행 터미널        산출물
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 요구사항 분석     ●Claude Code              Terminal 1    docs/specs/*.md
   & 수용 기준       ○Gemini (팩트체크)        Terminal 3    task-xxx.json

        │
        ▼

2. 작업 분해         ●Claude Code              Terminal 1    docs/plans/*.md
   & 구현 계획       ○Codex (실현성 검증)      Terminal 2    sub-tasks 생성

        │
        ▼

3. 구현 / 패치       ●Codex CLI                Terminal 2    src/ 변경
   생성               ○Claude Code (보조)       Terminal 1    브랜치 + 커밋

        │
        ▼

4. 코드 리뷰         ●Claude Code              Terminal 1    reports/*.claude.json
   & 위험 분석       ○Gemini (보안 검증)       Terminal 3    reports/*.gemini.json

        │
        ▼

5. 테스트 강화       ●Gemini CLI               Terminal 3    tests/ 추가
   & 회귀 설계       ○Codex (테스트 구현)      Terminal 2    커버리지 증가

        │
        ▼

6. 합의 & 판정      오케스트레이터             Terminal 4    consensus/*.json
                     (자동 계산)                              PR ready 판정

        │
        ▼

7. 릴리스 준비       ●Claude Code              Terminal 1    CHANGELOG, 릴리스노트
                     ○Codex (배포 스크립트)    Terminal 2    deploy scripts

        │
        ▼

8. 인간 최종 승인    개발자                     —             merge + deploy
   & 배포

●= Primary    ○= Secondary
```

### 3.2 단계별 에이전트 실행 예시

#### Stage 1: 요구사항 분석 (Claude Code — Terminal 1)

```bash
# Terminal 1: Claude Code
$ claude
> 이슈 #42의 요구사항을 분석하고 docs/specs/issue-042.md에
  수용 기준을 작성해줘. 기존 코드베이스 구조를 참고해서
  영향 범위도 분석해.

# Claude Code가 수행하는 작업:
# 1. GitHub 이슈 내용 읽기
# 2. 코드베이스 탐색 (관련 파일 식별)
# 3. docs/specs/issue-042.md 작성
# 4. .orchestra/tasks/backlog/task-042-impl.json 생성
# 5. git add + commit
```

```bash
# Terminal 3: Gemini CLI (팩트체크)
$ gemini
> .orchestra/tasks/backlog/ 에 새 태스크가 있어.
  docs/specs/issue-042.md의 수용 기준이 기존 API 스펙과
  모순되는지 검증해줘.

# Gemini가 수행하는 작업:
# 1. 스펙 문서 읽기
# 2. 기존 API 문서/테스트와 교차 검증
# 3. .orchestra/reports/task-042-spec.gemini.json에 결과 기록
```

#### Stage 3: 구현 (Codex CLI — Terminal 2)

```bash
# Terminal 2: Codex CLI
$ codex exec --sandbox workspace-write \
    --prompt "docs/plans/task-042-plan.md에 따라 구현해줘. \
              각 sub-task별로 커밋을 분리하고, \
              구현 완료 후 .orchestra/tasks/in_progress/task-042-impl.json을 \
              review/ 로 이동해."

# Codex가 수행하는 작업:
# 1. 계획서 읽기
# 2. feature 브랜치에서 코드 구현
# 3. 단위 테스트 기본 작성
# 4. 커밋 분리 (sub-task 단위)
# 5. 태스크 상태를 review/로 이동
```

#### Stage 4: 코드 리뷰 (Claude Code — Terminal 1)

```bash
# Terminal 1: Claude Code
$ claude
> .orchestra/tasks/review/task-042-impl.json 태스크를 리뷰해줘.
  Codex가 구현한 변경사항의 diff를 분석하고,
  .orchestra/reports/task-042-impl.claude.json에
  release_readiness 스키마에 맞춰 리포트를 작성해.

# Claude Code가 수행하는 작업:
# 1. git diff 분석
# 2. 보안, 성능, 설계 관점 리뷰
# 3. JSON 리포트 작성 (score, vote, blockers, evidence)
```

#### Stage 6: 합의 (Orchestrator — Terminal 4)

```bash
# Terminal 4: Orchestrator (자동)
$ python scripts/orchestrator.py --watch

# 오케스트레이터가 자동 수행:
# [14:32:01] task-042-impl: 리포트 수집 중 (claude: ✓, codex: pending, gemini: ✓)
# [14:35:22] task-042-impl: 모든 리포트 도착
# [14:35:23] task-042-impl: 합의 계산 중...
# [14:35:23] task-042-impl: Consensus 94.2% (PASS) → PR ready
# [14:35:24] task-042-impl: → .orchestra/consensus/task-042-impl.consensus.json 기록
```

### 3.3 에이전트별 AGENTS.md 구조

각 에이전트가 리포지토리 컨텍스트를 올바르게 이해하도록, 루트에 역할 문서를 배치한다.

```
project-root/
├── AGENTS.md                  # 전체 오케스트레이션 규칙 (공통)
├── CLAUDE.md                  # Claude Code 전용 지시사항
├── CODEX.md                   # Codex CLI 전용 지시사항
├── GEMINI.md                  # Gemini CLI 전용 지시사항
```

**AGENTS.md (공통 규칙) 핵심 내용:**

```markdown
# 오케스트레이션 공통 규칙

## 태스크 관리
- 작업 전 반드시 .orchestra/tasks/backlog/ 확인
- 태스크 수령 시 locked_by에 자신의 agent_id 기록
- 작업 완료 시 태스크를 다음 단계 디렉토리로 이동
- 다른 에이전트가 잠근 태스크는 수정 금지

## 파일 충돌 방지
- 구현 에이전트만 src/ 수정 가능 (구현 단계에서)
- 리뷰 에이전트는 src/ 수정 불가, reports/에만 기록
- 테스트 에이전트만 tests/ 추가 가능 (테스트 단계에서)
- docs/는 해당 단계의 Primary 에이전트만 수정

## 리포트 형식
- 모든 리포트는 schemas/release_readiness.schema.json 준수
- 파일명: {task_id}.{agent_id}.json

## 금지 사항
- CI/테스트 실패를 무시하거나 override 금지
- 시크릿, 인증정보를 코드/리포트에 포함 금지
- 다른 에이전트의 리포트를 수정 금지
```

---

## 4. Phase별 구현 계획 및 체크리스트

### Phase 1: MVP (4–6주)

**목표:** 2개 에이전트(Claude Code + Codex CLI)로 기본 협업 루프 구축

#### 체크리스트

- [ ] **오케스트레이션 기반 구축**
  - [ ] `.orchestra/` 디렉토리 구조 생성
  - [ ] `config/agents.json` 작성 (에이전트 2개 등록)
  - [ ] `config/process.json` 작성 (개발 프로세스 6단계 정의)
  - [ ] 태스크 JSON 스키마 정의 (`schemas/task.schema.json`)
  - [ ] 리포트 JSON 스키마 정의 (`schemas/release_readiness.schema.json`)

- [ ] **에이전트 역할 문서**
  - [ ] `AGENTS.md` 공통 규칙 작성
  - [ ] `CLAUDE.md` 작성 (설계 + 리뷰 역할 지시)
  - [ ] `CODEX.md` 작성 (구현 + 패치 생성 역할 지시)

- [ ] **기본 오케스트레이터**
  - [ ] `scripts/orchestrator.py` 작성
  - [ ] 파일 시스템 watch (`.orchestra/tasks/` 감시)
  - [ ] 태스크 상태 전이 검증
  - [ ] 리포트 수집 → 합의 계산 트리거
  - [ ] 터미널 알림 출력

- [ ] **2-에이전트 협업 루프 검증**
  - [ ] Claude Code: 요구사항 → 스펙 → 태스크 생성
  - [ ] Codex CLI: 태스크 수령 → 구현 → 커밋
  - [ ] Claude Code: 코드 리뷰 → 리포트 작성
  - [ ] 오케스트레이터: 리포트 수집 → 합의 계산 (2 에이전트)

- [ ] **CI 연동 (별도 파이프라인)**
  - [ ] `.github/workflows/ci.yml`: 빌드, 테스트, 린트, 보안 스캔
  - [ ] CI 결과를 `.orchestra/reports/`에 자동 기록하는 스크립트

#### Phase 1 산출물

| 파일 | 설명 |
|------|------|
| `.orchestra/` 전체 구조 | 태스크 보드 + 리포트 + 합의 |
| `AGENTS.md`, `CLAUDE.md`, `CODEX.md` | 에이전트 역할 문서 |
| `scripts/orchestrator.py` | 파일 감시 + 합의 트리거 |
| `schemas/task.schema.json` | 태스크 정의 스키마 |
| `schemas/release_readiness.schema.json` | 리포트 스키마 |

---

### Phase 2: 3-에이전트 풀 가동 + 합의 엔진 (8–12주)

**목표:** Gemini CLI 추가, 가중 합의 알고리즘, 전체 프로세스 자동화

#### 체크리스트

- [ ] **Gemini CLI 통합**
  - [ ] `GEMINI.md` 작성 (테스트 강화 + Red Team 역할)
  - [ ] `config/agents.json` 업데이트 (3개 에이전트, 가중치 설정)
  - [ ] Gemini의 팩트체크 워크플로우 검증

- [ ] **합의 엔진 완성**
  - [ ] `scripts/consensus.py` 구현
  - [ ] 가중치: `effective_weight = base_weight × reliability × confidence`
  - [ ] 합의 비율: `Σ(w_i × ready_i) / Σ(w_i)` ≥ 0.9
  - [ ] Veto 처리: 즉시 차단 → re-review loop (최대 2회)
  - [ ] 점수 분산 감지: 편차 > 20pt → 추가 증거 수집 요청

- [ ] **프로세스 자동화**
  - [ ] 오케스트레이터: 단계 전이 시 다음 에이전트에 자동 할당
  - [ ] 태스크 잠금/해제 자동화
  - [ ] 리포트 도착 감지 → 합의 자동 계산
  - [ ] PR 자동 생성 (합의 통과 시)

- [ ] **신뢰도 추적 시작**
  - [ ] `config/agent_reliability.json` 초기화
  - [ ] 합의 통과 후 CI 결과 기반 신뢰도 업데이트 스크립트
  - [ ] 프로덕션 인시던트 연동 (수동 기록 → Phase 3에서 자동화)

- [ ] **개발자 UX**
  - [ ] `scripts/dashboard.py`: 터미널 기반 대시보드 (태스크 현황, 에이전트 상태)
  - [ ] `scripts/task_create.py`: 태스크 생성 CLI 도구
  - [ ] `scripts/report_view.py`: 합의 결과 조회

---

### Phase 3: 강화 및 운영 최적화 (8–12주)

**목표:** 신뢰도 피드백 루프, 비용 관리, 보안 거버넌스

#### 체크리스트

- [ ] **에이전트 신뢰도 자동 피드백**
  - [ ] 배포 성공/실패에 따른 자동 점수 조정
  - [ ] 에이전트별 히스토리컬 정확도 대시보드
  - [ ] 신뢰도 급락 시 가중치 자동 하향 + 알림

- [ ] **비용 관리**
  - [ ] 에이전트별 토큰 사용량 추적 (`.orchestra/logs/` 분석)
  - [ ] 태스크 규모별 에이전트 선택적 실행 (소규모 변경 → Claude만)
  - [ ] 프롬프트 최적화 (컨텍스트 길이 관리)

- [ ] **보안 거버넌스**
  - [ ] `docs/security/owasp_llm_matrix.md`: OWASP LLM Top 10 대응
  - [ ] `docs/security/nist_ssdf_policy.md`: NIST SSDF 정렬
  - [ ] 에이전트 출력물 시크릿 스캔 자동화
  - [ ] 프롬프트 인젝션 방어 테스트 (Red Team Gemini 활용)

- [ ] **확장 옵션 (선택)**
  - [ ] n8n 연동: Slack 알림, 외부 승인 흐름
  - [ ] GitHub Actions 연동: 합의 결과 → 자동 PR 라벨링
  - [ ] 웹 대시보드: `.orchestra/` 데이터 시각화

---

## 5. 핵심 컴포넌트 상세 설계

### 5.1 태스크 스키마 (task.schema.json)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "OrchestraTask",
  "type": "object",
  "required": ["task_id", "title", "stage", "created_at", "assigned_to"],
  "properties": {
    "task_id": { "type": "string", "pattern": "^task-[0-9]{3,}(-[a-z]+)?$" },
    "title": { "type": "string" },
    "description": { "type": "string" },
    "stage": {
      "type": "string",
      "enum": ["requirements", "planning", "implementation", "review", "testing", "consensus", "release"]
    },
    "priority": { "enum": ["critical", "high", "medium", "low"] },
    "assigned_to": {
      "type": "object",
      "properties": {
        "primary": { "enum": ["claude", "codex", "gemini", "orchestrator"] },
        "secondary": { "enum": ["claude", "codex", "gemini", null] }
      }
    },
    "locked_by": { "type": ["string", "null"] },
    "locked_at": { "type": ["string", "null"], "format": "date-time" },
    "source_issue": { "type": "string" },
    "depends_on": { "type": "array", "items": { "type": "string" } },
    "artifacts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "type": { "enum": ["spec", "plan", "code", "test", "report"] },
          "path": { "type": "string" }
        }
      }
    },
    "created_at": { "type": "string", "format": "date-time" },
    "updated_at": { "type": "string", "format": "date-time" }
  }
}
```

### 5.2 릴리스 준비 리포트 스키마 (release_readiness.schema.json)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgentReleaseReadiness",
  "type": "object",
  "required": ["agent_id", "task_id", "timestamp", "score", "confidence", "vote", "blockers", "evidence"],
  "properties": {
    "agent_id": { "type": "string", "enum": ["claude", "codex", "gemini"] },
    "task_id": { "type": "string" },
    "timestamp": { "type": "string", "format": "date-time" },
    "score": { "type": "integer", "minimum": 0, "maximum": 100 },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "vote": { "type": "string", "enum": ["ready", "not_ready", "veto"] },
    "stage_evaluated": {
      "type": "string",
      "enum": ["requirements", "planning", "implementation", "review", "testing"]
    },
    "blockers": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["severity", "description"],
        "properties": {
          "severity": { "enum": ["critical", "high", "medium", "low"] },
          "description": { "type": "string" },
          "file_path": { "type": "string" },
          "suggested_fix": { "type": "string" }
        }
      }
    },
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "reference"],
        "properties": {
          "type": { "enum": ["ci_report", "test_result", "security_scan", "coverage", "code_review", "spec_review"] },
          "reference": { "type": "string" },
          "summary": { "type": "string" }
        }
      }
    }
  }
}
```

### 5.3 합의 엔진

```python
# scripts/consensus.py

import json, sys
from dataclasses import dataclass
from pathlib import Path

CONSENSUS_THRESHOLD = 0.9
SCORE_READY_THRESHOLD = 90
DISPERSION_ALERT_THRESHOLD = 20

def load_config():
    agents = json.loads(Path(".orchestra/config/agents.json").read_text())
    return {a["id"]: a for a in agents["agents"]}

def load_reliability():
    path = Path(".orchestra/config/agent_reliability.json")
    if path.exists():
        return json.loads(path.read_text())
    return {}

@dataclass
class AgentReport:
    agent_id: str
    task_id: str
    score: int
    confidence: float
    vote: str
    blockers: list
    evidence: list

def compute_consensus(reports: list[AgentReport]) -> dict:
    config = load_config()
    reliability = load_reliability()

    # Veto 즉시 차단
    vetoes = [r for r in reports if r.vote == "veto"]
    if vetoes:
        return {
            "can_proceed": False,
            "ratio": 0.0,
            "reason": f"VETO by {[v.agent_id for v in vetoes]}",
            "action": "re-review (max 2회, 이후 인간 에스컬레이션)",
            "details": {r.agent_id: {"score": r.score, "vote": r.vote} for r in reports}
        }

    total_weight = 0.0
    ready_weight = 0.0
    scores = []
    details = {}

    for r in reports:
        agent_cfg = config.get(r.agent_id, {})
        base_w = agent_cfg.get("base_weight", 0.2)
        rel = reliability.get(r.agent_id, 1.0)
        effective_w = base_w * rel * r.confidence
        total_weight += effective_w
        scores.append(r.score)
        details[r.agent_id] = {
            "score": r.score, "vote": r.vote,
            "confidence": r.confidence, "effective_weight": round(effective_w, 4)
        }

        if r.score >= SCORE_READY_THRESHOLD and r.vote == "ready":
            ready_weight += effective_w

    ratio = ready_weight / total_weight if total_weight > 0 else 0

    # 점수 분산
    if len(scores) > 1 and (max(scores) - min(scores)) > DISPERSION_ALERT_THRESHOLD:
        return {
            "can_proceed": False,
            "ratio": round(ratio, 4),
            "reason": f"Score dispersion: {scores} (max gap > {DISPERSION_ALERT_THRESHOLD})",
            "action": "additional evidence collection",
            "details": details
        }

    passed = ratio >= CONSENSUS_THRESHOLD
    return {
        "can_proceed": passed,
        "ratio": round(ratio, 4),
        "summary": f"Consensus {ratio:.1%} ({'PASS' if passed else 'FAIL'})",
        "action": "PR ready" if passed else "re-work needed",
        "details": details
    }
```

### 5.4 오케스트레이터

```python
# scripts/orchestrator.py (핵심 구조)

import json, time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

ORCHESTRA_DIR = Path(".orchestra")
TASKS_DIR = ORCHESTRA_DIR / "tasks"
REPORTS_DIR = ORCHESTRA_DIR / "reports"

class TaskWatcher(FileSystemEventHandler):
    """태스크 디렉토리 변경 감지"""

    def on_moved(self, event):
        """태스크가 디렉토리 간 이동 시 (상태 전이)"""
        if event.dest_path.startswith(str(TASKS_DIR / "review")):
            task_file = Path(event.dest_path)
            task = json.loads(task_file.read_text())
            self.assign_reviewers(task)

    def assign_reviewers(self, task):
        """리뷰 단계 진입 시, 리뷰 에이전트 지정"""
        task_id = task["task_id"]
        implementer = task.get("locked_by")

        # 구현자가 아닌 에이전트를 리뷰어로 지정
        reviewers = [a for a in ["claude", "codex", "gemini"] if a != implementer]
        log(f"[{task_id}] Review assigned to: {reviewers}")

        # 리뷰 요청 기록
        for reviewer in reviewers:
            request = {"task_id": task_id, "action": "review", "assigned_to": reviewer}
            (ORCHESTRA_DIR / "logs" / f"{reviewer}.log").open("a").write(
                json.dumps(request) + "\n"
            )

class ReportWatcher(FileSystemEventHandler):
    """리포트 도착 감지 → 합의 트리거"""

    def on_created(self, event):
        if not event.src_path.endswith(".json"):
            return

        report_path = Path(event.src_path)
        task_id = report_path.stem.split(".")[0]  # task-042-impl.claude.json → task-042-impl

        # 해당 태스크의 모든 리포트 수집
        reports = list(REPORTS_DIR.glob(f"{task_id}.*.json"))
        expected = self.get_expected_reviewers(task_id)

        arrived = {r.stem.split(".")[-1] for r in reports}  # {claude, gemini}
        log(f"[{task_id}] Reports: {arrived}/{expected}")

        if arrived >= expected:
            self.trigger_consensus(task_id, reports)

    def trigger_consensus(self, task_id, report_paths):
        """합의 계산 실행"""
        from consensus import compute_consensus, AgentReport

        reports = []
        for p in report_paths:
            data = json.loads(p.read_text())
            reports.append(AgentReport(**{k: data[k] for k in AgentReport.__dataclass_fields__}))

        result = compute_consensus(reports)
        output_path = ORCHESTRA_DIR / "consensus" / f"{task_id}.consensus.json"
        output_path.write_text(json.dumps(result, indent=2))

        status = "✅ PASS" if result["can_proceed"] else "❌ FAIL"
        log(f"[{task_id}] Consensus: {result.get('ratio', 0):.1%} {status}")

def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

if __name__ == "__main__":
    observer = Observer()
    observer.schedule(TaskWatcher(), str(TASKS_DIR), recursive=True)
    observer.schedule(ReportWatcher(), str(REPORTS_DIR), recursive=False)
    observer.start()
    log("Orchestrator started. Watching .orchestra/ ...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

### 5.5 agents.json 설정

```json
{
  "agents": [
    {
      "id": "claude",
      "cli": "claude",
      "base_weight": 0.40,
      "roles": ["requirements", "planning", "review", "release"],
      "primary_stages": ["requirements", "planning", "review", "release"],
      "constraints": {
        "can_modify": ["docs/", ".orchestra/tasks/", ".orchestra/reports/"],
        "cannot_modify_during_review": ["src/", "tests/"]
      }
    },
    {
      "id": "codex",
      "cli": "codex",
      "base_weight": 0.35,
      "roles": ["implementation", "testing"],
      "primary_stages": ["implementation"],
      "constraints": {
        "can_modify": ["src/", "tests/", ".orchestra/tasks/", ".orchestra/reports/"],
        "sandbox": "workspace-write"
      }
    },
    {
      "id": "gemini",
      "cli": "gemini",
      "base_weight": 0.25,
      "roles": ["testing", "review", "fact-check"],
      "primary_stages": ["testing"],
      "constraints": {
        "can_modify": ["tests/", ".orchestra/reports/"],
        "role_note": "Red Team - 팩트체크 및 보안 검증"
      }
    }
  ]
}
```

---

## 6. 잠재적 문제점 및 해소 방안

### 6.1 동시성 및 충돌

| # | 문제 | 영향 | 확률 | 해소 방안 |
|---|------|------|------|-----------|
| C1 | 두 에이전트가 동일 파일 동시 수정 | 높음 | 높음 | 단계별 수정 권한 분리 (AGENTS.md), 태스크 잠금 (locked_by), Git 충돌 시 구현 에이전트 우선 |
| C2 | 태스크 이중 수령 (두 에이전트가 동시 claim) | 중간 | 중간 | 파일 잠금: `locked_by` + `locked_at` 기록, 오케스트레이터가 중복 감지 시 후순위 해제 |
| C3 | Git push 충돌 | 중간 | 중간 | 에이전트별 작업 브랜치 분리, merge는 인간 또는 오케스트레이터가 수행 |

### 6.2 에이전트 품질

| # | 문제 | 영향 | 확률 | 해소 방안 |
|---|------|------|------|-----------|
| Q1 | 에이전트가 AGENTS.md 지시를 무시 | 높음 | 중간 | 오케스트레이터가 산출물 검증 (스키마 체크, 권한 외 파일 수정 감지) |
| Q2 | JSON 리포트 스키마 미준수 | 높음 | 높음 | `validate_schema.py` 자동 검증, 실패 시 에이전트에 재작성 요청 |
| Q3 | 에이전트 환각 → 거짓 "ready" | 높음 | 중간 | CI hard gate (에이전트 판단과 독립), 다중 에이전트 교차 검증, 분산 검사 |
| Q4 | 에이전트가 컨텍스트 한계로 대규모 코드베이스 파악 실패 | 중간 | 높음 | 태스크를 소규모 단위로 분할, 관련 파일만 컨텍스트에 포함하도록 AGENTS.md에 명시 |

### 6.3 오케스트레이션

| # | 문제 | 영향 | 확률 | 해소 방안 |
|---|------|------|------|-----------|
| O1 | 에이전트 간 교착 (상충 의견 반복) | 중간 | 중간 | Re-review 최대 2회 → 인간 에스컬레이션 |
| O2 | 오케스트레이터 프로세스 크래시 | 중간 | 낮음 | 상태가 파일 시스템에 있으므로 재시작하면 복구, systemd 또는 pm2로 자동 재시작 |
| O3 | 특정 에이전트 CLI 장기 무응답 | 중간 | 중간 | 태스크 잠금 타임아웃 (30분), 초과 시 오케스트레이터가 잠금 해제 + 재할당 |
| O4 | 합의 임계값 과도 엄격 → 개발 지연 | 중간 | 중간 | Phase 2에서 0.85→0.9 단계적 상향, 히스토리 기반 조정 |

### 6.4 보안

| # | 문제 | OWASP LLM | 해소 방안 |
|---|------|-----------|-----------|
| S1 | 프롬프트 인젝션 (이슈/PR 내용 경유) | LLM01 | 외부 입력을 별도 파일로 격리 후 참조, 시스템 프롬프트와 분리 |
| S2 | 에이전트가 시크릿을 코드/리포트에 노출 | LLM06 | 커밋 전 `gitleaks` 자동 스캔, pre-commit hook |
| S3 | 에이전트가 권한 외 명령 실행 | LLM08 | Codex `--sandbox workspace-write`, Claude/Gemini는 파일 수정 범위를 AGENTS.md로 제한 |

### 6.5 위험 대응 흐름

```
에이전트 산출물 도착
       │
       ▼
┌──────────────┐     ┌─────────────────────┐
│ 수정 권한    │─NO─▶│ 거부: 권한 외 수정   │
│ 범위 내?     │     │ 에이전트에 알림      │
└──────┬───────┘     └─────────────────────┘
       │YES
       ▼
┌──────────────┐     ┌─────────────────────┐
│ JSON Schema  │─NO─▶│ 재작성 요청 (max 3) │
│ 유효?        │     │ 실패 시 에이전트 제외│
└──────┬───────┘     └─────────────────────┘
       │YES
       ▼
┌──────────────┐     ┌─────────────────────┐
│ Veto 존재?   │─YES▶│ Re-review loop      │
│              │     │ (max 2회)           │
└──────┬───────┘     │ 초과 → 인간         │
       │NO          └─────────────────────┘
       ▼
┌──────────────┐
│ 점수 분산    │─YES▶ 추가 증거 수집 요청
│ > 20pt?      │
└──────┬───────┘
       │NO
       ▼
┌──────────────┐     ┌─────────────────────┐
│ ratio ≥ 0.9? │─YES▶│ PR 생성 가능        │
│              │     │ 개발자에게 알림      │
└──────┬───────┘     └─────────────────────┘
       │NO
       ▼
  해당 에이전트에
  re-work 요청
```

---

## 7. 데모 시나리오

### 7.1 Demo 1: "Two-Agent Loop" (Phase 1)

**목적:** Claude Code + Codex CLI 2-에이전트 기본 협업 시연

**사전 조건:**
- Python FastAPI 리포지토리 준비 (`/api/health` 엔드포인트)
- `.orchestra/` 구조 초기화 완료
- Terminal 1: Claude Code, Terminal 2: Codex CLI, Terminal 4: Orchestrator

**시연 순서:**

```
시간   Terminal 1 (Claude)         Terminal 2 (Codex)          Terminal 4 (Orchestrator)
─────  ────────────────────────    ────────────────────────    ─────────────────────────
0:00   "이슈 #1의 요구사항을                                   [watching...]
        분석하고 스펙 작성해줘"
0:02   → docs/specs/issue-001.md                               [task-001 생성 감지]
        작성 완료
       → .orchestra/tasks/backlog/
        task-001-impl.json 생성
0:03                                                           [task-001-impl: backlog]
0:04                               "backlog에서 task-001을
                                    수령하고 구현해줘"
0:05                               → locked_by: "codex"       [task-001-impl: in_progress
                                                                locked_by: codex]
0:10                               → src/api/users.py 구현
                                   → tests/test_users.py
                                   → task를 review/로 이동
0:11                                                           [task-001-impl: review]
                                                               [Review → claude 할당]
0:12   "review/ 태스크를
        리뷰해줘"
0:15   → .orchestra/reports/
        task-001-impl.claude.json
        {score:88, vote:"not_ready",
         blockers:[입력검증 누락]}
0:15                                                           [Reports: claude ✓]
                                                               [Consensus: 1/1 agent]
                                                               [score 88 < 90: FAIL]
                                                               [→ re-work 요청]
```

**검증 포인트:**
- Claude가 스펙을 작성하고 태스크를 올바르게 생성했는가
- Codex가 태스크를 잠그고 구현 후 review/로 이동했는가
- Claude가 리뷰 리포트를 스키마에 맞게 작성했는가
- 오케스트레이터가 합의를 자동 계산했는가

---

### 7.2 Demo 2: "Three-Agent Consensus" (Phase 2)

**목적:** 3개 에이전트 전체 프로세스 + 합의 통과 시연

**시연 순서:**

```
Terminal 1 (Claude)      Terminal 2 (Codex)       Terminal 3 (Gemini)      Terminal 4 (Orch.)
────────────────────     ────────────────────     ────────────────────     ──────────────────

[1.요구사항]
스펙 작성                                        팩트체크 검증
docs/specs/feat-002.md                           reports/...gemini.json

[2.작업분해]
계획 작성                실현성 검증
docs/plans/feat-002.md   피드백

[3.구현]
                         코드 구현
                         src/ 변경 + 커밋
                         → review/로 이동                                  [review 감지]

[4.코드리뷰]
리뷰 리포트 작성                                 보안 검증 리포트          [리포트 수집]
score:95, ready                                  score:91, ready

[5.테스트강화]
                         테스트 보조 구현          추가 테스트 작성
                                                 reports/...gemini.json

[6.합의]                                                                   합의 계산
                                                                           ratio: 94% PASS
                                                                           → PR ready

[7.릴리스]
릴리스노트 작성          배포 스크립트 점검

[8.인간 승인]
개발자: PR 확인 → merge → deploy
```

**기대 합의 결과:**

```json
{
  "can_proceed": true,
  "ratio": 0.94,
  "summary": "Consensus 94% (PASS)",
  "action": "PR ready",
  "details": {
    "claude": { "score": 95, "vote": "ready", "confidence": 0.92, "effective_weight": 0.368 },
    "codex":  { "score": 92, "vote": "ready", "confidence": 0.88, "effective_weight": 0.308 },
    "gemini": { "score": 91, "vote": "ready", "confidence": 0.85, "effective_weight": 0.213 }
  }
}
```

---

### 7.3 Demo 3: "Veto & Red Team" (Phase 2)

**목적:** Gemini Red Team이 보안 취약점을 발견하고 Veto → 수정 후 복귀

**시연 순서:**

1. Codex가 SQL 쿼리에 사용자 입력을 직접 삽입하는 코드 구현
2. Claude 리뷰: `score: 72, vote: "not_ready"` (구조 문제 지적)
3. **Gemini 리뷰: `vote: "veto"` (SQL Injection 탐지)**
4. 오케스트레이터: 즉시 합의 차단, re-review loop 진입
5. Codex에 re-work 요청 → parameterized query로 수정
6. 재리뷰 → Gemini veto 해제 → 합의 통과

---

### 7.4 Demo 4: "Agent Down — Graceful Degradation" (Phase 3)

**목적:** Gemini CLI 장애 시 2-에이전트로 합의 진행

**시연 순서:**

1. Gemini CLI 터미널 의도적으로 종료
2. 태스크가 review/에 도착 → 오케스트레이터가 Gemini에 할당 시도
3. 30분 타임아웃 → Gemini 잠금 해제
4. 오케스트레이터: Claude + Codex 2개 리포트로 가중치 재분배 후 합의 계산
5. 합의 결과에 "degraded mode: gemini unavailable" 기록

---

## 8. 부록: 워크플로우 다이어그램

### 8.1 에이전트 협업 시퀀스

```
Developer        Claude Code       Codex CLI        Gemini CLI       Orchestrator
(인간)           (Terminal 1)      (Terminal 2)     (Terminal 3)     (Terminal 4)
   │                 │                 │                 │                │
   │─ 이슈 생성 ───▶│                 │                 │                │
   │                 │── 스펙 작성 ──▶│                 │                │
   │                 │   docs/specs/   │                 │                │
   │                 │── 태스크 생성 ─┼─────────────────┼───────────────▶│
   │                 │  backlog/       │                 │                │[태스크 감지]
   │                 │                 │                 │                │
   │                 │                 │◀── 팩트체크 ───│                │
   │                 │                 │   요청(선택)    │                │
   │                 │                 │                 │                │
   │                 │── 작업 분해 ──▶│                 │                │
   │                 │   docs/plans/   │                 │                │
   │                 │                 │                 │                │
   │                 │                 │── claim ───────┼───────────────▶│
   │                 │                 │   locked_by:    │                │[잠금 기록]
   │                 │                 │   "codex"       │                │
   │                 │                 │                 │                │
   │                 │                 │── 구현 ────────┼────────────────│
   │                 │                 │   src/ 변경     │                │
   │                 │                 │   커밋          │                │
   │                 │                 │                 │                │
   │                 │                 │── review/ 이동 ─┼───────────────▶│
   │                 │                 │                 │                │[리뷰어 할당]
   │                 │                 │                 │                │
   │                 │◀── 리뷰 요청 ──┼─────────────────┼────────────────│
   │                 │                 │                 │◀── 리뷰 요청 ─│
   │                 │                 │                 │                │
   │                 │── 리뷰 리포트 ─┼─────────────────┼───────────────▶│
   │                 │   .claude.json  │                 │                │[리포트 수집]
   │                 │                 │                 │                │
   │                 │                 │                 │── 리뷰 리포트 ▶│
   │                 │                 │                 │  .gemini.json  │[리포트 수집]
   │                 │                 │                 │                │
   │                 │                 │── 자기평가 ─────┼───────────────▶│
   │                 │                 │  .codex.json    │                │[전원 도착]
   │                 │                 │                 │                │
   │                 │                 │                 │                │── 합의 계산
   │                 │                 │                 │                │   ratio ≥ 0.9?
   │                 │                 │                 │                │
   │◀── 합의 결과 ──┼─────────────────┼─────────────────┼────────────────│
   │   "PASS: PR     │                 │                 │                │
   │    ready"        │                 │                 │                │
   │                 │                 │                 │                │
   │── PR 확인 ──────┼─────────────────┼─────────────────┼────────────────│
   │── merge ────────┼─────────────────┼─────────────────┼────────────────│
   │── deploy ───────┼─────────────────┼─────────────────┼────────────────│
```

### 8.2 에이전트 역할 매트릭스

```
               요구사항   작업분해   구현/패치   코드리뷰   테스트강화   릴리스준비
              ─────────  ────────  ─────────  ────────  ─────────  ──────────
Claude Code     ●(P)      ●(P)                  ●(P)                  ●(P)
Codex CLI                 ○(S)      ●(P)        ○(self)   ○(S)        ○(S)
Gemini CLI      ○(FC)                           ○(Red)    ●(P)

●(P) = Primary    ○(S) = Secondary    ○(FC) = Fact-Check    ○(Red) = Red Team
```

### 8.3 디렉토리 구조

```
project-root/
├── AGENTS.md                          # 오케스트레이션 공통 규칙
├── CLAUDE.md                          # Claude Code 역할 지시
├── CODEX.md                           # Codex CLI 역할 지시
├── GEMINI.md                          # Gemini CLI 역할 지시
├── .orchestra/
│   ├── config/
│   │   ├── agents.json                # 에이전트 등록, 가중치, 권한
│   │   ├── consensus.json             # 합의 임계값, 분산 한도
│   │   ├── process.json               # 개발 프로세스 단계 정의
│   │   └── agent_reliability.json     # 신뢰도 점수 (Phase 3)
│   ├── tasks/
│   │   ├── backlog/
│   │   ├── in_progress/
│   │   ├── review/
│   │   └── done/
│   ├── reports/                       # {task_id}.{agent_id}.json
│   ├── consensus/                     # {task_id}.consensus.json
│   └── logs/                          # 에이전트 활동 로그
├── schemas/
│   ├── task.schema.json
│   └── release_readiness.schema.json
├── scripts/
│   ├── orchestrator.py                # 파일 감시 + 합의 트리거
│   ├── consensus.py                   # 가중 합의 알고리즘
│   ├── validate_schema.py             # JSON 스키마 검증
│   ├── task_create.py                 # 태스크 생성 CLI
│   ├── dashboard.py                   # 터미널 대시보드 (Phase 2)
│   └── report_view.py                 # 합의 결과 조회 (Phase 2)
├── docs/
│   ├── specs/                         # 요구사항 스펙 (Claude 생성)
│   ├── plans/                         # 작업 분해 계획 (Claude 생성)
│   └── security/
│       ├── owasp_llm_matrix.md
│       └── nist_ssdf_policy.md
├── src/                               # 소스 코드 (Codex 수정)
└── tests/                             # 테스트 (Gemini/Codex 작성)
```

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|-----------|
| v1.0 | 2026-03-14 | 초판 (GitHub Actions 기반) |
| v1.1 | 2026-03-14 | 기존 인프라 참조 제거, 단일 환경 개정 |
| v2.0 | 2026-03-14 | **전면 재설계:** 다중 터미널 CLI 에이전트 협업 구조로 변경. 파일 시스템 기반 태스크 보드(`.orchestra/`), 에이전트별 역할 문서(CLAUDE.md/CODEX.md/GEMINI.md), 제품개발 프로세스 7단계별 에이전트 배치, 오케스트레이터(file watcher), 태스크 잠금/상태 전이, 현실적 데모 시나리오(터미널별 타임라인) |
