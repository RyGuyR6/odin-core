#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="21.5b-diagnostic"
ROOT=""
BACKEND=""
PYTHON_BIN=""
REPORT_DIR=""
CHECKS=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ CHECKS=$((CHECKS+1)); printf '✅ %s\n' "$1"; }
fail(){ printf '❌ %s\n' "$1" >&2; exit 1; }

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
[[ -n "$ROOT" ]] || fail "Could not locate odin-core repository"

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
[[ -n "$PYTHON_BIN" ]] || fail "Python interpreter not found"

STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT_DIR="$ROOT/.odin-diagnostics/github-token-source/$STAMP"
mkdir -p "$REPORT_DIR"

printf '\n============================================================\n'
printf 'ODIN MILESTONE %s — GITHUB TOKEN SOURCE DIAGNOSTIC\n' "$MILESTONE"
printf '============================================================\n'
printf 'Repository: %s\nBackend:    %s\nPython:     %s\n' "$ROOT" "$BACKEND" "$PYTHON_BIN"
printf 'Report:     %s\n' "$REPORT_DIR"
printf 'Mode: read-only diagnostic; no source files are modified\n'

step "Capturing repository and runtime metadata"
{
  printf 'timestamp=%s\n' "$(date --iso-8601=seconds)"
  printf 'root=%s\n' "$ROOT"
  printf 'backend=%s\n' "$BACKEND"
  printf 'python=%s\n' "$PYTHON_BIN"
  printf 'git_branch=%s\n' "$(git -C "$ROOT" branch --show-current 2>/dev/null || true)"
  printf 'git_commit=%s\n' "$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  printf 'git_status_begin\n'
  git -C "$ROOT" status --short 2>/dev/null || true
  printf 'git_status_end\n'
} > "$REPORT_DIR/runtime.txt"
ok "Runtime metadata captured"

step "Scanning environment variable names without exposing secret values"
(
  cd "$ROOT"
  REPORT_DIR="$REPORT_DIR" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

report = Path(os.environ["REPORT_DIR"])

interesting = {}
for key, value in sorted(os.environ.items()):
    upper = key.upper()
    if "GITHUB" in upper or "ODIN" in upper or "TOKEN" in upper or "ENV" in upper:
        encoded = value.encode("utf-8", errors="replace")
        interesting[key] = {
            "present": True,
            "length": len(value),
            "sha256_prefix": hashlib.sha256(encoded).hexdigest()[:12],
            "is_empty": value == "",
        }

(report / "environment.json").write_text(
    json.dumps(interesting, indent=2, sort_keys=True),
    encoding="utf-8",
)
PY
)
ok "Environment names recorded with redacted fingerprints"

step "Locating environment and configuration files"
find "$ROOT" \
  -path "$ROOT/.git" -prune -o \
  -path "$ROOT/.odin-backups" -prune -o \
  -path "$ROOT/.odin-diagnostics" -prune -o \
  -type f \( \
    -name '.env' -o \
    -name '.env.*' -o \
    -name '*settings*.py' -o \
    -name '*config*.py' -o \
    -name 'pyproject.toml' -o \
    -name 'pytest.ini' -o \
    -name 'tox.ini' -o \
    -name 'conftest.py' \
  \) -print | sort > "$REPORT_DIR/config_files.txt"
ok "Configuration file inventory captured"

step "Scanning source code for GitHub credential and provider references"
patterns=(
  'ODIN_GITHUB_TOKEN'
  'GITHUB_TOKEN'
  'GITHUB_PAT'
  'GH_TOKEN'
  'GitHubClient('
  'GitHubProvider('
  'GitHubService('
  'Settings('
  'BaseSettings'
  'SettingsConfigDict'
  'load_dotenv'
  'dotenv'
  'os.environ'
  'os.getenv'
  'environ.get'
)

: > "$REPORT_DIR/source_matches.txt"
for pattern in "${patterns[@]}"; do
  printf '\n===== PATTERN: %s =====\n' "$pattern" >> "$REPORT_DIR/source_matches.txt"
  grep -RInF \
    --exclude-dir=.git \
    --exclude-dir=.venv \
    --exclude-dir=venv \
    --exclude-dir=node_modules \
    --exclude-dir=.odin-backups \
    --exclude-dir=.odin-diagnostics \
    --exclude='*.pyc' \
    -- "$pattern" "$ROOT" >> "$REPORT_DIR/source_matches.txt" 2>/dev/null || true
done
ok "Credential and constructor references captured"

step "Scanning dotenv files with secret values redacted"
REPORT_DIR="$REPORT_DIR" ROOT="$ROOT" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

root = Path(os.environ["ROOT"])
report = Path(os.environ["REPORT_DIR"])
excluded = {".git", ".venv", "venv", "node_modules", ".odin-backups", ".odin-diagnostics"}

records = []
for path in root.rglob(".env*"):
    if any(part in excluded for part in path.parts):
        continue
    if not path.is_file():
        continue

    entries = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        records.append({"path": str(path.relative_to(root)), "error": str(exc)})
        continue

    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        upper = key.upper()
        if "GITHUB" in upper or "TOKEN" in upper or "ODIN" in upper:
            entries.append(
                {
                    "line": number,
                    "key": key,
                    "length": len(value),
                    "is_empty": value == "",
                    "sha256_prefix": hashlib.sha256(
                        value.encode("utf-8", errors="replace")
                    ).hexdigest()[:12],
                }
            )

    records.append(
        {
            "path": str(path.relative_to(root)),
            "interesting_entries": entries,
        }
    )

(report / "dotenv_scan.json").write_text(
    json.dumps(records, indent=2, sort_keys=True),
    encoding="utf-8",
)
PY
ok "Dotenv credential entries recorded without secret disclosure"

step "Inspecting imported settings and GitHub resolution in isolated processes"
cat > "$REPORT_DIR/runtime_probe.py" <<'PY'
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from typing import Any


def fingerprint(value: Any) -> dict[str, Any]:
    if value is None:
        return {"present": False, "type": "NoneType"}
    text = str(value)
    return {
        "present": True,
        "type": type(value).__name__,
        "length": len(text),
        "is_empty": text == "",
        "sha256_prefix": hashlib.sha256(
            text.encode("utf-8", errors="replace")
        ).hexdigest()[:12],
    }


result: dict[str, Any] = {
    "cwd": os.getcwd(),
    "python": sys.executable,
    "environment": {},
    "imports": {},
}

for key in (
    "ODIN_GITHUB_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "GH_TOKEN",
):
    result["environment"][key] = fingerprint(os.environ.get(key))

try:
    settings_module = importlib.import_module("app.core.settings")
    settings = settings_module.settings
    result["imports"]["settings_module"] = settings_module.__file__
    result["imports"]["settings_value"] = fingerprint(
        getattr(settings, "ODIN_GITHUB_TOKEN", None)
    )
    result["imports"]["settings_fields"] = sorted(
        name for name in dir(settings) if "GITHUB" in name.upper()
    )
except Exception as exc:
    result["imports"]["settings_error"] = f"{type(exc).__name__}: {exc}"

try:
    client_module = importlib.import_module("app.services.github.client")
    result["imports"]["client_module"] = client_module.__file__

    resolver = getattr(client_module, "resolve_github_token", None)
    if callable(resolver):
        result["imports"]["resolver_value"] = fingerprint(resolver())

    client = client_module.GitHubClient(token=None)
    result["imports"]["client_token"] = fingerprint(client.token)
    result["imports"]["client_configured"] = bool(client.configured)
except Exception as exc:
    result["imports"]["client_error"] = f"{type(exc).__name__}: {exc}"

try:
    package = importlib.import_module("app.services.github")
    result["imports"]["package_module"] = package.__file__
    github = getattr(package, "github", None)
    if github is not None:
        result["imports"]["proxy_configured"] = bool(
            getattr(github, "configured", False)
        )
        result["imports"]["proxy_initialized"] = bool(
            getattr(github, "initialized", False)
        )
except Exception as exc:
    result["imports"]["package_error"] = f"{type(exc).__name__}: {exc}"

print(json.dumps(result, indent=2, sort_keys=True))
PY

(
  cd "$ROOT"
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" "$REPORT_DIR/runtime_probe.py"
) > "$REPORT_DIR/probe_normal.json"

(
  cd "$ROOT"
  env -u ODIN_GITHUB_TOKEN \
      -u GITHUB_TOKEN \
      -u GITHUB_PAT \
      -u GH_TOKEN \
      PYTHONPATH="$BACKEND" \
      "$PYTHON_BIN" "$REPORT_DIR/runtime_probe.py"
) > "$REPORT_DIR/probe_env_unset.json"

(
  cd "$ROOT"
  ODIN_GITHUB_TOKEN="" \
  GITHUB_TOKEN="" \
  GITHUB_PAT="" \
  GH_TOKEN="" \
  PYTHONPATH="$BACKEND" \
  "$PYTHON_BIN" "$REPORT_DIR/runtime_probe.py"
) > "$REPORT_DIR/probe_env_empty.json"

(
  cd "$ROOT"
  ODIN_GITHUB_TOKEN="diagnostic-sentinel-token" \
  PYTHONPATH="$BACKEND" \
  "$PYTHON_BIN" "$REPORT_DIR/runtime_probe.py"
) > "$REPORT_DIR/probe_sentinel.json"
ok "Isolated runtime probes completed"

step "Tracing settings source precedence"
REPORT_DIR="$REPORT_DIR" ROOT="$ROOT" BACKEND="$BACKEND" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT"])
backend = Path(os.environ["BACKEND"])
report = Path(os.environ["REPORT_DIR"])

records = []
for path in backend.rglob("*.py"):
    if any(part in {".venv", "__pycache__"} for part in path.parts):
        continue
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except Exception:
        continue

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                parts = []
                current = node.func
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                name = ".".join(reversed(parts))

            if name and any(
                token in name
                for token in (
                    "Settings",
                    "BaseSettings",
                    "GitHubClient",
                    "GitHubProvider",
                    "GitHubService",
                    "load_dotenv",
                    "dotenv_values",
                )
            ):
                records.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": getattr(node, "lineno", None),
                        "call": name,
                    }
                )

(report / "ast_constructor_calls.json").write_text(
    json.dumps(records, indent=2, sort_keys=True),
    encoding="utf-8",
)
PY
ok "Constructor and dotenv call sites identified"

step "Checking pytest configuration and environment injection"
{
  for file in \
    "$ROOT/pyproject.toml" \
    "$ROOT/pytest.ini" \
    "$ROOT/tox.ini" \
    "$BACKEND/pyproject.toml" \
    "$BACKEND/pytest.ini" \
    "$BACKEND/tox.ini" \
    "$BACKEND/tests/conftest.py" \
    "$ROOT/conftest.py"; do
    if [[ -f "$file" ]]; then
      printf '\n===== %s =====\n' "${file#"$ROOT/"}"
      sed -n '1,260p' "$file"
    fi
  done
} > "$REPORT_DIR/pytest_configuration.txt"
ok "Pytest configuration captured"

step "Running targeted pytest probe with secret-safe diagnostics"
cat > "$REPORT_DIR/test_token_source_probe.py" <<'PY'
from __future__ import annotations

import hashlib
import os

from app.core.settings import settings
from app.services.github.client import GitHubClient


def safe(value):
    if value is None:
        return "absent"
    text = str(value)
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    return f"present:length={len(text)}:sha256={digest}"


def test_report_token_sources():
    print("")
    print("ODIN_GITHUB_TOKEN env:", safe(os.environ.get("ODIN_GITHUB_TOKEN")))
    print("GITHUB_TOKEN env:", safe(os.environ.get("GITHUB_TOKEN")))
    print("GITHUB_PAT env:", safe(os.environ.get("GITHUB_PAT")))
    print("GH_TOKEN env:", safe(os.environ.get("GH_TOKEN")))
    print("settings.ODIN_GITHUB_TOKEN:", safe(settings.ODIN_GITHUB_TOKEN))

    client = GitHubClient(token=None)
    print("GitHubClient.token:", safe(client.token))
    print("GitHubClient.configured:", client.configured)

    assert True
PY

(
  cd "$BACKEND"
  env -u ODIN_GITHUB_TOKEN \
      -u GITHUB_TOKEN \
      -u GITHUB_PAT \
      -u GH_TOKEN \
      PYTHONPATH="$BACKEND" \
      "$PYTHON_BIN" -m pytest -q -s "$REPORT_DIR/test_token_source_probe.py"
) > "$REPORT_DIR/pytest_probe.txt" 2>&1 || true
ok "Pytest-specific token source probe completed"

step "Generating a consolidated diagnostic summary"
REPORT_DIR="$REPORT_DIR" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

report = Path(os.environ["REPORT_DIR"])

def load(name):
    path = report / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

normal = load("probe_normal.json") or {}
unset = load("probe_env_unset.json") or {}
empty = load("probe_env_empty.json") or {}
sentinel = load("probe_sentinel.json") or {}
dotenv = load("dotenv_scan.json") or []
environment = load("environment.json") or {}

lines = []
lines.append("ODIN GITHUB TOKEN SOURCE DIAGNOSTIC")
lines.append("=" * 44)
lines.append("")

def configured(data):
    return (
        data.get("imports", {})
        .get("client_configured", "unknown")
    )

lines.append(f"Normal process configured:        {configured(normal)}")
lines.append(f"All known token env vars unset:   {configured(unset)}")
lines.append(f"All known token env vars empty:   {configured(empty)}")
lines.append(f"Sentinel ODIN token configured:   {configured(sentinel)}")
lines.append("")

settings_unset = (
    unset.get("imports", {})
    .get("settings_value", {})
    .get("present", False)
)
client_unset = (
    unset.get("imports", {})
    .get("client_token", {})
    .get("present", False)
)

if client_unset:
    lines.append(
        "PRIMARY FINDING: GitHubClient still receives a token when all known "
        "GitHub token environment variables are removed."
    )
    if settings_unset:
        lines.append(
            "Likely source: app.core.settings loaded ODIN_GITHUB_TOKEN from "
            "a dotenv/config source."
        )
    else:
        lines.append(
            "Likely source: another constructor or alternate token resolver."
        )
else:
    lines.append(
        "PRIMARY FINDING: GitHubClient is unconfigured when known token "
        "environment variables are removed."
    )
    lines.append(
        "Likely source of previous failures: pytest or shell environment injection."
    )

interesting_dotenv = []
for item in dotenv:
    entries = item.get("interesting_entries") or []
    if entries:
        interesting_dotenv.append((item.get("path"), entries))

lines.append("")
lines.append(f"Interesting process environment keys: {len(environment)}")
lines.append(f"Dotenv files with GitHub/token entries: {len(interesting_dotenv)}")
for path, entries in interesting_dotenv:
    keys = ", ".join(entry["key"] for entry in entries)
    lines.append(f"  - {path}: {keys}")

lines.append("")
lines.append("Review these files:")
for name in (
    "probe_normal.json",
    "probe_env_unset.json",
    "probe_env_empty.json",
    "probe_sentinel.json",
    "environment.json",
    "dotenv_scan.json",
    "source_matches.txt",
    "ast_constructor_calls.json",
    "pytest_configuration.txt",
    "pytest_probe.txt",
):
    lines.append(f"  - {name}")

(report / "SUMMARY.txt").write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8",
)
print("\n".join(lines))
PY
ok "Diagnostic summary generated"

step "Creating portable report archive"
tar -C "$(dirname "$REPORT_DIR")" \
  -czf "$REPORT_DIR.tar.gz" \
  "$(basename "$REPORT_DIR")"
ok "Diagnostic report archive created"

printf '\n============================================================\n'
printf '✅ ODIN MILESTONE %s COMPLETE\n' "$MILESTONE"
printf '============================================================\n'
printf 'Checks passed: %s\n' "$CHECKS"
printf 'Report folder: %s\n' "$REPORT_DIR"
printf 'Report archive: %s.tar.gz\n' "$REPORT_DIR"
printf '\nNo Odin source files were modified.\n'
printf '\nSend back the contents of:\n'
printf '  %s/SUMMARY.txt\n' "$REPORT_DIR"
printf '\nFor deeper inspection, also send:\n'
printf '  %s/probe_env_unset.json\n' "$REPORT_DIR"
printf '  %s/dotenv_scan.json\n' "$REPORT_DIR"
printf '  %s/pytest_probe.txt\n' "$REPORT_DIR"
