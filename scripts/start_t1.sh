#!/usr/bin/env bash
# start_t1.sh - Start Orchestrator (T1 terminal)
#
# Usage (from any directory):
#   bash ../orch-agent-cli/scripts/start_t1.sh
#
# Target project path is read from config/config.yaml (orchestrator.target_project_path).
# Override at runtime: TARGET_PROJECT_PATH=/other/path bash scripts/start_t1.sh
#
# Run this LAST, after T2/T3/T4 are already waiting.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ORCH_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Always run from orch-agent-cli root (orchestrator reads config/config.yaml from CWD)
cd "$ORCH_DIR"

echo "=== T1: Orchestrator ==="
echo "orch-agent-cli: $ORCH_DIR"
echo "config:         $ORCH_DIR/config/config.yaml"
echo ""

# --- Auto-setup venv if needed ---
if [ ! -d ".venv" ]; then
  echo "[setup] Creating virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install -e ".[dev]" -q
  echo "[setup] Done."
fi

source .venv/bin/activate

# --- Validate config ---
if [ ! -f "config/config.yaml" ]; then
  echo "ERROR: config/config.yaml not found. Run templates/setup.sh first." >&2
  exit 1
fi

# --- Pre-flight: GitHub token ---
if [ -z "${GITHUB_TOKEN:-}" ]; then
  if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
    export GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"
  fi
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "WARNING: GITHUB_TOKEN not set. GitHub API calls will fail." >&2
fi

# --- Zombie/stale process cleanup ---
EXISTING_PIDS=$(pgrep -f "python.*scripts.orchestrator" 2>/dev/null || true)
if [ -n "$EXISTING_PIDS" ]; then
  echo "[T1] Found existing orchestrator process(es): $EXISTING_PIDS"
  for pid in $EXISTING_PIDS; do
    STATE=$(ps -o state= -p "$pid" 2>/dev/null || echo "")
    if [ -z "$STATE" ] || echo "$STATE" | grep -q "^[TZ]"; then
      echo "[T1] Killing stopped/zombie process $pid..."
      kill -9 "$pid" 2>/dev/null || true
    else
      echo "ERROR: Orchestrator is already running (PID $pid). Stop it first." >&2
      exit 1
    fi
  done
  sleep 1
fi

echo "[T1] Starting orchestrator... (Ctrl+C to stop)"
echo ""

exec python3 -m scripts.orchestrator
