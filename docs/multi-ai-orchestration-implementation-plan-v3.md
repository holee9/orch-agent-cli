---
id: SPEC-INFRA-001
title: Multi-AI CLI Agent Orchestration System
version: "3.0"
status: planned
created: 2026-03-14
updated: 2026-03-14
author: Human Developer
priority: high
---

## HISTORY (변경 이력)

| 버전 | 날짜 | 변경 내용 |
|------|------|-----------|
| v1.0 | 2026-03-14 | 초판 (GitHub Actions 기반) |
| v1.1 | 2026-03-14 | 기존 인프라 참조 제거, 단일 환경 개정 |
| v2.0 | 2026-03-14 | **전면 재설계:** 다중 터미널 CLI 에이전트 협업 구조로 변경. 파일 시스템 기반 태스크 보드(`.orchestra/`), 에이전트별 역할 문서(CLAUDE.md/CODEX.md/GEMINI.md), 제품개발 프로세스 7단계별 에이전트 배치, 오케스트레이터(file watcher), 태스크 잠금/상태 전이, 현실적 데모 시나리오 |
| v3.0 | 2026-03-14 | **확장 개정:** orch-agent-cli의 설치형 도구 성격 명시, GitHub Issues 이중 레이어 통신 아키텍처, 기술 타당성 분석(방법 A/B/C/D 비교), 인간 문서 생애주기(BRIEF → Final Report), GitHub Issues 프로토콜 및 라벨 체계, 에이전트 자율 루프 및 종료 조건, 언어 정책 통합 |

---

# Multi-AI CLI Agent Orchestration — 구현 계획서

> **문서 버전:** v3.0
> **작성일:** 2026-03-14
> **기반 문서:** v2.0 계획서 + 기술 타당성 분석 결과
> **핵심 원칙:** 속도보다 품질. 에이전트 간 60초 지연 허용. 충분한 검토 우선.

---

## 목차

1. [프로젝트 성격 및 운영 개념](#1-프로젝트-성격-및-운영-개념)
2. [설치 및 통합 방법](#2-설치-및-통합-방법)
3. [기술 타당성 분석: GitHub Issues 이벤트 감지](#3-기술-타당성-분석-github-issues-이벤트-감지)
4. [이중 레이어 통신 아키텍처](#4-이중-레이어-통신-아키텍처)
5. [인간 문서 생애주기](#5-인간-문서-생애주기)
6. [GitHub Issues 프로토콜](#6-github-issues-프로토콜)
7. [에이전트 자율 루프 및 종료 조건](#7-에이전트-자율-루프-및-종료-조건)
8. [시스템 요구사항](#8-시스템-요구사항)
9. [합의 기준](#9-합의-기준)
10. [제품개발 프로세스별 에이전트 운영](#10-제품개발-프로세스별-에이전트-운영)
11. [Phase별 구현 계획](#11-phase별-구현-계획)
12. [핵심 컴포넌트 설계](#12-핵심-컴포넌트-설계)
13. [잠재적 문제점, 데모 시나리오 및 언어 정책](#13-잠재적-문제점-데모-시나리오-및-언어-정책)

---

## 1. 프로젝트 성격 및 운영 개념

### 1.1 orch-agent-cli의 성격

**이 리포지토리는 개발 대상이 아니다.**

`orch-agent-cli`는 **타 프로젝트에 설치하여 사용하는 오케스트레이터 도구**이다. 별도의 실제 개발 프로젝트(target project)에 포함시켜 CLI 에이전트들이 해당 프로젝트를 자율적으로 개발하도록 지원한다.

```
orch-agent-cli (이 리포지토리)
  ↓ git submodule 또는 독립 실행
target-project/ (실제 개발이 이루어지는 별도 repo)
  ├── src/              ← 에이전트들이 개발하는 코드
  ├── .orchestrator/    ← orch-agent-cli 서브모듈 (선택 A)
  ├── .orchestra/       ← 로컬 운영 상태 (lock, cache, log)
  ├── AGENTS.md         ← 에이전트 공통 규칙
  ├── CLAUDE.md         ← Claude Code 전용 지시사항
  ├── CODEX.md          ← Codex CLI 전용 지시사항
  ├── GEMINI.md         ← Gemini CLI 전용 지시사항
  └── inbox/            ← 인간이 작성하는 BRIEF 파일 투입구
```

### 1.2 운영 형태: 아이디어 1개 → 자율 완주 → 최종 보고

**인간의 역할은 최소화된다.**

```
인간 개입 포인트         에이전트 자율 구간
─────────────────────────────────────────────────────────────────
① BRIEF 작성            →  [에이전트 분석/설계/구현/리뷰/테스트]
                             (에이전트 간 GitHub Issues로 토론)
② Final Report 수신     →  필요 시 추가 BRIEF 작성
③ PR merge + deploy     ↑─ Final Report가 이 시점을 알려줌
```

1. **인간이 할 일:** `inbox/BRIEF-{날짜}.md` 파일 1개 작성
2. **에이전트가 할 일:** Orchestrator가 BRIEF를 감지하여 GitHub Kickoff Issue 생성 → 에이전트들이 자율적으로 개발 완주
3. **인간이 받는 것:** Final Report (GitHub Issue + 로컬 파일) → PR review → merge

### 1.3 에이전트 프로파일

| 에이전트 | CLI 도구 | 실행 방식 | 핵심 역할 |
|----------|----------|-----------|-----------|
| **Claude Code** | `claude` | 터미널 인터랙티브 / `claude -p` 비대화 | 설계자 + 리뷰어 + 릴리스 매니저 |
| **Codex CLI** | `codex` | `codex exec --sandbox workspace-write` | 구현자 + 패치 생성기 |
| **Gemini CLI** | `gemini` | 터미널 인터랙티브 / API 호출 | 테스트 강화 + 팩트체커 (Red Team) |
| **Orchestrator** | `python orchestrator.py` | 상시 실행 데몬 | GitHub API 단일 창구 + 라우터 + 품질 게이트 |

### 1.4 CI/CD와의 관계

| 구분 | 역할 |
|------|------|
| CLI 에이전트 (본 문서 범위) | 요구사항 분석, 설계, 구현, 리뷰, 테스트 작성 |
| CI/CD (GitHub Actions 등) | 빌드, 린트, 보안 스캔, 배포 (에이전트 결과물 검증 게이트) |

---

## 2. 설치 및 통합 방법

### 2.1 Option A: Git Submodule (권장)

target project 루트에서:

```bash
git submodule add https://github.com/your-org/orch-agent-cli .orchestrator
cp .orchestrator/templates/AGENTS.md .
cp .orchestrator/templates/CLAUDE.md .
cp .orchestrator/templates/CODEX.md .
cp .orchestrator/templates/GEMINI.md .
mkdir -p inbox .orchestra/{state,logs,cache}
```

### 2.2 Option B: 독립 실행 (별도 터미널에서 직접 실행)

`.env` 파일에 target project를 지정:

```bash
# .env (orch-agent-cli 루트)
GITHUB_REPO=owner/target-project
TARGET_PROJECT_PATH=/path/to/target-project
POLLING_INTERVAL_SECONDS=60
```

실행:

```bash
cd /path/to/orch-agent-cli
python scripts/orchestrator.py --target /path/to/target-project
```

### 2.3 config.yaml 구조

```yaml
# .orchestrator/config.yaml (target project 내)
github:
  repo: "owner/target-project"
  polling_interval: 60          # seconds (품질 우선 — 속도 불필요)
  labels:
    routing:
      claude: "agent:claude"
      codex: "agent:codex"
      gemini: "agent:gemini"
    status:
      - "status:assigned"
      - "status:in-progress"
      - "status:review"
      - "status:approved"
      - "status:blocked"
    type:
      - "type:kickoff"
      - "type:spec"
      - "type:implementation"
      - "type:review"
      - "type:test"
      - "type:final-report"

agents:
  claude:
    weight: 0.40
    primary_stages: [requirements, planning, review, release]
  codex:
    weight: 0.35
    primary_stages: [implementation]
  gemini:
    weight: 0.25
    primary_stages: [testing, fact-check]

consensus:
  threshold: 0.9
  score_ready_min: 90
  dispersion_alert: 20
  max_rereviews: 2              # 초과 시 인간 에스컬레이션

quality:
  brief_inbox_dir: "inbox/"
  brief_archive_dir: "docs/briefs/"
  session_archive_dir: "docs/sessions/"
```

---

## 3. 기술 타당성 분석: GitHub Issues 이벤트 감지

### 3.1 시나리오

동일 PC에서 터미널 4개를 열고 각각 `claude`, `codex`, `gemini`, `python orchestrator.py`를 실행한다.
각 에이전트가 GitHub Issues의 변화(새 이슈, 댓글 추가, 라벨 변경)를 어떻게 감지하는가?

### 3.2 방법별 타당성 평가

#### 방법 A: 에이전트별 직접 GitHub API Polling

- **구현:** 각 에이전트가 `gh issue list --label agent:claude --state open`을 주기적으로 실행
- **장점:** 구현 간단, 추가 인프라 없음
- **문제점:**
  - **Rate Limit:** GitHub 인증 계정 5,000 req/hour. 에이전트 3개 × 2 req/min × 60 min = 360 req/hour (허용 범위이나 복잡한 query 추가 시 증가)
  - **레이스 컨디션:** 두 에이전트가 동시에 "미할당" 이슈를 보고 동시에 claim 시도 → GitHub는 다중 assignee를 허용하므로 양쪽 모두 성공 → 중복 작업 발생
  - **지연:** 30-60초 polling 간격
- **판정: 단독 사용 부적합. 레이스 컨디션 문제 미해결.**

#### 방법 B: GitHub Webhooks

- **구현:** GitHub repo에서 webhook 설정 → 로컬 HTTP 서버로 이벤트 전송
- **장점:** 실시간 이벤트 수신
- **문제점:**
  - **로컬 개발 환경 문제:** GitHub webhook은 공개 URL에 POST를 보냄. 로컬 localhost는 GitHub에서 접근 불가 → ngrok, cloudflared 등 터널링 도구 필수
  - **설정 복잡성:** "설치형 시스템"에서 webhook 설정은 사용자마다 다른 부가 작업 필요
  - **단일 수신점:** 하나의 HTTP 서버가 모든 이벤트를 받아야 함 → Orchestrator 전담 필수
- **판정: 가능하나 설치 복잡성이 높아 기본 옵션으로 부적합. Phase 2 선택 옵션.**

#### 방법 C: gh CLI `gh issue watch` 명령

- **구현 시도:** `gh issue watch 42` 같은 실시간 구독 명령어 사용
- **판정: 해당 명령어 gh CLI에 존재하지 않음. 불가.**

#### 방법 D: Orchestrator 중앙 Polling + 로컬 상태 관리 (권장)

- **전제:** 속도보다 품질이 목표. 에이전트 간 60초 지연은 완전히 허용.
- **구현:**
  1. Orchestrator만 GitHub API를 polling (60초 간격)
  2. Orchestrator가 이슈 상태를 로컬 `.orchestra/cache/`에 캐싱 (lock 관리용)
  3. 각 에이전트는 Orchestrator가 기록한 로컬 할당 파일을 확인 (60-120초 간격)
  4. 에이전트가 결과물 생성 → GitHub Issue에 댓글 + 로컬 파일 백업
- **장점:**
  - GitHub API 호출 = Orchestrator 1개만 → rate limit 여유
  - 레이스 컨디션 없음 (Orchestrator 단일 라우터 역할)
  - GitHub Issues = 공식 기록이자 인간 감사 추적
  - 속도 불필요 → 아키텍처 단순화 가능
- **단점:**
  - Orchestrator 단일 장애점 → pm2/systemd 자동 재시작으로 완화
  - 네트워크 없으면 GitHub sync 불가 → 로컬 상태로 작업 계속 + 이후 sync
- **판정: 구현 가능, 현실적, 품질 중심 운영에 최적.**

### 3.3 방법 비교표

| 방법 | 구현 가능성 | 복잡도 | 레이스 컨디션 | 권장 |
|------|-----------|-------|-------------|------|
| A: 에이전트별 직접 polling | 가능 (제한적) | 낮음 | 있음 | Phase 1 프로토타입만 |
| B: GitHub Webhooks | 가능 (ngrok 필요) | 높음 | 없음 | Phase 2 선택 옵션 |
| C: gh watch 명령 | **불가** | - | - | - |
| D: Orchestrator 중앙 polling + 로컬 상태 | 가능 | 중간 | 없음 | **권장 (기본)** |

---

## 4. 이중 레이어 통신 아키텍처

### 4.1 핵심 원칙

**속도보다 품질.** 에이전트 간 60초 지연은 허용. 충분한 검토가 우선이다.

### 4.2 아키텍처 다이어그램

```
┌────────────────────────────────────────────────────────────────────┐
│                        개발자 워크스테이션                          │
│                                                                    │
│  Terminal 1 (Claude Code)    Terminal 2 (Codex CLI)                │
│  ┌───────────────────────┐   ┌───────────────────────┐            │
│  │ $ claude              │   │ $ codex               │            │
│  │ > [polling 로컬 할당  │   │ > [polling 로컬 할당  │            │
│  │    파일 60-120초]      │   │    파일 60-120초]      │            │
│  └───────────────────────┘   └───────────────────────┘            │
│                                                                    │
│  Terminal 3 (Gemini CLI)     Terminal 4 (Orchestrator)             │
│  ┌───────────────────────┐   ┌───────────────────────┐            │
│  │ $ gemini              │   │ $ python orchestrator │            │
│  │ > [polling 로컬 할당  │   │                       │            │
│  │    파일 60-120초]      │   │ [60초 GitHub polling] │            │
│  └───────────────────────┘   │ [단일 API 창구]        │            │
│                               │ [라우터 + 품질 게이트]│            │
│                               └──────────┬────────────┘            │
│                                          │                         │
│  ┌───────────────────────────────────────▼──────────────────────┐  │
│  │                   .orchestra/ (로컬 상태)                     │  │
│  │  state/assigned/  ← 에이전트별 할당 파일 (로컬 릴레이)        │  │
│  │  cache/issues/    ← GitHub Issues 로컬 캐시                  │  │
│  │  logs/            ← 에이전트 활동 로그                        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                               │                                    │
└───────────────────────────────┼────────────────────────────────────┘
                                │ gh CLI (60초 polling + 결과 push)
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                    GitHub Issues (공식 레코드)                      │
│                                                                    │
│  #1 KICKOFF        #2 Spec Review      #3 Implementation           │
│  [type:kickoff]    [agent:claude]      [agent:codex]               │
│  [status:done]     [status:approved]   [status:in-progress]        │
│                                                                    │
│  → 모든 요구사항, 설계 결정, 리뷰 결과, 에이전트 간 토론 기록       │
│  → 인간이 언제든 감사 추적 가능                                      │
└────────────────────────────────────────────────────────────────────┘
```

### 4.3 두 레이어의 역할 분리

**Layer 1 — GitHub Issues (공식 기록):**

- 모든 요구사항, 설계 결정, 리뷰 결과 (인간 가시성)
- 에이전트 간 토론과 합의 과정 전체
- Blocking 이슈 및 해결 과정 (품질 추적)
- Final Report 이슈 (인간 알림)

**Layer 2 — 로컬 `.orchestra/` (운영 상태):**

- 에이전트 실행 lock (충돌 방지)
- GitHub Issues 로컬 캐시 (Orchestrator 작업용, 속도 릴레이 아님)
- 에이전트별 할당 파일 (Orchestrator가 기록, 에이전트가 60-120초마다 확인)
- 에이전트 활동 로그 (디버깅용)

### 4.4 Orchestrator의 단일 GitHub API 창구 역할

```
각 에이전트            Orchestrator              GitHub
─────────────         ─────────────────         ──────────────
할당 파일 확인  ←─── 이슈 상태 캐싱       ←─── GitHub API polling
(60-120초 간격)        (60초 간격)                (rate limit 여유)

결과물 생성    ───→   댓글 게시 요청       ───→  Issue 댓글 추가
(로컬 파일)            (gh issue comment)         (공식 기록)
```

### 4.5 품질 우선 설계 반영

- 에이전트가 충분히 검토 후 댓글 달기 → 빠른 응답 압박 없음
- Veto / re-review 사이클 권장 → 결함 조기 발견이 목표
- Orchestrator가 quality gate 역할 강화 (스키마 검증, blocker 추적)

---

## 5. 인간 문서 생애주기

### 5.1 인간이 작성하는 문서: 초기 계획지시서 (BRIEF)

**위치:** `inbox/BRIEF-{YYYY-MM-DD}.md`
**언어:** 한국어 (기술 용어는 영어)

**구조:**

```markdown
# Project Brief: {프로젝트명}
**작성일:** YYYY-MM-DD
**대상 repo:** {GitHub repo URL}

## 개발 목표
(무엇을 만들 것인지 1-3줄 설명)

## 핵심 요구사항
- (기능 요구사항 bullet)

## 기술 제약사항
- Language/Framework 선호도
- 사용 금지 라이브러리 등

## 품질 기준
- 테스트 커버리지 목표
- 성능 요구사항
- 보안 기준

## 범위 제외 (Out of Scope)
- (명시적으로 이번에 하지 않을 것들)
```

**처리 흐름:**

```
인간: inbox/BRIEF-2026-03-14.md 작성
   ↓ (Orchestrator가 inbox/ 디렉토리 60초 polling)
Orchestrator: BRIEF 내용 파싱 → 영어로 변환
   ↓
GitHub Issue #1 생성 (영어, type:kickoff)
   Title: "KICKOFF: {영어 프로젝트명}"
   Body:
     ## Objective
     (한국어 목표를 영어 요약으로)
     ## Requirements
     ## Constraints
     ## Quality Standards
     ## Source Brief
     Local file: docs/briefs/BRIEF-2026-03-14.md (Korean original preserved)
   ↓
원본 BRIEF → docs/briefs/ 로 이동 보관 (inbox/ 비움)
   ↓
에이전트들: 영어 Kickoff Issue 읽고 자율 작업 시작
```

**핵심:** 인간이 한국어로 쓴 BRIEF는 영구 보관되고, 에이전트용 GitHub Issue는 Orchestrator가 영어로 변환 생성한다.

### 5.2 에이전트가 생성하는 중간 문서

| 단계 | 생성 주체 | 로컬 파일 | GitHub 반영 |
|------|----------|----------|------------|
| 요구사항 분석 | Claude | `docs/specs/SPEC-{id}.md` | Issue 본문으로 |
| 구현 계획 | Claude | `docs/plans/PLAN-{id}.md` | Issue 댓글로 |
| 구현 결과 | Codex | git commit history | Issue 댓글 + PR 링크 |
| 코드 리뷰 | Claude | `docs/reviews/REVIEW-{id}.md` | Issue 댓글로 |
| 테스트 계획 | Gemini | `docs/test-plans/TEST-{id}.md` | Issue 댓글로 |
| 합의 결과 | Orchestrator | `.orchestra/cache/consensus/{id}.json` | Issue 라벨 `status:approved` |

### 5.3 인간이 받는 최종 문서: Final Report

**GitHub Issue:** `type:final-report` 라벨, 인간 계정 @mention
**로컬 파일:** `docs/reports/REPORT-{session_id}-{date}.md`
**언어:** 한국어 + 기술 용어 영어

**구조:**

```markdown
# Final Development Report
**Session:** {session_id}
**Date:** YYYY-MM-DD
**Project:** {target repo}
**Triggered by:** inbox/BRIEF-{date}.md

## Executive Summary
(3줄 이내, 무엇이 완성되었는가)

## 완료된 개발 내용
- 구현된 기능 목록
- 변경된 파일 목록
- 생성된 테스트 수

## GitHub Issues 처리 결과
| Issue | 제목 | 상태 | 처리 에이전트 |
|-------|------|------|--------------|
| #1 | KICKOFF | Closed | Orchestrator |
| #2 | Spec Review | Closed | Claude+Gemini |
| ... | ... | ... | ... |

## 품질 지표
- 테스트 커버리지: XX%
- 코드 리뷰 점수: XX/100
- 보안 이슈: 없음 / N건 (해결 완료)

## 에이전트 합의 결과
- 최종 Consensus 비율: XX%
- Veto 발생 여부: 없음 / N회 (재작업 후 해결)

## 잔여 고려사항 (인간 판단 필요)
- (에이전트가 확신하지 못한 결정 사항)

## 권장 다음 단계
- PR merge 후 staging 배포 권장
- 추가 요구사항이 있다면 새 BRIEF 작성
```

### 5.4 세션 아카이브

완료 후 보관되는 자료:

- GitHub Issues 전체 (target repo에 영구 보관)
- `docs/sessions/SESSION-{date}/` — 핵심 문서 로컬 사본
- Git 히스토리 — 코드 변경 전체 이력
- `.orchestra/logs/` — 에이전트 활동 로그

---

## 6. GitHub Issues 프로토콜

### 6.1 라벨 체계

**Routing 라벨 (담당 에이전트):**

| 라벨 | 의미 |
|------|------|
| `agent:claude` | Claude Code 담당 |
| `agent:codex` | Codex CLI 담당 |
| `agent:gemini` | Gemini CLI 담당 |
| `agent:orchestrator` | Orchestrator 관리 |

**Status 라벨 (진행 상태):**

| 라벨 | 의미 |
|------|------|
| `status:assigned` | 에이전트에 할당됨 |
| `status:in-progress` | 에이전트 작업 중 |
| `status:review` | 리뷰 대기 중 |
| `status:approved` | 합의 통과 |
| `status:blocked` | Veto 또는 차단 상태 |
| `status:human-needed` | 인간 개입 필요 |

**Type 라벨 (이슈 종류):**

| 라벨 | 의미 |
|------|------|
| `type:kickoff` | BRIEF에서 생성된 시작 이슈 |
| `type:spec` | 요구사항/스펙 이슈 |
| `type:implementation` | 구현 태스크 이슈 |
| `type:review` | 코드 리뷰 이슈 |
| `type:test` | 테스트 관련 이슈 |
| `type:final-report` | 최종 보고서 이슈 |
| `type:escalation` | 인간 에스컬레이션 |

### 6.2 이슈 생명주기

```
[Orchestrator] BRIEF 감지 → #1 KICKOFF Issue 생성 (type:kickoff)
       ↓
[Claude] KICKOFF 댓글 분석 → #2 SPEC Issue 생성 (type:spec, agent:claude)
       ↓
[Gemini] SPEC 팩트체크 댓글 → #2에 검증 결과 댓글
       ↓
[Orchestrator] 검증 완료 확인 → #2에 status:approved 라벨
       ↓
[Claude] 구현 계획 → #3 Implementation Issue 생성 (type:implementation, agent:codex)
       ↓
[Codex] 구현 완료 → #3에 PR 링크 댓글 → status:review 라벨
       ↓
[Claude + Gemini] 코드 리뷰 댓글 → 합의 계산
       ↓
[Orchestrator] 합의 통과 → #3 Close + Final Report Issue 생성 (type:final-report)
       ↓
[인간] Final Report Issue에 @mention → PR 확인 → merge
```

### 6.3 gh CLI 명령어 패턴 (에이전트용)

```bash
# 이슈 생성 (Orchestrator / Claude)
gh issue create \
  --title "SPEC: Implement user authentication" \
  --body "$(cat docs/specs/SPEC-001.md)" \
  --label "type:spec,agent:claude,status:in-progress"

# 댓글 추가 (모든 에이전트)
gh issue comment 2 \
  --body "## Review Result\n\nSPEC verified against existing API contracts.\n\n**Status:** No conflicts found.\n**Verdict:** Ready for implementation."

# 라벨 변경 (Orchestrator)
gh issue edit 2 --add-label "status:approved" --remove-label "status:review"

# 이슈 Close (Orchestrator)
gh issue close 3 --comment "Implementation complete. Consensus: 94.2% (PASS). PR: #42"

# 내 할당 이슈 목록 조회 (각 에이전트)
gh issue list --label "agent:claude,status:assigned" --json number,title,labels
```

### 6.4 에이전트 댓글 형식 (영어 필수)

```markdown
## [Agent: claude] Spec Review Result

**Task:** SPEC-001 — User Authentication
**Verdict:** APPROVED
**Confidence:** 0.92

### Findings
- All acceptance criteria are testable and unambiguous
- No conflicts with existing API contracts
- Security requirements align with OWASP Top 10

### Blockers
None

### Next Steps
Ready for implementation assignment to Codex.

---
*Generated by claude at 2026-03-14T10:32:01Z*
*Local file: docs/reviews/REVIEW-SPEC-001.claude.md*
```

---

## 7. 에이전트 자율 루프 및 종료 조건

### 7.1 각 에이전트의 Polling 루프 구조

```python
# 에이전트별 내부 루프 (AGENTS.md 지시사항 기반)

while True:
    # 1. 로컬 할당 파일 확인 (Orchestrator가 기록)
    assignment = read_local_assignment(f".orchestra/state/assigned/{agent_id}.json")

    if assignment:
        # 2. GitHub Issue에서 컨텍스트 로드
        issue = gh_issue_view(assignment["issue_number"])

        # 3. 작업 수행 (스테이지별)
        result = perform_stage_task(assignment["stage"], issue)

        # 4. 로컬 파일 저장
        save_local_artifact(result)

        # 5. GitHub Issue에 댓글 (공식 기록)
        gh_issue_comment(assignment["issue_number"], format_comment(result))

        # 6. Orchestrator에 완료 신호 (로컬 파일 기록)
        write_completion_signal(agent_id, assignment["task_id"])

    # 7. 60-120초 대기 후 재확인
    sleep(60 + random(60))   # jitter로 충돌 방지
```

### 7.2 Orchestrator의 중앙 루프

```python
while True:
    # 1. inbox/ 확인 (새 BRIEF 파일)
    briefs = scan_inbox()
    for brief in briefs:
        kickoff_issue = create_kickoff_issue(parse_brief(brief))
        archive_brief(brief)

    # 2. GitHub Issues 상태 polling (60초 간격)
    open_issues = gh_api_list_issues(state="open")
    cache_issues(open_issues)

    # 3. 완료 신호 처리 → 다음 단계 이슈 생성 또는 라벨 업데이트
    completions = read_completion_signals()
    for completion in completions:
        advance_workflow(completion)

    # 4. 품질 게이트 검사
    check_quality_gates()

    # 5. 타임아웃 감지 (30분 무응답 에이전트)
    release_stale_locks()

    sleep(60)
```

### 7.3 종료 조건

세션이 완료되는 조건:

1. **정상 완료:** 모든 `type:implementation` 이슈가 Close + 합의 통과 → Final Report 이슈 생성
2. **인간 에스컬레이션:** 동일 이슈에서 re-review 2회 초과 → `type:escalation` 이슈 생성 + 인간 @mention → 세션 일시 중단
3. **에러 종료:** Orchestrator가 3회 재시도 후 실패 → 로컬 에러 로그 + `type:escalation` 이슈

### 7.4 에스컬레이션 조건

```
동일 이슈에서 re-review 발생 횟수가 max_rereviews (기본값: 2)를 초과하면:

1. Orchestrator가 type:escalation 이슈 생성
   Title: "ESCALATION: Human review needed for Issue #N"
   Body: 에스컬레이션 이유, 에이전트 의견 불일치 내용, 권장 결정 사항

2. 인간 계정 @mention

3. 해당 이슈는 status:human-needed 라벨로 대기

4. 나머지 independent 이슈는 계속 진행 (blocking 아닌 경우)
```

### 7.5 Final Report 생성 트리거

```
Orchestrator 판단 기준:
  - 모든 type:implementation 이슈: Closed
  - 모든 type:spec 이슈: status:approved
  - 에스컬레이션 이슈 없음 (또는 모두 해결)
  → Final Report 이슈 생성 (type:final-report)
  → docs/reports/REPORT-{session_id}-{date}.md 생성
  → 인간 @mention
```

---

## 8. 시스템 요구사항

### 8.1 EARS 형식 요구사항

| EARS 패턴 | 요구사항 |
|-----------|---------|
| Ubiquitous | The system shall use GitHub Issues as the primary inter-agent communication bus and audit trail |
| Ubiquitous | The system shall be installable as a git submodule or run standalone with GITHUB_REPO configuration |
| Ubiquitous | The system shall enforce a single GitHub API access point through the Orchestrator to prevent rate limit exhaustion |
| Ubiquitous | The system shall validate all agent output files against JSON schemas before processing |
| Event-Driven | WHEN a BRIEF file appears in `inbox/` THEN the Orchestrator shall parse it, create a GitHub Kickoff Issue (in English), and archive the original |
| Event-Driven | WHEN all expected agent reviews are complete for an issue THEN the consensus engine shall calculate the weighted readiness score |
| Event-Driven | WHEN a `veto` vote is submitted THEN the Orchestrator shall halt the issue workflow and initiate re-review (max 2 times before human escalation) |
| State-Driven | IF an agent assignment exceeds 30 minutes without a completion signal THEN the Orchestrator shall release the assignment and re-assign |
| State-Driven | IF all implementation issues are closed with consensus passed THEN the Orchestrator shall generate the Final Report and notify the human |
| State-Driven | IF re-review count exceeds `max_rereviews` THEN the Orchestrator shall create an escalation issue and halt the affected workflow |
| Unwanted | The system shall not allow an agent to post GitHub comments in any language other than English |
| Unwanted | The system shall not proceed to the next stage if JSON schema validation fails |
| Unwanted | The system shall not commit secrets or credentials to version control |
| Optional | Where possible, the Orchestrator shall provide a local terminal dashboard showing real-time issue status and agent activity |

---

## 9. 합의 기준

### 9.1 시나리오 1: 정상 합의 통과

- **Given:** 구현 이슈가 review 단계에 진입하고 3개 에이전트 모두 리뷰 댓글을 제출함
- **When:** Orchestrator가 합의 엔진을 실행함
- **Then:** 가중 합의 비율 ≥ 0.9이면 이슈가 Close되고 다음 단계로 진행함

### 9.2 시나리오 2: Veto 처리

- **Given:** Gemini가 `"vote": "veto"`를 포함한 리뷰 댓글을 제출함
- **When:** 합의 엔진이 Veto를 감지함
- **Then:** 즉시 합의가 중단되고 `status:blocked` 라벨 추가, re-review loop 시작 (최대 2회)

### 9.3 시나리오 3: 에이전트 타임아웃

- **Given:** Codex가 구현 이슈를 수령 후 30분 동안 완료 신호 미제출
- **When:** Orchestrator가 타임아웃을 감지함
- **Then:** 로컬 할당 파일 초기화, 이슈를 재할당

### 9.4 합의 알고리즘

```
가중 합의 비율 = (ready 에이전트의 유효 가중치 합) / (전체 유효 가중치 합)

유효 가중치 = base_weight × reliability_score × confidence

기본 가중치:
  claude: 0.40
  codex:  0.35
  gemini: 0.25

판정:
  ratio >= 0.9            → PASS (PR ready)
  ratio < 0.9             → FAIL (re-work 요청)
  veto 존재               → 즉시 FAIL (re-review loop)
  점수 분산 > 20pt        → 추가 증거 수집 요청
```

---

## 10. 제품개발 프로세스별 에이전트 운영

### 10.1 프로세스 흐름과 에이전트 배치

```
제품개발 프로세스          담당 에이전트              GitHub Issue            산출물
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

0. BRIEF 파싱         ●Orchestrator          #1 KICKOFF Issue        docs/briefs/ 아카이브

        │
        ▼

1. 요구사항 분석     ●Claude Code            #2 SPEC Issue           docs/specs/SPEC-{id}.md
   & 수용 기준       ○Gemini (팩트체크)      (#2에 검증 댓글)

        │
        ▼

2. 작업 분해         ●Claude Code            #3 PLAN Issue           docs/plans/PLAN-{id}.md
   & 구현 계획       ○Codex (실현성 검증)    (#3에 피드백 댓글)

        │
        ▼

3. 구현 / 패치       ●Codex CLI              #4 Implementation       src/ 변경, 브랜치 + 커밋
   생성               ○Claude Code (보조)     Issue (#4에 PR 링크)

        │
        ▼

4. 코드 리뷰         ●Claude Code            #4에 리뷰 댓글          docs/reviews/REVIEW-{id}.md
   & 위험 분석       ○Gemini (보안 검증)

        │
        ▼

5. 테스트 강화       ●Gemini CLI             #5 Test Issue           tests/ 추가
   & 회귀 설계       ○Codex (테스트 구현)    (#5에 커버리지 댓글)

        │
        ▼

6. 합의 & 판정       ●Orchestrator           #4, #5 Close            .orchestra/cache/consensus/
                      (자동 계산)             + status:approved

        │
        ▼

7. 릴리스 준비       ●Claude Code            PR 생성 댓글            CHANGELOG, 릴리스노트
                      ○Codex (배포 스크립트)

        │
        ▼

8. Final Report       ●Orchestrator          #N FINAL-REPORT         docs/reports/REPORT-*.md
   & 인간 알림                               Issue (@mention)

        │
        ▼

9. 인간 최종 승인    개발자                   PR 확인                 merge + deploy

●= Primary    ○= Secondary
```

### 10.2 에이전트 역할 매트릭스

```
                BRIEF   요구사항  작업분해  구현/패치  코드리뷰  테스트강화  합의  릴리스
               파싱     분석      분해               위험분석              판정  준비
              ──────   ────────  ────────  ─────────  ────────  ──────────  ────  ──────
Claude Code            ●(P)      ●(P)                  ●(P)                      ●(P)
Codex CLI              ○(S)                ●(P)         ○(self)  ○(S)
Gemini CLI             ○(FC)               ○(S)         ○(Red)   ●(P)
Orchestrator  ●(P)                                                          ●(P)        ●(P)

●(P) = Primary    ○(S) = Secondary    ○(FC) = Fact-Check    ○(Red) = Red Team
```

### 10.3 에이전트별 지시 문서 구조

```
target-project/
├── AGENTS.md    ← 공통 오케스트레이션 규칙 (GitHub Issues 통신 포함)
├── CLAUDE.md    ← Claude Code 전용 지시사항
├── CODEX.md     ← Codex CLI 전용 지시사항
└── GEMINI.md    ← Gemini CLI 전용 지시사항
```

**AGENTS.md (공통 규칙) 핵심 내용 (영어로 작성):**

```markdown
# Orchestration Common Rules

## GitHub Issues Communication
- Check .orchestra/state/assigned/{your_agent_id}.json every 60-120 seconds
- All GitHub Issue comments MUST be in English
- Post results as GitHub Issue comments AND save local files
- Never post comments in Korean or any language other than English

## File Scope Restrictions
- implementation phase: Codex modifies src/ only
- review phase: Claude/Gemini add comments only (no src/ modifications)
- testing phase: Gemini/Codex modify tests/ only
- docs/ modifications: primary agent of each stage only

## Output Format
- All reports: schemas/release_readiness.schema.json compliant
- File naming: {task_id}.{agent_id}.json

## Prohibited Actions
- Do not ignore CI/test failures
- Do not include secrets or credentials in comments or reports
- Do not modify other agents' local report files
- Do not post comments in non-English languages
```

---

## 11. Phase별 구현 계획

### Phase 1: MVP — 로컬 파일 기반 2-에이전트 루프 (4-6주)

**목표:** Claude Code + Codex CLI + Orchestrator 기본 루프 구축. GitHub Issues를 기본 통신 버스로 사용.

| Task ID | 작업 | 담당 | 산출물 |
|---------|------|------|--------|
| P1-T01 | `.orchestra/` 디렉토리 구조 생성 | 인간 | 디렉토리 트리 |
| P1-T02 | `config.yaml` 작성 | 인간 | 설정 파일 |
| P1-T03 | GitHub Labels 생성 스크립트 | 인간 | `scripts/setup_labels.py` |
| P1-T04 | `schemas/task.schema.json` 정의 | 인간 | JSON Schema |
| P1-T05 | `schemas/release_readiness.schema.json` 정의 | 인간 | JSON Schema |
| P1-T06 | `scripts/orchestrator.py` 구현 (inbox polling + GitHub polling) | Claude Code | Orchestrator 기본 |
| P1-T07 | `scripts/consensus.py` 구현 | Claude Code | 가중 합산 + Veto 처리 |
| P1-T08 | 에이전트 역할 문서 작성 (AGENTS.md, CLAUDE.md, CODEX.md) | 인간 | 역할 문서 3종 |
| P1-T09 | BRIEF → Kickoff Issue 변환 기능 구현 | Claude Code | `scripts/brief_parser.py` |
| P1-T10 | 2-에이전트 협업 E2E 검증 (Demo 1) | Claude + Codex | 검증 보고서 |

### Phase 2: 3-에이전트 풀 가동 + 품질 강화 (8-12주)

**목표:** Gemini CLI 추가, 전체 GitHub Issues 기반 워크플로우, 품질 게이트 강화

| Task ID | 작업 | 담당 | 산출물 |
|---------|------|------|--------|
| P2-T01 | `GEMINI.md` 작성 (Red Team 역할) | 인간 | 에이전트 역할 문서 |
| P2-T02 | Final Report 자동 생성 기능 | Claude Code | `scripts/report_generator.py` |
| P2-T03 | 에스컬레이션 이슈 자동 생성 로직 | Claude Code | orchestrator.py 확장 |
| P2-T04 | 3-에이전트 합의 알고리즘 검증 | Claude + Codex + Gemini | 검증 보고서 |
| P2-T05 | `scripts/dashboard.py` 구현 (터미널 대시보드) | Claude Code | 실시간 대시보드 |
| P2-T06 | GitHub Webhook 지원 추가 (선택 옵션) | Claude Code | `scripts/webhook_server.py` |
| P2-T07 | `config/agent_reliability.json` + CI 기반 업데이트 | Claude Code | 신뢰도 추적 시스템 |
| P2-T08 | 3-에이전트 E2E 검증 — Full Workflow (Demo 2) | Claude + Codex + Gemini | 검증 보고서 |

### Phase 3: 강화 및 운영 최적화 (8-12주)

**목표:** 신뢰도 피드백 루프, 보안 거버넌스, 멀티 프로젝트 지원

| Task ID | 작업 | 담당 | 산출물 |
|---------|------|------|--------|
| P3-T01 | 배포 성공/실패 기반 신뢰도 자동 점수 조정 | Claude Code | 신뢰도 피드백 루프 |
| P3-T02 | 에이전트별 비용 추적 모듈 | Claude Code | 비용 추적 모듈 |
| P3-T03 | `docs/security/owasp_llm_matrix.md` 작성 | 인간 | OWASP LLM Top 10 대응 |
| P3-T04 | 에이전트 출력물 시크릿 스캔 자동화 | Claude Code | 시크릿 스캔 스크립트 |
| P3-T05 | 프롬프트 인젝션 방어 테스트 (Red Team Gemini) | Gemini | 방어 테스트 보고서 |
| P3-T06 | 멀티 target project 동시 지원 | Claude Code | orchestrator.py 확장 |

---

## 12. 핵심 컴포넌트 설계

### 12.1 디렉토리 구조

```
orch-agent-cli/ (이 리포지토리)
├── scripts/
│   ├── orchestrator.py          # 중앙 Orchestrator (GitHub API 단일 창구)
│   ├── consensus.py             # 가중 합의 알고리즘
│   ├── brief_parser.py          # BRIEF 파싱 + 영어 변환 + Kickoff Issue 생성
│   ├── report_generator.py      # Final Report 자동 생성
│   ├── setup_labels.py          # GitHub Labels 초기 설정
│   ├── validate_schema.py       # JSON 스키마 검증
│   ├── dashboard.py             # 터미널 대시보드 (Phase 2)
│   └── webhook_server.py        # GitHub Webhook 수신 서버 (Phase 2 선택)
├── schemas/
│   ├── task.schema.json
│   └── release_readiness.schema.json
├── templates/                   # target project에 복사하는 기본 문서
│   ├── AGENTS.md
│   ├── CLAUDE.md
│   ├── CODEX.md
│   └── GEMINI.md
└── docs/                        # orch-agent-cli 자체 문서

target-project/ (실제 개발 대상)
├── .orchestrator/               # orch-agent-cli 서브모듈 (Option A)
├── .orchestra/
│   ├── state/
│   │   └── assigned/            # 에이전트별 할당 파일
│   │       ├── claude.json
│   │       ├── codex.json
│   │       └── gemini.json
│   ├── cache/
│   │   ├── issues/              # GitHub Issues 로컬 캐시
│   │   └── consensus/           # 합의 결과 캐시
│   └── logs/                    # 에이전트 활동 로그
├── inbox/                       # 인간이 BRIEF 파일을 투입하는 곳
├── docs/
│   ├── briefs/                  # 처리된 BRIEF 아카이브 (한국어 원본)
│   ├── specs/                   # 요구사항 스펙 (Claude 생성, 영어)
│   ├── plans/                   # 작업 분해 계획 (Claude 생성, 영어)
│   ├── reviews/                 # 코드 리뷰 (Claude/Gemini 생성, 영어)
│   ├── test-plans/              # 테스트 계획 (Gemini 생성, 영어)
│   ├── reports/                 # Final Report (한국어 + 기술용어 영어)
│   └── sessions/                # 세션 아카이브
├── src/                         # 소스 코드 (Codex 수정)
└── tests/                       # 테스트 (Gemini/Codex 작성)
```

### 12.2 태스크 스키마 (task.schema.json)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "OrchestraTask",
  "type": "object",
  "required": ["task_id", "title", "stage", "github_issue_number", "created_at"],
  "properties": {
    "task_id": { "type": "string", "pattern": "^task-[0-9]{3,}(-[a-z]+)?$" },
    "title": { "type": "string" },
    "description": { "type": "string" },
    "github_issue_number": { "type": "integer" },
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
    "rereview_count": { "type": "integer", "default": 0 },
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

### 12.3 릴리스 준비 리포트 스키마 (release_readiness.schema.json)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgentReleaseReadiness",
  "type": "object",
  "required": ["agent_id", "task_id", "github_issue_number", "timestamp", "score", "confidence", "vote", "blockers", "evidence"],
  "properties": {
    "agent_id": { "type": "string", "enum": ["claude", "codex", "gemini"] },
    "task_id": { "type": "string" },
    "github_issue_number": { "type": "integer" },
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

### 12.4 합의 엔진 (consensus.py)

```python
import json
from dataclasses import dataclass
from pathlib import Path

CONSENSUS_THRESHOLD = 0.9
SCORE_READY_THRESHOLD = 90
DISPERSION_ALERT_THRESHOLD = 20

@dataclass
class AgentReport:
    agent_id: str
    task_id: str
    github_issue_number: int
    score: int
    confidence: float
    vote: str
    blockers: list
    evidence: list

def compute_consensus(reports: list[AgentReport], config: dict) -> dict:
    # Veto 즉시 차단
    vetoes = [r for r in reports if r.vote == "veto"]
    if vetoes:
        return {
            "can_proceed": False,
            "ratio": 0.0,
            "reason": f"VETO by {[v.agent_id for v in vetoes]}",
            "action": "re-review (max 2 times, then human escalation)",
            "details": {r.agent_id: {"score": r.score, "vote": r.vote} for r in reports}
        }

    agents_cfg = {a["id"]: a for a in config["agents"].values() if isinstance(a, dict)}
    reliability = load_reliability()

    total_weight = 0.0
    ready_weight = 0.0
    scores = []
    details = {}

    for r in reports:
        base_w = config["agents"].get(r.agent_id, {}).get("weight", 0.25)
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

    # 점수 분산 검사
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

def load_reliability() -> dict:
    path = Path(".orchestra/cache/agent_reliability.json")
    return json.loads(path.read_text()) if path.exists() else {}
```

### 12.5 agents.json 설정

```json
{
  "agents": {
    "claude": {
      "id": "claude",
      "cli": "claude",
      "weight": 0.40,
      "primary_stages": ["requirements", "planning", "review", "release"],
      "constraints": {
        "can_modify": ["docs/", ".orchestra/state/"],
        "cannot_modify_during_review": ["src/", "tests/"]
      }
    },
    "codex": {
      "id": "codex",
      "cli": "codex",
      "weight": 0.35,
      "primary_stages": ["implementation"],
      "constraints": {
        "can_modify": ["src/", "tests/", ".orchestra/state/"],
        "sandbox": "workspace-write"
      }
    },
    "gemini": {
      "id": "gemini",
      "cli": "gemini",
      "weight": 0.25,
      "primary_stages": ["testing", "fact-check"],
      "constraints": {
        "can_modify": ["tests/", ".orchestra/state/"],
        "role_note": "Red Team — fact-check and security verification"
      }
    }
  }
}
```

---

## 13. 잠재적 문제점, 데모 시나리오 및 언어 정책

### 13.1 잠재적 문제점 및 해소 방안

#### 동시성 및 충돌

| # | 문제 | 영향 | 확률 | 해소 방안 |
|---|------|------|------|-----------|
| C1 | 두 에이전트가 동일 파일 동시 수정 | 높음 | 높음 | 단계별 수정 권한 분리 (AGENTS.md), 로컬 lock 파일 |
| C2 | 이슈 이중 할당 (레이스 컨디션) | 중간 | 낮음 | Orchestrator 단일 라우터 → 레이스 컨디션 원천 차단 |
| C3 | Git push 충돌 | 중간 | 중간 | 에이전트별 작업 브랜치 분리, merge는 인간 또는 Orchestrator |

#### 에이전트 품질

| # | 문제 | 영향 | 확률 | 해소 방안 |
|---|------|------|------|-----------|
| Q1 | 에이전트가 AGENTS.md 지시를 무시 | 높음 | 중간 | Orchestrator가 산출물 검증 (스키마 체크, 파일 범위 감지) |
| Q2 | JSON 리포트 스키마 미준수 | 높음 | 높음 | `validate_schema.py` 자동 검증, 실패 시 재작성 요청 |
| Q3 | 에이전트 환각 → 거짓 "ready" | 높음 | 중간 | CI hard gate, 다중 에이전트 교차 검증, 분산 검사 |
| Q4 | 에이전트가 한국어로 GitHub 댓글 작성 | 중간 | 중간 | AGENTS.md에 English-only 명시, Orchestrator가 언어 감지 후 재작성 요청 |

#### GitHub 통신

| # | 문제 | 영향 | 확률 | 해소 방안 |
|---|------|------|------|-----------|
| G1 | GitHub API rate limit 초과 | 높음 | 낮음 | Orchestrator 단일 창구 + 60초 간격 → 여유 충분 |
| G2 | 네트워크 장애로 GitHub sync 불가 | 중간 | 낮음 | 로컬 상태로 작업 계속 + 네트워크 복구 후 sync |
| G3 | Orchestrator 프로세스 크래시 | 중간 | 낮음 | pm2/systemd 자동 재시작, 로컬 상태 파일에서 복구 |

#### 보안

| # | 문제 | OWASP LLM | 해소 방안 |
|---|------|-----------|-----------|
| S1 | 프롬프트 인젝션 (이슈 내용 경유) | LLM01 | 외부 입력을 별도 파일로 격리, 시스템 프롬프트와 분리 |
| S2 | 에이전트가 시크릿을 GitHub 댓글에 노출 | LLM06 | GitHub 게시 전 `gitleaks` 스캔, pre-commit hook |
| S3 | 에이전트가 권한 외 명령 실행 | LLM08 | Codex `--sandbox workspace-write`, Claude/Gemini 파일 범위 제한 |

### 13.2 E2E 검증 결과 (2026-03-14)

#### 파이프라인 검증 완료
- **검증 방법:** `run_agent.sh`를 통한 실제 headless CLI 실행
- **검증 환경:** holee9/orch-test-target (격리 테스트 리포)
- **결과:** 3개 에이전트 전체 파이프라인 정상 작동 확인

#### 발견된 기술 이슈
1. **Bash 3.2 호환성** — macOS 기본 bash가 `${var^^}` 미지원. `tr`로 수정.
2. **claude -p 인증** — 서브프로세스 환경 충돌로 오진 가능. 사용자 터미널에서 OAuth 정상 작동.

#### Phase 2 진입 조건 충족 여부
- ✅ 핵심 아키텍처 검증 (이중 레이어 통신)
- ✅ 3개 에이전트 자율 실행
- ✅ GitHub Issues 연동
- ✅ 완료 신호 및 리포트 생성
- ⚠️ Gemini가 지적한 blockers: `release_readiness.schema.json` 누락, `PLAN-001.md` 누락 → Phase 2에서 해결

#### 향후 방향 (Phase 2)
1. Orchestrator가 완료 신호를 감지해 다음 에이전트에 자동 할당하는 전체 순환 루프 구현
2. `release_readiness.schema.json` 정비
3. 합의 엔진 연동 (3개 에이전트 투표 → 자동 다음 단계 결정)
4. BRIEF → Final Report 전체 자동 흐름 E2E 테스트

---

### 13.3 데모 시나리오

#### Demo 1: "BRIEF to Kickoff" (Phase 1)

**목적:** BRIEF 파일 1개로 자동으로 GitHub Kickoff Issue 생성되는 과정 시연

```
시간    이벤트
─────   ─────────────────────────────────────────────────────────────
0:00    인간: inbox/BRIEF-2026-03-14.md 작성 (한국어)
0:01    Orchestrator: inbox/ 감지 → BRIEF 파싱 → 영어로 변환
0:02    Orchestrator: GitHub Issue #1 생성
         Title: "KICKOFF: FastAPI User Authentication System"
         Labels: type:kickoff, status:assigned, agent:claude
0:02    원본 BRIEF → docs/briefs/ 이동 보관
0:03    Claude: .orchestra/state/assigned/claude.json 확인
         → Issue #1 할당됨 감지
0:04    Claude: Issue #1 내용 분석 → docs/specs/SPEC-001.md 작성
         → GitHub Issue #2 생성 (type:spec, agent:claude)
         → Issue #2에 SPEC 내용 댓글
```

#### Demo 2: "Three-Agent Consensus" (Phase 2)

**목적:** 3개 에이전트 전체 프로세스 + 합의 통과 + Final Report 시연

```
Terminal 1 (Claude)      Terminal 2 (Codex)       Terminal 3 (Gemini)      Terminal 4 (Orch.)
────────────────────     ────────────────────     ────────────────────     ──────────────────

[1. 요구사항]
SPEC 작성                                         팩트체크 댓글
Issue #2 생성                                     → Issue #2에 게시
                                                              → status:approved 라벨

[2. 구현]
                          Issue #3 수령
                          코드 구현
                          PR 생성 → Issue #3 댓글
                                                              [review 단계 감지]

[3. 리뷰]
리뷰 댓글 게시                                    보안 검증 댓글
score:95, ready                                   score:91, ready
→ Issue #3에 게시                                 → Issue #3에 게시

[4. 합의]                                                                 합의 계산
                                                                          ratio: 94% PASS
                                                                          Issue #3 Close

[5. Final Report]                                                         Issue #N 생성
                                                                          (type:final-report)
                                                                          인간 @mention

[6. 인간]
PR 확인 → merge → deploy
```

#### Demo 3: "Veto & Red Team" (Phase 2)

1. Codex가 SQL 쿼리에 사용자 입력을 직접 삽입하는 코드 구현
2. Claude 리뷰: `score: 72, vote: "not_ready"` (구조 문제 지적) → Issue 댓글
3. **Gemini 리뷰: `vote: "veto"` (SQL Injection 탐지)** → Issue 댓글
4. Orchestrator: 즉시 합의 차단, `status:blocked` 라벨, re-review loop
5. Codex에 re-work 요청 → parameterized query로 수정
6. 재리뷰 → Gemini veto 해제 → 합의 통과

#### Demo 4: "Agent Down — Graceful Degradation" (Phase 3)

1. Gemini CLI 터미널 의도적으로 종료
2. Orchestrator가 30분 타임아웃 감지 → Gemini 할당 해제
3. Claude + Codex 2개 리포트로 가중치 재분배 후 합의 계산
4. Final Report에 "degraded mode: gemini unavailable" 기록

### 13.4 언어 정책

#### 언어 정책 완성표

| 문서/채널 | 언어 | 근거 |
|----------|------|------|
| `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `GEMINI.md` | **English** | 에이전트 직접 읽음, 오류 최소화 |
| GitHub Issues (에이전트 생성 이슈/댓글) | **English** | 에이전트 간 통신, 오류 최소화 |
| `.orchestra/` JSON 파일 (내부) | **English** | 에이전트 처리, 기계 판독 |
| `docs/specs/`, `docs/plans/`, `docs/reviews/` | **English** | 에이전트 생성 문서 |
| Code comments, commit messages | **English** | 기존 coding-standards.md |
| `inbox/BRIEF-{date}.md` (인간 작성) | **한국어** (기술용어는 영어) | 인간 작성 |
| Kickoff Issue (BRIEF 변환 시) | **English** | Orchestrator 자동 변환 |
| `docs/reports/REPORT-*.md` (Final Report) | **한국어** + 기술용어 영어 | 인간 최종 독자 |
| `README.md`, `CHANGELOG.md` | **한국어** + 기술용어 영어 | 인간 독자 |
| `docs/sessions/` 아카이브 | **한국어** + 기술용어 영어 | 인간 참고 |
| 구현 계획서 (`*-plan-*.md`) | **한국어** + 기술용어 영어 | 인간 기획 문서 |

#### BRIEF 처리 시 언어 변환 흐름

```
인간: inbox/BRIEF.md → 한국어 작성
  ↓ Orchestrator 파싱
GitHub Issue #1 (KICKOFF) → 영어 자동 변환
  Title: "KICKOFF: {영어 프로젝트명}"
  Body: 한국어 목표를 영어 요약으로 변환
  원본 보존: docs/briefs/BRIEF-{date}.md (Korean original preserved)
  ↓
에이전트들: 영어 Kickoff Issue 읽고 작업 시작
  ↓
인간: Final Report (한국어 + 기술용어 영어) 수신
```

### 13.5 v3 계획서 검증 체크리스트

1. ✓ "타 프로젝트에 설치하는 도구"임이 섹션 1에 명시
2. ✓ GitHub Issues 이벤트 감지 기술 타당성 분석 포함 (방법 A/B/C/D)
3. ✓ 방법 C (gh watch) 불가 명시
4. ✓ 방법 B (Webhook) 높은 복잡성으로 Phase 2 선택 옵션 명시
5. ✓ 권장 방법 D (하이브리드)가 아키텍처 다이어그램으로 표현
6. ✓ 인간 입력 = BRIEF 파일 1개, 형식과 처리 과정 명시
7. ✓ Final Report 형식과 전달 방법 명시
8. ✓ GitHub Issues 라벨 체계와 gh CLI 명령 패턴 포함
9. ✓ 에이전트 자율 루프 종료 조건 명시
10. ✓ **속도보다 품질 원칙**이 아키텍처 전반에 반영 (60초 polling, re-review 장려, quality gate 강화)
11. ✓ 언어 정책: 에이전트 간 English, 인간 문서 Korean + 영어 기술용어

---

*문서 끝*
