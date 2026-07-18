#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "Installing Odin CLI v1"
echo "========================================"

mkdir -p "$ROOT/scripts/odin_cli"

touch "$ROOT/scripts/odin_cli/__init__.py"

###################################################
# doctor.py
###################################################

cat > "$ROOT/scripts/odin_cli/doctor.py" <<'PY'
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def check(name, func):
    try:
        func()
        print(f"{GREEN}✓{RESET} {name}")
        return True
    except Exception as e:
        print(f"{RED}✗{RESET} {name}: {e}")
        return False


def run():
    print()
    print("========== Odin Doctor ==========")

    results = []

    results.append(check(
        "Backend exists",
        lambda: BACKEND.exists() or (_ for _ in ()).throw(Exception("Missing backend"))
    ))

    results.append(check(
        "Virtual Environment",
        lambda: (BACKEND / ".venv").exists() or (_ for _ in ()).throw(Exception(".venv missing"))
    ))

    results.append(check(
        "Python",
        lambda: subprocess.run(
            [str(BACKEND / ".venv/bin/python"), "--version"],
            check=True,
            capture_output=True
        )
    ))

    print()
    passed = sum(results)
    total = len(results)

    print(f"Health Score: {passed}/{total}")

    if passed != total:
        sys.exit(1)
PY

###################################################
# odin.py
###################################################

cat > "$ROOT/scripts/odin.py" <<'PY'
#!/usr/bin/env python3

import argparse

from odin_cli import doctor

parser = argparse.ArgumentParser(prog="odin")

sub = parser.add_subparsers(dest="command")

doctor_cmd = sub.add_parser("doctor")
doctor_cmd.set_defaults(func=lambda args: doctor.run())

args = parser.parse_args()

if hasattr(args, "func"):
    args.func(args)
else:
    parser.print_help()
PY

chmod +x "$ROOT/scripts/odin.py"

echo
echo "========================================"
echo "Odin CLI Installed"
echo "========================================"
echo
echo "Run:"
echo "python scripts/odin.py doctor"
