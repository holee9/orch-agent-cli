#!/usr/bin/env bash
# start_t3.sh - Start Codex agent runner (T3 terminal)
#
# Usage:
#   bash scripts/start_t3.sh [target_dir]
#
# target_dir: path to the target project (default: current directory)
# Run BEFORE T1 (orchestrator).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="${1:-$(pwd)}"

echo "=== T3: Codex Agent Runner ==="
echo "Target project: $TARGET_DIR"
echo ""

exec bash "$SCRIPT_DIR/run_agent.sh" codex "$TARGET_DIR"
