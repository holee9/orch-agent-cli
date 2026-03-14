# Multi-AI CLI Agent Orchestration

> 여러 AI CLI 에이전트(Claude Code, Codex CLI, Gemini CLI)가 동일한 Git repository를 공유하며,
> 제품 개발의 각 단계를 자율적으로 분담하는 **파일 시스템 기반 orchestration** 시스템입니다.

---

## 목차

1. [개요](#1-개요)
2. [아키텍처](#2-아키텍처)
3. [에이전트 역할](#3-에이전트-역할)
4. [Task 라이프사이클](#4-task-라이프사이클)
5. [개발 프로세스 흐름](#5-개발-프로세스-흐름)
6. [Consensus 엔진](#6-consensus-엔진)
7. [디렉토리 구조](#7-디렉토리-구조)
8. [구현 Roadmap](#8-구현-roadmap)
9. [위험 요소 및 대응](#9-위험-요소-및-대응)
10. [Demo 시나리오](#10-demo-시나리오)

---

## 1. 개요

### 핵심 개념

이 시스템은 GitHub Actions 같은 CI/CD pipeline 안에서 에이전트를 자동 호출하는 구조가 **아닙니다**.

개발자가 여러 개의 terminal 창을 열고, 각 terminal에서 CLI 에이전트를 직접 실행합니다. 에이전트들은 동일한 Git repository를 공유하며, 요구사항 분석부터 release 준비까지 각 단계를 역할에 따라 분담합니다.

```
개발자 워크스테이션
┌─────────────────────────────────────────────────────────┐
│  Terminal 1 (Claude Code)    Terminal 2 (Codex CLI)      │
│  ┌─────────────────────┐    ┌─────────────────────┐     │
│  │ $ claude            │    │ $ codex             │     │
│  │ > /review PR #42    │    │ > implement task-003│     │
│  └─────────────────────┘    └─────────────────────┘     │
│                                                          │
│  Terminal 3 (Gemini CLI)     Terminal 4 (Orchestrator)   │
│  ┌─────────────────────┐    ┌─────────────────────┐     │
│  │ $ gemini            │    │ $ python orche.py   │     │
│  │ > enhance tests for │    │ [watching task board]│     │
│  └─────────────────────┘    └─────────────────────┘     │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Shared Git Repository (local)           │   │
│  │  ├── src/          ← 에이전트들이 동시에 읽고 씀  │   │
│  │  ├── .orchestra/   ← orchestration 상태/task 보드 │   │
│  │  └── docs/         ← spec, plan, report          │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### CI/CD와의 구분

| 구분 | 역할 | 비고 |
|------|------|------|
| CLI 에이전트 (본 프로젝트) | 요구사항 분석, 설계, 구현, 리뷰, 테스트 작성 | 개발자가 terminal에서 직접 운영 |
| CI/CD (GitHub Actions 등) | 빌드, lint, 보안 scan, 배포 | 에이전트 결과물을 검증하는 **별도 pipeline** |

에이전트는 코드를 작성하고 리뷰하는 **개발 참여자**이고, CI/CD는 그 결과물을 검증하는 **quality gate**입니다. 이 두 역할은 명확히 분리됩니다.

---

## 2. 아키텍처

### 파일 시스템 기반 Task Board

에이전트 간 협업은 **공유 repository 내 `.orchestra/` 디렉토리**를 통해 이루어집니다. 외부 서비스 없이 file system과 Git만으로 상태를 관리합니다.

```
.orchestra/
├── config/
│   ├── agents.json              # 에이전트 등록 및 가중치
│   ├── consensus.json           # 합의 threshold, 분산 한도
│   └── process.json             # 개발 프로세스 단계 정의
├── tasks/
│   ├── backlog/                 # 대기 중인 task
│   ├── in_progress/             # 에이전트가 작업 중 (locked_by 설정)
│   ├── review/                  # review 대기
│   └── done/                    # 완료
├── reports/                     # 에이전트별 평가 report
│   ├── task-003.claude.json
│   ├── task-003.codex.json
│   └── task-003.gemini.json
├── consensus/                   # 합의 결과
│   └── task-003.consensus.json
└── logs/                        # 에이전트 활동 log
```

### Orchestrator의 역할

`scripts/orchestrator.py`는 별도 terminal에서 상시 실행되는 경량 프로세스입니다.

**담당 업무:**
- `.orchestra/tasks/` 디렉토리 감시 (file watcher)
- task 상태 전이 검증
- `review/`에 도착한 task에 대해 reviewer 에이전트 지정
- 모든 report 수집 완료 시 `consensus.py` 실행
- 합의 결과를 `.orchestra/consensus/`에 기록
- 개발자에게 terminal 알림

**담당하지 않는 업무:**
- 에이전트를 직접 실행하거나 종료
- 코드 수정
- 배포

---

## 3. 에이전트 역할

| 에이전트 | CLI 도구 | 실행 방식 | 핵심 역할 |
|----------|----------|-----------|-----------|
| **Claude Code** | `claude` | Terminal interactive / `claude -p` 비대화 모드 | 설계자 + reviewer + release manager |
| **Codex CLI** | `codex` | `codex exec --sandbox workspace-write` | 구현자 + patch 생성기 |
| **Gemini CLI** | `gemini` | Terminal interactive / API 호출 | 테스트 강화 + fact-checker (Red Team) |

### 역할 매트릭스

```
               요구사항   작업분해   구현/Patch   코드리뷰   테스트강화   Release
              ─────────  ────────  ──────────  ────────  ─────────  ────────
Claude Code     ●(P)      ●(P)                   ●(P)                  ●(P)
Codex CLI                 ○(S)       ●(P)         ○(self)   ○(S)       ○(S)
Gemini CLI      ○(FC)                             ○(Red)    ●(P)

●(P) = Primary    ○(S) = Secondary    ○(FC) = Fact-Check    ○(Red) = Red Team
```

---

## 4. Task 라이프사이클

```
                    Orchestrator 또는 개발자가 task 생성
                                    │
                                    ▼
┌──────────┐    에이전트가     ┌────────────┐    작업 완료     ┌──────────┐
│ backlog/ │────────────────▶│in_progress/│────────────────▶│ review/  │
│          │  task 잠금(claim) │locked_by:  │   결과물 commit  │          │
└──────────┘                  │ "codex"    │                  └────┬─────┘
                              └────────────┘              다른 에이전트가 review
                                                          report 작성
                                                                    │
                                                                    ▼
                                                             ┌──────────┐
                                                             │  done/   │
                                                             └──────────┘
```

### Task JSON 구조 (`task.schema.json`)

task 파일에는 다음 주요 필드가 포함됩니다:

| 필드 | 설명 |
|------|------|
| `task_id` | `task-001`, `task-042-impl` 형식의 고유 ID |
| `stage` | `requirements` → `planning` → `implementation` → `review` → `testing` → `consensus` → `release` |
| `assigned_to.primary` | 담당 에이전트 (`claude`, `codex`, `gemini`) |
| `locked_by` | 현재 작업 중인 에이전트 ID (충돌 방지용 lock) |
| `artifacts` | 산출물 목록 (spec, plan, code, test, report) |

---

## 5. 개발 프로세스 흐름

제품 개발의 7단계 + 인간 최종 승인으로 구성됩니다:

```
Stage 1: 요구사항 분석     → Claude Code (Primary) + Gemini (fact-check)
Stage 2: 작업 분해/계획    → Claude Code (Primary) + Codex (실현성 검증)
Stage 3: 구현/Patch 생성   → Codex CLI (Primary) + Claude Code (보조)
Stage 4: 코드 Review       → Claude Code (Primary) + Gemini (보안 검증)
Stage 5: 테스트 강화       → Gemini CLI (Primary) + Codex (구현 보조)
Stage 6: Consensus 판정    → Orchestrator (자동 계산)
Stage 7: Release 준비      → Claude Code (Primary) + Codex (배포 script)
Stage 8: 인간 최종 승인    → 개발자가 merge + deploy
```

### Stage별 실행 예시

**Stage 1 — 요구사항 분석 (Terminal 1):**
```bash
$ claude
> 이슈 #42의 요구사항을 분석하고 docs/specs/issue-042.md에
  acceptance criteria를 작성해줘.
```

**Stage 3 — 구현 (Terminal 2):**
```bash
$ codex exec --sandbox workspace-write \
    --prompt "docs/plans/task-042-plan.md에 따라 구현해줘. \
              각 sub-task별로 commit을 분리하고, \
              완료 후 task를 review/로 이동해."
```

**Stage 4 — 코드 Review (Terminal 1):**
```bash
$ claude
> .orchestra/tasks/review/task-042-impl.json을 review해줘.
  .orchestra/reports/task-042-impl.claude.json에
  release_readiness schema에 맞춰 report를 작성해.
```

---

## 6. Consensus 엔진

### 합의 알고리즘

모든 에이전트의 report가 수집되면 `scripts/consensus.py`가 자동으로 실행됩니다.

```
유효 가중치 = base_weight × reliability × confidence

합의 비율 = Σ(유효 가중치 × ready 여부) / Σ(유효 가중치)
```

**판정 기준:**
- 합의 비율 ≥ 0.9 (90%) → **PASS** → PR 생성 가능
- 합의 비율 < 0.9 → **FAIL** → 해당 에이전트에 re-work 요청
- `veto` 투표 발생 → **즉시 차단** → re-review loop (최대 2회 → 인간 escalation)
- 점수 분산 > 20pt → **추가 증거 수집** 요청

### Report 스키마 (`release_readiness.schema.json`)

에이전트가 작성하는 report의 핵심 필드:

| 필드 | 타입 | 설명 |
|------|------|------|
| `score` | 0–100 정수 | 릴리스 준비도 점수 |
| `confidence` | 0.0–1.0 | 해당 평가에 대한 에이전트 신뢰도 |
| `vote` | `ready` / `not_ready` / `veto` | 최종 투표 |
| `blockers` | 배열 | 차단 이슈 목록 (severity + 설명 + 수정 제안) |
| `evidence` | 배열 | 근거 자료 (CI report, test result, security scan 등) |

### 에이전트 가중치 설정

```json
Claude Code : base_weight 0.40  (설계·리뷰 전문가)
Codex CLI   : base_weight 0.35  (구현 전문가)
Gemini CLI  : base_weight 0.25  (테스트·보안 검증)
```

---

## 7. 디렉토리 구조

```
project-root/
├── AGENTS.md                          # 오케스트레이션 공통 규칙
├── CLAUDE.md                          # Claude Code 역할 지시
├── CODEX.md                           # Codex CLI 역할 지시
├── GEMINI.md                          # Gemini CLI 역할 지시
├── .orchestra/
│   ├── config/
│   │   ├── agents.json                # 에이전트 등록, 가중치, 권한
│   │   ├── consensus.json             # 합의 threshold, 분산 한도
│   │   ├── process.json               # 개발 프로세스 단계 정의
│   │   └── agent_reliability.json     # 신뢰도 점수 (Phase 3)
│   ├── tasks/
│   │   ├── backlog/
│   │   ├── in_progress/
│   │   ├── review/
│   │   └── done/
│   ├── reports/                       # {task_id}.{agent_id}.json
│   ├── consensus/                     # {task_id}.consensus.json
│   └── logs/                          # 에이전트 활동 log
├── schemas/
│   ├── task.schema.json               # Task 정의 schema
│   └── release_readiness.schema.json  # Report schema
├── scripts/
│   ├── orchestrator.py                # File watcher + consensus trigger
│   ├── consensus.py                   # 가중 합의 알고리즘
│   ├── validate_schema.py             # JSON schema 검증
│   ├── task_create.py                 # Task 생성 CLI 도구
│   ├── dashboard.py                   # Terminal 대시보드 (Phase 2)
│   └── report_view.py                 # 합의 결과 조회 (Phase 2)
├── docs/
│   ├── specs/                         # 요구사항 spec (Claude 생성)
│   ├── plans/                         # 작업 분해 계획 (Claude 생성)
│   └── security/
│       ├── owasp_llm_matrix.md
│       └── nist_ssdf_policy.md
├── src/                               # 소스 코드 (Codex 수정)
└── tests/                             # 테스트 (Gemini/Codex 작성)
```

---

## 8. 구현 Roadmap

### Phase 1 — MVP (4–6주)

**목표:** Claude Code + Codex CLI 2개 에이전트로 기본 협업 loop 구축

- [ ] `.orchestra/` 디렉토리 구조 생성
- [ ] Task JSON schema 및 report schema 정의
- [ ] `AGENTS.md`, `CLAUDE.md`, `CODEX.md` 역할 문서 작성
- [ ] `scripts/orchestrator.py` — file system watch + 합의 trigger
- [ ] 2-에이전트 협업 loop 검증 (요구사항 → 구현 → review → consensus)
- [ ] CI pipeline 연동 (별도 GitHub Actions workflow)

### Phase 2 — 3-Agent 풀 가동 + Consensus 엔진 (8–12주)

**목표:** Gemini CLI 추가, 가중 합의 알고리즘, 전체 프로세스 자동화

- [ ] `GEMINI.md` 작성 (테스트 강화 + Red Team 역할)
- [ ] `scripts/consensus.py` 완성 (가중치, veto 처리, 분산 감지)
- [ ] PR 자동 생성 (합의 통과 시)
- [ ] `scripts/dashboard.py` — terminal 기반 대시보드
- [ ] 에이전트 신뢰도(reliability) 추적 시작

### Phase 3 — 강화 및 운영 최적화 (8–12주)

**목표:** 신뢰도 feedback loop, 비용 관리, 보안 governance

- [ ] 배포 성공/실패 기반 신뢰도 자동 업데이트
- [ ] 에이전트별 token 사용량 추적 및 비용 최적화
- [ ] OWASP LLM Top 10 대응 문서 및 자동화
- [ ] NIST SSDF 정렬
- [ ] n8n 연동 (Slack 알림, 외부 승인 흐름) — 선택사항

---

## 9. 위험 요소 및 대응

### 동시성 문제

| 문제 | 대응 방안 |
|------|-----------|
| 두 에이전트가 동일 파일 동시 수정 | 단계별 수정 권한 분리 + `locked_by` task 잠금 |
| Task 이중 수령 (두 에이전트가 동시 claim) | `locked_by` + `locked_at` 기록, orchestrator가 중복 감지 시 해제 |
| Git push 충돌 | 에이전트별 작업 branch 분리 |

### 에이전트 품질 문제

| 문제 | 대응 방안 |
|------|-----------|
| JSON report schema 미준수 | `validate_schema.py` 자동 검증, 실패 시 재작성 요청 |
| 에이전트 hallucination → 거짓 "ready" | CI hard gate (에이전트 판단과 독립), 다중 에이전트 교차 검증 |
| Context 한계로 대규모 codebase 파악 실패 | Task를 소규모 단위로 분할, 관련 파일만 context에 포함 |

### 보안

| 위협 | OWASP LLM | 대응 방안 |
|------|-----------|-----------|
| Prompt injection (이슈/PR 내용 경유) | LLM01 | 외부 입력을 별도 파일로 격리 후 참조 |
| 에이전트가 secret을 code/report에 노출 | LLM06 | commit 전 `gitleaks` 자동 scan, pre-commit hook |
| 에이전트가 권한 외 명령 실행 | LLM08 | Codex `--sandbox workspace-write`, `AGENTS.md`로 파일 수정 범위 제한 |

---

## 10. Demo 시나리오

### Demo 1 — Two-Agent Loop (Phase 1)

Claude Code + Codex CLI의 기본 협업 흐름을 검증합니다.

1. Claude Code가 요구사항을 분석하고 spec 및 task를 생성
2. Codex CLI가 task를 claim하고 구현 후 `review/`로 이동
3. Claude Code가 review report 작성 (score, vote, blockers)
4. Orchestrator가 합의를 자동 계산

### Demo 2 — Three-Agent Consensus (Phase 2)

3개 에이전트 전체 프로세스와 합의 통과를 시연합니다. 기대 결과:

```json
{
  "can_proceed": true,
  "ratio": 0.94,
  "summary": "Consensus 94% (PASS)",
  "action": "PR ready"
}
```

### Demo 3 — Veto & Red Team (Phase 2)

Gemini가 SQL Injection을 발견하고 `veto`를 투표 → orchestrator가 즉시 차단 → Codex가 parameterized query로 수정 → 재리뷰 → 합의 통과

### Demo 4 — Graceful Degradation (Phase 3)

Gemini CLI 장애 시 30분 timeout → 잠금 해제 → Claude + Codex 2개 에이전트로 가중치 재분배하여 합의 진행. 합의 결과에 `"degraded mode: gemini unavailable"` 기록.

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|-----------|
| v1.0 | 2026-03-14 | 초판 (GitHub Actions 기반) |
| v1.1 | 2026-03-14 | 기존 인프라 참조 제거, 단일 환경 개정 |
| v2.0 | 2026-03-14 | 전면 재설계: 다중 terminal CLI 에이전트 협업 구조, file system 기반 task board, orchestrator, 가중 consensus 엔진 |
