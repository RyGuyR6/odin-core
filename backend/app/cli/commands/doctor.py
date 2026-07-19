from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REQUIRED_PATHS = (
    "backend/app",
    "backend/app/cli/odin.py",
    "backend/pyproject.toml",
    "odin_mcp",
    "odin_mcp/server.py",
)

REQUIRED_MODULES = (
    "fastapi",
    "pydantic",
    "pytest",
)


def _run_command(
    command: list[str],
    *,
    cwd: Path,
) -> tuple[bool, str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )

    output = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )

    return result.returncode == 0, output


def run(args) -> int:
    repo_root: Path = args.repo_root
    failures = 0

    print("Odin Doctor")
    print("=" * 50)

    print("\nRequired paths")

    for relative_path in REQUIRED_PATHS:
        path = repo_root / relative_path

        if path.exists():
            print(f"[OK]      {relative_path}")
        else:
            print(f"[MISSING] {relative_path}")
            failures += 1

    print("\nPython")
    print(f"[INFO] executable: {sys.executable}")
    print(f"[INFO] version:    {sys.version.split()[0]}")

    print("\nPython dependencies")

    for module_name in REQUIRED_MODULES:
        if importlib.util.find_spec(module_name) is not None:
            print(f"[OK]      {module_name}")
        else:
            print(f"[MISSING] {module_name}")
            failures += 1

    print("\nCompilation")

    compile_targets = (
        repo_root / "backend" / "app",
        repo_root / "odin_mcp",
    )

    for target in compile_targets:
        if not target.exists():
            continue

        success, output = _run_command(
            [
                sys.executable,
                "-m",
                "compileall",
                "-q",
                str(target),
            ],
            cwd=repo_root,
        )

        relative_target = target.relative_to(repo_root)

        if success:
            print(f"[OK]      {relative_target}")
        else:
            print(f"[FAILED]  {relative_target}")
            failures += 1

            if output:
                print(output)

    print("\nGit repository")

    success, output = _run_command(
        ["git", "status", "--short"],
        cwd=repo_root,
    )

    if success:
        print("[OK]      git status")

        if output:
            print(output)
        else:
            print("[INFO]    working tree clean")
    else:
        print("[FAILED]  git status")
        failures += 1

        if output:
            print(output)

    print()

    if failures:
        print(f"Doctor found {failures} issue(s).")
        return 1

    print("Doctor found no issues.")
    return 0