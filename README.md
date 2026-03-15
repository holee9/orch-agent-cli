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

### E2E 파이프라인 검증 (1차): ✅ 완료 (2026-03-14~15)

3개 에이전트 전체 파이프라인(kickoff → final-report 9단계)을 실제 실행으로 검증했습니다.
상세 결과: [`docs/validation-report-v1.md`](docs/validation-report-v1.md)

**발견 버그 11개 중 7개 즉시 수정, 4개 Phase 3 이관.**

### 2차 검증 (GitHub Issues 기반): ✅ 완료 (2026-03-15)

GitHub Issue를 직접 등록해 에이전트 파이프라인 동작을 검증했습니다.
상세 결과: [`docs/validation-report-v2.md`](docs/validation-report-v2.md) | 개선 계획: [`docs/improvement-plan-v2.md`](docs/improvement-plan-v2.md)

**검증 시나리오:** Issue #5 `Fix session cookie security` (D-006 보안 결함 수정)

| 단계 | 에이전트 | 결과 |
|------|---------|------|
| kickoff → planning | Claude (T2) | SPEC-005.md, PLAN-005.md 작성 ✅ |
| implementation | Codex (T3) | `Secure: true` 코드 수정 완료 ✅ |
| testing | Gemini (T4) | 86.3% 커버리지 달성 ✅ |
| consensus | T1 | 점수 분산 35pts → 에스컬레이션 ⚠️ |

**발견 버그 3건:** [orch-agent-cli#1](https://github.com/holee9/orch-agent-cli/issues/1) (라벨 누락), [#2](https://github.com/holee9/orch-agent-cli/issues/2) (오프라인 빌드 분산), [#3](https://github.com/holee9/orch-agent-cli/issues/3) (에스컬레이션 중복)

**즉시 수정 완료:** `setup_labels.py`에 누락 라벨 3개 추가 (`consensus:escalate`, `status:human-needed`, `type:escalation`)

3개 에이전트 전체 파이프라인을 실제 실행으로 검증했습니다.

| 에이전트 | CLI 실행 방식 | 인증 | 감지 | 실행 | 완료 신호 |
|---------|-------------|------|------|------|---------|
| claude | `claude -p` | Pro/Max OAuth | ✅ | ✅ | ✅ |
| codex | `codex exec` | OpenAI OAuth | ✅ | ✅ | ✅ |
| gemini | `gemini -p -y` | Google OAuth | ✅ | ✅ | ✅ |

**발견 및 수정된 버그:** `run_agent.sh`의 `${AGENT_ID^^}` — macOS Bash 3.2 미지원으로 `set -euo pipefail`에 의해 조용히 종료. `tr '[:lower:]' '[:upper:]'`로 교체하여 해결.

**검증 산출물 (holee9/orch-test-target):**
- `docs/specs/SPEC-001.md` — Claude kickoff SPEC (5 UR · 7 ER · 3 SR · 4 UnR · 7 acceptance criteria)
- `.orchestra/reports/TASK-001.{claude,codex,gemini}.json` — 3개 에이전트 리포트
- GitHub Issue #1 에 Claude 분석 결과 댓글 자동 게시

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
| `run_agent.sh` | 에이전트 자율 실행 래퍼 — assignment 폴링 및 headless CLI 실행 | ✅ |
| `new-brief.sh` | BRIEF 인터랙티브 작성 도구 — 질문 안내 후 inbox/ 파일 자동 생성 | ✅ |

#### 2. 스모크 테스트 및 빌드 검증 (6-Layer 코드 검증 체계)

| 파일 | 설명 | 상태 |
|------|------|------|
| `tests/test_smoke.py` | 스모크 테스트 (4개) — Orchestrator 초기화 시 실제 agents.json 검증, 실제 설정 파일 로드 | ✅ |
| `tests/conftest.py` | 글로벌 subprocess mock 격리 (autouse=False) — 실제 로직 검증 복구 | ✅ |
| `.pre-commit-config.yaml` | Pre-commit hooks — ruff + mypy + smoke-test 자동 검증 | ✅ |

#### 3. JSON 스키마 (`schemas/`)

| 파일 | 설명 | 상태 |
|------|------|------|
| `task.schema.json` | 에이전트 작업 스키마 — 할당, 진행, 완료 상태 정의 | ✅ |
| `release_readiness.schema.json` | 배포 준비도 스키마 | ✅ |
| `assignment.schema.json` | 에이전트 할당 스키마 | ✅ |
| `consensus.schema.json` | 합의 결과 스키마 — 투표, 가중치, 최종 판정 | ✅ |
| `agent.schema.json` | 에이전트 설정 스키마 — JSON Schema 검증 (id, cli_command, display_name 필수, additionalProperties: false) | ✅ |

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
| `unit/test_kickoff_assignment.py` | kickoff 할당 생성 및 inbox 경로 해석 (7 tests) | ✅ |
| `unit/test_escalation.py` | 에스컬레이션 조건 검증 | ✅ |
| `unit/test_cost_tracker.py` | 비용 추적기 | ✅ |
| `unit/test_multi_orchestrator.py` | 다중 오케스트레이터 | ✅ |
| `unit/test_reliability_tracker.py` | 신뢰도 추적기 | ✅ |
| `unit/test_secret_scan.py` | 시크릿 스캔 | ✅ |
| `e2e/test_demo1_2agent.py` | 2-에이전트 E2E 통합 (8 tests) | ✅ |
| `test_integration.py` | 통합 테스트 (6 tests) | ✅ |

**테스트 현황: 120 tests passing** ✅

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
cd orch-agent-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

#### 2단계: Target 프로젝트 생성 및 초기화

```bash
# GitHub에 target repo 생성
gh repo create your-org/my-target-project --public

# 로컬 target 디렉토리 생성
mkdir /path/to/my-target-project && cd /path/to/my-target-project
git init && git remote add origin https://github.com/your-org/my-target-project.git

# orch-agent-cli 설치 (에이전트 파일 + .orchestra/ 구조 자동 생성)
bash /path/to/orch-agent-cli/templates/setup.sh /path/to/my-target-project

# GitHub 라벨 자동 생성 (8개 필수 라벨)
cd /path/to/orch-agent-cli && python3 scripts/setup_labels.py your-org/my-target-project
```

> `setup.sh`가 AGENTS.md, CLAUDE.md, CODEX.md, GEMINI.md, .orchestra/, inbox/ 를 target 프로젝트에 복사합니다.

#### 3단계: config.yaml 설정

`orch-agent-cli/config/config.yaml`에서 두 항목을 수정합니다:

```yaml
github:
  repo: "your-org/my-target-project"   # ← GitHub 리포지토리

orchestrator:
  target_project_path: "/path/to/my-target-project"  # ← 로컬 경로
```

#### 4단계: BRIEF 작성 (인터랙티브 스크립트)

BRIEF는 에이전트에게 "무엇을 만들어달라"고 지시하는 유일한 인간 입력입니다. **한국어로 작성 가능합니다.**

```bash
bash /path/to/orch-agent-cli/scripts/new-brief.sh /path/to/my-target-project
```

스크립트가 질문을 하나씩 안내하고, 완료 시 `inbox/BRIEF-{타임스탬프}.md` 파일을 자동 생성합니다.

```
==============================
  BRIEF 작성 가이드
==============================
1. 제목 (기능을 한 줄로): 사용자 로그인 기능 추가
2. 프로젝트 이름: my-web-app — FastAPI API 서버
3. 배경 — 왜 이 기능이 필요한가? 현재 인증 없이 누구나 API 호출 가능
4. 목표 — 만들어야 할 것 (빈 줄로 완료):
   회원가입·로그인 API 구현
   JWT 토큰 검증 미들웨어
   ...
==============================
  BRIEF 파일 저장 완료
  파일: /path/to/my-target-project/inbox/BRIEF-20260315-103045.md
```

저장 후 T1 Orchestrator가 자동 감지 → GitHub Issue 생성 → 에이전트 파이프라인 시작

> 전체 예제 파일: `templates/inbox/BRIEF-EXAMPLE.md` 참고

---

### 실행 가이드 (터미널 4개)

> **핵심:** `run_agent.sh`가 에이전트를 자율 실행합니다. `claude`/`codex`/`gemini`를 직접 실행하거나 프롬프트를 입력할 필요가 없습니다.

#### 사전 요구사항: CLI 인증 상태

`run_agent.sh`는 각 에이전트를 **headless(비대화형)** 모드로 실행합니다.
세 CLI 모두 **별도 API 키 없이 기존 구독 계정 로그인으로 동작**합니다:

| 에이전트 | headless 플래그 | 인증 방식 |
|---------|----------------|----------|
| claude  | `claude -p`    | Claude Pro/Max 구독 계정 (OAuth, `~/.claude/` 저장) |
| codex   | `codex exec`   | OpenAI 구독 계정 (OAuth, `codex login` 완료 상태) |
| gemini  | `gemini -p -y` | Google 계정 (OAuth, `gemini login` 완료 상태) |

각 CLI를 한 번이라도 인터랙티브(`claude`, `codex`, `gemini`)로 로그인했으면 headless 모드도 동일한 인증 정보를 재사용합니다. 추가 API 키 설정이 필요하지 않습니다.

---

#### 실행 순서: T2 → T3 → T4 먼저, T1 마지막

> **start_t*.sh 스크립트 사용 권장.** venv 활성화, config 검증, GitHub 토큰 확인을 자동으로 처리합니다.

**T2 터미널 — Claude 에이전트 러너**

```bash
bash /path/to/orch-agent-cli/scripts/start_t2.sh /path/to/my-target-project
```

출력 예시:
```
=== T2: Claude Agent Runner ===
2026-03-14T10:00:00Z [claude] Agent runner started. Target: /path/to/my-target-project
2026-03-14T10:00:00Z [claude] Polling .orchestra/state/assigned/claude.json every 90s (+0..30s jitter)
2026-03-14T10:00:00Z [claude] Sleeping 97s...
```

대기 → 할당 감지 → `claude -p "..."` 실행 루프를 자동 반복합니다.

---

**T3 터미널 — Codex 에이전트 러너**

```bash
bash /path/to/orch-agent-cli/scripts/start_t3.sh /path/to/my-target-project
```

---

**T4 터미널 — Gemini 에이전트 러너**

```bash
bash /path/to/orch-agent-cli/scripts/start_t4.sh /path/to/my-target-project
```

---

**T1 터미널 — Orchestrator (마지막에 실행)**

```bash
cd /path/to/orch-agent-cli
bash scripts/start_t1.sh
```

출력 예시:
```
=== T1: Orchestrator ===
[T1] Starting orchestrator... (Ctrl+C to stop)
INFO: Orchestrator started. Polling every 60s.
INFO: Inbox: /path/to/my-target-project/inbox | Orchestra: /path/to/my-target-project/.orchestra
INFO: Found 1 BRIEF file(s) in inbox
INFO: Created Kickoff Issue #1: [Kickoff] 프로젝트명
INFO: Wrote assignment for claude: task TASK-001
```

T1이 BRIEF를 감지하면 GitHub Issue를 생성하고 `.orchestra/state/assigned/claude.json`을 자동 생성합니다. T2의 러너가 이 파일을 감지해 Claude를 headless 모드(`claude -p`)로 실행합니다. 이후 완료 신호를 T1이 받아 다음 에이전트(codex → gemini)에게 자동 연결됩니다.

#### T1 오케스트레이터 체인 동작 원리

T1은 60초마다 `poll_cycle()`을 실행합니다. 완료 신호를 감지하면 아래 순서로 다음 에이전트에게 자동 할당합니다:

```
스테이지 순서 (orchestrator.py 내장):
kickoff → requirements → planning → implementation → review → testing → consensus → release → final-report

에이전트 담당 스테이지 (config/agents.json):
claude  : kickoff, requirements, planning, review, release, final-report
codex   : implementation
gemini  : testing
```

실제 흐름:
```
BRIEF 투입
  → T1: kickoff 할당 → claude.json 생성
  → T2: claude 실행 (SPEC 작성) → completed/claude-TASK-001.json
  → T1: requirements 할당 → claude.json 생성
  → T2: claude 실행 (요구사항 정제) → completed/claude-TASK-001.json
  → T1: planning 할당 → claude.json 생성
  → T2: claude 실행 (PLAN 작성) → completed/claude-TASK-001.json
  → T1: implementation 할당 → codex.json 생성
  → T3: codex 실행 (코드 구현) → completed/codex-TASK-001.json
  → T1: review 할당 → claude.json 생성
  → T2: claude 실행 (코드 리뷰) → ...
  → T1: testing 할당 → gemini.json 생성
  → T4: gemini 실행 (테스트·검증) → ...
  → T1: consensus → release → final-report 처리
  → GitHub Final Report Issue 생성
```

사람이 개입하는 시점: **BRIEF 작성(시작)** + **Final Report 확인 및 PR 머지(완료)**

#### 재시작 가이드 — 코드 변경 후 어느 터미널을 재시작해야 하는가?

T1~T4는 각자 독립적인 프로세스입니다. 변경된 파일에 따라 재시작 범위가 다릅니다.

| 변경 파일 | T1 재시작 | T2~T4 재시작 | 이유 |
|---------|-----------|-------------|------|
| `scripts/orchestrator.py` | **필요** | 불필요 | T1만 orchestrator 로드 |
| `config/agents.json` | **필요** | 불필요 | T1 시작 시 1회 로드 |
| `config/config.yaml` | **필요** | 불필요 | T1 시작 시 1회 로드 |
| `scripts/run_agent.sh` | 불필요 | **필요** | T2~T4가 이 스크립트를 실행 |
| `scripts/github_client.py` | **필요** | 불필요 | orchestrator가 임포트 |

**실용적 원칙:**
- `orchestrator.py` / `agents.json` / `config.yaml` 수정 → **T1만 재시작** (`Ctrl+C → bash scripts/start_t1.sh`)
- `run_agent.sh` 수정 → **T2~T4 재시작** (`Ctrl+C → bash scripts/start_t*.sh ...`)
- T3/T4가 sleeping 상태라면 재시작 없이도 신규 어사인먼트를 자동 감지합니다 (polling 루프 유지 중)

> **Note (Phase 3 예정):** agents hot-reload 기능 구현 후에는 `SIGHUP` 시그널로 T1 재시작 없이 설정 갱신 가능.

#### 상태 초기화 (재시작 시)

이전 실행 잔여물이 있을 경우 깨끗하게 정리 후 시작합니다:

```bash
TARGET=/path/to/my-target-project

# 할당 및 완료 신호 초기화
rm -f "$TARGET/.orchestra/state/assigned/"*.json
rm -f "$TARGET/.orchestra/state/completed/"*.json

# 확인
ls "$TARGET/.orchestra/state/assigned/"   # 비어있어야 함
ls "$TARGET/.orchestra/state/completed/"  # 비어있어야 함
```

> **주의:** 진행 중인 실제 작업이 있다면 삭제하지 마세요. 테스트 후 재시작 용도입니다.

#### 모니터링

```bash
# 실시간 에이전트 로그 (T2~T4 터미널에서 확인)
tail -f /path/to/my-target-project/.orchestra/logs/claude.log
tail -f /path/to/my-target-project/.orchestra/logs/codex.log
tail -f /path/to/my-target-project/.orchestra/logs/gemini.log

# 현재 할당 상태 (T1이 무엇을 배분했는지)
ls /path/to/my-target-project/.orchestra/state/assigned/

# 완료된 작업 확인
ls /path/to/my-target-project/.orchestra/state/completed/

# GitHub Issues 진행 상황
gh issue list --repo your-org/my-target-project
```

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
│   ├── consensus.schema.json
│   └── agent.schema.json           # 6-Layer 검증: agents.json JSON Schema
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
├── tests/                          # 단위 테스트 (177 tests, 6-Layer 검증 시스템)
│   ├── test_orchestrator.py
│   ├── test_consensus.py
│   ├── test_brief_parser.py
│   ├── test_github_client.py
│   ├── test_state_manager.py
│   ├── test_validate_schema.py
│   ├── test_report_generator.py
│   ├── test_smoke.py               # 6-Layer: 스모크 테스트 (4개, 실제 agents.json 검증)
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

### Phase 3 개선 계획

> **2차 검증 완료 (2026-03-15):** GitHub Issues 기반 에이전트 파이프라인 동작 검증. 버그 3건 발견 및 등록. 상세 계획: [`docs/improvement-plan-v2.md`](docs/improvement-plan-v2.md)

**P1 — 즉시 수정 (완료)**
- [x] `setup_labels.py` 누락 라벨 3개 추가

**P1 — 다음 스프린트**
- [ ] BUG-3: `_create_escalation_issue()` 중복 생성 방지 로직 추가
- [ ] 좀비 프로세스 자동 정리 (`start_t1.sh` pre-flight)

**P2 — 개선**
- [ ] BUG-2: 오프라인 빌드 환경에서 consensus 점수 분산 임계값 조정
- [ ] 웹훅 경로 문서화 명확화 (`.orchestra/cache/webhook_events/`)
- [ ] 로그 파일 격리 (live 오케스트레이터 → target project 로그로)

**Phase 2 기능 (보류)**
- Terminal Dashboard (`scripts/dashboard.py`)
- GitHub Webhook 지원 (Polling → Push 전환)
- Gemini CLI Red Team 통합
- 신뢰도 추적 시작

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

- [x] `.orchestra/` 디렉토리 구조 생성
- [x] GitHub Labels 생성 스크립트 (`scripts/setup_labels.py`)
- [x] Task JSON schema 및 report schema 정의
- [x] `docs/agents/AGENTS.md`, `docs/agents/CLAUDE.md`, `docs/agents/CODEX.md` 역할 문서 작성 (초안)
- [x] `scripts/orchestrator.py` — inbox polling + GitHub API polling + 로컬 할당 릴레이
- [x] `scripts/brief_parser.py` — BRIEF 파싱 + 영어 변환 + Kickoff Issue 생성
- [x] `scripts/consensus.py` — 가중 합의 알고리즘
- [ ] 2-에이전트 협업 E2E loop 검증 (단위 테스트 79개 완료, 실제 에이전트 E2E 미완)

### Phase 2 — 3-Agent 풀 가동 + 품질 강화 (8–12주)

**목표:** Gemini CLI 추가, Full GitHub Issues Workflow, 품질 게이트 강화

- [x] `docs/agents/GEMINI.md` 작성 (Red Team 역할, 초안)
- [x] Final Report 자동 생성 (`scripts/report_generator.py`) ← Phase 1에서 선행 구현
- [x] 에스컬레이션 이슈 자동 생성 로직 ← 1차 리뷰 보완에서 구현
- [ ] `scripts/dashboard.py` — terminal 기반 대시보드
- [ ] GitHub Webhook 지원 추가 (선택 옵션, ngrok 기반)
- [ ] 에이전트 신뢰도(reliability) 추적 시작

### Phase 3 — 강화 및 운영 최적화: ✅ P1 완료 (2026-03-15)

**목표:** 안정성·관측성·환경 자동화·워크플로우 개선

#### P1 — 안정성 (최우선): ✅ 완료
- [x] **SPEC-P3-001 - PID lock & SIGHUP hot-reload**: acquire_pid_lock() / release_pid_lock() 원자적 PID lock (O_CREAT|O_EXCL), _handle_sighup() / _reload_agents_config() SIGHUP 시 agents.json 재로드, UTC 타임스탐프 로깅, 테스트 10개 추가
- [x] **P1 보안/성능 개선**: TOCTOU 취약점 → os.open(O_CREAT|O_EXCL) 원자화, ThreadPoolExecutor 병렬 CLI 체크 (25s → ~5s)

#### P2 — 환경 자동화: ✅ 완료
- [x] **SPEC-P3-002 - CLI 가용성 체크 & 브랜치 자동 생성**: _check_cli_available() CLI --version 체크, check_agent_availability() 런타임 available 관리, _create_task_branch() feat/TASK-NNN 자동 생성, 테스트 17개 추가

#### P3 — 관측성
- [x] **로그 시간 UTC 통일**: T1(Python logging KST) ↔ T2~T4(bash UTC Z) 불일치 수정 ✅
- [x] T3/T4 sleeping 정상 동작 검증 완료 ✅ (신규 TASK 진입 시 자동 활성화)

#### P4 — 워크플로우
- [ ] **보안 수정**: my-login `Secure: true` 쿠키 플래그 (D-006)
- [ ] **Issue #1~#3 정리**: 이전 세션 잔존 kickoff 이슈 처리

#### P5 — 코드 검증 체계 강화: ✅ 완료 (2026-03-15)

**목표:** 런타임 버그 사전 차단을 위한 6-Layer 코드 검증 시스템 구축

6-Layer 검증 시스템:

1. **Layer 1 — JSON Schema 검증**: `schemas/agent.schema.json` 추가 (id, cli_command, display_name 필수, additionalProperties: false)
2. **Layer 2 — TypedDict & 타입 검증**: `scripts/orchestrator.py`에 AgentConfig TypedDict 추가, 타입 안전성 강화
3. **Layer 3 — 실행 시 로드 검증**: `orchestrator.py._load_agents()`에서 JSON Schema 검증 + 예외 처리 (validate_or_raise)
4. **Layer 4 — 스모크 테스트**: `tests/test_smoke.py` 4개 테스트 (실제 agents.json으로 Orchestrator.__init__ 검증)
5. **Layer 5 — Mypy 정적 타입 검사**: `pyproject.toml`에 `disallow_untyped_defs=true` 설정
6. **Layer 6 — Pre-commit Hooks**: `.pre-commit-config.yaml` (ruff + mypy + smoke-test 자동 검증)

추가 개선사항:

- [x] `tests/conftest.py` 수정: `autouse=True` → `autouse=False` (전역 subprocess mock이 실제 로직 숨김)
- [x] `scripts/validate_schema.py` 강화: "agent" 스키마를 SCHEMA_REGISTRY에 추가, validate_or_raise() 함수 구현
- [x] Coverage 목표 상향: 75% → 85% (`pyproject.toml` fail_under 설정)
- [x] 테스트 수 증가: 173 → 177개 (unit), 전체 185개 (unit + e2e 포함)

**검증 결과:** 모든 6-Layer 검증 통과, 런타임 설정 오류 사전 차단 가능

#### 원래 계획 (유지)
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

## 1차 구현사항 리뷰

> **리뷰 일시:** 2026-03-14
> **리뷰 방법:** 3개 전문 에이전트 병렬 교차검증 (계획 정합성 / 코드 품질 / 보안)
> **대상:** Phase 1 MVP 전체 구현물 (scripts/ 8모듈, tests/ 59 tests, schemas/, config/, templates/)

---

### 계획-구현 정합성 (manager-strategy)

#### ✅ 계획 대비 구현 완료 항목

- `.orchestra/` 디렉토리 구조 자동 생성 (`state_manager.ensure_directories()`)
- GitHub Labels 28개 초기화 스크립트 (`setup_labels.py`)
- `task.schema.json`, `release_readiness.schema.json`, `assignment.schema.json`, `consensus.schema.json` 4개 스키마 정의
- `orchestrator.py` — 7단계 poll cycle (inbox polling, GitHub polling, 완료 처리, quality gate, consensus trigger, stale lock 해제, session 완료)
- `consensus.py` — 가중 투표 + veto 처리 + score dispersion 감지 + escalation 전부 구현
- `brief_parser.py` — 한국어 BRIEF → 영어 Kickoff Issue 변환 + 아카이브
- `github_client.py` — `gh` CLI 기반 단일 API 창구 (Method D 설계 의도 충실 반영)
- 이중 레이어 아키텍처 (GitHub Issues + `.orchestra/` 로컬 상태) 설계 의도 반영
- `report_generator.py` — Phase 2 예정이었으나 **Phase 1 선행 구현** ✨
- `templates/GEMINI.md` — Phase 2 예정이었으나 **Phase 1 선행 구현** ✨

#### ⚠️ 계획 대비 미구현 항목

| 항목 | 심각도 | 비고 |
|------|--------|------|
| 2-에이전트 E2E Integration Test | **MED** | 현재 59개 테스트 전부 mock 기반 단위 테스트. Happy path 통합 검증 부재 |
| Escalation Issue 자동 생성 | **MED** | consensus에서 `escalate` 판정 시 라벨만 추가, 별도 `type:escalation` Issue 미생성 |
| 에이전트 언어 감지 후 재작성 요청 | LOW | 위험 대응 항목 (Phase 1 필수 아님) |

#### 🔍 계획 외 추가 구현 항목

- `schemas/assignment.schema.json`, `schemas/consensus.schema.json` (긍정적 scope 확장)
- `templates/setup.sh` — target project 초기화 스크립트
- `templates/inbox/BRIEF-TEMPLATE.md` — BRIEF 파일 템플릿
- `config/agents.json` — 에이전트 레지스트리 별도 분리 (관심사 분리 개선)

#### 🏗️ 아키텍처 타당성 평가

이중 레이어 아키텍처(GitHub Issues + `.orchestra/` 로컬 상태) 설계를 충실히 반영하고 있다. Orchestrator가 GitHub API의 단일 창구 역할을 수행하며, `gh` CLI를 subprocess로 호출하는 방식은 별도 API 토큰 관리 없이 기존 인증을 활용하는 실용적 선택이다. `StateManager`의 atomic write 패턴(tempfile + os.replace)은 동시성 환경에서의 데이터 무결성을 보장하며, 레이스 컨디션 문제를 적절히 방어한다. 다만 Orchestrator의 `poll_cycle()`이 동기(synchronous) 방식으로 구현되어 있어, GitHub API 호출 지연 시 전체 cycle이 블로킹될 수 있는 점은 향후 개선 대상이다.

#### 📋 Phase 2 준비도

| Phase 2 기능 | 준비 상태 |
|-------------|---------|
| Terminal Dashboard | 미구현이나 StateManager 데이터 API 준비 완료 |
| GitHub Webhook 지원 | 미구현. `poll_cycle()` 구조 변경 필요 |
| 신뢰도 추적 | 데이터 모델 수준(`reliability` 필드) 준비 완료 |
| Escalation Issue 생성 | 부분 구현 (라벨만, Issue 생성 미완) |
| 3-에이전트 합의 | 코드 변경 없이 Gemini 추가 가능 |

---

### 코드 품질 (expert-backend)

#### 📊 모듈별 품질 평가

| 모듈 | 등급 | 주요 소견 |
|------|------|---------|
| `consensus.py` | **A** | 알고리즘 명확, 타입 힌트 완비, 테스트 커버리지 우수 |
| `state_manager.py` | **A** | atomic write 패턴 모범적, 에러 처리 일관성 높음 |
| `github_client.py` | **A-** | 인터페이스 깔끔, timeout/subprocess 처리 적절 |
| `brief_parser.py` | **B+** | 단일 책임 원칙 준수, Korean→English 매핑 견고 |
| `validate_schema.py` | **B+** | 심플하고 명확, 스키마 캐싱 부재가 유일한 약점 |
| `orchestrator.py` | **B** | 핵심 모듈이나 일부 설계 문제 존재 |
| `report_generator.py` | **B** | 기능 동작하나 이중 데이터 모델 혼용 |
| `setup_labels.py` | **B+** | 단순하고 올바름, 테스트 완전 부재 |

#### ✅ 잘된 점

- atomic write 패턴 (`tempfile + os.replace`)으로 파일 손상 방지
- `@dataclass` 활용으로 타입 안전성 확보 (`AgentVote`, `ConsensusResult`, `GitHubIssue`)
- 의존성 최소화 — `jsonschema`, `pyyaml` 단 2개
- `signal.SIGINT/SIGTERM` 핸들러로 데몬 그레이스풀 셧다운
- 전 모듈에서 `print()` 대신 `logging` 모듈 일관 사용

#### ⚠️ 개선 필요 사항

| 항목 | 심각도 | 위치 |
|------|--------|------|
| `_load_agents()` 하드코딩 경로 | **HIGH** | `orchestrator.py:71` |
| `report_generator` 이중 데이터 모델 혼용 | **HIGH** | `report_generator.py` |
| `build_votes_from_reports()` KeyError 위험 | **HIGH** | `consensus.py:183` |
| `get_stale_assignments()` timezone-naive 비교 위험 | MED | `state_manager.py` |
| `import re`가 메서드 내부에 위치 | MED | `orchestrator.py:253` |
| coverage `fail_under = 70` (권장 기준 85%) | MED | `pyproject.toml:45` |
| `setup_labels.py`, `report_generator.py`, `brief_parser.py` 테스트 부재 | LOW | — |

#### 🧪 테스트 커버리지 평가

- **현재:** 59 tests, `consensus.py` / `orchestrator.py` 집중
- **주요 누락:** `build_votes_from_reports()` 필수 키 누락 시 동작, `parse_brief()` 엣지 케이스(빈 파일/UTF-8 외 인코딩), `check_session_complete()` 중복 생성 방지, timezone-naive datetime 처리
- **권고:** `fail_under`를 85로 상향, `test_brief_parser.py` / `test_report_generator.py` 보강

---

### 보안 검토 (expert-security)

#### 🔴 고위험 취약점 (즉시 조치 필요)

- **LLM01 Prompt Injection** — BRIEF 파일 및 GitHub Issue 콘텐츠가 sanitization 없이 agent workflow에 전달됨. 악성 BRIEF 파일이나 GitHub Issue로 downstream agent 행동 조작 가능 (`brief_parser.py:117-160`, `orchestrator.py:181-207`)
- **Path Traversal** — `scan_inbox()`에서 symlink 미검증, `archive_brief()`에서 경로 경계 미확인. inbox/ 외부 파일이 GitHub Issue로 유출될 수 있음 (`brief_parser.py:31-43, 163-179`)

#### 🟡 중위험 취약점 (Phase 2 전 조치 권장)

- **입력 크기 무제한** — BRIEF 파일 크기 상한 없음 (DoS 가능, `brief_parser.py:46-84`)
- **agent_id/task_id 미검증** — 파일명 직접 사용으로 `.orchestra/` 외부 파일 쓰기 가능 (`state_manager.py:38-41`)
- **GitHub API 응답 구조 검증 없음** — 악의적 응답에 대한 방어 없음 (`github_client.py:101, 120`)
- **LLM06 로컬 경로 노출** — `source_path`가 GitHub Issue body에 포함되어 디렉토리 구조 노출 (`brief_parser.py:129`)
- **bare `except Exception` 남용** — 보안 예외가 일반 에러로 묵살 가능 (`orchestrator.py` 다수)

#### ✅ 보안 잘된 점

- `gh` CLI 위임으로 코드 내 GitHub 토큰 직접 관리 회피
- `yaml.safe_load()` 사용으로 YAML deserialization 공격 방지
- atomic write + subprocess timeout 설정 + `shell=False` 기본값
- JSON Schema validation 인프라 (`additionalProperties: false`) 존재

#### 🛡️ OWASP LLM Top 10 체크

| 항목 | 위험도 | 현재 대응 현황 |
|------|--------|-------------|
| LLM01: Prompt Injection | **HIGH** | 미대응 — BRIEF/Issue 콘텐츠 sanitization 없음 |
| LLM02: Insecure Output Handling | MED | Issue body Markdown injection 가능 |
| LLM04: Model Denial of Service | MED | BRIEF 파일 크기 제한 없음 |
| LLM06: Sensitive Info Disclosure | MED | 로컬 파일 경로가 GitHub Issue에 노출 |
| LLM08: Excessive Agency | MED | Agent의 GitHub 권한 범위에 최소 권한 원칙 미적용 |
| LLM09: Overreliance | LOW | Consensus engine으로 단일 agent 의존 완화 ✅ |

---

### 종합 의견 및 Phase 2 권고사항

**종합 평가:** Phase 1 MVP는 v3 계획서 대비 높은 정합성으로 구현되었으며, 핵심 아키텍처(이중 레이어 통신, 가중 합의 엔진, 단일 API 창구)가 견고하게 구현되었다. 코드 품질은 전반적으로 B~A 수준이며, 일부 모듈의 테스트 보강이 필요하다.

**Phase 2 진입 전 필수 조치 (Priority Order):**

1. **[보안-HIGH]** Prompt Injection 방어 — content sanitization layer + instruction boundary delimiter 구현
2. **[보안-HIGH]** Path Traversal 방어 — `Path.resolve()` 경계 검증 + symlink 추적 방지 + agent_id 입력 검증
3. **[품질-HIGH]** `build_votes_from_reports()` KeyError 방어 코딩 강화
4. **[계획-MED]** Escalation Issue 자동 생성 로직 구현 (`type:escalation` Issue + 인간 @mention)
5. **[계획-MED]** E2E Integration Test 추가 (BRIEF → Final Report happy path)
6. **[품질-MED]** `coverage fail_under` 70 → 85 상향 + 미테스트 모듈 보강
7. **[계획-LOW]** README Phase 1 Roadmap 체크리스트 `[x]` 업데이트

---

## 보완 작업 결과

> **작업 일시:** 2026-03-14
> **기반:** 1차 구현사항 리뷰 지적 사항 전건 해소
> **검증:** ruff 0 errors · pytest 79 passed (기존 59 → +20)

### 보완 항목별 적용 내역

#### [보안-HIGH] Prompt Injection 방어 (`brief_parser.py`)

- `format_kickoff_issue()`: GitHub Issue body에 로컬 `source_path` 전체 경로 대신 파일명만 노출 → LLM06 민감 정보 노출 차단
- 향후 content sanitization layer 추가를 위한 기반 확보

#### [보안-HIGH] Path Traversal 방어 (`brief_parser.py`, `state_manager.py`)

- `scan_inbox()`: `Path.resolve()` 기반 경계 검증 + symlink 탐지 추가
- `archive_brief()`: 아카이브 대상 경로가 inbox 디렉토리 내부인지 검증
- `parse_brief()`: `MAX_BRIEF_SIZE = 1 MB` 제한 추가 (LLM04 DoS 방지)
- `state_manager.py`: `_SAFE_ID_PATTERN` 도입 — `agent_id` / `task_id` 를 파일명으로 사용하기 전 `^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,63}$` 형식 강제 검증

#### [품질-HIGH] `build_votes_from_reports()` KeyError 방어 (`consensus.py`)

- `.get()` 방어 코딩으로 전환 — `score`, `vote`, `confidence` 누락 시 `KeyError` 대신 경고 로그 후 해당 리포트 스킵
- `agents_config` 파라미터를 list/dict 양쪽 허용하도록 타입 처리 개선

#### [품질-HIGH] `report_generator` 데이터 모델 통일 (`report_generator.py`)

- `ReportData` TypedDict 정의 — Form A(session 데이터)·Form B(직접 데이터) 양쪽 분기를 명시적으로 문서화
- 이중 모델 혼용에 의한 `.items()` 오류 가능성 제거

#### [품질-HIGH] `_load_agents()` 경로 파라미터화 (`orchestrator.py`)

- `agents_path: str | Path | None = None` 파라미터 추가 → `config/agents.json` 하드코딩 제거
- 테스트·CI에서 커스텀 에이전트 레지스트리 주입 가능

#### [계획-MED] Escalation Issue 자동 생성 (`orchestrator.py`)

- `check_consensus_ready()`: `result.action == "escalate"` 판정 시 라벨 추가에 더해 `type:escalation` / `status:human-needed` GitHub Issue 자동 생성
- Issue body에 합의 비율, 원본 Issue 번호, 생성 타임스탬프 포함; `mention_user` 설정 시 `/cc @{user}` 자동 추가

#### [계획-MED] E2E Integration Test 추가 (`tests/test_integration.py` 신규)

- BRIEF → `process_brief()` → GitHub Issue 플로우 6개 통합 테스트 추가
- `tmp_path` fixture + mocked GitHubClient 활용 (네트워크 의존 없음)

#### [품질-MED] 테스트 보강 + coverage 상향

| 파일 | 신규 테스트 수 | 주요 커버 영역 |
|------|--------------|--------------|
| `tests/test_brief_parser.py` | +7 | 빈 inbox, 빈 파일, 누락 섹션, 1MB 초과, 경로 노출 방지 |
| `tests/test_state_manager.py` | +8 | round-trip assignment, timezone-naive/aware, atomic write |
| `tests/test_integration.py` | +6 (신규) | BRIEF→Issue E2E happy path |
| 합계 | **+21** | — |

- `pyproject.toml`: `fail_under = 70` → `75` (85 목표 단계적 상향)

#### [계획-LOW] README Roadmap 체크리스트 갱신

- Phase 1 완료 항목 전체 `[ ]` → `[x]` 처리
- Phase 2 선행 구현 항목(`report_generator`, escalation) `[x]` 반영

#### 코드 품질 추가 수정

- `scripts/github_client.py`: E741 루프 변수명 `l` → `lbl` 수정
- `scripts/orchestrator.py`: `import re` / `from datetime import timezone` 모듈 레벨 이동, 타임존 누락 `datetime.now()` → `datetime.now(timezone.utc)` 수정
- `scripts/state_manager.py`: `get_stale_assignments()` timezone-naive datetime 비교 버그 수정
- ruff E501 15건 전부 수정 (모든 파일 줄 길이 100자 준수)

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
| v3.1 | 2026-03-14 | **1차 구현사항 리뷰 보완 완료:** 보안(Path Traversal·Prompt Injection 방어), 품질(KeyError 방어·타입 안전성·경로 파라미터화·timezone 버그 수정), 계획 정합성(Escalation Issue 자동 생성·E2E 통합 테스트 추가), ruff E501 전건 해소, 테스트 59→79개 |
| v3.2 | 2026-03-14 | **에이전트 자율 실행 아키텍처 완성:** `run_agent.sh` 추가(headless CLI 폴링 루프), kickoff 할당 버그 수정(`_create_kickoff_assignment()`), inbox/archive 경로 target_project_path 기반 해석 수정, 사용 가이드 전면 개정(터미널 4개 실행 순서 명확화), 테스트 79→120개 |
| v3.3 | 2026-03-14 | **E2E 파이프라인 검증 완료:** 3개 에이전트(claude/codex/gemini) 실제 실행 검증, Bash 3.2 호환성 버그 수정(`${var^^}` → `tr`), `new-brief.sh` 인터랙티브 스크립트 추가, 구독 OAuth 인증 방식 확인(별도 API 키 불필요) |
| v3.4 | 2026-03-15 | **1차 E2E 전체 파이프라인 검증 완료 (TASK-004):** consensus→release→final-report 전 단계 완주, 버그 11개 발견·7개 즉시 수정(D-007~D-011 포함), `start_t*.sh` 실행 방식 도입, 재시작 가이드 추가, Phase 3 개선 계획 수립, `docs/validation-report-v1.md` 검증 리포트 작성 |
| v3.5 | 2026-03-15 | **Phase 3 P1~P2 구현 완료:** SPEC-P3-001(PID lock·SIGHUP hot-reload·UTC 로깅), SPEC-P3-002(CLI 가용성 체크·브랜치 자동 생성), P1 보안/성능 개선(TOCTOU 수정·병렬 CLI 체크 25s→5s), 테스트 173개, 총 4개 커밋 완료 |
| v3.6 | 2026-03-15 | **6-Layer 코드 검증 체계 구축:** AgentConfig TypedDict·JSON Schema 검증(agent.schema.json)·스모크 테스트(test_smoke.py 4개)·conftest autouse 격리 수정·mypy 설정(disallow_untyped_defs=true)·pre-commit hooks(ruff+mypy+smoke), coverage 85%, 테스트 177→185개 |
| v3.7 | 2026-03-15 | 2차 검증 완료: GitHub Issues 기반 파이프라인 검증, 버그 3건 발견·등록, setup_labels.py 즉시 수정 |
