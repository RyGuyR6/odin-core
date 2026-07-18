#!/usr/bin/env bash
set -e

cat > scripts/odin <<'BASH'
#!/usr/bin/env bash

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT/backend"

exec .venv/bin/python -m app.cli.odin "$@"
BASH

chmod +x scripts/odin

echo "✅ Odin launcher fixed."
