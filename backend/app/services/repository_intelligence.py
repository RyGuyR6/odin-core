from __future__ import annotations

import ast
import json
import os
import re
import sqlite3
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from math import sqrt
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.llm.exceptions import AllProvidersFailedError, ProviderConfigurationError
from app.llm.models import EmbeddingRequest
from app.llm.service import get_llm_service
from app.repositories.config import get_repository_settings
from app.repositories.git import GitClient
from app.repositories.indexer import RepositoryIndexer
from app.repositories.security import safe_child

DB_PATH = Path(
    os.getenv(
        "ODIN_REPOSITORY_DB",
        os.getenv("ODIN_AUTH_DB", "data/odin.db"),
    )
)
ENTRYPOINT_NAMES = {
    "main.py",
    "__main__.py",
    "app.py",
    "server.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "package.json",
    "Makefile",
    "Dockerfile",
}
CONFIG_SUFFIXES = (".config.js", ".config.ts", ".config.mjs", ".config.cjs")
SCRIPT_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
SOURCE_EXTENSIONS = {".py", *SCRIPT_EXTENSIONS}
LOCAL_SCRIPT_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]
IMPORT_RE = re.compile(
    r"^\s*import\s+(?:type\s+)?(?P<what>.+?)\s+from\s+[\"'](?P<module>[^\"']+)[\"']",
    re.MULTILINE,
)
BARE_IMPORT_RE = re.compile(r"^\s*import\s+[\"'](?P<module>[^\"']+)[\"']", re.MULTILINE)
EXPORT_FROM_RE = re.compile(
    r"^\s*export\s+(?:\*|\{[^}]+\})\s+from\s+[\"'](?P<module>[^\"']+)[\"']",
    re.MULTILINE,
)
CLASS_RE = re.compile(
    r"^\s*(?:export\s+default\s+|export\s+)?class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
INTERFACE_RE = re.compile(
    r"^\s*export\s+interface\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
)
ENUM_RE = re.compile(
    r"^\s*(?:export\s+)?enum\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
)
FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+default\s+|export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
CONST_RE = re.compile(
    r"^\s*(?:export\s+)?const\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=",
    re.MULTILINE,
)
ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?const\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?(?:\([^\)]*\)|[A-Za-z_][A-Za-z0-9_]*)\s*=>",
    re.MULTILINE,
)
METHOD_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+|async\s+)*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.MULTILINE,
)
ROUTE_HINT_RE = re.compile(
    r"(?:router|app)\.(?:get|post|put|patch|delete|options|head)\s*\("
)
FASTAPI_ROUTE_RE = re.compile(
    r"@(?:router|app)\.(?:get|post|put|patch|delete|options|head)\s*\("
)
ENV_FILE_RE = re.compile(r"(?:^|/)\.env(?:\..+)?$")
SCRIPT_SYMBOL_PATTERNS = (
    (INTERFACE_RE, "interface"),
    (ENUM_RE, "enum"),
    (FUNCTION_RE, "function"),
    (ARROW_RE, "function"),
    (CONST_RE, "constant"),
)


class FileNode(BaseModel):
    name: str
    path: str
    type: str
    children: list["FileNode"] = Field(default_factory=list)


class InventoryEntry(BaseModel):
    path: str
    size: int
    kind: str
    language: str | None = None
    binary: bool = False
    modified_ns: int | None = None
    sha256: str | None = None


class SymbolRelationship(BaseModel):
    type: str
    target: str


class SymbolRecord(BaseModel):
    name: str
    qualified_name: str
    kind: str
    file_path: str
    line: int
    language: str | None = None
    module: str | None = None
    container: str | None = None
    exported: bool = False
    decorators: list[str] = Field(default_factory=list)
    bases: list[str] = Field(default_factory=list)
    relationships: list[SymbolRelationship] = Field(default_factory=list)


class DocumentationRecord(BaseModel):
    path: str
    line: int = 1
    title: str
    kind: str
    language: str | None = None
    symbol: str | None = None
    excerpt: str
    related_paths: list[str] = Field(default_factory=list)
    related_symbols: list[str] = Field(default_factory=list)


class SymbolReferenceRecord(BaseModel):
    symbol: str
    file_path: str
    line: int
    kind: str = "reference"
    excerpt: str = ""


class ArchitectureCategory(BaseModel):
    category: str
    files: list[str] = Field(default_factory=list)


class DependencyNode(BaseModel):
    id: str
    label: str
    kind: str = "file"


class DependencyEdge(BaseModel):
    source: str
    target: str
    kind: str = "import"
    external: bool = False


class DependencyGraphRecord(BaseModel):
    nodes: list[DependencyNode] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)
    circular_dependencies: list[list[str]] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)


class MajorModule(BaseModel):
    name: str
    file_count: int


class RepositorySummaryRecord(BaseModel):
    project_purpose: str
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    architecture: list[str] = Field(default_factory=list)
    major_modules: list[MajorModule] = Field(default_factory=list)
    key_entry_points: list[str] = Field(default_factory=list)
    test_framework: list[str] = Field(default_factory=list)
    build_system: list[str] = Field(default_factory=list)
    package_manager: list[str] = Field(default_factory=list)


class RepositoryIntelligencePayload(BaseModel):
    repository: str
    local_path: str
    indexed_revision: str | None = None
    inventory: list[InventoryEntry] = Field(default_factory=list)
    directory_tree: FileNode
    symbols: list[SymbolRecord] = Field(default_factory=list)
    references: list[SymbolReferenceRecord] = Field(default_factory=list)
    documentation: list[DocumentationRecord] = Field(default_factory=list)
    architecture: list[ArchitectureCategory] = Field(default_factory=list)
    dependency_graph: DependencyGraphRecord = Field(
        default_factory=DependencyGraphRecord
    )
    summary: RepositorySummaryRecord
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepositoryScanRecord(BaseModel):
    repository: str
    local_path: str | None = None
    status: str = "idle"
    scan_started_at: str | None = None
    scan_completed_at: str | None = None
    updated_at: str | None = None
    error: str | None = None
    payload: RepositoryIntelligencePayload | None = None


FileNode.model_rebuild()


@dataclass(slots=True)
class ImportReference:
    module: str
    line: int
    external: bool
    resolved_path: str | None = None


@dataclass(slots=True)
class AnalysisResult:
    symbols: list[SymbolRecord]
    imports: list[ImportReference]
    references: list[SymbolReferenceRecord]
    documentation: list[DocumentationRecord]
    architecture_matches: set[str]
    exported_names: set[str]


class RepositoryIntelligenceService:
    def __init__(self) -> None:
        self.indexer = RepositoryIndexer()
        self.git = GitClient(timeout_seconds=15)
        self._active_scans: dict[str, threading.Event] = {}
        self._scan_lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        self._initialize(connection)
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS repository_scans (
                full_name TEXT PRIMARY KEY,
                local_path TEXT,
                status TEXT NOT NULL,
                scan_started_at TEXT,
                scan_completed_at TEXT,
                updated_at TEXT NOT NULL,
                error TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}'
            )
            """)
        connection.commit()

    def _set_cancel_event(
        self,
        full_name: str,
        *,
        create: bool = False,
    ) -> threading.Event | None:
        with self._scan_lock:
            if create:
                event = threading.Event()
                self._active_scans[full_name] = event
                return event
            return self._active_scans.get(full_name)

    def _clear_cancel_event(self, full_name: str) -> None:
        with self._scan_lock:
            self._active_scans.pop(full_name, None)

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    def count_connected_repositories(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM sqlite_master WHERE type='table' AND name='connected_repositories'"
            ).fetchone()
            if not row or not row["count"]:
                return 0
            result = connection.execute(
                "SELECT COUNT(*) AS count FROM connected_repositories"
            ).fetchone()
            return int(result["count"])

    def get_scan(self, full_name: str) -> RepositoryScanRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM repository_scans WHERE full_name = ?",
                (full_name,),
            ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def render_repository_context(self, full_name: str) -> str | None:
        record = self.get_scan(full_name)
        if record is None or record.payload is None or record.status != "ready":
            return None
        summary = record.payload.summary
        architecture = ", ".join(summary.architecture[:6]) or "unknown architecture"
        entry_points = ", ".join(summary.key_entry_points[:6]) or "none detected"
        major_modules = (
            ", ".join(module.name for module in summary.major_modules[:6])
            or "none detected"
        )
        frameworks = ", ".join(summary.frameworks) or "none detected"
        languages = ", ".join(summary.languages) or "none detected"
        return "\n".join(
            [
                f"Repository: {full_name}",
                f"Purpose: {summary.project_purpose}",
                f"Languages: {languages}",
                f"Frameworks: {frameworks}",
                f"Architecture: {architecture}",
                f"Major modules: {major_modules}",
                f"Key entry points: {entry_points}",
            ]
        )

    def mark_scanning(self, full_name: str, local_path: str) -> None:
        now = self.now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repository_scans (
                    full_name, local_path, status, scan_started_at, scan_completed_at,
                    updated_at, error, payload_json
                ) VALUES (?, ?, 'scanning', ?, NULL, ?, NULL, '{}')
                ON CONFLICT(full_name) DO UPDATE SET
                    local_path=excluded.local_path,
                    status='scanning',
                    scan_started_at=excluded.scan_started_at,
                    scan_completed_at=NULL,
                    updated_at=excluded.updated_at,
                    error=NULL,
                    payload_json='{}'
                """,
                (full_name, local_path, now, now),
            )
            connection.commit()

    def save_scan(
        self, full_name: str, payload: RepositoryIntelligencePayload
    ) -> RepositoryScanRecord:
        now = self.now()
        data = payload.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repository_scans (
                    full_name, local_path, status, scan_started_at, scan_completed_at,
                    updated_at, error, payload_json
                ) VALUES (?, ?, 'ready', ?, ?, ?, NULL, ?)
                ON CONFLICT(full_name) DO UPDATE SET
                    local_path=excluded.local_path,
                    status='ready',
                    scan_completed_at=excluded.scan_completed_at,
                    updated_at=excluded.updated_at,
                    error=NULL,
                    payload_json=excluded.payload_json
                """,
                (
                    full_name,
                    payload.local_path,
                    now,
                    now,
                    now,
                    json.dumps(data, sort_keys=True),
                ),
            )
            connection.commit()
        return self.get_scan(full_name) or RepositoryScanRecord(
            repository=full_name,
            local_path=payload.local_path,
            status="ready",
            updated_at=now,
            scan_completed_at=now,
            payload=payload,
        )

    def save_failure(
        self, full_name: str, local_path: str, error: str
    ) -> RepositoryScanRecord:
        now = self.now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repository_scans (
                    full_name, local_path, status, scan_started_at, scan_completed_at,
                    updated_at, error, payload_json
                ) VALUES (?, ?, 'error', ?, NULL, ?, ?, '{}')
                ON CONFLICT(full_name) DO UPDATE SET
                    local_path=excluded.local_path,
                    status='error',
                    updated_at=excluded.updated_at,
                    error=excluded.error
                """,
                (full_name, local_path, now, now, error),
            )
            connection.commit()
        return self.get_scan(full_name) or RepositoryScanRecord(
            repository=full_name,
            local_path=local_path,
            status="error",
            updated_at=now,
            error=error,
        )

    def save_cancelled(self, full_name: str, local_path: str) -> RepositoryScanRecord:
        now = self.now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repository_scans (
                    full_name, local_path, status, scan_started_at, scan_completed_at,
                    updated_at, error, payload_json
                ) VALUES (?, ?, 'cancelled', ?, NULL, ?, NULL, '{}')
                ON CONFLICT(full_name) DO UPDATE SET
                    local_path=excluded.local_path,
                    status='cancelled',
                    updated_at=excluded.updated_at,
                    error=NULL
                """,
                (full_name, local_path, now, now),
            )
            connection.commit()
        return self.get_scan(full_name) or RepositoryScanRecord(
            repository=full_name,
            local_path=local_path,
            status="cancelled",
            updated_at=now,
        )

    def start_indexing(self, full_name: str, local_path: str) -> RepositoryScanRecord:
        root = self.validate_local_path(local_path)
        cancel_event = self._set_cancel_event(full_name, create=True)
        assert cancel_event is not None
        self.mark_scanning(full_name, str(root))

        def worker() -> None:
            try:
                self.scan_repository(full_name, str(root), cancel_event=cancel_event)
            finally:
                self._clear_cancel_event(full_name)

        thread = threading.Thread(
            target=worker,
            name=f"repository-index-{full_name.replace('/', '-')}",
            daemon=True,
        )
        thread.start()
        return self.get_scan(full_name) or RepositoryScanRecord(
            repository=full_name,
            local_path=str(root),
            status="scanning",
            scan_started_at=self.now(),
            updated_at=self.now(),
        )

    def cancel_indexing(self, full_name: str) -> RepositoryScanRecord:
        event = self._set_cancel_event(full_name)
        record = self.get_scan(full_name)
        if event is None or record is None or record.status != "scanning":
            raise ValueError("Repository is not currently indexing.")
        event.set()
        return self.save_cancelled(full_name, record.local_path or "")

    def scan_repository(
        self,
        full_name: str,
        local_path: str,
        *,
        cancel_event: threading.Event | None = None,
    ) -> RepositoryScanRecord:
        root = self.validate_local_path(local_path)
        previous = self.get_scan(full_name)
        self.mark_scanning(full_name, str(root))
        started = time.perf_counter()
        try:
            payload = self._build_payload(
                full_name,
                root,
                previous_payload=(
                    previous.payload if previous and previous.payload else None
                ),
                cancel_event=cancel_event,
            )
            if cancel_event is not None and cancel_event.is_set():
                return self.save_cancelled(full_name, str(root))
            payload.metadata["duration_ms"] = round(
                (time.perf_counter() - started) * 1000,
                3,
            )
            return self.save_scan(full_name, payload)
        except Exception as exc:
            return self.save_failure(full_name, str(root), str(exc))

    def _record_from_row(self, row: sqlite3.Row) -> RepositoryScanRecord:
        payload = json.loads(row["payload_json"] or "{}")
        return RepositoryScanRecord(
            repository=row["full_name"],
            local_path=row["local_path"],
            status=row["status"],
            scan_started_at=row["scan_started_at"],
            scan_completed_at=row["scan_completed_at"],
            updated_at=row["updated_at"],
            error=row["error"],
            payload=(
                RepositoryIntelligencePayload.model_validate(payload)
                if payload and payload != {}
                else None
            ),
        )

    def validate_local_path(self, local_path: str) -> Path:
        if not local_path:
            raise ValueError("A local repository path is required before scanning.")
        raw_path = Path(local_path).expanduser()
        if not raw_path.is_absolute():
            raise ValueError("Repository path must be absolute.")
        if ".." in raw_path.parts:
            raise ValueError("Repository path must not contain parent traversal.")
        candidate = raw_path.resolve()
        if not candidate.exists() or not candidate.is_dir():
            raise ValueError("Repository path does not exist.")

        settings = get_repository_settings()
        roots = [Path.cwd().resolve(), settings.workspace_root.resolve()]
        configured = os.getenv("ODIN_REPOSITORY_SCAN_ROOTS", "").strip()
        if configured:
            roots.extend(
                Path(value).expanduser().resolve()
                for value in configured.split(os.pathsep)
                if value.strip()
            )
        for root in roots:
            if not self._is_relative_to(candidate, root):
                continue
            relative = candidate.relative_to(root).as_posix()
            sanitized = safe_child(root, relative)
            if sanitized == candidate:
                return sanitized
        raise ValueError("Repository path is outside the allowed scan roots.")

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def is_stale(self, full_name: str) -> bool:
        record = self.get_scan(full_name)
        if record is None or record.payload is None or record.status != "ready":
            return True
        current_revision = self._head_revision(Path(record.payload.local_path))
        indexed_revision = record.payload.indexed_revision
        return bool(
            current_revision
            and indexed_revision
            and current_revision != indexed_revision
        )

    def list_documentation(
        self,
        full_name: str,
        *,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        record = self.get_scan(full_name)
        if record is None or record.payload is None or record.status != "ready":
            return []
        needle = query.lower() if query else None
        matches = []
        for item in record.payload.documentation:
            haystacks = (
                item.path.lower(),
                item.title.lower(),
                item.excerpt.lower(),
                (item.symbol or "").lower(),
            )
            if needle and not any(needle in haystack for haystack in haystacks):
                continue
            matches.append(item.model_dump(mode="json"))
            if len(matches) >= limit:
                break
        return matches

    def read_file(
        self, full_name: str, path: str, *, max_chars: int = 6000
    ) -> dict[str, Any]:
        record = self.get_scan(full_name)
        if record is None or record.payload is None or record.status != "ready":
            raise ValueError(
                "Repository file content is not available. Scan the repository first."
            )
        root = Path(record.payload.local_path)
        safe_path = safe_child(root, path)
        text = safe_path.read_text(encoding="utf-8", errors="replace")
        return {
            "repository": full_name,
            "path": path,
            "content": text[:max_chars],
            "truncated": len(text) > max_chars,
            "indexed_revision": record.payload.indexed_revision,
        }

    def find_symbol_references(
        self,
        full_name: str,
        symbol: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        record = self.get_scan(full_name)
        if record is None or record.payload is None or record.status != "ready":
            return []
        query = symbol.lower().strip()
        matches = [
            reference.model_dump(mode="json")
            for reference in record.payload.references
            if query in reference.symbol.lower()
        ]
        return matches[:limit]

    def dependency_impact(self, full_name: str, path: str) -> dict[str, Any]:
        record = self.get_scan(full_name)
        if record is None or record.payload is None or record.status != "ready":
            return {"path": path, "dependencies": [], "dependents": [], "tests": []}
        dependencies = sorted(
            {
                edge.target
                for edge in record.payload.dependency_graph.edges
                if edge.source == path and edge.target
            }
        )
        dependents = sorted(
            {
                edge.source
                for edge in record.payload.dependency_graph.edges
                if edge.target == path
            }
        )
        tests = sorted(
            entry.path
            for entry in record.payload.inventory
            if entry.kind == "test"
            and (
                path in entry.path
                or any(Path(path).stem in candidate for candidate in (entry.path,))
            )
        )
        return {
            "path": path,
            "dependencies": dependencies,
            "dependents": dependents,
            "tests": tests[:20],
        }

    async def search_repository(
        self,
        full_name: str,
        query: str,
        *,
        limit: int = 20,
        language: str | None = None,
        file_type: str | None = None,
        symbol_type: str | None = None,
        include_documentation: bool | None = None,
    ) -> dict[str, Any]:
        record = self.get_scan(full_name)
        if record is None or record.payload is None or record.status != "ready":
            return {"results": [], "count": 0, "stale": True}
        payload = record.payload
        root = Path(payload.local_path)
        needle = query.strip().lower()
        inventory_by_path = {entry.path: entry for entry in payload.inventory}
        results: list[dict[str, Any]] = []

        def include_path(path: str) -> bool:
            entry = inventory_by_path.get(path)
            if entry is None:
                return False
            if language and (entry.language or "").lower() != language.lower():
                return False
            if file_type and entry.kind != file_type:
                return False
            if include_documentation is True and entry.kind != "documentation":
                return False
            if include_documentation is False and entry.kind == "documentation":
                return False
            return True

        def add_result(
            *,
            file_path: str,
            match_type: str,
            score: float,
            excerpt: str,
            symbol: str | None = None,
            line: int | None = None,
        ) -> None:
            if not include_path(file_path):
                return
            entry = inventory_by_path[file_path]
            if symbol_type and match_type == "symbol":
                matched_symbol = next(
                    (
                        item
                        for item in payload.symbols
                        if item.file_path == file_path and item.qualified_name == symbol
                    ),
                    None,
                )
                if matched_symbol is None or matched_symbol.kind != symbol_type:
                    return
            results.append(
                {
                    "repository": full_name,
                    "file_path": file_path,
                    "symbol": symbol,
                    "source_location": {"line": line} if line else None,
                    "relevance_score": round(score, 3),
                    "match_type": match_type,
                    "excerpt": excerpt[:800],
                    "indexed_revision": payload.indexed_revision,
                    "language": entry.language,
                    "file_type": entry.kind,
                }
            )

        for entry in payload.inventory:
            lower_path = entry.path.lower()
            if lower_path == needle:
                add_result(
                    file_path=entry.path,
                    match_type="exact_file",
                    score=120,
                    excerpt=entry.path,
                )
            elif needle and needle in lower_path:
                add_result(
                    file_path=entry.path,
                    match_type="path",
                    score=88,
                    excerpt=entry.path,
                )

        for symbol in payload.symbols:
            haystacks = [
                symbol.name.lower(),
                symbol.qualified_name.lower(),
                symbol.file_path.lower(),
            ]
            if any(needle == haystack for haystack in haystacks[:2]):
                add_result(
                    file_path=symbol.file_path,
                    match_type="symbol",
                    score=110,
                    excerpt=f"{symbol.kind} {symbol.qualified_name}",
                    symbol=symbol.qualified_name,
                    line=symbol.line,
                )
            elif needle and any(needle in haystack for haystack in haystacks):
                add_result(
                    file_path=symbol.file_path,
                    match_type="symbol",
                    score=84,
                    excerpt=f"{symbol.kind} {symbol.qualified_name}",
                    symbol=symbol.qualified_name,
                    line=symbol.line,
                )

        for document in payload.documentation:
            if (
                not needle
                or needle in document.title.lower()
                or needle in document.excerpt.lower()
                or needle in document.path.lower()
            ):
                add_result(
                    file_path=document.path,
                    match_type="documentation",
                    score=76,
                    excerpt=document.excerpt,
                    symbol=document.symbol,
                    line=document.line,
                )

        for hit in self.indexer.search_content(
            root, query, max_results=max(limit * 2, 20)
        ):
            add_result(
                file_path=hit["path"],
                match_type="lexical",
                score=64,
                excerpt=hit["text"],
                line=hit["line"],
            )

        results = await self._semantic_rank(query, results)
        deduped: dict[tuple[str, str, str | None, int | None], dict[str, Any]] = {}
        for item in sorted(
            results,
            key=lambda current: (-current["relevance_score"], current["file_path"]),
        ):
            key = (
                item["file_path"],
                item["match_type"],
                item.get("symbol"),
                (
                    item["source_location"]["line"]
                    if item.get("source_location")
                    else None
                ),
            )
            deduped.setdefault(key, item)
        ordered = list(deduped.values())[:limit]
        return {
            "results": ordered,
            "count": len(ordered),
            "stale": self.is_stale(full_name),
            "indexed_revision": payload.indexed_revision,
        }

    async def _semantic_rank(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(results) > 24:
            results = results[:24]
        try:
            response = await get_llm_service().embeddings(
                EmbeddingRequest(
                    input=[
                        query,
                        *[
                            " | ".join(
                                str(value)
                                for value in (
                                    item.get("file_path"),
                                    item.get("symbol"),
                                    item.get("excerpt"),
                                    item.get("match_type"),
                                )
                                if value
                            )
                            for item in results
                        ],
                    ],
                    integration_point="repository_context",
                )
            )
        except (ProviderConfigurationError, AllProvidersFailedError):
            return results
        vectors = response.embeddings
        if len(vectors) != len(results) + 1:
            return results
        query_vector = vectors[0]
        for item, vector in zip(results, vectors[1:], strict=True):
            item["relevance_score"] = round(
                float(item["relevance_score"])
                + max(0.0, self._cosine_similarity(query_vector, vector)) * 24,
                3,
            )
            item["match_type"] = (
                "semantic"
                if item["match_type"] == "lexical" and item["relevance_score"] > 75
                else item["match_type"]
            )
        return results

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        length = min(len(left), len(right))
        if length == 0:
            return 0.0
        numerator = sum(left[index] * right[index] for index in range(length))
        left_norm = (
            sqrt(sum(left[index] * left[index] for index in range(length))) or 1.0
        )
        right_norm = (
            sqrt(sum(right[index] * right[index] for index in range(length))) or 1.0
        )
        return numerator / (left_norm * right_norm)

    def _build_payload(
        self,
        full_name: str,
        root: Path,
        *,
        previous_payload: RepositoryIntelligencePayload | None = None,
        cancel_event: threading.Event | None = None,
    ) -> RepositoryIntelligencePayload:
        entries = self.indexer.build(root)
        inventory = [
            InventoryEntry(
                path=entry.path,
                size=entry.size,
                kind=entry.kind.value,
                language=entry.language,
                binary=entry.binary,
                modified_ns=entry.modified_ns,
                sha256=entry.sha256,
            )
            for entry in entries
        ]
        inventory_paths = {entry.path for entry in inventory}
        module_map = self._build_python_module_map(inventory)
        symbols: list[SymbolRecord] = []
        references: list[SymbolReferenceRecord] = []
        documentation: list[DocumentationRecord] = []
        edges: list[DependencyEdge] = []
        architecture_matches: dict[str, set[str]] = defaultdict(set)
        metadata = self._build_metadata(root, entries)
        revision = self._head_revision(root)
        current_entries = {entry.path: entry for entry in inventory}
        previous_entries = {
            entry.path: entry
            for entry in (previous_payload.inventory if previous_payload else [])
        }
        changed_files = sorted(
            path
            for path, entry in current_entries.items()
            if path not in previous_entries
            or previous_entries[path].sha256 != entry.sha256
        )
        deleted_files = sorted(
            path for path in previous_entries if path not in current_entries
        )
        unchanged_files = {
            path
            for path in current_entries
            if path in previous_entries and path not in changed_files
        }

        if previous_payload is not None:
            for symbol in previous_payload.symbols:
                if symbol.file_path in unchanged_files:
                    symbols.append(symbol)
            for reference in previous_payload.references:
                if reference.file_path in unchanged_files:
                    references.append(reference)
            for document in previous_payload.documentation:
                if document.path in unchanged_files:
                    documentation.append(document)
            for edge in previous_payload.dependency_graph.edges:
                if edge.source in unchanged_files:
                    edges.append(edge)
            for category in previous_payload.architecture:
                for path in category.files:
                    if path in unchanged_files:
                        architecture_matches[category.category].add(path)

        for entry in inventory:
            if cancel_event is not None and cancel_event.is_set():
                break
            if entry.path in unchanged_files:
                self._categorize_path(entry.path, architecture_matches)
                continue
            if entry.binary:
                self._categorize_path(entry.path, architecture_matches)
                continue
            path = root / entry.path
            text = path.read_text(encoding="utf-8", errors="replace")
            documentation.extend(self._extract_documentation(entry, text))
            if not self._is_parseable(entry.path):
                self._categorize_path(entry.path, architecture_matches)
                continue
            result = self._analyze_file(entry, text, module_map, inventory_paths)
            symbols.extend(result.symbols)
            references.extend(result.references)
            documentation.extend(result.documentation)
            for category in result.architecture_matches:
                architecture_matches[category].add(entry.path)
            self._categorize_path(entry.path, architecture_matches)
            for item in result.imports:
                target = item.resolved_path or item.module
                edges.append(
                    DependencyEdge(
                        source=entry.path,
                        target=target,
                        external=item.external,
                    )
                )

        tree = self._build_tree(inventory)
        graph = self._build_dependency_graph(inventory, edges)
        architecture = [
            ArchitectureCategory(category=category, files=sorted(files))
            for category, files in sorted(architecture_matches.items())
            if files
        ]
        summary = self._build_summary(
            full_name, root, inventory, architecture, graph, metadata
        )
        return RepositoryIntelligencePayload(
            repository=full_name,
            local_path=str(root),
            indexed_revision=revision,
            inventory=inventory,
            directory_tree=tree,
            symbols=sorted(
                symbols, key=lambda symbol: (symbol.file_path, symbol.line, symbol.name)
            ),
            references=sorted(
                self._dedupe_references(references),
                key=lambda reference: (
                    reference.file_path,
                    reference.line,
                    reference.symbol,
                ),
            ),
            documentation=sorted(
                self._dedupe_documentation(documentation),
                key=lambda item: (item.path, item.line, item.title),
            ),
            architecture=architecture,
            dependency_graph=graph,
            summary=summary,
            metadata={
                **metadata,
                "changed_files": changed_files,
                "deleted_files": deleted_files,
                "symbols_indexed": len(symbols),
                "documents_indexed": len(documentation),
                "references_indexed": len(references),
            },
        )

    @staticmethod
    def _is_parseable(path: str) -> bool:
        suffix = Path(path).suffix.lower()
        return suffix in SOURCE_EXTENSIONS or Path(path).name in {
            "package.json",
            "pyproject.toml",
        }

    @staticmethod
    def _build_python_module_map(inventory: list[InventoryEntry]) -> dict[str, str]:
        module_map: dict[str, str] = {}
        for entry in inventory:
            if Path(entry.path).suffix != ".py":
                continue
            relative = Path(entry.path)
            parts = list(relative.with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            module = ".".join(parts)
            if module:
                module_map[module] = entry.path
        return module_map

    def _analyze_file(
        self,
        entry: InventoryEntry,
        text: str,
        module_map: dict[str, str],
        inventory_paths: set[str],
    ) -> AnalysisResult:
        suffix = Path(entry.path).suffix.lower()
        if suffix == ".py":
            return self._analyze_python(entry, text, module_map)
        if suffix in SCRIPT_EXTENSIONS:
            return self._analyze_script(entry, text, inventory_paths)
        if Path(entry.path).name == "package.json":
            return AnalysisResult(
                symbols=[],
                imports=[],
                references=[],
                documentation=[],
                architecture_matches={"configuration"},
                exported_names=set(),
            )
        return AnalysisResult(
            symbols=[],
            imports=[],
            references=[],
            documentation=[],
            architecture_matches=set(),
            exported_names=set(),
        )

    def _analyze_python(
        self,
        entry: InventoryEntry,
        text: str,
        module_map: dict[str, str],
    ) -> AnalysisResult:
        try:
            tree = ast.parse(text, filename=entry.path)
        except SyntaxError:
            return AnalysisResult(
                symbols=[],
                imports=[],
                references=[],
                documentation=[],
                architecture_matches=set(),
                exported_names=set(),
            )

        symbols: list[SymbolRecord] = []
        imports: list[ImportReference] = []
        references: list[SymbolReferenceRecord] = []
        documentation: list[DocumentationRecord] = []
        architecture_matches: set[str] = set()
        module_name = self._python_module_name(entry.path)

        class Visitor(ast.NodeVisitor):
            def __init__(self, outer: RepositoryIntelligenceService) -> None:
                self.outer = outer
                self.class_stack: list[str] = []

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                bases = [self.outer._python_name(base) for base in node.bases]
                decorators = [
                    self.outer._python_name(item) for item in node.decorator_list
                ]
                kind = (
                    "enum" if any(base.endswith("Enum") for base in bases) else "class"
                )
                qualified_name = (
                    ".".join([*self.class_stack, node.name])
                    if self.class_stack
                    else node.name
                )
                relationships = [
                    SymbolRelationship(type="inherits", target=base)
                    for base in bases
                    if base
                ]
                symbols.append(
                    SymbolRecord(
                        name=node.name,
                        qualified_name=qualified_name,
                        kind=kind,
                        file_path=entry.path,
                        line=node.lineno,
                        language=entry.language,
                        module=module_name,
                        container=self.class_stack[-1] if self.class_stack else None,
                        decorators=decorators,
                        bases=bases,
                        relationships=relationships,
                    )
                )
                docstring = ast.get_docstring(node)
                if docstring:
                    documentation.append(
                        DocumentationRecord(
                            path=entry.path,
                            line=node.lineno,
                            title=qualified_name,
                            kind="docstring",
                            language=entry.language,
                            symbol=qualified_name,
                            excerpt=docstring[:1200],
                            related_paths=[entry.path],
                            related_symbols=[qualified_name],
                        )
                    )
                self.class_stack.append(node.name)
                self.generic_visit(node)
                self.class_stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                decorators = [
                    self.outer._python_name(item) for item in node.decorator_list
                ]
                kind = "method" if self.class_stack else "function"
                qualified_name = (
                    ".".join([*self.class_stack, node.name])
                    if self.class_stack
                    else node.name
                )
                symbols.append(
                    SymbolRecord(
                        name=node.name,
                        qualified_name=qualified_name,
                        kind=kind,
                        file_path=entry.path,
                        line=node.lineno,
                        language=entry.language,
                        module=module_name,
                        container=self.class_stack[-1] if self.class_stack else None,
                        decorators=decorators,
                        relationships=(
                            [
                                SymbolRelationship(
                                    type="member_of", target=self.class_stack[-1]
                                )
                            ]
                            if self.class_stack
                            else []
                        ),
                    )
                )
                if any(
                    decorator.startswith(("router.", "app."))
                    for decorator in decorators
                ):
                    architecture_matches.add("api_routes")
                docstring = ast.get_docstring(node)
                if docstring:
                    documentation.append(
                        DocumentationRecord(
                            path=entry.path,
                            line=node.lineno,
                            title=qualified_name,
                            kind="docstring",
                            language=entry.language,
                            symbol=qualified_name,
                            excerpt=docstring[:1200],
                            related_paths=[entry.path],
                            related_symbols=[qualified_name],
                        )
                    )
                self.generic_visit(node)

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Assign(self, node: ast.Assign) -> None:
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        symbols.append(
                            SymbolRecord(
                                name=target.id,
                                qualified_name=(
                                    f"{self.class_stack[-1]}.{target.id}"
                                    if self.class_stack
                                    else target.id
                                ),
                                kind="constant",
                                file_path=entry.path,
                                line=node.lineno,
                                language=entry.language,
                                module=module_name,
                                container=(
                                    self.class_stack[-1] if self.class_stack else None
                                ),
                                relationships=(
                                    [
                                        SymbolRelationship(
                                            type="member_of",
                                            target=self.class_stack[-1],
                                        )
                                    ]
                                    if self.class_stack
                                    else []
                                ),
                            )
                        )
                self.generic_visit(node)

            def visit_Import(self, node: ast.Import) -> None:
                for alias in node.names:
                    resolved = alias.name if alias.name in module_map else None
                    if resolved is None:
                        resolved = module_map.get(alias.name)
                    imports.append(
                        ImportReference(
                            module=alias.name,
                            line=node.lineno,
                            external=resolved is None,
                            resolved_path=resolved,
                        )
                    )
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                module = self.outer._resolve_python_import(
                    module_name, node.module, node.level, module_map
                )
                imports.append(
                    ImportReference(
                        module=node.module or "",
                        line=node.lineno,
                        external=module is None,
                        resolved_path=module,
                    )
                )
                self.generic_visit(node)

            def visit_Name(self, node: ast.Name) -> None:
                if isinstance(node.ctx, ast.Load):
                    references.append(
                        SymbolReferenceRecord(
                            symbol=node.id,
                            file_path=entry.path,
                            line=node.lineno,
                            kind="name",
                            excerpt=self.outer._line_excerpt(text, node.lineno),
                        )
                    )
                self.generic_visit(node)

        Visitor(self).visit(tree)
        module_docstring = ast.get_docstring(tree)
        if module_docstring:
            documentation.append(
                DocumentationRecord(
                    path=entry.path,
                    line=1,
                    title=module_name or entry.path,
                    kind="module_docstring",
                    language=entry.language,
                    excerpt=module_docstring[:1200],
                    related_paths=[entry.path],
                )
            )

        if FASTAPI_ROUTE_RE.search(text):
            architecture_matches.add("api_routes")
        if "APIRouter" in text:
            architecture_matches.add("controllers")
        if "BaseModel" in text or "dataclass" in text:
            architecture_matches.add("models")
        if "middleware" in entry.path.lower():
            architecture_matches.add("middleware")
        if any(token in entry.path.lower() for token in ("service", "services")):
            architecture_matches.add("services")
        if any(
            token in entry.path.lower()
            for token in ("storage", "database", "repository")
        ):
            architecture_matches.add("database_layer")
        if Path(entry.path).name in {"settings.py", "config.py"}:
            architecture_matches.add("configuration")
        return AnalysisResult(
            symbols=symbols,
            imports=imports,
            references=references,
            documentation=documentation,
            architecture_matches=architecture_matches,
            exported_names=set(),
        )

    def _analyze_script(
        self,
        entry: InventoryEntry,
        text: str,
        inventory_paths: set[str],
    ) -> AnalysisResult:
        symbols: list[SymbolRecord] = []
        imports: list[ImportReference] = []
        references: list[SymbolReferenceRecord] = []
        documentation: list[DocumentationRecord] = self._extract_script_symbol_docs(
            entry, text
        )
        architecture_matches: set[str] = set()
        exported_names: set[str] = set()
        module_name = entry.path.replace("/", ":")

        for match in IMPORT_RE.finditer(text):
            module = match.group("module")
            resolved = self._resolve_script_import(entry.path, module, inventory_paths)
            imports.append(
                ImportReference(
                    module=module,
                    line=self._line_number(text, match.start()),
                    external=resolved is None,
                    resolved_path=resolved,
                )
            )
            references.append(
                SymbolReferenceRecord(
                    symbol=Path(module).name or module,
                    file_path=entry.path,
                    line=self._line_number(text, match.start()),
                    kind="import",
                    excerpt=self._line_excerpt(
                        text, self._line_number(text, match.start())
                    ),
                )
            )
        for match in BARE_IMPORT_RE.finditer(text):
            module = match.group("module")
            resolved = self._resolve_script_import(entry.path, module, inventory_paths)
            imports.append(
                ImportReference(
                    module=module,
                    line=self._line_number(text, match.start()),
                    external=resolved is None,
                    resolved_path=resolved,
                )
            )
            references.append(
                SymbolReferenceRecord(
                    symbol=Path(module).name or module,
                    file_path=entry.path,
                    line=self._line_number(text, match.start()),
                    kind="import",
                    excerpt=self._line_excerpt(
                        text, self._line_number(text, match.start())
                    ),
                )
            )
        for match in EXPORT_FROM_RE.finditer(text):
            module = match.group("module")
            resolved = self._resolve_script_import(entry.path, module, inventory_paths)
            imports.append(
                ImportReference(
                    module=module,
                    line=self._line_number(text, match.start()),
                    external=resolved is None,
                    resolved_path=resolved,
                )
            )
            references.append(
                SymbolReferenceRecord(
                    symbol=Path(module).name or module,
                    file_path=entry.path,
                    line=self._line_number(text, match.start()),
                    kind="export_from",
                    excerpt=self._line_excerpt(
                        text, self._line_number(text, match.start())
                    ),
                )
            )

        class_blocks = self._class_blocks(text)
        for match in CLASS_RE.finditer(text):
            name = match.group("name")
            line = self._line_number(text, match.start())
            exported = self._is_exported_line(text, match.start())
            if exported:
                exported_names.add(name)
            symbols.append(
                SymbolRecord(
                    name=name,
                    qualified_name=name,
                    kind="class",
                    file_path=entry.path,
                    line=line,
                    language=entry.language,
                    module=module_name,
                    exported=exported,
                )
            )
            block = class_blocks.get(name)
            if block is not None:
                offset, source = block
                for method_match in METHOD_RE.finditer(source):
                    method_name = method_match.group("name")
                    if method_name == "constructor":
                        continue
                    symbols.append(
                        SymbolRecord(
                            name=method_name,
                            qualified_name=f"{name}.{method_name}",
                            kind="method",
                            file_path=entry.path,
                            line=self._line_number(text, offset + method_match.start()),
                            language=entry.language,
                            module=module_name,
                            container=name,
                            relationships=[
                                SymbolRelationship(type="member_of", target=name)
                            ],
                        )
                    )

        for pattern, kind in SCRIPT_SYMBOL_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group("name")
                if kind == "constant" and not name.isupper():
                    continue
                exported = self._is_exported_line(text, match.start())
                if exported:
                    exported_names.add(name)
                symbols.append(
                    SymbolRecord(
                        name=name,
                        qualified_name=name,
                        kind=kind,
                        file_path=entry.path,
                        line=self._line_number(text, match.start()),
                        language=entry.language,
                        module=module_name,
                        exported=exported,
                    )
                )

        lower_path = entry.path.lower()
        if Path(entry.path).name == "route.ts":
            architecture_matches.add("api_routes")
        if Path(entry.path).name == "middleware.ts" or "middleware" in lower_path:
            architecture_matches.add("middleware")
        if (
            "/components/" in f"/{lower_path}"
            or Path(entry.path).suffix.lower() == ".tsx"
        ):
            architecture_matches.add("components")
        if "/services/" in f"/{lower_path}" or lower_path.endswith("service.ts"):
            architecture_matches.add("services")
        if "/models/" in f"/{lower_path}" or lower_path.endswith("model.ts"):
            architecture_matches.add("models")
        if any(
            name in lower_path for name in ("config", "next.config", "eslint.config")
        ):
            architecture_matches.add("configuration")
        if ROUTE_HINT_RE.search(text):
            architecture_matches.add("api_routes")
        references.extend(self._script_symbol_references(entry, text, symbols))
        return AnalysisResult(
            symbols=symbols,
            imports=imports,
            references=references,
            documentation=documentation,
            architecture_matches=architecture_matches,
            exported_names=exported_names,
        )

    @staticmethod
    def _python_module_name(path: str) -> str:
        relative = Path(path)
        parts = list(relative.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    @staticmethod
    def _python_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = RepositoryIntelligenceService._python_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        if isinstance(node, ast.Call):
            return RepositoryIntelligenceService._python_name(node.func)
        if isinstance(node, ast.Subscript):
            return RepositoryIntelligenceService._python_name(node.value)
        return ""

    @staticmethod
    def _resolve_python_import(
        current_module: str,
        module: str | None,
        level: int,
        module_map: dict[str, str],
    ) -> str | None:
        base_parts = current_module.split(".") if current_module else []
        if level:
            if len(base_parts) >= level:
                base_parts = base_parts[:-level]
            else:
                base_parts = []
        if module:
            candidate = ".".join([*base_parts, module]) if base_parts else module
        else:
            candidate = ".".join(base_parts)
        return module_map.get(candidate)

    @staticmethod
    def _resolve_script_import(
        source_path: str,
        target: str,
        inventory_paths: set[str],
    ) -> str | None:
        if not target.startswith((".", "/")):
            return None
        source = Path(source_path)
        base = (
            source.parent / target
            if target.startswith(".")
            else Path(target.lstrip("/"))
        )
        candidates = [base]
        for suffix in LOCAL_SCRIPT_EXTENSIONS:
            candidates.append(base.with_suffix(suffix))
            candidates.append(base / f"index{suffix}")
        for candidate in candidates:
            resolved = candidate.as_posix().lstrip("./")
            if resolved in inventory_paths:
                return resolved
        return None

    @staticmethod
    def _line_number(text: str, index: int) -> int:
        return text.count("\n", 0, index) + 1

    @staticmethod
    def _is_exported_line(text: str, index: int) -> bool:
        line_start = text.rfind("\n", 0, index) + 1
        line_end = text.find("\n", index)
        if line_end == -1:
            line_end = len(text)
        return text[line_start:line_end].lstrip().startswith("export")

    @staticmethod
    def _extract_brace_block(text: str, start: int) -> tuple[int, str] | None:
        brace_start = text.find("{", start)
        if brace_start == -1:
            return None
        depth = 0
        for index in range(brace_start, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return brace_start + 1, text[brace_start + 1 : index]
        return None

    def _class_blocks(self, text: str) -> dict[str, tuple[int, str]]:
        blocks: dict[str, tuple[int, str]] = {}
        for match in CLASS_RE.finditer(text):
            block = self._extract_brace_block(text, match.end())
            if block is not None:
                blocks[match.group("name")] = block
        return blocks

    @staticmethod
    def _line_excerpt(text: str, line_number: int) -> str:
        lines = text.splitlines()
        if line_number <= 0 or line_number > len(lines):
            return ""
        return lines[line_number - 1].strip()[:400]

    def _extract_documentation(
        self,
        entry: InventoryEntry,
        text: str,
    ) -> list[DocumentationRecord]:
        suffix = Path(entry.path).suffix.lower()
        if suffix not in {".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json"}:
            return []
        title = Path(entry.path).name
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip() or title
                break
            if stripped.startswith("[") and stripped.endswith("]"):
                title = stripped.strip("[]") or title
                break
        return [
            DocumentationRecord(
                path=entry.path,
                line=1,
                title=title[:200],
                kind="documentation",
                language=entry.language,
                excerpt=text[:1600],
                related_paths=[entry.path],
            )
        ]

    def _extract_script_symbol_docs(
        self,
        entry: InventoryEntry,
        text: str,
    ) -> list[DocumentationRecord]:
        docs: list[DocumentationRecord] = []
        block_pattern = re.compile(r"/\*\*(?P<body>.*?)\*/", re.DOTALL)
        for match in block_pattern.finditer(text):
            body = re.sub(
                r"^\s*\*\s?", "", match.group("body"), flags=re.MULTILINE
            ).strip()
            if not body:
                continue
            docs.append(
                DocumentationRecord(
                    path=entry.path,
                    line=self._line_number(text, match.start()),
                    title=Path(entry.path).name,
                    kind="comment",
                    language=entry.language,
                    excerpt=body[:1200],
                    related_paths=[entry.path],
                )
            )
            if len(docs) >= 5:
                break
        return docs

    def _script_symbol_references(
        self,
        entry: InventoryEntry,
        text: str,
        symbols: list[SymbolRecord],
    ) -> list[SymbolReferenceRecord]:
        references: list[SymbolReferenceRecord] = []
        seen: set[tuple[str, int]] = set()
        for symbol in symbols:
            pattern = re.compile(rf"\b{re.escape(symbol.name)}\b")
            for match in pattern.finditer(text):
                line = self._line_number(text, match.start())
                key = (symbol.name, line)
                if key in seen or line == symbol.line:
                    continue
                seen.add(key)
                references.append(
                    SymbolReferenceRecord(
                        symbol=symbol.name,
                        file_path=entry.path,
                        line=line,
                        kind="name",
                        excerpt=self._line_excerpt(text, line),
                    )
                )
        return references

    @staticmethod
    def _dedupe_references(
        references: list[SymbolReferenceRecord],
    ) -> list[SymbolReferenceRecord]:
        seen: set[tuple[str, str, int, str]] = set()
        deduped: list[SymbolReferenceRecord] = []
        for reference in references:
            key = (
                reference.symbol,
                reference.file_path,
                reference.line,
                reference.kind,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(reference)
        return deduped

    @staticmethod
    def _dedupe_documentation(
        documentation: list[DocumentationRecord],
    ) -> list[DocumentationRecord]:
        seen: set[tuple[str, int, str, str | None]] = set()
        deduped: list[DocumentationRecord] = []
        for item in documentation:
            key = (item.path, item.line, item.title, item.symbol)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _head_revision(self, root: Path) -> str | None:
        try:
            if not self.git.is_repository(root):
                return None
            return self.git.head_sha(root)
        except Exception:
            return None

    @staticmethod
    def _build_tree(inventory: list[InventoryEntry]) -> FileNode:
        root = FileNode(name="/", path="", type="directory", children=[])
        directories: dict[str, FileNode] = {"": root}

        for entry in sorted(inventory, key=lambda item: item.path):
            parts = Path(entry.path).parts
            current_path = ""
            parent = root
            for directory in parts[:-1]:
                current_path = f"{current_path}/{directory}".strip("/")
                if current_path not in directories:
                    node = FileNode(
                        name=directory, path=current_path, type="directory", children=[]
                    )
                    parent.children.append(node)
                    directories[current_path] = node
                parent = directories[current_path]
            parent.children.append(
                FileNode(name=parts[-1], path=entry.path, type="file", children=[])
            )

        return root

    def _build_dependency_graph(
        self,
        inventory: list[InventoryEntry],
        edges: list[DependencyEdge],
    ) -> DependencyGraphRecord:
        nodes = [
            DependencyNode(id=entry.path, label=entry.path)
            for entry in inventory
            if self._is_parseable(entry.path)
        ]
        seen_edges: set[tuple[str, str, bool]] = set()
        deduped_edges: list[DependencyEdge] = []
        for edge in edges:
            key = (edge.source, edge.target, edge.external)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            deduped_edges.append(edge)
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in deduped_edges:
            if not edge.external and edge.target:
                adjacency[edge.source].append(edge.target)
        cycles = self._strongly_connected_components(adjacency)
        return DependencyGraphRecord(
            nodes=nodes,
            edges=deduped_edges,
            circular_dependencies=cycles,
            entry_points=self._entry_points(inventory),
        )

    def _build_metadata(self, root: Path, entries: list[Any]) -> dict[str, Any]:
        manifest = self.indexer.manifest(root.name, root, entries).model_dump(
            mode="json"
        )
        return {
            "scanned_at": self.now(),
            "root_name": root.name,
            "file_count": len(entries),
            "files_indexed": manifest["files_indexed"],
            "total_bytes": manifest["total_bytes"],
            "detected_languages": manifest["languages"],
            "detected_frameworks": manifest["frameworks"],
        }

    def _build_summary(
        self,
        full_name: str,
        root: Path,
        inventory: list[InventoryEntry],
        architecture: list[ArchitectureCategory],
        graph: DependencyGraphRecord,
        metadata: dict[str, Any],
    ) -> RepositorySummaryRecord:
        purpose = self._project_purpose(root, full_name)
        language_counts = Counter(
            entry.language for entry in inventory if entry.language
        )
        languages = [name for name, _ in language_counts.most_common()]
        frameworks = self._normalize_framework_names(
            metadata.get("detected_frameworks")
            or self._frameworks_from_files(root, inventory)
        )
        package_manager = sorted(set(self._package_managers(inventory, root)))
        build_system = sorted(set(self._build_systems(inventory, root)))
        test_framework = sorted(set(self._test_frameworks(inventory, root)))
        module_counts = Counter(
            Path(entry.path).parts[0] if Path(entry.path).parts else entry.path
            for entry in inventory
        )
        major_modules = [
            MajorModule(name=name, file_count=count)
            for name, count in module_counts.most_common(8)
            if name
        ]
        architecture_names = [item.category for item in architecture]
        return RepositorySummaryRecord(
            project_purpose=purpose,
            languages=languages,
            frameworks=frameworks,
            architecture=architecture_names,
            major_modules=major_modules,
            key_entry_points=graph.entry_points,
            test_framework=test_framework,
            build_system=build_system,
            package_manager=package_manager,
        )

    @staticmethod
    def _frameworks_from_files(root: Path, inventory: list[InventoryEntry]) -> set[str]:
        frameworks: set[str] = set()
        paths = {entry.path for entry in inventory}
        if "backend/pyproject.toml" in paths or "pyproject.toml" in paths:
            for file_name in ("backend/pyproject.toml", "pyproject.toml"):
                path = root / file_name
                if path.exists():
                    text = path.read_text(encoding="utf-8", errors="ignore").lower()
                    for value, label in (
                        ("fastapi", "FastAPI"),
                        ("django", "Django"),
                        ("flask", "Flask"),
                        ("pydantic", "Pydantic"),
                    ):
                        if value in text:
                            frameworks.add(label)
        for file_name in ("frontend/package.json", "package.json"):
            path = root / file_name
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            dependencies = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {}),
            }
            for value, label in (
                ("next", "Next.js"),
                ("react", "React"),
                ("vue", "Vue"),
                ("svelte", "Svelte"),
                ("express", "Express"),
                ("vitest", "Vitest"),
            ):
                if value in dependencies:
                    frameworks.add(label)
        return frameworks

    @staticmethod
    def _normalize_framework_names(values: list[str] | set[str]) -> list[str]:
        canonical = {
            "fastapi": "FastAPI",
            "next.js": "Next.js",
            "react": "React",
            "vue": "Vue",
            "svelte": "Svelte",
            "express": "Express",
            "vitest": "Vitest",
            "pydantic": "Pydantic",
            "django": "Django",
            "flask": "Flask",
        }
        return sorted({canonical.get(value.lower(), value) for value in values})

    @staticmethod
    def _package_managers(inventory: list[InventoryEntry], root: Path) -> list[str]:
        paths = {entry.path for entry in inventory}
        managers: list[str] = []
        if any(name in paths for name in ("package.json", "frontend/package.json")):
            managers.append("npm")
        if any(
            name in paths
            for name in (
                "pyproject.toml",
                "backend/pyproject.toml",
                "requirements.txt",
                "backend/requirements.txt",
                "uv.lock",
                "backend/uv.lock",
            )
        ):
            managers.append("Python")
        if (root / "frontend/package-lock.json").exists() or (
            root / "package-lock.json"
        ).exists():
            managers.append("npm")
        return managers

    @staticmethod
    def _build_systems(inventory: list[InventoryEntry], root: Path) -> list[str]:
        paths = {entry.path for entry in inventory}
        systems: list[str] = []
        if any(name in paths for name in ("Makefile", "backend/Makefile")):
            systems.append("Make")
        if any(name in paths for name in ("package.json", "frontend/package.json")):
            systems.append("Next.js")
        if any(name in paths for name in ("pyproject.toml", "backend/pyproject.toml")):
            systems.append("PyProject")
        if (root / "Dockerfile").exists() or (root / "frontend/Dockerfile").exists():
            systems.append("Docker")
        return systems

    @staticmethod
    def _test_frameworks(inventory: list[InventoryEntry], root: Path) -> list[str]:
        frameworks: list[str] = []
        paths = {entry.path for entry in inventory}
        if any(name in paths for name in ("backend/pyproject.toml", "pyproject.toml")):
            for file_name in ("backend/pyproject.toml", "pyproject.toml"):
                path = root / file_name
                if (
                    path.exists()
                    and "pytest"
                    in path.read_text(encoding="utf-8", errors="ignore").lower()
                ):
                    frameworks.append("pytest")
                    break
        for file_name in ("frontend/package.json", "package.json"):
            path = root / file_name
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            scripts = data.get("scripts", {})
            if "test" in scripts:
                frameworks.append(
                    "Vitest" if "vitest" in scripts["test"] else "npm test"
                )
        return frameworks

    @staticmethod
    def _project_purpose(root: Path, full_name: str) -> str:
        for file_name in ("README.md", "README.rst", "README.txt"):
            path = root / file_name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                cleaned = stripped.lstrip("#").strip()
                if cleaned and cleaned.lower() != root.name.lower():
                    return cleaned[:240]
        return f"Repository intelligence snapshot for {full_name}."

    @staticmethod
    def _entry_points(inventory: list[InventoryEntry]) -> list[str]:
        candidates: list[str] = []
        for entry in inventory:
            path = entry.path
            name = Path(path).name
            if name in ENTRYPOINT_NAMES or name.endswith(CONFIG_SUFFIXES):
                candidates.append(path)
            elif "/app/" in f"/{path}" and name in {
                "page.tsx",
                "layout.tsx",
                "route.ts",
            }:
                candidates.append(path)
        return sorted(dict.fromkeys(candidates))[:20]

    @staticmethod
    def _categorize_path(path: str, categories: dict[str, set[str]]) -> None:
        lower_path = path.lower()
        name = Path(path).name.lower()
        if name == "middleware.ts" or "middleware" in lower_path:
            categories["middleware"].add(path)
        if any(
            token in lower_path
            for token in ("/service", "/services/", "service.py", "service.ts")
        ):
            categories["services"].add(path)
        if any(
            token in lower_path for token in ("/controller", "/controllers/", "api/")
        ):
            categories["controllers"].add(path)
        if any(token in lower_path for token in ("/model", "/models/", "models.py")):
            categories["models"].add(path)
        if "/components/" in f"/{lower_path}" or name.endswith(".tsx"):
            categories["components"].add(path)
        if any(
            token in lower_path
            for token in ("storage/", "database/", "sqlite", "repository/")
        ):
            categories["database_layer"].add(path)
        if name.startswith(".env") or ENV_FILE_RE.search(path):
            categories["environment_files"].add(path)
        if (
            name in {"package.json", "pyproject.toml", "makefile", "dockerfile"}
            or name.endswith(CONFIG_SUFFIXES)
            or "config" in name
        ):
            categories["configuration"].add(path)
        if name == "route.ts" or name == "main.py":
            categories["api_routes"].add(path)

    @staticmethod
    def _strongly_connected_components(
        adjacency: dict[str, list[str]],
    ) -> list[list[str]]:
        index = 0
        stack: list[str] = []
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        on_stack: set[str] = set()
        components: list[list[str]] = []

        def visit(node: str) -> None:
            nonlocal index
            indices[node] = index
            lowlinks[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in adjacency.get(node, []):
                if neighbor not in indices:
                    visit(neighbor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[neighbor])

            if lowlinks[node] == indices[node]:
                component: list[str] = []
                while stack:
                    member = stack.pop()
                    on_stack.remove(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    components.append(sorted(component))

        for node in sorted(adjacency):
            if node not in indices:
                visit(node)
        return sorted(components)


repository_intelligence_service = RepositoryIntelligenceService()
