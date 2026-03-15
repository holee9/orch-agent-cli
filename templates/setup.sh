#!/usr/bin/env bash
# setup.sh - Initialize target project for orch-agent-cli orchestration
#
# Usage (from orch-agent-cli directory):
#   bash templates/setup.sh <target_project_path> <github_owner/repo>
#
# Example:
#   bash templates/setup.sh /Volumes/project/my-new-project myorg/my-new-project

set -euo pipefail

TARGET_DIR="${1:?Usage: bash templates/setup.sh <target_project_path> <github_owner/repo>}"
GITHUB_REPO="${2:?Usage: bash templates/setup.sh <target_project_path> <github_owner/repo>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ORCHESTRA_DIR="${TARGET_DIR}/.orchestra"
TARGET_ABS="$(cd "${TARGET_DIR}" && pwd)"

echo "=== orch-agent-cli Setup ==="
echo "Target:      ${TARGET_ABS}"
echo "GitHub repo: ${GITHUB_REPO}"
echo ""

# --- Create .orchestra directory structure ---
echo "Creating .orchestra/ directory structure..."
mkdir -p "${ORCHESTRA_DIR}/state/assigned"
mkdir -p "${ORCHESTRA_DIR}/state/completed"
mkdir -p "${ORCHESTRA_DIR}/cache"
mkdir -p "${ORCHESTRA_DIR}/reports"
mkdir -p "${ORCHESTRA_DIR}/logs"
mkdir -p "${ORCHESTRA_DIR}/consensus"
mkdir -p "${ORCHESTRA_DIR}/config"

# --- Create inbox and docs directories ---
echo "Creating inbox/ and docs/ directories..."
mkdir -p "${TARGET_DIR}/inbox"
mkdir -p "${TARGET_DIR}/docs/specs"
mkdir -p "${TARGET_DIR}/docs/plans"
mkdir -p "${TARGET_DIR}/docs/briefs"

# --- Copy agent instruction files ---
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

# --- Create session config ---
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

# --- Update orch-agent-cli config/config.yaml with new target ---
echo "Updating config/config.yaml..."
CONFIG_FILE="${ORCH_DIR}/config/config.yaml"
if [ -f "${CONFIG_FILE}" ]; then
    # Update github.repo and orchestrator.target_project_path in-place
    python3 - "${CONFIG_FILE}" "${GITHUB_REPO}" "${TARGET_ABS}" << 'PYEOF'
import sys, re

config_path, github_repo, target_path = sys.argv[1], sys.argv[2], sys.argv[3]

with open(config_path, 'r') as f:
    content = f.read()

# Replace github.repo line
content = re.sub(
    r'^(\s*repo:\s*).*$',
    lambda m: f'{m.group(1)}"{github_repo}"  # Set via env GITHUB_REPO or here',
    content, flags=re.MULTILINE
)
# Replace orchestrator.target_project_path line
content = re.sub(
    r'^(\s*target_project_path:\s*).*$',
    lambda m: f'{m.group(1)}"{target_path}"  # Set via env TARGET_PROJECT_PATH or here',
    content, flags=re.MULTILINE
)

with open(config_path, 'w') as f:
    f.write(content)

print(f"  github.repo = {github_repo}")
print(f"  target_project_path = {target_path}")
PYEOF
else
    echo "  WARNING: config/config.yaml not found in orch-agent-cli"
fi

# --- Create terminal wrapper scripts in target project ---
echo "Creating terminal wrapper scripts..."
ORCH_REL="$(python3 -c "import os; print(os.path.relpath('${ORCH_DIR}', '${TARGET_ABS}'))")"

for terminal in t1 t2 t3 t4; do
    cat > "${TARGET_DIR}/start_${terminal}.sh" << EOF
#!/usr/bin/env bash
# Run from project root: bash start_${terminal}.sh
exec bash "\$(cd "\$(dirname "\$0")" && pwd)/${ORCH_REL}/scripts/start_${terminal}.sh"
EOF
    chmod +x "${TARGET_DIR}/start_${terminal}.sh"
    echo "  Created start_${terminal}.sh"
done

# --- Add .orchestra to .gitignore ---
GITIGNORE="${TARGET_DIR}/.gitignore"
if [ -f "${GITIGNORE}" ]; then
    if ! grep -q "^\.orchestra/" "${GITIGNORE}" 2>/dev/null; then
        printf "\n# orch-agent-cli state\n.orchestra/\ninbox/\nstart_t*.sh\n" >> "${GITIGNORE}"
        echo "Updated .gitignore"
    fi
else
    cat > "${GITIGNORE}" << 'EOF'
# orch-agent-cli state
.orchestra/
inbox/
start_t*.sh
EOF
    echo "Created .gitignore"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start all 4 terminals from ${TARGET_ABS}:"
echo ""
echo "  T2 (Claude runner):   bash start_t2.sh"
echo "  T3 (Codex runner):    bash start_t3.sh"
echo "  T4 (Gemini runner):   bash start_t4.sh"
echo "  T1 (Orchestrator):    bash start_t1.sh   ← run last"
echo ""
echo "Then drop a BRIEF file into: ${TARGET_DIR}/inbox/"
