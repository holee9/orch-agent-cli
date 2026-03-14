#!/usr/bin/env bash
# start_t4.sh - Start Gemini agent runner (T4 terminal)
#
# Usage:
#   bash scripts/start_t4.sh [target_dir]
#
# target_dir: path to the target project (default: current directory)
# Run BEFORE T1 (orchestrator).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="${1:-$(pwd)}"

echo "=== T4: Gemini Agent Runner ==="
echo "Target project: $TARGET_DIR"
echo ""

exec bash "$SCRIPT_DIR/run_agent.sh" gemini "$TARGET_DIR"
