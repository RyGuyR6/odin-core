from __future__ import annotations
import os
import subprocess
import tempfile
from pathlib import Path

def run() -> list[str]:
    root = Path(tempfile.mkdtemp(prefix="odin-m21-"))
    os.environ["ODIN_REPOSITORY_WORKSPACE_ROOT"] = str(root / "workspaces")
    os.environ["ODIN_REPOSITORY_DB"] = str(root / "repositories.db")
    os.environ["ODIN_GIT_ALLOW_PUSH"] = "false"

    from .config import get_repository_settings
    from .exceptions import DirtyWorkspaceError, UnsafeRepositoryError
    from .manager import RepositoryManager
    from .models import CommitRequest, FileWriteRequest, PatchRequest, SearchRequest, WorkspaceCreate

    source = root / "source"
    subprocess.run(["git", "init", "-b", "main", str(source)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Odin Validator"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.email", "validator@odin.local"], check=True)
    (source / "README.md").write_text("# Validation\n")
    (source / "app.py").write_text("def hello():\n    return 'odin'\n")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-m", "initial"], check=True, capture_output=True, text=True)

    manager = RepositoryManager(get_repository_settings())
    checks = []

    workspace = manager.create(WorkspaceCreate(name="validation", local_path=str(source)))
    assert workspace.current_branch == "main"
    checks.append("workspace-create")

    status = manager.status(workspace.id)
    assert status.clean
    checks.append("status")

    manager.write_file(workspace.id, FileWriteRequest(path="src/new.py", content="VALUE = 21\n"))
    assert manager.read_file(workspace.id, "src/new.py")["content"] == "VALUE = 21\n"
    checks.append("safe-files")

    results = manager.search(workspace.id, SearchRequest(query="VALUE"))
    assert results and results[0]["path"] == "src/new.py"
    checks.append("content-search")

    status = manager.status(workspace.id)
    assert not status.clean
    diff = manager.git.diff(Path(workspace.path))
    assert "src/new.py" not in diff.text  # untracked files are not in git diff
    checks.append("git-status")

    manager.git.add(Path(workspace.path), ["src/new.py"])
    staged = manager.git.diff(Path(workspace.path), staged=True)
    assert "VALUE = 21" in staged.text
    checks.append("diff")

    commit = manager.commit(workspace.id, CommitRequest(
        message="feat: add validation source", paths=None,
        author_name="Odin Validator", author_email="validator@odin.local",
    ))
    assert commit["sha"]
    checks.append("commit")

    manager.git.checkout(Path(workspace.path), "validation-branch", create=True)
    assert manager.git.current_branch(Path(workspace.path)) == "validation-branch"
    checks.append("branch")

    patch = """diff --git a/README.md b/README.md
index 9ef3c72..09dcfe1 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # Validation
+Milestone 21
"""
    manager.apply_patch(workspace.id, PatchRequest(patch=patch, check_only=True))
    manager.apply_patch(workspace.id, PatchRequest(patch=patch))
    assert "Milestone 21" in manager.read_file(workspace.id, "README.md")["content"]
    checks.append("patch")

    manifest = manager.index(workspace.id)
    assert manifest.files_indexed >= 3
    assert manager.store.index_count(workspace.id) >= 3
    checks.append("index-manifest")

    try:
        manager.read_file(workspace.id, "../escape.txt")
    except UnsafeRepositoryError:
        checks.append("path-sandbox")
    else:
        raise AssertionError("Path traversal was not blocked")

    try:
        manager.delete(workspace.id, force=False)
    except DirtyWorkspaceError:
        checks.append("dirty-protection")
    else:
        raise AssertionError("Dirty workspace deletion should be blocked")

    events = manager.store.events(workspace.id)
    assert events
    checks.append("audit")

    manager.delete(workspace.id, force=True)
    assert not Path(workspace.path).exists()
    checks.append("delete")

    return checks

if __name__ == "__main__":
    checks = run()
    print(f"Milestone 21 validation passed: {len(checks)} checks")
    for check in checks:
        print(check)
