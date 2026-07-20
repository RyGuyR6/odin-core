#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ODIN_ROOT:-/workspaces/odin-core}"
INSTALLER="$ROOT/ow-004-runtime-dashboard.sh"
TARGET="$ROOT/frontend/components/dashboard/runtime-dashboard.tsx"
STAMP="$(date +%Y%m%d-%H%M%S)"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

[[ -d "$ROOT" ]] || fail "Repository root not found: $ROOT"
[[ -f "$INSTALLER" ]] || fail "OW-004 installer not found: $INSTALLER"

echo "[INFO] The previous OW-004 rollback removed the generated dashboard file."
echo "[INFO] Patching the OW-004 installer so it generates lint-safe React code."

cp "$INSTALLER" "$INSTALLER.bak-$STAMP"
echo "[OK] Installer backup created: $INSTALLER.bak-$STAMP"

python3 - "$INSTALLER" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
original = text

text = re.sub(r"\bClock3\s*,\s*", "", text)
text = re.sub(r",\s*Clock3\b", "", text)

patterns = [
    r"useEffect\(\(\) => \{ void load\(\); const id = window\.setInterval\(\(\) => void load\(\), 10000\); return \(\) => window\.clearInterval\(id\); \}, \[load\]\);",
    r"useEffect\(\(\)\s*=>\s*\{\s*void load\(\);\s*const id = window\.setInterval\(\(\)\s*=>\s*void load\(\),\s*10000\);\s*return \(\)\s*=>\s*window\.clearInterval\(id\);\s*\},\s*\[load\]\);",
]

replacement = '''useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void load();
    }, 0);

    const id = window.setInterval(() => {
      void load();
    }, 10000);

    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(id);
    };
  }, [load]);'''

replaced = False
for pattern in patterns:
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count:
        replaced = True
        break

if not replaced and replacement not in text:
    raise SystemExit(
        "[FAIL] Could not locate the generated useEffect block inside "
        "ow-004-runtime-dashboard.sh. No changes were written."
    )

text = re.sub(
    r"(?m)^(\s*)setLoading\(true\);\s*$",
    "",
    text,
    count=1,
)

if text == original:
    print("[INFO] Installer already appears to contain the fix.")
else:
    path.write_text(text)
    print("[OK] Patched OW-004 installer.")
PY

chmod +x "$INSTALLER"

echo "[INFO] Checking that the bad effect is no longer embedded..."
if grep -Fq 'useEffect(() => { void load();' "$INSTALLER"; then
  fail "The old synchronous effect is still present in the installer."
fi

echo "[INFO] Re-running OW-004..."
cd "$ROOT"
"$INSTALLER"

[[ -f "$TARGET" ]] || fail "OW-004 completed but did not create $TARGET"

echo "[INFO] Running final frontend verification..."
cd "$ROOT/frontend"
npm run verify

echo
echo "[OK] OW-004 completed and frontend verification passed."
echo
echo "Commit the completed milestone with:"
echo "  cd \"$ROOT\""
echo "  git add -A"
echo "  git commit -m \"feat: complete OW-004 runtime dashboard\""
echo "  git push origin main"
