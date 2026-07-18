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
