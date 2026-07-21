from __future__ import annotations

import ast
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.repositories.config import get_repository_settings
from app.repositories.indexer import RepositoryIndexer

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
CLASS_RE = re.compile(r"^\s*(?:export\s+default\s+|export\s+)?class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
INTERFACE_RE = re.compile(r"^\s*export\s+interface\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
ENUM_RE = re.compile(r"^\s*(?:export\s+)?enum\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
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
ROUTE_HINT_RE = re.compile(r"(?:router|app)\.(?:get|post|put|patch|delete|options|head)\s*\(")
FASTAPI_ROUTE_RE = re.compile(r"@(?:router|app)\.(?:get|post|put|patch|delete|options|head)\s*\(")
ENV_FILE_RE = re.compile(r"(?:^|/)\.env(?:\..+)?$")


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
    inventory: list[InventoryEntry] = Field(default_factory=list)
    directory_tree: FileNode
    symbols: list[SymbolRecord] = Field(default_factory=list)
    architecture: list[ArchitectureCategory] = Field(default_factory=list)
    dependency_graph: DependencyGraphRecord = Field(default_factory=DependencyGraphRecord)
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
    architecture_matches: set[str]
    exported_names: set[str]


class RepositoryIntelligenceService:
    def __init__(self) -> None:
        self.indexer = RepositoryIndexer()

    def _connect(self) -> sqlite3.Connection:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        self._initialize(connection)
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
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
            """
        )
        connection.commit()

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
        major_modules = ", ".join(module.name for module in summary.major_modules[:6]) or "none detected"
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

    def save_scan(self, full_name: str, payload: RepositoryIntelligencePayload) -> RepositoryScanRecord:
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

    def save_failure(self, full_name: str, local_path: str, error: str) -> RepositoryScanRecord:
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

    def scan_repository(self, full_name: str, local_path: str) -> RepositoryScanRecord:
        root = self._validate_local_path(local_path)
        self.mark_scanning(full_name, str(root))
        try:
            payload = self._build_payload(full_name, root)
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

    def _validate_local_path(self, local_path: str) -> Path:
        if not local_path:
            raise ValueError("A local repository path is required before scanning.")
        candidate = Path(local_path).expanduser().resolve()
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
        if not any(self._is_relative_to(candidate, root) for root in roots):
            raise ValueError("Repository path is outside the allowed scan roots.")
        return candidate

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _build_payload(self, full_name: str, root: Path) -> RepositoryIntelligencePayload:
        entries = self.indexer.build(root)
        inventory = [
            InventoryEntry(
                path=entry.path,
                size=entry.size,
                kind=entry.kind.value,
                language=entry.language,
                binary=entry.binary,
            )
            for entry in entries
        ]
        inventory_paths = {entry.path for entry in inventory}
        module_map = self._build_python_module_map(inventory)
        symbols: list[SymbolRecord] = []
        edges: list[DependencyEdge] = []
        architecture_matches: dict[str, set[str]] = defaultdict(set)
        metadata = self._build_metadata(root, entries)

        for entry in inventory:
            if entry.binary or not self._is_parseable(entry.path):
                self._categorize_path(entry.path, architecture_matches)
                continue
            path = root / entry.path
            text = path.read_text(encoding="utf-8", errors="replace")
            result = self._analyze_file(entry, text, module_map, inventory_paths)
            symbols.extend(result.symbols)
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
        summary = self._build_summary(full_name, root, inventory, architecture, graph, metadata)
        return RepositoryIntelligencePayload(
            repository=full_name,
            local_path=str(root),
            inventory=inventory,
            directory_tree=tree,
            symbols=sorted(symbols, key=lambda symbol: (symbol.file_path, symbol.line, symbol.name)),
            architecture=architecture,
            dependency_graph=graph,
            summary=summary,
            metadata=metadata,
        )

    @staticmethod
    def _is_parseable(path: str) -> bool:
        suffix = Path(path).suffix.lower()
        return suffix in SOURCE_EXTENSIONS or Path(path).name in {"package.json", "pyproject.toml"}

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
            return AnalysisResult(symbols=[], imports=[], architecture_matches={"configuration"}, exported_names=set())
        return AnalysisResult(symbols=[], imports=[], architecture_matches=set(), exported_names=set())

    def _analyze_python(
        self,
        entry: InventoryEntry,
        text: str,
        module_map: dict[str, str],
    ) -> AnalysisResult:
        try:
            tree = ast.parse(text, filename=entry.path)
        except SyntaxError:
            return AnalysisResult(symbols=[], imports=[], architecture_matches=set(), exported_names=set())

        symbols: list[SymbolRecord] = []
        imports: list[ImportReference] = []
        architecture_matches: set[str] = set()
        module_name = self._python_module_name(entry.path)

        class Visitor(ast.NodeVisitor):
            def __init__(self, outer: RepositoryIntelligenceService) -> None:
                self.outer = outer
                self.class_stack: list[str] = []

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                bases = [self.outer._python_name(base) for base in node.bases]
                decorators = [self.outer._python_name(item) for item in node.decorator_list]
                kind = "enum" if any(base.endswith("Enum") for base in bases) else "class"
                qualified_name = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
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
                self.class_stack.append(node.name)
                self.generic_visit(node)
                self.class_stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                decorators = [self.outer._python_name(item) for item in node.decorator_list]
                kind = "method" if self.class_stack else "function"
                qualified_name = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
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
                            [SymbolRelationship(type="member_of", target=self.class_stack[-1])]
                            if self.class_stack
                            else []
                        ),
                    )
                )
                if any(decorator.startswith(("router.", "app.")) for decorator in decorators):
                    architecture_matches.add("api_routes")
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
                                container=self.class_stack[-1] if self.class_stack else None,
                                relationships=(
                                    [SymbolRelationship(type="member_of", target=self.class_stack[-1])]
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
                module = self.outer._resolve_python_import(module_name, node.module, node.level, module_map)
                imports.append(
                    ImportReference(
                        module=node.module or "",
                        line=node.lineno,
                        external=module is None,
                        resolved_path=module,
                    )
                )
                self.generic_visit(node)

        Visitor(self).visit(tree)

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
        if any(token in entry.path.lower() for token in ("storage", "database", "repository")):
            architecture_matches.add("database_layer")
        if Path(entry.path).name in {"settings.py", "config.py"}:
            architecture_matches.add("configuration")
        return AnalysisResult(symbols=symbols, imports=imports, architecture_matches=architecture_matches, exported_names=set())

    def _analyze_script(
        self,
        entry: InventoryEntry,
        text: str,
        inventory_paths: set[str],
    ) -> AnalysisResult:
        symbols: list[SymbolRecord] = []
        imports: list[ImportReference] = []
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
                            relationships=[SymbolRelationship(type="member_of", target=name)],
                        )
                    )

        for pattern, kind in ((INTERFACE_RE, "interface"), (ENUM_RE, "enum"), (FUNCTION_RE, "function"), (ARROW_RE, "function"), (CONST_RE, "constant")):
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
        if "/components/" in f"/{lower_path}" or Path(entry.path).suffix.lower() == ".tsx":
            architecture_matches.add("components")
        if "/services/" in f"/{lower_path}" or lower_path.endswith("service.ts"):
            architecture_matches.add("services")
        if "/models/" in f"/{lower_path}" or lower_path.endswith("model.ts"):
            architecture_matches.add("models")
        if any(name in lower_path for name in ("config", "next.config", "eslint.config")):
            architecture_matches.add("configuration")
        if ROUTE_HINT_RE.search(text):
            architecture_matches.add("api_routes")
        return AnalysisResult(symbols=symbols, imports=imports, architecture_matches=architecture_matches, exported_names=exported_names)

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
        base = source.parent / target if target.startswith(".") else Path(target.lstrip("/"))
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
                    node = FileNode(name=directory, path=current_path, type="directory", children=[])
                    parent.children.append(node)
                    directories[current_path] = node
                parent = directories[current_path]
            parent.children.append(FileNode(name=parts[-1], path=entry.path, type="file", children=[]))

        return root

    def _build_dependency_graph(
        self,
        inventory: list[InventoryEntry],
        edges: list[DependencyEdge],
    ) -> DependencyGraphRecord:
        nodes = [DependencyNode(id=entry.path, label=entry.path) for entry in inventory if self._is_parseable(entry.path)]
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
        manifest = self.indexer.manifest(root.name, root, entries).model_dump(mode="json")
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
        language_counts = Counter(entry.language for entry in inventory if entry.language)
        languages = [name for name, _ in language_counts.most_common()]
        frameworks = self._normalize_framework_names(
            metadata.get("detected_frameworks") or self._frameworks_from_files(root, inventory)
        )
        package_manager = sorted(set(self._package_managers(inventory, root)))
        build_system = sorted(set(self._build_systems(inventory, root)))
        test_framework = sorted(set(self._test_frameworks(inventory, root)))
        module_counts = Counter(Path(entry.path).parts[0] if Path(entry.path).parts else entry.path for entry in inventory)
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
                    for value, label in (("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask"), ("pydantic", "Pydantic")):
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
            dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for value, label in (("next", "Next.js"), ("react", "React"), ("vue", "Vue"), ("svelte", "Svelte"), ("express", "Express"), ("vitest", "Vitest")):
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
        if any(name in paths for name in ("pyproject.toml", "backend/pyproject.toml", "requirements.txt", "backend/requirements.txt", "uv.lock", "backend/uv.lock")):
            managers.append("Python")
        if (root / "frontend/package-lock.json").exists() or (root / "package-lock.json").exists():
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
                if path.exists() and "pytest" in path.read_text(encoding="utf-8", errors="ignore").lower():
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
                frameworks.append("Vitest" if "vitest" in scripts["test"] else "npm test")
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
            elif path.startswith("frontend/app/") and name in {"page.tsx", "layout.tsx", "route.ts"}:
                candidates.append(path)
        return sorted(dict.fromkeys(candidates))[:20]

    @staticmethod
    def _categorize_path(path: str, categories: dict[str, set[str]]) -> None:
        lower_path = path.lower()
        name = Path(path).name.lower()
        if name == "middleware.ts" or "middleware" in lower_path:
            categories["middleware"].add(path)
        if any(token in lower_path for token in ("/service", "/services/", "service.py", "service.ts")):
            categories["services"].add(path)
        if any(token in lower_path for token in ("/controller", "/controllers/", "api/")):
            categories["controllers"].add(path)
        if any(token in lower_path for token in ("/model", "/models/", "models.py")):
            categories["models"].add(path)
        if "/components/" in f"/{lower_path}" or name.endswith(".tsx"):
            categories["components"].add(path)
        if any(token in lower_path for token in ("storage/", "database/", "sqlite", "repository/")):
            categories["database_layer"].add(path)
        if name.startswith(".env") or ENV_FILE_RE.search(path):
            categories["environment_files"].add(path)
        if name in {"package.json", "pyproject.toml", "makefile", "dockerfile"} or name.endswith(CONFIG_SUFFIXES) or "config" in name:
            categories["configuration"].add(path)
        if name == "route.ts" or name == "main.py":
            categories["api_routes"].add(path)

    @staticmethod
    def _strongly_connected_components(adjacency: dict[str, list[str]]) -> list[list[str]]:
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
