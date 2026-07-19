#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

OUT="architecture_report.txt"

{
echo "=========================================="
echo "ODIN ARCHITECTURE REPORT"
echo "=========================================="
echo
} > "$OUT"

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
            echo
            echo "=========================================="
            echo "$FILE"
            echo "=========================================="
            sed -n '1,250p' "$FILE"
        } >> "$OUT"
    fi
done

append_section () {
    TITLE="$1"
    PATTERN="$2"

    {
        echo
        echo "=========================================="
        echo "$TITLE"
        echo "=========================================="
    } >> "$OUT"

    grep -RFn \
        --exclude-dir=__pycache__ \
        --exclude="*.pyc" \
        "$PATTERN" odin_mcp >> "$OUT" || true
}

append_section "CLASS DEFINITIONS" "class "
append_section "CONSTRUCTORS" "def __init__"
append_section "REGISTERED TOOL FUNCTIONS" "register_"
append_section "ENGINEERING SERVICE" "EngineeringService("
append_section "GIT SERVICE" "GitService("
append_section "FILESYSTEM SERVICE" "FilesystemService("
append_section "REPOSITORY SEARCH SERVICE" "RepositorySearchService("
append_section "MCP TOOLS" "@mcp.tool"
append_section "SERVER REGISTRATION" "register_"

echo
echo "Report written to:"
echo "  $OUT"
echo
echo "View with:"
echo "  head -200 $OUT"
