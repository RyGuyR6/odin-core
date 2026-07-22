from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from .models import FileIndexEntry, FileKind, RepositoryManifest

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".venv", "venv", "node_modules",
    "dist", "build", "coverage", ".next", ".nuxt", "target", "vendor",
}
LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".cpp": "C++", ".cc": "C++", ".c": "C",
    ".h": "C/C++ Header", ".swift": "Swift", ".kt": "Kotlin",
    ".sh": "Shell", ".sql": "SQL", ".html": "HTML", ".css": "CSS",
    ".vue": "Vue", ".svelte": "Svelte", ".md": "Markdown",
}
CONFIG_NAMES = {
    "pyproject.toml", "package.json", "requirements.txt", "poetry.lock",
    "uv.lock", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "Dockerfile", "docker-compose.yml", "compose.yml", "Makefile",
}
DOC_NAMES = {"README.md", "README.rst", "README.txt", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE"}
SECRET_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "credentials.yml",
    "credentials.yaml",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".der", ".kdbx"}


@dataclass(slots=True)
class RepositoryIndexStats:
    files_considered: int = 0
    files_indexed: int = 0
    skipped_ignored: int = 0
    skipped_large: int = 0
    skipped_secret: int = 0
    stopped_by_limit: bool = False
    skipped_samples: dict[str, list[str]] = field(
        default_factory=lambda: {
            "ignored": [],
            "large": [],
            "secret": [],
        }
    )

class RepositoryIndexer:
    def __init__(self, max_file_bytes: int = 2_000_000, max_files: int = 20_000):
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files
        self.last_stats = RepositoryIndexStats()

    def _kind(self, relative: Path) -> FileKind:
        name = relative.name
        parts = {p.lower() for p in relative.parts}
        if name in CONFIG_NAMES or name.startswith(".env"):
            return FileKind.config
        if name in DOC_NAMES or relative.suffix.lower() in {".md", ".rst"}:
            return FileKind.documentation
        if "test" in parts or "tests" in parts or name.startswith("test_") or name.endswith("_test.py"):
            return FileKind.test
        if relative.suffix.lower() in LANGUAGES:
            return FileKind.source
        if relative.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".woff", ".woff2"}:
            return FileKind.asset
        return FileKind.other

    @staticmethod
    def _binary(path: Path) -> bool:
        try:
            chunk = path.read_bytes()[:8192]
        except OSError:
            return True
        return b"\0" in chunk

    @staticmethod
    def _is_secret_path(relative: Path) -> bool:
        name = relative.name
        lower_name = name.lower()
        if name in SECRET_NAMES or lower_name in SECRET_NAMES:
            return True
        if lower_name.startswith(".env.") and lower_name not in {
            ".env.example",
            ".env.sample",
            ".env.template",
        }:
            return True
        if relative.suffix.lower() in SECRET_SUFFIXES:
            return True
        return False

    def _record_skip(self, reason: str, path: Path) -> None:
        bucket = self.last_stats.skipped_samples.setdefault(reason, [])
        if len(bucket) < 5:
            bucket.append(path.as_posix())

    def build(self, root: Path) -> list[FileIndexEntry]:
        self.last_stats = RepositoryIndexStats()
        entries: list[FileIndexEntry] = []
        for current, dirs, files in os.walk(root):
            kept_dirs = []
            for directory in sorted(dirs):
                if directory in IGNORE_DIRS:
                    self.last_stats.skipped_ignored += 1
                    self._record_skip("ignored", Path(current).joinpath(directory).relative_to(root))
                    continue
                kept_dirs.append(directory)
            dirs[:] = kept_dirs
            for filename in sorted(files):
                path = Path(current) / filename
                relative = path.relative_to(root)
                self.last_stats.files_considered += 1
                if self._is_secret_path(relative):
                    self.last_stats.skipped_secret += 1
                    self._record_skip("secret", relative)
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_size > self.max_file_bytes:
                    self.last_stats.skipped_large += 1
                    self._record_skip("large", relative)
                    continue
                binary = self._binary(path)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                entries.append(FileIndexEntry(
                    path=relative.as_posix(), size=stat.st_size, modified_ns=stat.st_mtime_ns,
                    sha256=digest, kind=self._kind(relative),
                    language=LANGUAGES.get(relative.suffix.lower()), binary=binary,
                ))
                self.last_stats.files_indexed += 1
                if len(entries) >= self.max_files:
                    self.last_stats.stopped_by_limit = True
                    return entries
        return entries

    def manifest(self, workspace_id: str, root: Path, entries: list[FileIndexEntry]) -> RepositoryManifest:
        root_files = sorted(p.name for p in root.iterdir() if p.is_file())[:200]
        languages: dict[str, int] = {}
        frameworks: set[str] = set()
        package_managers: set[str] = set()
        tests: list[str] = []
        builds: list[str] = []
        names = {entry.path for entry in entries}

        for entry in entries:
            if entry.language:
                languages[entry.language] = languages.get(entry.language, 0) + 1

        if "pyproject.toml" in names:
            package_managers.add("Python")
            tests.append("pytest")
            builds.append("python -m build")
            try:
                text = (root / "pyproject.toml").read_text(errors="ignore").lower()
                for name in ("fastapi", "django", "flask"):
                    if name in text:
                        frameworks.add(name.title())
            except OSError:
                pass
        if "package.json" in names:
            package_managers.add("npm")
            tests.append("npm test")
            builds.append("npm run build")
            try:
                data = json.loads((root / "package.json").read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                mapping = {"react": "React", "next": "Next.js", "vue": "Vue", "svelte": "Svelte", "express": "Express"}
                for dep, framework in mapping.items():
                    if dep in deps:
                        frameworks.add(framework)
            except (OSError, json.JSONDecodeError):
                pass
        if "Cargo.toml" in names:
            package_managers.add("Cargo"); tests.append("cargo test"); builds.append("cargo build")
        if "go.mod" in names:
            package_managers.add("Go modules"); tests.append("go test ./..."); builds.append("go build ./...")
        if "pom.xml" in names:
            package_managers.add("Maven"); tests.append("mvn test"); builds.append("mvn package")

        return RepositoryManifest(
            workspace_id=workspace_id, root_files=root_files,
            languages=dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
            frameworks=sorted(frameworks), package_managers=sorted(package_managers),
            test_commands=tests, build_commands=builds,
            files_indexed=len(entries), total_bytes=sum(entry.size for entry in entries),
        )

    def search_content(
        self, root: Path, query: str, glob: str | None = None,
        max_results: int = 100, case_sensitive: bool = False,
    ) -> list[dict]:
        results = []
        needle = query if case_sensitive else query.lower()
        iterator = root.rglob(glob or "*")
        for path in iterator:
            if not path.is_file() or any(part in IGNORE_DIRS for part in path.relative_to(root).parts):
                continue
            try:
                if path.stat().st_size > self.max_file_bytes or self._binary(path):
                    continue
                text = path.read_text(errors="replace")
            except OSError:
                continue
            for line_number, line in enumerate(text.splitlines(), 1):
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    results.append({
                        "path": path.relative_to(root).as_posix(),
                        "line": line_number,
                        "text": line[:1000],
                    })
                    if len(results) >= max_results:
                        return results
        return results
