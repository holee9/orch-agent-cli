#!/usr/bin/env bash
# start_t2.sh - Start Claude agent runner (T2 terminal)
#
# Usage:
#   bash scripts/start_t2.sh [target_dir]
#
# target_dir: path to the target project (default: current directory)
# Run BEFORE T1 (orchestrator).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="${1:-$(pwd)}"

echo "=== T2: Claude Agent Runner ==="
echo "Target project: $TARGET_DIR"
echo ""

exec bash "$SCRIPT_DIR/run_agent.sh" claude "$TARGET_DIR"
