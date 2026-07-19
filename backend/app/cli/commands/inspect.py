from __future__ import annotations

from pathlib import Path


INSPECT_PATHS = (
    "backend/app",
    "backend/app/services",
    "backend/app/cli",
    "odin_mcp",
    "odin_mcp/core",
    "odin_mcp/services",
    "odin_mcp/tools",
)


def _count_files(directory: Path, suffix: str = ".py") -> int:
    return sum(1 for path in directory.rglob(f"*{suffix}") if path.is_file())


def run(args) -> int:
    repo_root: Path = args.repo_root

    print("Odin Inspector")
    print("=" * 50)

    for relative_path in INSPECT_PATHS:
        path = repo_root / relative_path

        if not path.exists():
            print(f"[MISSING] {relative_path}")
            continue

        file_count = _count_files(path)

        print(f"[OK] {relative_path}")
        print(f"     Python files : {file_count}")

    print()

    print("Repository Summary")
    print("-" * 50)

    backend = repo_root / "backend"
    odin_mcp = repo_root / "odin_mcp"

    if backend.exists():
        print(f"Backend Python files : {_count_files(backend)}")

    if odin_mcp.exists():
        print(f"MCP Python files     : {_count_files(odin_mcp)}")

    print()

    print("Inspection complete.")

    return 0