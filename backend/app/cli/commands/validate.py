from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(
    command: list[str],
    *,
    cwd: Path,
) -> int:
    print()
    print("$", " ".join(command))

    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
    )

    return result.returncode


def run(args) -> int:
    repo_root: Path = args.repo_root
    failures = 0

    print("Odin Validator")
    print("=" * 50)

    compile_targets = (
        repo_root / "backend" / "app",
        repo_root / "odin_mcp",
    )

    for target in compile_targets:
        if not target.exists():
            print(f"[SKIP] Missing target: {target.relative_to(repo_root)}")
            continue

        return_code = _run(
            [
                sys.executable,
                "-m",
                "compileall",
                "-q",
                str(target),
            ],
            cwd=repo_root,
        )

        if return_code == 0:
            print(f"[OK] Compiled {target.relative_to(repo_root)}")
        else:
            print(f"[FAILED] Compilation failed for {target.relative_to(repo_root)}")
            failures += 1

    tests_dir = repo_root / "tests"

    if tests_dir.exists():
        return_code = _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
            ],
            cwd=repo_root,
        )

        if return_code == 0:
            print("[OK] Tests passed")
        else:
            print("[FAILED] Tests failed")
            failures += 1
    else:
        print()
        print("[SKIP] No root tests directory found")

    backend_tests = repo_root / "backend" / "tests"

    if backend_tests.exists():
        return_code = _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests",
            ],
            cwd=repo_root / "backend",
        )

        if return_code == 0:
            print("[OK] Backend tests passed")
        else:
            print("[FAILED] Backend tests failed")
            failures += 1
    else:
        print("[SKIP] No backend tests directory found")

    print()

    if failures:
        print(f"Validation completed with {failures} failure(s).")
        return 1

    print("Validation completed successfully.")
    return 0