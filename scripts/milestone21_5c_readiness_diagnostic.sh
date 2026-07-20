#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""
BACKEND=""
PYTHON_BIN=""
OUT_DIR=""

for candidate in \
  "${ODIN_ROOT:-}" \
  "$(pwd)" \
  "/workspaces/odin-core" \
  "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$candidate" ]] || continue
  if [[ -d "$candidate/backend/app" ]]; then
    ROOT="$(cd "$candidate" && pwd)"
    BACKEND="$ROOT/backend"
    break
  fi
done

if [[ -z "$ROOT" ]]; then
  echo "❌ Could not locate odin-core repository" >&2
  exit 1
fi

for candidate in \
  "$BACKEND/.venv/bin/python" \
  "$ROOT/.venv/bin/python" \
  "$(command -v python3 || true)" \
  "$(command -v python || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "❌ Python interpreter not found" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="$ROOT/.odin-diagnostics/milestone21_5c_readiness/$STAMP"
mkdir -p "$OUT_DIR"

echo
echo "============================================================"
echo "ODIN 21.5c READINESS DIAGNOSTIC"
echo "============================================================"
echo "Repository: $ROOT"
echo "Backend:    $BACKEND"
echo "Python:     $PYTHON_BIN"
echo "Output:     $OUT_DIR"
echo

cp "$BACKEND/app/services/container.py" "$OUT_DIR/container.py.txt"
[[ -f "$BACKEND/app/services/runtime.py" ]] &&
  cp "$BACKEND/app/services/runtime.py" "$OUT_DIR/runtime.py.txt"
[[ -f "$BACKEND/app/core/odin.py" ]] &&
  cp "$BACKEND/app/core/odin.py" "$OUT_DIR/odin.py.txt"

echo "▶ Inspecting live service-container metadata"

(
  cd "$BACKEND"
  ODIN_DIAGNOSTIC_OUTPUT="$OUT_DIR" ODIN_GITHUB_TOKEN="" PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
import asyncio
import inspect
import json
import traceback
from pathlib import Path

output = Path(__import__("os").environ["ODIN_DIAGNOSTIC_OUTPUT"])

report = {
    "imports": {},
    "container": {},
    "startup": {},
    "runtime": {},
}

try:
    import app.services.container as container_module
    from app.services.container import container

    report["imports"]["container_module"] = container_module.__file__
    report["container"]["class"] = f"{type(container).__module__}.{type(container).__qualname__}"
    report["container"]["attributes"] = sorted(vars(container).keys())
    report["container"]["services_before"] = sorted(
        getattr(container, "services", {}).keys()
    )
    report["container"]["definitions_before"] = sorted(
        getattr(container, "_definitions", {}).keys()
    )

    health_method = getattr(container, "health", None)
    report["container"]["has_health"] = callable(health_method)
    if callable(health_method):
        report["container"]["health_before"] = health_method()

    startup_method = getattr(container, "startup", None)
    if callable(startup_method):
        result = startup_method()
        if inspect.isawaitable(result):
            asyncio.run(result)
        report["startup"]["status"] = "ok"
    else:
        report["startup"]["status"] = "missing"

    report["container"]["services_after"] = sorted(
        getattr(container, "services", {}).keys()
    )
    report["container"]["definitions_after"] = sorted(
        getattr(container, "_definitions", {}).keys()
    )

    if callable(health_method):
        report["container"]["health_after"] = health_method()

except Exception as exc:
    report["startup"]["status"] = "error"
    report["startup"]["error"] = f"{type(exc).__name__}: {exc}"
    report["startup"]["traceback"] = traceback.format_exc()

try:
    import app.services.runtime as runtime_module
    from app.services.runtime import runtime

    report["imports"]["runtime_module"] = runtime_module.__file__
    report["runtime"]["class"] = f"{type(runtime).__module__}.{type(runtime).__qualname__}"
    report["runtime"]["state"] = getattr(getattr(runtime, "state", None), "value", getattr(runtime, "state", None))

    snapshot = getattr(runtime, "snapshot", None)
    if callable(snapshot):
        report["runtime"]["snapshot"] = snapshot()

    required = getattr(runtime, "_required_service_failures", None)
    if callable(required):
        report["runtime"]["required_failures"] = required()

    optional = getattr(runtime, "_optional_service_failures", None)
    if callable(optional):
        report["runtime"]["optional_failures"] = optional()

except Exception as exc:
    report["runtime"]["error"] = f"{type(exc).__name__}: {exc}"
    report["runtime"]["traceback"] = traceback.format_exc()

text = json.dumps(report, indent=2, default=str)
print(text)
(output / "service_health_report.json").write_text(text + "\n")
PY
) 2>&1 | tee "$OUT_DIR/service_health_console.txt"

echo
echo "▶ Inspecting registrations and health implementation"

{
  echo "===== container.py relevant lines ====="
  grep -nE \
    'class ServiceContainer|def register|def register_factory|def startup|def shutdown|def health|state|initialized|required|configured' \
    "$BACKEND/app/services/container.py" || true

  echo
  echo "===== service registrations ====="
  grep -RInE \
    'container\.register|register_factory|register_lazy|register_service' \
    "$BACKEND/app" --exclude-dir='__pycache__' || true

  echo
  echo "===== runtime readiness implementation ====="
  if [[ -f "$BACKEND/app/services/runtime.py" ]]; then
    grep -nE \
      '_service_failed|required_service_failures|optional_service_failures|services\.health' \
      "$BACKEND/app/services/runtime.py" || true
  else
    echo "runtime.py is not currently installed"
  fi
} | tee "$OUT_DIR/source_scan.txt"

echo
echo "▶ Running isolated eager-service probe"

(
  cd "$BACKEND"
  ODIN_GITHUB_TOKEN="" PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
import inspect
import json
from app.services.container import ServiceContainer

class ProbeService:
    def __init__(self):
        self.started = False
        self.stopped = False

    def startup(self):
        self.started = True

    def shutdown(self):
        self.stopped = True

services = ServiceContainer()
probe = ProbeService()
services.register("health", probe)

before = services.health() if hasattr(services, "health") else None

result = services.startup()
if inspect.isawaitable(result):
    import asyncio
    asyncio.run(result)

after = services.health() if hasattr(services, "health") else None

print(json.dumps({
    "probe_started": probe.started,
    "health_before": before,
    "health_after": after,
}, indent=2, default=str))
PY
) 2>&1 | tee "$OUT_DIR/eager_service_probe.txt"

cat > "$OUT_DIR/SUMMARY.txt" <<EOF
ODIN 21.5c readiness diagnostic completed.

Please share these files:
1. service_health_report.json
2. eager_service_probe.txt
3. source_scan.txt

Diagnostic directory:
$OUT_DIR

This script did not modify application source files.
EOF

echo
echo "============================================================"
echo "✅ DIAGNOSTIC COMPLETE"
echo "============================================================"
echo "Output: $OUT_DIR"
echo
cat "$OUT_DIR/SUMMARY.txt"
