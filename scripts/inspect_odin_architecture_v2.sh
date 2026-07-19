#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

OUT="architecture_report.txt"

# Cleaner grep
GREP="grep -R -n --exclude-dir=__pycache__ --exclude=*.pyc"

echo "==========================================" > "$OUT"
echo "        ODIN ARCHITECTURE REPORT" >> "$OUT"
echo "==========================================" >> "$OUT"
echo >> "$OUT"

FILES=(
    "odin_mcp/server.py"
    "odin_mcp/core/orchestrator.py"
    "odin_mcp/core/execute.py"
    "odin_mcp/core/brain.py"
    "odin_mcp/services/engineering_service.py"
    "odin_mcp/services/git_service.py"
    "odin_mcp/services/filesystem_service.py"
    "odin_mcp/services/repository_search_service.py"
    "odin_mcp/services/task_executor.py"
    "odin_mcp/services/plan_executor.py"
    "odin_mcp/services/autonomous_executor.py"
    "odin_mcp/services/validation_service.py"
)

for FILE in "${FILES[@]}"; do
    if [[ -f "$FILE" ]]; then
        {
            echo "=========================================="
            echo "$FILE"
            echo "=========================================="
            sed -n '1,250p' "$FILE"
            echo
        } >> "$OUT"
    fi
done

section() {
    {
        echo
        echo "=========================================="
        echo "$1"
        echo "=========================================="
    } >> "$OUT"
}

section "CLASS DEFINITIONS"
eval "$GREP '^class '" odin_mcp >> "$OUT" || true

section "CONSTRUCTORS"
eval "$GREP 'def __init__'" odin_mcp >> "$OUT" || true

section "REGISTERED TOOL FUNCTIONS"
eval "$GREP 'register_.*tools'" odin_mcp >> "$OUT" || true

section "ENGINEERING SERVICE REFERENCES"
eval "$GREP 'EngineeringService\\('" odin_mcp >> "$OUT" || true

section "GIT SERVICE REFERENCES"
eval "$GREP 'GitService\\('" odin_mcp >> "$OUT" || true

section "FILESYSTEM SERVICE REFERENCES"
eval "$GREP 'FilesystemService\\('" odin_mcp >> "$OUT" || true

section "REPOSITORY SEARCH REFERENCES"
eval "$GREP 'RepositorySearchService\\('" odin_mcp >> "$OUT" || true

section "BRAIN REFERENCES"
eval "$GREP 'OdinBrain\\|BrainPipeline\\|BrainExecutionPipeline'" odin_mcp >> "$OUT" || true

section "MCP TOOLS"
eval "$GREP '@mcp.tool'" odin_mcp >> "$OUT" || true

section "SERVER REGISTRATION"
eval "$GREP 'register_.*tools\\(mcp\\)'" odin_mcp >> "$OUT" || true

echo
echo "=========================================="
echo " Architecture report complete"
echo "=========================================="
echo
echo "Output:"
echo "  $OUT"
echo
echo "Useful commands:"
echo "  head -200 $OUT"
echo "  sed -n '201,400p' $OUT"
echo "  sed -n '401,600p' $OUT"
echo
