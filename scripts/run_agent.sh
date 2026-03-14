#!/usr/bin/env bash
# run_agent.sh - Autonomous agent runner with assignment polling
#
# Usage:
#   bash scripts/run_agent.sh claude  [target_dir]
#   bash scripts/run_agent.sh codex   [target_dir]
#   bash scripts/run_agent.sh gemini  [target_dir]
#
# Polls .orchestra/state/assigned/{agent_id}.json every POLL_INTERVAL seconds.
# When assignment found, runs the agent CLI non-interactively and writes completion signal.

set -euo pipefail

AGENT_ID="${1:?Usage: run_agent.sh <claude|codex|gemini> [target_dir]}"
TARGET_DIR="${2:-$(pwd)}"
POLL_INTERVAL="${POLL_INTERVAL:-90}"
JITTER="${JITTER:-30}"  # random 0..30s added to interval

ASSIGNMENT_FILE="$TARGET_DIR/.orchestra/state/assigned/$AGENT_ID.json"
COMPLETED_DIR="$TARGET_DIR/.orchestra/state/completed"
LOGS_DIR="$TARGET_DIR/.orchestra/logs"

mkdir -p "$COMPLETED_DIR" "$LOGS_DIR"
LOG_FILE="$LOGS_DIR/$AGENT_ID.log"

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') [$AGENT_ID] $*" | tee -a "$LOG_FILE"; }

# --- Verify CLI is available ---
case "$AGENT_ID" in
  claude) CLI_CMD="claude" ;;
  codex)  CLI_CMD="codex" ;;
  gemini) CLI_CMD="gemini" ;;
  *) echo "ERROR: Unknown agent '$AGENT_ID'. Use: claude, codex, gemini" >&2; exit 1 ;;
esac

if ! command -v "$CLI_CMD" &>/dev/null; then
  echo "ERROR: '$CLI_CMD' not found in PATH" >&2
  exit 1
fi


log "Agent runner started. Target: $TARGET_DIR"
log "Polling $ASSIGNMENT_FILE every ${POLL_INTERVAL}s (+0..${JITTER}s jitter)"

cd "$TARGET_DIR"

# --- Main polling loop ---
while true; do
  if [ -f "$ASSIGNMENT_FILE" ]; then
    TASK_DATA=$(cat "$ASSIGNMENT_FILE")
    TASK_ID=$(echo "$TASK_DATA" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['task_id'])" 2>/dev/null || echo "UNKNOWN")
    STAGE=$(echo "$TASK_DATA" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('stage',''))" 2>/dev/null || echo "")
    ISSUE_NUM=$(echo "$TASK_DATA" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('github_issue_number',''))" 2>/dev/null || echo "")

    COMPLETION_FILE="$COMPLETED_DIR/${AGENT_ID}-${TASK_ID}.json"

    # Skip if already completed
    if [ -f "$COMPLETION_FILE" ]; then
      log "Task $TASK_ID already completed, skipping"
      sleep "$POLL_INTERVAL"
      continue
    fi

    log "Assignment detected: $TASK_ID (stage=$STAGE, issue=#$ISSUE_NUM)"

    # Build role-specific prompt
    ROLE_FILE="${AGENT_ID^^}.md"
    if [ ! -f "$ROLE_FILE" ]; then
      ROLE_FILE="AGENTS.md"
    fi

    PROMPT="You have a new assignment. Assignment data:
$(cat "$ASSIGNMENT_FILE")

Your role and instructions are in $ROLE_FILE. Read it and execute the task for stage '$STAGE'.
- task_id: $TASK_ID
- github_issue_number: $ISSUE_NUM
- Write your report to .orchestra/reports/${TASK_ID}.${AGENT_ID}.json
- When complete, write completion signal to .orchestra/state/completed/${AGENT_ID}-${TASK_ID}.json"

    log "Executing $CLI_CMD for task $TASK_ID..."

    # Run agent non-interactively
    EXIT_CODE=0
    case "$AGENT_ID" in
      claude) claude -p "$PROMPT" 2>>"$LOG_FILE" || EXIT_CODE=$? ;;
      codex)  codex exec "$PROMPT" 2>>"$LOG_FILE" || EXIT_CODE=$? ;;
      gemini) gemini -p "$PROMPT" --yolo 2>>"$LOG_FILE" || EXIT_CODE=$? ;;
    esac

    STATUS="success"
    if [ "$EXIT_CODE" -ne 0 ]; then
      log "WARNING: $CLI_CMD exited with code $EXIT_CODE"
      STATUS="error"
    fi

    # Write completion signal (orchestrator reads this to advance workflow)
    python3 -c "
import json, sys
from datetime import datetime, timezone
data = {
    'agent_id': '$AGENT_ID',
    'task_id': '$TASK_ID',
    'completed_at': datetime.now(timezone.utc).isoformat(),
    'status': '$STATUS',
    'report_path': '.orchestra/reports/${TASK_ID}.${AGENT_ID}.json'
}
with open('$COMPLETION_FILE', 'w') as f:
    json.dump(data, f, indent=2)
"
    log "Completion signal written: $COMPLETION_FILE (status=$STATUS)"
  fi

  # Sleep with jitter to avoid thundering herd
  SLEEP_TIME=$((POLL_INTERVAL + RANDOM % (JITTER + 1)))
  log "Sleeping ${SLEEP_TIME}s..."
  sleep "$SLEEP_TIME"
done
