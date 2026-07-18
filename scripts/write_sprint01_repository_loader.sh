#!/bin/bash
set -e

########################################
# __init__.py
########################################

cat > backend/app/repository/__init__.py <<'PY'
from .repository import Repository

__all__ = ["Repository"]
PY

########################################
# models.py
########################################

cat > backend/app/repository/models.py <<'PY'
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RepositoryFile:
    path: Path
    relative_path: str
    extension: str
PY

########################################
# loader.py
########################################

cat > backend/app/repository/loader.py <<'PY'
from pathlib import Path

from .models import RepositoryFile


class RepositoryLoader:

    DEFAULT_IGNORE = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        "node_modules",
        ".idea",
        ".vscode",
        "dist",
        "build",
    }

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def load(self) -> list[RepositoryFile]:

        files = []

        for path in self.root.rglob("*"):

            if not path.is_file():
                continue

            if any(part in self.DEFAULT_IGNORE for part in path.parts):
                continue

            if path.suffix != ".py":
                continue

            files.append(
                RepositoryFile(
                    path=path,
                    relative_path=str(path.relative_to(self.root)),
                    extension=path.suffix,
                )
            )

        files.sort(key=lambda file: file.relative_path)

        return files
PY

########################################
# repository.py
########################################

cat > backend/app/repository/repository.py <<'PY'
from pathlib import Path

from .loader import RepositoryLoader


class Repository:

    def __init__(self, root: str | Path):

        self.root = Path(root)
        self.files = []

    def load(self):

        loader = RepositoryLoader(self.root)

        self.files = loader.load()

        return self.files
PY

########################################
# test_loader.py
########################################

cat > backend/tests/repository/test_loader.py <<'PY'
from app.repository import Repository


def test_load_repository():

    repo = Repository(".")

    files = repo.load()

    assert len(files) > 0

    assert all(file.extension == ".py" for file in files)
PY

echo
echo "Sprint 1 source files written."
