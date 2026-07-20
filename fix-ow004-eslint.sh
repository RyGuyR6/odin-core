#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/workspaces/odin-core"
FILE="$ROOT/frontend/components/dashboard/runtime-dashboard.tsx"

if [[ ! -f "$FILE" ]]; then
  echo "[FAIL] $FILE not found"
  exit 1
fi

cp "$FILE" "$FILE.bak"

sed -i 's/Clock3,//g' "$FILE"

python3 <<'PY'
from pathlib import Path
import re

path = Path("/workspaces/odin-core/frontend/components/dashboard/runtime-dashboard.tsx")
text = path.read_text()

text = text.replace(
"useEffect(() => { void load(); const id = window.setInterval(() => void load(), 10000); return () => window.clearInterval(id); }, [load]);",
"""useEffect(() => {
  const start = () => {
    queueMicrotask(() => {
      void load();
    });
  };

  start();

  const id = window.setInterval(() => {
    void load();
  }, 10000);

  return () => window.clearInterval(id);
}, [load]);"""
)

text = text.replace(
"setLoading(true);",
"""if (!data) {
      setLoading(true);
    }"""
)

path.write_text(text)
PY

cd "$ROOT/frontend"
npm run verify

echo
echo "[OK] OW-004 ESLint fixes applied."
