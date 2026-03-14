#!/usr/bin/env bash
# new-brief.sh — Interactive BRIEF file creator
#
# Usage:
#   bash scripts/new-brief.sh [target_dir]
#
# Guides the user through writing a BRIEF file and saves it to
# {target_dir}/inbox/BRIEF-{YYYYMMDD-HHMMSS}.md

set -euo pipefail

TARGET_DIR="${1:-$(pwd)}"
INBOX_DIR="$TARGET_DIR/inbox"

# ── Color helpers ──────────────────────────────────────────────────────────
BOLD='\033[1m'; CYAN='\033[0;36m'; GREEN='\033[0;32m'; RESET='\033[0m'
say()  { echo -e "${CYAN}$*${RESET}"; }
bold() { echo -e "${BOLD}$*${RESET}"; }

# ── Validate target ────────────────────────────────────────────────────────
if [ ! -d "$INBOX_DIR" ]; then
  echo "ERROR: inbox/ not found at '$INBOX_DIR'"
  echo "  Run setup.sh first: bash /path/to/orch-agent-cli/templates/setup.sh $TARGET_DIR"
  exit 1
fi

# ── Prompt helper: read with prompt, allow multi-line with blank line end ──
ask() {
  local prompt="$1"
  local var_name="$2"
  local multiline="${3:-false}"
  echo
  bold "$prompt"
  if [ "$multiline" = "true" ]; then
    say "  (여러 줄 입력 가능. 빈 줄 입력 시 완료)"
    local lines=""
    while IFS= read -r line; do
      [ -z "$line" ] && break
      lines="${lines}- ${line}"$'\n'
    done
    eval "$var_name='$lines'"
  else
    read -r "$var_name"
  fi
}

# ── Introduction ──────────────────────────────────────────────────────────
echo
bold "==============================="
bold "  BRIEF 작성 가이드"
bold "==============================="
say "에이전트에게 '무엇을 만들어달라'고 지시하는 문서를 작성합니다."
say "한국어로 작성해도 됩니다. 완료 후 자동으로 inbox/에 저장됩니다."

# ── Collect inputs ────────────────────────────────────────────────────────
ask "1. 제목 (기능을 한 줄로): 예) 사용자 로그인 기능 추가" TITLE
ask "2. 프로젝트 이름 (한 줄): 예) my-web-app — FastAPI RESTful API 서버" PROJECT
ask "3. 배경 — 왜 이 기능이 필요한가?" BACKGROUND

bold
say "4. 목표 — 만들어야 할 것 (항목당 한 줄, 빈 줄로 완료)"
GOALS=""
while IFS= read -r line; do
  [ -z "$line" ] && break
  GOALS="${GOALS}- ${line}"$'\n'
done

bold
say "5. 범위 > 포함 — 구현할 기능 (항목당 한 줄, 빈 줄로 완료)"
SCOPE_IN=""
while IFS= read -r line; do
  [ -z "$line" ] && break
  SCOPE_IN="${SCOPE_IN}- ${line}"$'\n'
done

bold
say "6. 범위 > 제외 — 이번에 하지 않을 것 (항목당 한 줄, 빈 줄로 완료)"
SCOPE_OUT=""
while IFS= read -r line; do
  [ -z "$line" ] && break
  SCOPE_OUT="${SCOPE_OUT}- ${line}"$'\n'
done

ask "7. 기술스택 (언어/프레임워크/DB): 예) Python 3.11 / FastAPI / PostgreSQL" TECH
ask "8. 우선순위 P0 (필수 항목): 예) 회원가입·로그인 API, JWT 미들웨어" PRIORITY

# ── Generate file ─────────────────────────────────────────────────────────
TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
DATE=$(date '+%Y-%m-%d')
OUTFILE="$INBOX_DIR/BRIEF-${TIMESTAMP}.md"

cat > "$OUTFILE" << EOF
# ${TITLE}

## 프로젝트
${PROJECT}

## 배경
${BACKGROUND}

## 목표
${GOALS}
## 범위
### 포함
${SCOPE_IN}
### 제외
${SCOPE_OUT}
## 제약사항
- 기술스택: ${TECH}

## 기술스택
- ${TECH}

## 우선순위
- P0 (필수): ${PRIORITY}

## 일정
- 시작일: ${DATE}
- 마감일: (미정)
EOF

echo
bold "==============================="
bold "  BRIEF 파일 저장 완료"
bold "==============================="
say "  파일: $OUTFILE"
echo
say "Orchestrator(T1)가 이 파일을 감지하면 자동으로 GitHub Issue를 생성하고"
say "에이전트 파이프라인이 시작됩니다."
EOF
