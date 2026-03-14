# Multi-AI CLI Agent Orchestration

> 여러 AI CLI 에이전트(Claude Code, Codex CLI, Gemini CLI)가 GitHub Issues를 1차 통신 버스로 사용하며,
> **아이디어 파일 1개 등록 → 에이전트 자율 완주 → 최종 보고**를 실현하는 설치형 orchestration 도구입니다.

---

## 목차

1. [문서 구조 및 관리 정책](#0-문서-구조-및-관리-정책)
2. [개요: orch-agent-cli의 성격](#1-개요-orch-agent-cli의-성격)
3. [구현 현황 (Implementation Status)](#구현-현황-implementation-status)
4. [아키텍처: 이중 레이어 통신](#2-아키텍처-이중-레이어-통신)
5. [에이전트 역할](#3-에이전트-역할)
6. [인간 문서 생애주기](#4-인간-문서-생애주기)
7. [GitHub Issues 프로토콜](#5-github-issues-프로토콜)
8. [개발 프로세스 흐름](#6-개발-프로세스-흐름)
9. [Consensus 엔진](#7-consensus-엔진)
10. [디렉토리 구조](#8-디렉토리-구조)
11. [구현 Roadmap](#9-구현-roadmap)
12. [위험 요소 및 대응](#10-위험-요소-및-대응)
13. [Demo 시나리오](#11-demo-시나리오)

---

## 0. 문서 구조 및 관리 정책

### 문서 역할 구분표

| 파일 | 대상 독자 | 언어 | 목적 | 상태 |
|------|-----------|------|------|------|
| `README.md` | 인간 개발자 | 한국어 | 시스템 전체 개요 및 운영 가이드 (단일 진실 원본) | 운영 |
| `docs/agents/AGENTS.md` | 모든 AI 에이전트 | 영어 | 에이전트 공통 규칙 (GitHub Issues 통신, 파일 범위, 금지 사항) | (초안) |
| `docs/agents/CLAUDE.md` | Claude Code | 영어 | Claude Code 역할 및 단계별 프로토콜 | (초안) |
| `docs/agents/CODEX.md` | Codex CLI | 영어 | Codex CLI 역할 및 단계별 프로토콜 | (초안) |
| `docs/agents/GEMINI.md` | Gemini CLI | 영어 | Gemini CLI 역할 및 단계별 프로토콜 | (초안) |
| `docs/multi-ai-orchestration-implementation-plan-v3.md` | 인간 개발자 | 한국어 | 상세 설계 참고 문서 (최신) | 참고 |

> **위치 정책:** 에이전트 지시 문서는 시스템 구현 완료 후 루트로 승격 예정입니다.
> 현재는 기획 초안 단계이므로 `docs/agents/`에 위치합니다.

### README 업데이트 정책

README는 인간 개발자가 시스템의 현재 상태를 파악하기 위한 **단일 진실 원본**입니다.

다음 변경 발생 시 README를 함께 업데이트합니다:
- 에이전트 문서 구조 변경
- `.orchestra/` 스키마 또는 디렉토리 구조 변경
- GitHub Issues 라벨 체계 또는 프로토콜 변경
- 개발 프로세스 단계 추가 또는 수정
- 새로운 에이전트 추가 또는 기존 에이전트 역할 변경

### 에이전트 문서 작성 원칙

에이전트 지시 파일은 다음 원칙을 따릅니다:

- **언어**: 반드시 영어로 작성 (에이전트는 영어 컨텍스트에서 최적 동작)
- **최소 컨텍스트**: 불필요한 배경 설명 제거 — "무엇을", "어떻게"만 포함
- **3섹션 구조**: 모든 에이전트 파일은 `Role / Scope / Protocol` 세 섹션만 사용
- **파일 크기**: 50줄 이하 유지

---

## 1. 개요: orch-agent-cli의 성격

### 이 리포지토리는 개발 대상이 아닙니다

`orch-agent-cli`는 **타 프로젝트에 설치하여 사용하는 orchestration 도구**입니다. 실제 개발이 이루어지는 별도 target project에 포함시켜 CLI 에이전트들이 해당 프로젝트를 자율적으로 개발하도록 지원합니다.

```
orch-agent-cli (이 리포지토리)
  ↓ git submodule 또는 독립 실행
target-project/ (실제 개발이 이루어지는 별도 repo)
  ├── src/           ← 에이전트들이 개발하는 코드
  ├── .orchestrator/ ← orch-agent-cli 서브모듈 (선택 A)
  ├── .orchestra/    ← 로컬 운영 상태 (lock, cache, log)
  ├── inbox/         ← 인간이 BRIEF 파일을 투입하는 곳
  └── docs/          ← spec, plan, review, report
```

### 운영 형태: 아이디어 1개 → 자율 완주 → 최종 보고

인간의 역할은 최소화됩니다.

```
인간 개입 포인트           에이전트 자율 구간
─────────────────────────────────────────────────────────
① BRIEF 파일 작성   →  [에이전트 분석/설계/구현/리뷰/테스트]
                          (에이전트 간 GitHub Issues로 소통)
② Final Report 수신 →  필요 시 추가 BRIEF 작성
③ PR merge + deploy ↑── Final Report가 이 시점을 알려줌
```

### 설치 방법

**Option A — Git Submodule (권장):**
```bash
git submodule add https://github.com/your-org/orch-agent-cli .orchestrator
cp .orchestrator/templates/{AGENTS,CLAUDE,CODEX,GEMINI}.md .
mkdir -p inbox .orchestra/{state,logs,cache}
```

**Option B — 독립 실행:**
```bash
# .env에 target project 지정
GITHUB_REPO=owner/target-project
TARGET_PROJECT_PATH=/path/to/target-project
python scripts/orchestrator.py --target /path/to/target-project
```

### CI/CD와의 구분

| 구분 | 역할 |
|------|------|
| CLI 에이전트 (본 프로젝트) | 요구사항 분석, 설계, 구현, 리뷰, 테스트 작성 |
| CI/CD (GitHub Actions 등) | 빌드, lint, 보안 scan, 배포 (에이전트 결과물 검증 quality gate) |

---

## 구현 현황 (Implementation Status)

### Phase 1 MVP: ✅ 완료 (2026-03-14)

Multi-AI CLI Agent Orchestration의 첫 번째 완성 버전이 구현되었습니다. GitHub Issues 기반 다중 에이전트 협업 시스템의 핵심 기능이 모두 동작 가능 상태입니다.

### 구현된 파일 목록

#### 1. 스크립트 모듈 (`scripts/`)

| 파일 | 설명 | 상태 |
|------|------|------|
| `orchestrator.py` | 중앙 Orchestrator — GitHub API 단일 창구, 라우터, 품질 게이트 | ✅ |
| `consensus.py` | 가중 합의 알고리즘 — 3개 에이전트 투표 집계 및 판정 | ✅ |
| `brief_parser.py` | BRIEF 파싱 — 한국어 입력 분석 및 영어 Kickoff Issue 생성 | ✅ |
| `report_generator.py` | Final Report 자동 생성 — 한국어 + 기술 용어 영어 혼합 | ✅ |
| `setup_labels.py` | GitHub Labels 초기 설정 — routing, status, type 라벨 자동 생성 | ✅ |
| `github_client.py` | GitHub API 래퍼 — 이슈 CRUD, 댓글, 라벨 관리 | ✅ |
| `state_manager.py` | 로컬 상태 관리 — `.orchestra/state/` 파일 I/O | ✅ |
| `validate_schema.py` | JSON 스키마 검증 — task, release_readiness 스키마 준수 | ✅ |

#### 2. JSON 스키마 (`schemas/`)

| 파일 | 설명 | 상태 |
|------|------|------|
| `task.schema.json` | 에이전트 작업 스키마 — 할당, 진행, 완료 상태 정의 | ✅ |
| `release_readiness.schema.json` | 배포 준비도 스키마 | ✅ |
| `assignment.schema.json` | 에이전트 할당 스키마 | ✅ |
| `consensus.schema.json` | 합의 결과 스키마 — 투표, 가중치, 최종 판정 | ✅ |

#### 3. 설정 파일 (`config/`)

| 파일 | 설명 | 상태 |
|------|------|------|
| `config.yaml` | 프로젝트 설정 — GitHub repo, polling 간격, 임계값 | ✅ |
| `agents.json` | 에이전트 등록 — Claude, Codex, Gemini 기본 가중치 | ✅ |

#### 4. 템플릿 (`templates/`)

| 파일 | 설명 | 상태 |
|------|------|------|
| `AGENTS.md` | 모든 에이전트 공통 규칙 (영어) | ✅ |
| `CLAUDE.md` | Claude Code 역할 및 프로토콜 (영어) | ✅ |
| `CODEX.md` | Codex CLI 역할 및 프로토콜 (영어) | ✅ |
| `GEMINI.md` | Gemini CLI 역할 및 프로토콜 (영어) | ✅ |
| `setup.sh` | target project 초기 설정 스크립트 | ✅ |
| `inbox/BRIEF-TEMPLATE.md` | BRIEF 파일 템플릿 (한국어) | ✅ |

#### 5. 테스트 (`tests/`)

| 파일 | 테스트 항목 | 상태 |
|------|-----------|------|
| `test_orchestrator.py` | Orchestrator 라우팅 및 상태 관리 | ✅ |
| `test_consensus.py` | 합의 알고리즘 (14 tests) | ✅ |
| `test_brief_parser.py` | BRIEF 파싱 및 영어 변환 | ✅ |
| `test_github_client.py` | GitHub API 상호작용 | ✅ |
| `test_state_manager.py` | 로컬 상태 I/O | ✅ |
| `test_validate_schema.py` | JSON 스키마 검증 | ✅ |
| `test_report_generator.py` | Final Report 생성 | ✅ |

**테스트 현황: 59 tests passing** ✅

#### 6. 기타 파일

| 파일 | 설명 | 상태 |
|------|------|------|
| `pyproject.toml` | Python 패키지 설정 — 의존성, 메타데이터 | ✅ |
| `.gitignore` | Git 무시 규칙 | ✅ |
| `.env.example` | 환경 변수 템플릿 | ✅ |
| `fixtures/` | 테스트 픽스처 (mock data) | ✅ |

### 빠른 시작 가이드 (Quick Start)

#### 1단계: 의존성 설치

```bash
pip install jsonschema pyyaml requests
```

#### 2단계: GitHub 레이블 초기 설정

```bash
python scripts/setup_labels.py owner/repo
```

예: `python scripts/setup_labels.py my-org/my-target-project`

#### 3단계: Target 프로젝트 초기화

```bash
bash templates/setup.sh /path/to/target-project
```

이 명령은 target project에 다음을 자동 생성합니다:
- `.orchestra/` 디렉토리 구조
- `inbox/` 디렉토리
- `docs/` 하위 디렉토리들
- 에이전트 지시 문서 복사

#### 4단계: Orchestrator 실행

```bash
export GITHUB_REPO=owner/repo
export TARGET_PROJECT_PATH=/path/to/target-project
python scripts/orchestrator.py
```

Orchestrator는 60초 간격으로 다음을 반복 실행합니다:
- `inbox/` 디렉토리 모니터링 (새 BRIEF 감지)
- GitHub Issues 폴링 (에이전트 활동 추적)
- 로컬 상태 파일 동기화
- 합의 계산 및 판정

### 디렉토리 구조 (최신)

```
orch-agent-cli/                    # 본 리포지토리 (설치형 도구)
├── scripts/                        # Python 실행 모듈
│   ├── orchestrator.py            # 중앙 Orchestrator
│   ├── consensus.py               # 합의 알고리즘
│   ├── brief_parser.py            # BRIEF 파싱
│   ├── report_generator.py        # Final Report 생성
│   ├── setup_labels.py            # 레이블 초기화
│   ├── github_client.py           # GitHub API 래퍼
│   ├── state_manager.py           # 로컬 상태 관리
│   └── validate_schema.py         # 스키마 검증
├── schemas/                        # JSON 스키마 정의
│   ├── task.schema.json
│   ├── release_readiness.schema.json
│   ├── assignment.schema.json
│   └── consensus.schema.json
├── config/                         # 설정 파일
│   ├── config.yaml
│   └── agents.json
├── templates/                      # target project에 복사할 템플릿
│   ├── AGENTS.md
│   ├── CLAUDE.md
│   ├── CODEX.md
│   ├── GEMINI.md
│   ├── setup.sh
│   └── inbox/
│       └── BRIEF-TEMPLATE.md
├── tests/                          # 단위 테스트 (59 tests)
│   ├── test_orchestrator.py
│   ├── test_consensus.py
│   ├── test_brief_parser.py
│   ├── test_github_client.py
│   ├── test_state_manager.py
│   ├── test_validate_schema.py
│   ├── test_report_generator.py
│   └── fixtures/                   # 테스트 데이터
├── pyproject.toml                  # Python 패키지 설정
├── .gitignore
├── .env.example
├── docs/                           # 참고 문서
│   ├── agents/                     # 에이전트 지시 초안
│   │   ├── AGENTS.md
│   │   ├── CLAUDE.md
│   │   ├── CODEX.md
│   │   └── GEMINI.md
│   └── multi-ai-orchestration-implementation-plan-v3.md
└── README.md                       # 이 문서

target-project/                     # Target 프로젝트 (실제 개발 대상, 별도 repo)
├── .orchestrator/                  # orch-agent-cli git submodule (선택 옵션)
├── .orchestra/                     # 로컬 운영 상태
│   ├── state/
│   │   └── assigned/              # 에이전트별 할당 파일
│   ├── cache/
│   │   └── issues/                # GitHub Issues 로컬 캐시
│   └── logs/                       # 에이전트 활동 log
├── inbox/                          # BRIEF 파일 투입 위치
├── docs/
│   ├── briefs/                     # 처리된 BRIEF 아카이브
│   ├── specs/                      # 요구사항 SPEC
│   ├── plans/                      # 작업 계획
│   ├── reviews/                    # 코드 리뷰 문서
│   ├── test-plans/                 # 테스트 계획
│   ├── reports/                    # Final Report
│   └── sessions/                   # 세션 아카이브
├── src/                            # 소스 코드
├── tests/                          # 테스트 코드
└── .env                            # 로컬 환경 설정

```

### 다음 단계 (Phase 2)

Phase 1 MVP 완료 이후 다음 기능들이 계획되어 있습니다:

- **Terminal Dashboard** (`scripts/dashboard.py`) — 실시간 진행 상황 모니터링
- **GitHub Webhook 지원** — Polling에서 Push 기반 이벤트로 전환 (선택)
- **Gemini CLI Red Team 통합** — 보안 검증 자동화
- **신뢰도 추적 시작** — 에이전트별 성능 메트릭 수집

---

## 2. 아키텍처: 이중 레이어 통신

**핵심 원칙: 속도보다 품질.** 에이전트 간 60초 지연은 허용. 충분한 검토 우선.

### 이중 레이어 구조

```
┌──────────────────────────────────────────────────────────────────┐
│                      개발자 워크스테이션                          │
│                                                                  │
│  Terminal 1 (Claude Code)    Terminal 2 (Codex CLI)              │
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │ $ claude            │    │ $ codex             │             │
│  │ [60-120초 polling]  │    │ [60-120초 polling]  │             │
│  └─────────────────────┘    └─────────────────────┘             │
│                                                                  │
│  Terminal 3 (Gemini CLI)     Terminal 4 (Orchestrator)           │
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │ $ gemini            │    │ $ python orchestrator│            │
│  │ [60-120초 polling]  │    │ [60초 GitHub polling]│            │
│  └─────────────────────┘    │ [단일 API 창구]      │            │
│                              │ [라우터+품질 게이트] │            │
│                              └──────────┬──────────┘             │
│                                         │                        │
│  ┌──────────────────────────────────────▼─────────────────────┐  │
│  │               .orchestra/ (로컬 운영 상태)                  │  │
│  │  state/assigned/  ← 에이전트별 할당 파일 (로컬 릴레이)      │  │
│  │  cache/issues/    ← GitHub Issues 로컬 캐시                 │  │
│  │  logs/            ← 에이전트 활동 log                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                         │                        │
└─────────────────────────────────────────┼────────────────────────┘
                                          │ gh CLI (60초 polling)
                                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                  GitHub Issues (공식 레코드)                      │
│                                                                  │
│  모든 요구사항, 설계 결정, 리뷰 결과, 에이전트 간 토론 전체 기록  │
│  인간이 언제든 감사 추적 가능                                      │
└──────────────────────────────────────────────────────────────────┘
```

### 두 레이어의 역할

**Layer 1 — GitHub Issues (공식 기록):**
- 모든 요구사항, 설계 결정, 리뷰 결과
- 에이전트 간 토론과 합의 과정 전체
- Blocking 이슈 및 해결 과정
- Final Report 이슈 (인간 알림)

**Layer 2 — 로컬 `.orchestra/` (운영 상태):**
- 에이전트 실행 lock (충돌 방지)
- GitHub Issues 로컬 캐시 (Orchestrator 작업용, 속도 릴레이 아님)
- 에이전트별 할당 파일 (Orchestrator가 기록, 에이전트가 60-120초마다 확인)
- 에이전트 활동 log (디버깅용)

### GitHub Issues 이벤트 감지: 기술 타당성

| 방법 | 가능 여부 | 권장 |
|------|---------|------|
| A: 에이전트별 직접 polling | 가능 (레이스 컨디션 문제) | Phase 1 프로토타입만 |
| B: GitHub Webhooks | 가능 (ngrok 필요, 복잡) | Phase 2 선택 옵션 |
| C: `gh issue watch` 명령 | **불가** (해당 명령 없음) | — |
| D: Orchestrator 중앙 polling + 로컬 상태 | 가능 | **권장 (기본)** |

> 상세 분석: [`docs/multi-ai-orchestration-implementation-plan-v3.md` §3](docs/multi-ai-orchestration-implementation-plan-v3.md)

---

## 3. 에이전트 역할

| 에이전트 | CLI 도구 | 실행 방식 | 핵심 역할 |
|----------|----------|-----------|-----------|
| **Claude Code** | `claude` | Terminal interactive / `claude -p` 비대화 모드 | 설계자 + reviewer + release manager |
| **Codex CLI** | `codex` | `codex exec --sandbox workspace-write` | 구현자 + patch 생성기 |
| **Gemini CLI** | `gemini` | Terminal interactive / API 호출 | 테스트 강화 + fact-checker (Red Team) |
| **Orchestrator** | `python orchestrator.py` | 상시 실행 데몬 | GitHub API 단일 창구 + 라우터 + 품질 게이트 |

### 역할 매트릭스

```
               BRIEF   요구사항  작업분해  구현/Patch  코드리뷰  테스트강화  합의  Release
               파싱    분석      분해                위험분석              판정
              ──────  ────────  ────────  ──────────  ────────  ──────────  ────  ───────
Claude Code           ●(P)      ●(P)                   ●(P)                      ●(P)
Codex CLI             ○(S)                ●(P)          ○(self)  ○(S)
Gemini CLI            ○(FC)               ○(S)          ○(Red)   ●(P)
Orchestrator  ●(P)                                                          ●(P)        ●(P)

●(P) = Primary    ○(S) = Secondary    ○(FC) = Fact-Check    ○(Red) = Red Team
```

---

## 4. 인간 문서 생애주기

### BRIEF — 인간이 작성하는 시작 문서

**위치:** `inbox/BRIEF-{YYYY-MM-DD}.md`  **언어:** 한국어 (기술 용어는 영어)

```markdown
# Project Brief: {프로젝트명}
**작성일:** YYYY-MM-DD
**대상 repo:** {GitHub repo URL}

## 개발 목표
## 핵심 요구사항
## 기술 제약사항
## 품질 기준
## 범위 제외 (Out of Scope)
```

**처리 흐름:**

```
인간: inbox/BRIEF.md 한국어 작성
  ↓ Orchestrator가 60초 내 감지
GitHub Issue #1 (KICKOFF) 생성 — 영어로 자동 변환
  Title: "KICKOFF: {영어 프로젝트명}"
  Source brief: docs/briefs/BRIEF-{date}.md (Korean original preserved)
  ↓
에이전트들: 영어 Kickoff Issue 읽고 자율 작업 시작
```

### 에이전트 생성 중간 문서

| 단계 | 생성 주체 | 로컬 파일 | GitHub 반영 |
|------|----------|----------|------------|
| 요구사항 분석 | Claude | `docs/specs/SPEC-{id}.md` | Issue 본문 |
| 구현 계획 | Claude | `docs/plans/PLAN-{id}.md` | Issue 댓글 |
| 구현 결과 | Codex | git commit history | Issue 댓글 + PR 링크 |
| 코드 리뷰 | Claude | `docs/reviews/REVIEW-{id}.md` | Issue 댓글 |
| 테스트 계획 | Gemini | `docs/test-plans/TEST-{id}.md` | Issue 댓글 |

### Final Report — 인간이 받는 최종 문서

- **GitHub Issue:** `type:final-report` 라벨, 인간 계정 @mention
- **로컬 파일:** `docs/reports/REPORT-{session_id}-{date}.md`
- **언어:** 한국어 + 기술 용어 영어
- **내용:** Executive summary, 완료 내용, Issues 처리 결과, 품질 지표, 합의 결과, 잔여 고려사항

---

## 5. GitHub Issues 프로토콜

### 라벨 체계

**Routing (담당 에이전트):** `agent:claude` / `agent:codex` / `agent:gemini` / `agent:orchestrator`

**Status (진행 상태):** `status:assigned` / `status:in-progress` / `status:review` / `status:approved` / `status:blocked` / `status:human-needed`

**Type (이슈 종류):** `type:kickoff` / `type:spec` / `type:implementation` / `type:review` / `type:test` / `type:final-report` / `type:escalation`

### 이슈 생명주기

```
Orchestrator: BRIEF 감지 → #1 KICKOFF Issue (type:kickoff)
  ↓
Claude: #2 SPEC Issue 생성 + Gemini 팩트체크 댓글
  ↓
Orchestrator: 검증 완료 → status:approved
  ↓
Codex: #3 Implementation, 완료 후 PR 링크 댓글
  ↓
Claude + Gemini: 코드 리뷰 댓글 → 합의 계산
  ↓
Orchestrator: 합의 통과 → #3 Close + Final Report Issue 생성
  ↓
인간: Final Report 확인 → PR review → merge
```

### 에이전트 댓글 형식 (영어 필수)

```markdown
## [Agent: claude] Spec Review Result

**Task:** SPEC-001 — User Authentication
**Verdict:** APPROVED
**Confidence:** 0.92

### Findings
- All acceptance criteria are testable
- No conflicts with existing API contracts

### Blockers
None

---
*Generated by claude at 2026-03-14T10:32:01Z*
```

### gh CLI 명령어 패턴

```bash
# 이슈 생성
gh issue create --title "SPEC: Implement user authentication" \
  --body "$(cat docs/specs/SPEC-001.md)" \
  --label "type:spec,agent:claude,status:in-progress"

# 댓글 추가
gh issue comment 2 --body "## Review Result ..."

# 라벨 변경
gh issue edit 2 --add-label "status:approved" --remove-label "status:review"

# 내 할당 이슈 조회
gh issue list --label "agent:claude,status:assigned" --json number,title,labels
```

---

## 6. 개발 프로세스 흐름

```
Stage 0: BRIEF 파싱       → Orchestrator → #1 KICKOFF Issue
Stage 1: 요구사항 분석    → Claude (Primary) + Gemini (fact-check)
Stage 2: 작업 분해/계획   → Claude (Primary) + Codex (실현성 검증)
Stage 3: 구현/Patch 생성  → Codex CLI (Primary) + Claude Code (보조)
Stage 4: 코드 Review      → Claude Code (Primary) + Gemini (보안 검증)
Stage 5: 테스트 강화      → Gemini CLI (Primary) + Codex (구현 보조)
Stage 6: Consensus 판정   → Orchestrator (자동 계산)
Stage 7: Release 준비     → Claude Code (Primary) + Codex (배포 script)
Stage 8: Final Report     → Orchestrator → 인간 @mention
Stage 9: 인간 최종 승인   → 개발자 PR 확인 → merge → deploy
```

---

## 7. Consensus 엔진

### 합의 알고리즘

모든 에이전트의 review 댓글이 수집되면 Orchestrator가 `scripts/consensus.py`를 자동 실행합니다.

```
유효 가중치 = base_weight × reliability × confidence

합의 비율 = Σ(유효 가중치 × ready 여부) / Σ(유효 가중치)
```

**판정 기준:**
- 합의 비율 ≥ 0.9 (90%) → **PASS** → PR 생성 가능
- 합의 비율 < 0.9 → **FAIL** → 해당 에이전트에 re-work 요청
- `veto` 투표 발생 → **즉시 차단** → re-review loop (최대 2회 → 인간 escalation)
- 점수 분산 > 20pt → **추가 증거 수집** 요청

### 에이전트 기본 가중치

```
Claude Code : base_weight 0.40  (설계·리뷰 전문가)
Codex CLI   : base_weight 0.35  (구현 전문가)
Gemini CLI  : base_weight 0.25  (테스트·보안 검증)
```

### 에스컬레이션 조건

동일 이슈에서 re-review가 `max_rereviews` (기본값: 2회)를 초과하면:
1. Orchestrator가 `type:escalation` 이슈 생성 + 인간 @mention
2. 해당 이슈는 `status:human-needed`로 대기
3. 나머지 독립적인 이슈는 계속 진행

---

## 8. 디렉토리 구조

```
orch-agent-cli/ (이 리포지토리)
├── scripts/
│   ├── orchestrator.py          # 중앙 Orchestrator (GitHub API 단일 창구)
│   ├── consensus.py             # 가중 합의 알고리즘
│   ├── brief_parser.py          # BRIEF 파싱 + 영어 변환 + Kickoff Issue 생성
│   ├── report_generator.py      # Final Report 자동 생성
│   ├── setup_labels.py          # GitHub Labels 초기 설정
│   ├── validate_schema.py       # JSON schema 검증
│   ├── dashboard.py             # Terminal 대시보드 (Phase 2)
│   └── webhook_server.py        # GitHub Webhook 수신 서버 (Phase 2 선택)
├── schemas/
│   ├── task.schema.json
│   └── release_readiness.schema.json
├── templates/                   # target project에 복사하는 기본 문서
│   ├── AGENTS.md
│   ├── CLAUDE.md
│   ├── CODEX.md
│   └── GEMINI.md
└── docs/

target-project/ (실제 개발 대상 — 별도 repo)
├── .orchestrator/               # orch-agent-cli 서브모듈 (Option A)
├── .orchestra/
│   ├── state/assigned/          # 에이전트별 할당 파일
│   ├── cache/                   # GitHub Issues 로컬 캐시 + 합의 결과
│   └── logs/                    # 에이전트 활동 log
├── inbox/                       # BRIEF 파일 투입구
├── docs/
│   ├── briefs/                  # 처리된 BRIEF 아카이브 (한국어 원본)
│   ├── specs/                   # 요구사항 spec (Claude 생성, 영어)
│   ├── plans/                   # 작업 분해 계획 (Claude 생성, 영어)
│   ├── reviews/                 # 코드 리뷰 (Claude/Gemini 생성, 영어)
│   ├── test-plans/              # 테스트 계획 (Gemini 생성, 영어)
│   ├── reports/                 # Final Report (한국어 + 기술용어 영어)
│   └── sessions/                # 세션 아카이브
├── src/                         # 소스 코드 (Codex 수정)
└── tests/                       # 테스트 (Gemini/Codex 작성)
```

---

## 9. 구현 Roadmap

### Phase 1 — MVP (4–6주)

**목표:** Claude Code + Codex CLI + Orchestrator 기본 loop. GitHub Issues를 통신 버스로 사용.

- [ ] `.orchestra/` 디렉토리 구조 생성
- [ ] GitHub Labels 생성 스크립트 (`scripts/setup_labels.py`)
- [ ] Task JSON schema 및 report schema 정의
- [x] `docs/agents/AGENTS.md`, `docs/agents/CLAUDE.md`, `docs/agents/CODEX.md` 역할 문서 작성 (초안)
- [ ] `scripts/orchestrator.py` — inbox polling + GitHub API polling + 로컬 할당 릴레이
- [ ] `scripts/brief_parser.py` — BRIEF 파싱 + 영어 변환 + Kickoff Issue 생성
- [ ] `scripts/consensus.py` — 가중 합의 알고리즘
- [ ] 2-에이전트 협업 loop 검증

### Phase 2 — 3-Agent 풀 가동 + 품질 강화 (8–12주)

**목표:** Gemini CLI 추가, Full GitHub Issues Workflow, 품질 게이트 강화

- [x] `docs/agents/GEMINI.md` 작성 (Red Team 역할, 초안)
- [ ] Final Report 자동 생성 (`scripts/report_generator.py`)
- [ ] 에스컬레이션 이슈 자동 생성 로직
- [ ] `scripts/dashboard.py` — terminal 기반 대시보드
- [ ] GitHub Webhook 지원 추가 (선택 옵션, ngrok 기반)
- [ ] 에이전트 신뢰도(reliability) 추적 시작

### Phase 3 — 강화 및 운영 최적화 (8–12주)

**목표:** 신뢰도 feedback loop, 보안 governance, 멀티 project 지원

- [ ] 배포 성공/실패 기반 신뢰도 자동 점수 조정
- [ ] 에이전트별 token 사용량 추적 및 비용 최적화
- [ ] OWASP LLM Top 10 대응 문서 및 자동화
- [ ] 프롬프트 injection 방어 테스트 (Red Team Gemini)
- [ ] 멀티 target project 동시 지원

---

## 10. 위험 요소 및 대응

### 동시성 및 GitHub 통신

| 문제 | 대응 방안 |
|------|-----------|
| 이슈 이중 할당 (레이스 컨디션) | Orchestrator 단일 라우터 → 원천 차단 |
| 두 에이전트가 동일 파일 동시 수정 | 단계별 수정 권한 분리 + 로컬 lock 파일 |
| GitHub API rate limit 초과 | Orchestrator 단일 창구 + 60초 간격 → 여유 충분 |
| 네트워크 장애로 GitHub sync 불가 | 로컬 상태로 작업 계속 + 복구 후 sync |
| Orchestrator 프로세스 크래시 | pm2/systemd 자동 재시작, 로컬 상태 파일에서 복구 |

### 에이전트 품질

| 문제 | 대응 방안 |
|------|-----------|
| JSON report schema 미준수 | `validate_schema.py` 자동 검증, 실패 시 재작성 요청 |
| 에이전트 hallucination → 거짓 "ready" | CI hard gate, 다중 에이전트 교차 검증, 분산 검사 |
| 에이전트가 한국어로 GitHub 댓글 작성 | AGENTS.md English-only 명시, Orchestrator 언어 감지 후 재작성 요청 |
| Context 한계로 대규모 codebase 파악 실패 | Task를 소규모 단위로 분할, 관련 파일만 context에 포함 |

### 보안

| 위협 | OWASP LLM | 대응 방안 |
|------|-----------|-----------|
| Prompt injection (이슈 내용 경유) | LLM01 | 외부 입력을 별도 파일로 격리 후 참조 |
| 에이전트가 secret을 GitHub 댓글에 노출 | LLM06 | 게시 전 `gitleaks` scan, pre-commit hook |
| 에이전트가 권한 외 명령 실행 | LLM08 | Codex `--sandbox workspace-write`, `AGENTS.md`로 파일 수정 범위 제한 |

---

## 11. Demo 시나리오

### Demo 1 — BRIEF to Kickoff (Phase 1)

BRIEF 파일 1개로 자동으로 GitHub Kickoff Issue가 생성되는 과정을 검증합니다.

1. 인간: `inbox/BRIEF-2026-03-14.md` 작성 (한국어)
2. Orchestrator: 60초 내 감지 → 영어 Kickoff Issue #1 자동 생성
3. Claude: `.orchestra/state/assigned/claude.json` 확인 → Issue #2 SPEC 생성

### Demo 2 — Three-Agent Consensus (Phase 2)

3개 에이전트 전체 프로세스 + 합의 통과 + Final Report 시연. 기대 합의 결과:

```json
{
  "can_proceed": true,
  "ratio": 0.94,
  "summary": "Consensus 94% (PASS)",
  "action": "PR ready",
  "details": {
    "claude":  { "score": 95, "vote": "ready", "confidence": 0.92 },
    "codex":   { "score": 92, "vote": "ready", "confidence": 0.88 },
    "gemini":  { "score": 91, "vote": "ready", "confidence": 0.85 }
  }
}
```

### Demo 3 — Veto & Red Team (Phase 2)

Gemini가 SQL Injection을 발견하고 `veto` 투표 → Orchestrator가 `status:blocked` 라벨 → Codex가 parameterized query로 수정 → 재리뷰 → 합의 통과

### Demo 4 — Graceful Degradation (Phase 3)

Gemini CLI 장애 시 30분 timeout → 잠금 해제 → Claude + Codex 2개 에이전트로 가중치 재분배하여 합의 진행. Final Report에 `"degraded mode: gemini unavailable"` 기록.

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|-----------|
| v1.0 | 2026-03-14 | 초판 (GitHub Actions 기반) |
| v1.1 | 2026-03-14 | 기존 인프라 참조 제거, 단일 환경 개정 |
| v2.0 | 2026-03-14 | 전면 재설계: 다중 terminal CLI 에이전트 협업 구조, file system 기반 task board, orchestrator, 가중 consensus 엔진 |
| v2.1 | 2026-03-14 | 에이전트 지시 문서를 루트에서 `docs/agents/`로 이동 |
| v2.2 | 2026-03-14 | `implementation-plan-v2.md`를 루트에서 `docs/`로 이동 |
| v3.0 | 2026-03-14 | **v3 전면 개정 반영:** orch-agent-cli 설치형 도구 성격 명시, GitHub Issues 이중 레이어 통신 아키텍처, GitHub Issues 이벤트 감지 기술 타당성 분석, 인간 문서 생애주기 (BRIEF→Final Report), GitHub Issues 프로토콜 및 라벨 체계, 에이전트 자율 루프 및 에스컬레이션 조건 |
