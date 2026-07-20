from __future__ import annotations
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable
from .exceptions import DirtyWorkspaceError, GitCommandError, RepositoryValidationError
from .models import BranchInfo, CommitInfo, DiffResult, GitStatus, GitStatusEntry
from .security import validate_ref

class GitClient:
    def __init__(self, timeout_seconds: float = 120):
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        repo: Path | None,
        args: Iterable[str],
        *,
        check: bool = True,
        input_text: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = ["git"]
        if repo is not None:
            command += ["-C", str(repo)]
        command += list(args)
        process_env = os.environ.copy()
        process_env.update({
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C.UTF-8",
        })
        if env:
            process_env.update(env)
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout or self.timeout_seconds,
            env=process_env,
        )
        if check and result.returncode != 0:
            raise GitCommandError(command, result.returncode, result.stdout, result.stderr)
        return result

    def clone(self, url: str, destination: Path, branch: str | None = None, depth: int | None = None) -> None:
        args = ["clone", "--no-tags"]
        if branch:
            args += ["--branch", validate_ref(branch)]
        if depth:
            args += ["--depth", str(depth)]
        args += ["--", url, str(destination)]
        self.run(None, args)

    def initialize(self, path: Path, initial_branch: str = "main") -> None:
        path.mkdir(parents=True, exist_ok=True)
        result = self.run(None, ["init", "-b", initial_branch, str(path)], check=False)
        if result.returncode != 0:
            self.run(None, ["init", str(path)])
            self.run(path, ["checkout", "-b", initial_branch])

    def is_repository(self, path: Path) -> bool:
        return self.run(path, ["rev-parse", "--is-inside-work-tree"], check=False).returncode == 0

    def root(self, path: Path) -> Path:
        return Path(self.run(path, ["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()

    def current_branch(self, path: Path) -> str | None:
        result = self.run(path, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
        return result.stdout.strip() or None

    def head_sha(self, path: Path) -> str | None:
        result = self.run(path, ["rev-parse", "--verify", "HEAD"], check=False)
        return result.stdout.strip() or None

    def default_branch(self, path: Path) -> str | None:
        result = self.run(path, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], check=False)
        if result.returncode == 0 and "/" in result.stdout.strip():
            return result.stdout.strip().split("/", 1)[1]
        for candidate in ("main", "master"):
            if self.run(path, ["show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"], check=False).returncode == 0:
                return candidate
        return self.current_branch(path)

    def status(self, path: Path) -> GitStatus:
        result = self.run(path, ["status", "--porcelain=v2", "--branch", "-z"])
        tokens = result.stdout.split("\0")
        status = GitStatus()
        for token in tokens:
            if not token:
                continue
            if token.startswith("# branch.head "):
                head = token.removeprefix("# branch.head ")
                status.detached = head == "(detached)"
                status.branch = None if status.detached else head
            elif token.startswith("# branch.upstream "):
                status.upstream = token.removeprefix("# branch.upstream ")
            elif token.startswith("# branch.ab "):
                match = re.search(r"\+(\d+) -(\d+)", token)
                if match:
                    status.ahead, status.behind = int(match.group(1)), int(match.group(2))
            elif token.startswith("# branch.oid "):
                oid = token.removeprefix("# branch.oid ")
                status.head_sha = None if oid == "(initial)" else oid
            elif token.startswith("1 "):
                parts = token.split(" ", 8)
                xy = parts[1]
                status.entries.append(GitStatusEntry(path=parts[-1], index_status=xy[0], worktree_status=xy[1]))
            elif token.startswith("2 "):
                parts = token.split(" ", 9)
                xy = parts[1]
                payload = parts[-1].split("\t", 1)
                status.entries.append(GitStatusEntry(
                    path=payload[0], original_path=payload[1] if len(payload) > 1 else None,
                    index_status=xy[0], worktree_status=xy[1],
                ))
            elif token.startswith("? "):
                status.entries.append(GitStatusEntry(path=token[2:], index_status="?", worktree_status="?"))
            elif token.startswith("u "):
                parts = token.split(" ", 10)
                xy = parts[1]
                status.entries.append(GitStatusEntry(path=parts[-1], index_status=xy[0], worktree_status=xy[1]))
        status.clean = not status.entries
        return status

    def require_clean(self, path: Path) -> None:
        if not self.status(path).clean:
            raise DirtyWorkspaceError("Workspace has uncommitted changes")

    def branches(self, path: Path, include_remote: bool = True) -> list[BranchInfo]:
        refs = ["refs/heads"]
        if include_remote:
            refs.append("refs/remotes")
        fmt = "%(refname)|%(refname:short)|%(HEAD)|%(objectname)"
        output = self.run(path, ["for-each-ref", f"--format={fmt}", *refs]).stdout
        branches = []
        for line in output.splitlines():
            full, short, current, commit = line.split("|", 3)
            if short.endswith("/HEAD"):
                continue
            branches.append(BranchInfo(name=short, current=current == "*", remote=full.startswith("refs/remotes/"), commit=commit))
        return branches

    def checkout(self, path: Path, branch: str, create: bool = False, start_point: str | None = None, force: bool = False) -> None:
        branch = validate_ref(branch)
        args = ["checkout"]
        if force:
            args.append("--force")
        if create:
            args += ["-b", branch]
            if start_point:
                args.append(validate_ref(start_point))
        else:
            args.append(branch)
        self.run(path, args)

    def create_branch(self, path: Path, branch: str, start_point: str | None = None, checkout: bool = False) -> None:
        branch = validate_ref(branch)
        if checkout:
            self.checkout(path, branch, create=True, start_point=start_point)
            return
        args = ["branch", branch]
        if start_point:
            args.append(validate_ref(start_point))
        self.run(path, args)

    def delete_branch(self, path: Path, branch: str, force: bool = False) -> None:
        self.run(path, ["branch", "-D" if force else "-d", validate_ref(branch)])

    def diff(self, path: Path, staged: bool = False, ref: str | None = None, max_chars: int = 500000) -> DiffResult:
        args = ["diff", "--no-ext-diff", "--no-color"]
        if staged:
            args.append("--cached")
        if ref:
            args.append(validate_ref(ref))
        text = self.run(path, args).stdout
        stat_args = ["diff", "--shortstat"]
        if staged:
            stat_args.append("--cached")
        if ref:
            stat_args.append(validate_ref(ref))
        stat = self.run(path, stat_args).stdout
        numbers = [int(v) for v in re.findall(r"(\d+)", stat)]
        files = numbers[0] if numbers else 0
        insertions = next((int(x) for x in re.findall(r"(\d+) insertion", stat)), 0)
        deletions = next((int(x) for x in re.findall(r"(\d+) deletion", stat)), 0)
        truncated = len(text) > max_chars
        return DiffResult(
            text=text[:max_chars], files_changed=files, insertions=insertions,
            deletions=deletions, truncated=truncated,
        )

    def add(self, path: Path, paths: list[str] | None = None) -> None:
        self.run(path, ["add", "--", *(paths or ["."])])

    def commit(
        self, path: Path, message: str, paths: list[str] | None = None,
        allow_empty: bool = False, author_name: str | None = None, author_email: str | None = None,
    ) -> str:
        if paths is not None:
            self.add(path, paths)
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        env = {}
        if author_name:
            env["GIT_AUTHOR_NAME"] = author_name
            env["GIT_COMMITTER_NAME"] = author_name
        if author_email:
            env["GIT_AUTHOR_EMAIL"] = author_email
            env["GIT_COMMITTER_EMAIL"] = author_email
        self.run(path, args, env=env)
        sha = self.head_sha(path)
        if not sha:
            raise RepositoryValidationError("Commit completed but HEAD could not be resolved")
        return sha

    def log(self, path: Path, limit: int = 50, ref: str = "HEAD") -> list[CommitInfo]:
        fmt = "%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1e"
        result = self.run(path, ["log", f"--max-count={limit}", f"--format={fmt}", validate_ref(ref)], check=False)
        if result.returncode != 0:
            return []
        commits = []
        for record in result.stdout.strip("\x1e\n").split("\x1e"):
            if not record.strip():
                continue
            sha, short, name, email, authored, subject = record.strip().split("\x1f", 5)
            commits.append(CommitInfo(
                sha=sha, short_sha=short, author_name=name, author_email=email,
                authored_at=datetime.fromisoformat(authored), subject=subject,
            ))
        return commits

    def fetch(self, path: Path, remote: str = "origin", prune: bool = True) -> None:
        args = ["fetch"]
        if prune:
            args.append("--prune")
        args += ["--", remote]
        self.run(path, args)

    def pull(self, path: Path, remote: str, branch: str | None, rebase: bool, ff_only: bool) -> None:
        args = ["pull"]
        if rebase:
            args.append("--rebase")
        elif ff_only:
            args.append("--ff-only")
        args += ["--", remote]
        if branch:
            args.append(validate_ref(branch))
        self.run(path, args)

    def push(self, path: Path, remote: str, branch: str | None, set_upstream: bool, force_with_lease: bool) -> None:
        args = ["push"]
        if set_upstream:
            args.append("--set-upstream")
        if force_with_lease:
            args.append("--force-with-lease")
        args += ["--", remote]
        if branch:
            args.append(validate_ref(branch))
        self.run(path, args)

    def apply_patch(self, path: Path, patch: str, check_only: bool = False, reverse: bool = False) -> None:
        args = ["apply", "--whitespace=nowarn"]
        if check_only:
            args.append("--check")
        if reverse:
            args.append("--reverse")
        self.run(path, args, input_text=patch)

    def remotes(self, path: Path) -> dict[str, str]:
        output = self.run(path, ["remote", "-v"]).stdout
        result = {}
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] not in result:
                result[parts[0]] = parts[1]
        return result
