from __future__ import annotations
import json
import shutil
import uuid
from functools import lru_cache
from pathlib import Path
from .config import RepositorySettings, get_repository_settings
from .exceptions import (
    DirtyWorkspaceError, RepositoryValidationError, UnsafeRepositoryError,
    WorkspaceExistsError, WorkspaceNotFoundError,
)
from .git import GitClient
from .indexer import RepositoryIndexer
from .models import (
    CommitRequest, FileWriteRequest, PatchRequest, PullRequest, PushRequest,
    RepositoryManifest, SearchRequest, WorkspaceCreate, WorkspaceRecord, WorkspaceState,
)
from .security import safe_child, validate_repository_url
from .store import RepositoryStore

class RepositoryManager:
    def __init__(self, settings: RepositorySettings | None = None):
        self.settings = settings or get_repository_settings()
        self.git = GitClient(self.settings.command_timeout_seconds)
        self.store = RepositoryStore(self.settings.database_path)
        self.indexer = RepositoryIndexer(self.settings.max_file_bytes, self.settings.max_index_files)
        self.settings.workspace_root.mkdir(parents=True, exist_ok=True)

    def _path_for_name(self, name: str) -> Path:
        return safe_child(self.settings.workspace_root, name)

    def require(self, workspace_id: str) -> tuple[WorkspaceRecord, Path]:
        record = self.store.get_workspace(workspace_id)
        if not record or record.state == WorkspaceState.deleted:
            raise WorkspaceNotFoundError(f"Workspace not found: {workspace_id}")
        path = Path(record.path).resolve()
        try:
            path.relative_to(self.settings.workspace_root)
        except ValueError as exc:
            raise UnsafeRepositoryError("Stored workspace path is outside the configured root") from exc
        if not path.exists():
            raise WorkspaceNotFoundError(f"Workspace directory is missing: {path}")
        if not self.git.is_repository(path):
            raise RepositoryValidationError(f"Workspace is not a Git repository: {path}")
        return record, path

    def _refresh(self, record: WorkspaceRecord, path: Path) -> WorkspaceRecord:
        record.current_branch = self.git.current_branch(path)
        record.default_branch = self.git.default_branch(path)
        record.head_sha = self.git.head_sha(path)
        record.state = WorkspaceState.ready
        record.metadata["remotes"] = self.git.remotes(path)
        self.store.save_workspace(record)
        return record

    def create(self, request: WorkspaceCreate, actor_id: str | None = None) -> WorkspaceRecord:
        if bool(request.repository_url) == bool(request.local_path):
            raise RepositoryValidationError("Provide exactly one of repository_url or local_path")
        if self.store.get_workspace_by_name(request.name):
            raise WorkspaceExistsError(f"Workspace name already exists: {request.name}")
        destination = self._path_for_name(request.name)
        if destination.exists():
            raise WorkspaceExistsError(f"Workspace directory already exists: {destination}")

        workspace_id = uuid.uuid4().hex
        try:
            if request.repository_url:
                url = validate_repository_url(request.repository_url)
                self.git.clone(url, destination, request.branch, request.depth)
                source_url = url
            else:
                if not self.settings.allow_local_paths:
                    raise UnsafeRepositoryError("Local repository imports are disabled")
                source = Path(request.local_path or "").expanduser().resolve()
                if not self.git.is_repository(source):
                    raise RepositoryValidationError(f"Local path is not a Git repository: {source}")
                shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".odin-workspaces", ".odin-backups"))
                source_url = str(source)
            record = WorkspaceRecord(
                id=workspace_id, name=request.name, path=str(destination),
                repository_url=source_url, state=WorkspaceState.ready,
            )
            record = self._refresh(record, destination)
            self.store.record_event(workspace_id, "workspace.created", actor_id, {"name": request.name, "source": source_url})
            return record
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise

    def create_empty(self, name: str, actor_id: str | None = None) -> WorkspaceRecord:
        if self.store.get_workspace_by_name(name):
            raise WorkspaceExistsError(f"Workspace name already exists: {name}")
        destination = self._path_for_name(name)
        if destination.exists():
            raise WorkspaceExistsError(f"Workspace directory already exists: {destination}")
        self.git.initialize(destination)
        record = WorkspaceRecord(id=uuid.uuid4().hex, name=name, path=str(destination))
        record = self._refresh(record, destination)
        self.store.record_event(record.id, "workspace.created_empty", actor_id, {"name": name})
        return record

    def delete(self, workspace_id: str, remove_files: bool = True, force: bool = False, actor_id: str | None = None) -> None:
        record, path = self.require(workspace_id)
        if not force:
            self.git.require_clean(path)
        if remove_files:
            shutil.rmtree(path)
        self.store.delete_workspace(workspace_id, hard=remove_files)
        self.store.record_event(workspace_id, "workspace.deleted", actor_id, {"remove_files": remove_files, "force": force})

    def status(self, workspace_id: str):
        record, path = self.require(workspace_id)
        self._refresh(record, path)
        return self.git.status(path)

    def index(self, workspace_id: str, actor_id: str | None = None) -> RepositoryManifest:
        record, path = self.require(workspace_id)
        record.state = WorkspaceState.indexing
        self.store.save_workspace(record)
        try:
            entries = self.indexer.build(path)
            self.store.replace_index(workspace_id, [entry.model_dump(mode="json") for entry in entries])
            manifest = self.indexer.manifest(workspace_id, path, entries)
            manifest_path = path / ".odin" / "manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(manifest.model_dump_json(indent=2))
            record.metadata["manifest"] = manifest.model_dump(mode="json")
            record.state = WorkspaceState.ready
            self.store.save_workspace(record)
            self.store.record_event(workspace_id, "repository.indexed", actor_id, {
                "files": manifest.files_indexed, "bytes": manifest.total_bytes,
            })
            return manifest
        except Exception:
            record.state = WorkspaceState.error
            self.store.save_workspace(record)
            raise

    def manifest(self, workspace_id: str) -> RepositoryManifest | None:
        record, _ = self.require(workspace_id)
        value = record.metadata.get("manifest")
        return RepositoryManifest.model_validate(value) if value else None

    def read_file(self, workspace_id: str, relative: str, max_bytes: int | None = None) -> dict:
        _, root = self.require(workspace_id)
        path = safe_child(root, relative)
        if not path.is_file():
            raise WorkspaceNotFoundError(f"File not found: {relative}")
        limit = min(max_bytes or self.settings.max_file_bytes, self.settings.max_file_bytes)
        data = path.read_bytes()
        truncated = len(data) > limit
        return {
            "path": relative, "content": data[:limit].decode("utf-8", errors="replace"),
            "size": len(data), "truncated": truncated,
        }

    def write_file(self, workspace_id: str, request: FileWriteRequest, actor_id: str | None = None) -> dict:
        _, root = self.require(workspace_id)
        path = safe_child(root, request.path)
        if request.create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        elif not path.parent.exists():
            raise RepositoryValidationError(f"Parent directory does not exist: {path.parent}")
        encoded = request.content.encode("utf-8")
        if len(encoded) > self.settings.max_file_bytes:
            raise RepositoryValidationError("File exceeds configured maximum size")
        path.write_text(request.content)
        self.store.record_event(workspace_id, "file.written", actor_id, {"path": request.path, "bytes": len(encoded)})
        return {"path": request.path, "bytes": len(encoded)}

    def search(self, workspace_id: str, request: SearchRequest) -> list[dict]:
        _, root = self.require(workspace_id)
        return self.indexer.search_content(
            root, request.query, request.glob, request.max_results, request.case_sensitive
        )

    def commit(self, workspace_id: str, request: CommitRequest, actor_id: str | None = None) -> dict:
        record, path = self.require(workspace_id)
        sha = self.git.commit(
            path, request.message, request.paths, request.allow_empty,
            request.author_name, request.author_email,
        )
        self._refresh(record, path)
        self.store.record_event(workspace_id, "git.commit", actor_id, {"sha": sha, "message": request.message})
        return {"sha": sha, "branch": record.current_branch}

    def push(self, workspace_id: str, request: PushRequest, actor_id: str | None = None) -> dict:
        if not self.settings.allow_push:
            raise UnsafeRepositoryError("Git push is disabled. Set ODIN_GIT_ALLOW_PUSH=true to enable it.")
        if request.force_with_lease and not self.settings.allow_force_push:
            raise UnsafeRepositoryError("Force-with-lease is disabled")
        record, path = self.require(workspace_id)
        branch = request.branch or self.git.current_branch(path)
        self.git.push(path, request.remote, branch, request.set_upstream, request.force_with_lease)
        self._refresh(record, path)
        self.store.record_event(workspace_id, "git.push", actor_id, {
            "remote": request.remote, "branch": branch, "force_with_lease": request.force_with_lease,
        })
        return {"remote": request.remote, "branch": branch, "head_sha": record.head_sha}

    def pull(self, workspace_id: str, request: PullRequest, actor_id: str | None = None) -> dict:
        record, path = self.require(workspace_id)
        self.git.require_clean(path)
        branch = request.branch or self.git.current_branch(path)
        self.git.pull(path, request.remote, branch, request.rebase, request.ff_only)
        self._refresh(record, path)
        self.store.record_event(workspace_id, "git.pull", actor_id, {"remote": request.remote, "branch": branch})
        return {"branch": record.current_branch, "head_sha": record.head_sha}

    def apply_patch(self, workspace_id: str, request: PatchRequest, actor_id: str | None = None) -> dict:
        _, path = self.require(workspace_id)
        self.git.apply_patch(path, request.patch, request.check_only, request.reverse)
        self.store.record_event(workspace_id, "git.apply_patch", actor_id, {
            "check_only": request.check_only, "reverse": request.reverse,
        })
        return {"applied": not request.check_only, "checked": True}

@lru_cache(maxsize=1)
def get_repository_manager() -> RepositoryManager:
    return RepositoryManager()
