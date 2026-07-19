#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

OUT="architecture_report.txt"

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
)

for FILE in "${FILES[@]}"; do
    if [[ -f "$FILE" ]]; then
        echo "==========================================" >> "$OUT"
        echo "$FILE" >> "$OUT"
        echo "==========================================" >> "$OUT"
        sed -n '1,250p' "$FILE" >> "$OUT"
        echo >> "$OUT"
    fi
done

echo "==========================================" >> "$OUT"
echo "CLASS CONSTRUCTORS" >> "$OUT"
echo "==========================================" >> "$OUT"

grep -R "^class " odin_mcp -n >> "$OUT" || true
echo >> "$OUT"

grep -R "def __init__" odin_mcp -n >> "$OUT" || true
echo >> "$OUT"

echo "==========================================" >> "$OUT"
echo "REGISTERED TOOLS" >> "$OUT"
echo "==========================================" >> "$OUT"

grep -R "register_.*tools" odin_mcp -n >> "$OUT" || true
echo >> "$OUT"

echo "==========================================" >> "$OUT"
echo "ENGINEERING SERVICE INSTANTIATIONS" >> "$OUT"
echo "==========================================" >> "$OUT"

grep -R "EngineeringService(" odin_mcp -n >> "$OUT" || true
echo >> "$OUT"

echo "==========================================" >> "$OUT"
echo "GIT SERVICE INSTANTIATIONS" >> "$OUT"
echo "==========================================" >> "$OUT"

grep -R "GitService(" odin_mcp -n >> "$OUT" || true
echo >> "$OUT"

echo "==========================================" >> "$OUT"
echo "FILESYSTEM SERVICE INSTANTIATIONS" >> "$OUT"
echo "==========================================" >> "$OUT"

grep -R "FilesystemService(" odin_mcp -n >> "$OUT" || true
echo >> "$OUT"

echo
echo "=========================================="
echo " Architecture report generated"
echo "=========================================="
echo
echo "Output:"
echo "  architecture_report.txt"
echo
echo "Next:"
echo "  cat architecture_report.txt"
echo
