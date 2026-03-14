#!/usr/bin/env bash
# setup.sh - Initialize target project for orch-agent-cli orchestration
# Usage: bash setup.sh [target_project_path]

set -euo pipefail

TARGET_DIR="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCHESTRA_DIR="${TARGET_DIR}/.orchestra"

echo "=== orch-agent-cli Setup ==="
echo "Target: ${TARGET_DIR}"
echo ""

# Create .orchestra directory structure
echo "Creating .orchestra/ directory structure..."
mkdir -p "${ORCHESTRA_DIR}/state/assigned"
mkdir -p "${ORCHESTRA_DIR}/state/completed"
mkdir -p "${ORCHESTRA_DIR}/cache"
mkdir -p "${ORCHESTRA_DIR}/reports"
mkdir -p "${ORCHESTRA_DIR}/logs"
mkdir -p "${ORCHESTRA_DIR}/consensus"
mkdir -p "${ORCHESTRA_DIR}/config"

# Create inbox directory
echo "Creating inbox/ directory..."
mkdir -p "${TARGET_DIR}/inbox"

# Copy agent instruction files
echo "Copying agent instruction files..."
for file in AGENTS.md CLAUDE.md CODEX.md GEMINI.md; do
    src="${SCRIPT_DIR}/${file}"
    if [ -f "${src}" ]; then
        cp "${src}" "${TARGET_DIR}/${file}"
        echo "  Copied ${file}"
    else
        echo "  WARNING: ${file} not found in templates/"
    fi
done

# Create session config if not exists
SESSION_CONFIG="${ORCHESTRA_DIR}/config/session.json"
if [ ! -f "${SESSION_CONFIG}" ]; then
    echo "Creating session config..."
    cat > "${SESSION_CONFIG}" << EOF
{
  "session_id": "session-$(date +%Y%m%d-%H%M%S)",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "initialized"
}
EOF
else
    echo "Session config already exists, skipping."
fi

# Add .orchestra to .gitignore if not already present
GITIGNORE="${TARGET_DIR}/.gitignore"
if [ -f "${GITIGNORE}" ]; then
    if ! grep -q "^\.orchestra/" "${GITIGNORE}" 2>/dev/null; then
        echo "" >> "${GITIGNORE}"
        echo "# orch-agent-cli state" >> "${GITIGNORE}"
        echo ".orchestra/" >> "${GITIGNORE}"
        echo "inbox/" >> "${GITIGNORE}"
        echo "Updated .gitignore"
    fi
else
    cat > "${GITIGNORE}" << 'EOF'
# orch-agent-cli state
.orchestra/
inbox/
EOF
    echo "Created .gitignore"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Directory structure:"
echo "  ${ORCHESTRA_DIR}/"
echo "  ├── state/assigned/    # Agent assignment files"
echo "  ├── state/completed/   # Completion signals"
echo "  ├── cache/             # Cached GitHub data"
echo "  ├── reports/           # Agent review reports"
echo "  ├── logs/              # Orchestrator logs"
echo "  ├── consensus/         # Consensus results"
echo "  └── config/            # Session configuration"
echo "  ${TARGET_DIR}/inbox/   # Drop BRIEF files here"
echo ""
echo "Next steps:"
echo "  1. Copy a BRIEF-*.md file to ${TARGET_DIR}/inbox/"
echo "  2. Start the orchestrator: orch-agent"
