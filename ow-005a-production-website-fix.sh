#!/usr/bin/env bash
set -Eeuo pipefail

# OW-005A — Production website stabilization
# Installs deterministic Next.js standalone asset packaging for Render.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ODIN_ROOT:-$SCRIPT_DIR}"
FRONTEND="$ROOT/frontend"
PACKAGE_JSON="$FRONTEND/package.json"
PREPARE_SCRIPT="$FRONTEND/scripts/prepare-standalone.mjs"
VERIFY_SCRIPT="$FRONTEND/scripts/verify-standalone.mjs"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/ow-005a-$STAMP"
CHANGED=0

log() { printf '[%s] %s\n' "$1" "$2"; }
fail() { log FAIL "$*" >&2; exit 1; }

rollback() {
  local exit_code=$?
  if [[ $exit_code -eq 0 ]]; then
    return
  fi

  log WARN "Installation failed. Rolling back OW-005A changes."
  if [[ -f "$BACKUP_DIR/package.json" ]]; then
    cp "$BACKUP_DIR/package.json" "$PACKAGE_JSON"
  fi
  if [[ -f "$BACKUP_DIR/prepare-standalone.mjs" ]]; then
    mkdir -p "$(dirname "$PREPARE_SCRIPT")"
    cp "$BACKUP_DIR/prepare-standalone.mjs" "$PREPARE_SCRIPT"
  else
    rm -f "$PREPARE_SCRIPT"
  fi
  if [[ -f "$BACKUP_DIR/verify-standalone.mjs" ]]; then
    cp "$BACKUP_DIR/verify-standalone.mjs" "$VERIFY_SCRIPT"
  else
    rm -f "$VERIFY_SCRIPT"
  fi
  exit "$exit_code"
}
trap rollback ERR INT TERM

[[ -f "$ROOT/README.md" && -d "$ROOT/backend" && -d "$ROOT/frontend" ]] || fail "Run this script from the odin-core repository root, or set ODIN_ROOT. Resolved root: $ROOT"
[[ -d "$FRONTEND" ]] || fail "Frontend directory not found: $FRONTEND"
[[ -f "$PACKAGE_JSON" ]] || fail "package.json not found: $PACKAGE_JSON"
command -v node >/dev/null 2>&1 || fail "Node.js is required."
command -v npm >/dev/null 2>&1 || fail "npm is required."
command -v python3 >/dev/null 2>&1 || fail "Python 3 is required."

mkdir -p "$BACKUP_DIR" "$(dirname "$PREPARE_SCRIPT")"
cp "$PACKAGE_JSON" "$BACKUP_DIR/package.json"
if [[ -f "$PREPARE_SCRIPT" ]]; then
  cp "$PREPARE_SCRIPT" "$BACKUP_DIR/prepare-standalone.mjs"
fi
if [[ -f "$VERIFY_SCRIPT" ]]; then
  cp "$VERIFY_SCRIPT" "$BACKUP_DIR/verify-standalone.mjs"
fi

log INFO "Installing deterministic standalone asset packaging."

cat > "$PREPARE_SCRIPT" <<'MJS'
import { cp, mkdir, rm, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(scriptDirectory, "..");
const nextRoot = path.join(frontendRoot, ".next");
const standaloneRoot = path.join(nextRoot, "standalone");

async function exists(target) {
  try {
    await stat(target);
    return true;
  } catch (error) {
    if (error && error.code === "ENOENT") return false;
    throw error;
  }
}

async function copyDirectory(source, destination, { required = false } = {}) {
  if (!(await exists(source))) {
    if (required) {
      throw new Error(`Required build directory is missing: ${source}`);
    }
    console.log(`[standalone] Skipping missing optional directory: ${source}`);
    return;
  }

  await rm(destination, { recursive: true, force: true });
  await mkdir(path.dirname(destination), { recursive: true });
  await cp(source, destination, { recursive: true, force: true });
  console.log(`[standalone] Copied ${source} -> ${destination}`);
}

async function main() {
  if (!(await exists(path.join(standaloneRoot, "server.js")))) {
    throw new Error(
      "Next.js standalone server was not generated. Confirm next.config.ts contains output: 'standalone'.",
    );
  }

  await copyDirectory(
    path.join(nextRoot, "static"),
    path.join(standaloneRoot, ".next", "static"),
    { required: true },
  );

  await copyDirectory(
    path.join(frontendRoot, "public"),
    path.join(standaloneRoot, "public"),
  );

  console.log("[standalone] Production bundle is ready.");
}

main().catch((error) => {
  console.error(`[standalone] ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
MJS

python3 - "$PACKAGE_JSON" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
data = json.loads(path.read_text())
scripts = data.setdefault("scripts", {})

scripts["build"] = "next build && node scripts/prepare-standalone.mjs"
scripts["start:standalone"] = "node .next/standalone/server.js"
scripts["verify:standalone"] = "node scripts/verify-standalone.mjs"

path.write_text(json.dumps(data, indent=2) + "\n")
PY

cat > "$VERIFY_SCRIPT" <<'MJS'
import { access } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const required = [
  ".next/standalone/server.js",
  ".next/standalone/.next/static",
];

for (const relativePath of required) {
  const target = path.join(root, relativePath);
  try {
    await access(target);
    console.log(`[verify] OK ${relativePath}`);
  } catch {
    console.error(`[verify] MISSING ${relativePath}`);
    process.exitCode = 1;
  }
}

if (!process.exitCode) {
  console.log("[verify] Standalone production assets are packaged correctly.");
}
MJS

log INFO "Installing frontend dependencies."
cd "$FRONTEND"
npm ci

log INFO "Running frontend verification."
npm run lint
npm run typecheck
npm run build
npm run verify:standalone

trap - ERR INT TERM
CHANGED=1
log OK "OW-005A installed successfully."
echo
echo "Render settings:"
echo "  Root Directory: frontend"
echo "  Build Command:  npm ci && npm run build"
echo "  Start Command:  npm run start:standalone"
echo "  Environment:    HOSTNAME=0.0.0.0"
echo
echo "Commit with:"
echo "  cd \"$ROOT\""
echo "  git add frontend/package.json frontend/scripts/prepare-standalone.mjs frontend/scripts/verify-standalone.mjs"
echo "  git commit -m \"fix(frontend): package standalone assets for Render\""
echo "  git push origin main"
