class RepositoryError(Exception):
    """Base repository workspace error."""

class WorkspaceNotFoundError(RepositoryError):
    pass

class WorkspaceExistsError(RepositoryError):
    pass

class GitCommandError(RepositoryError):
    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(stderr.strip() or stdout.strip() or f"Git command failed: {' '.join(command)}")

class DirtyWorkspaceError(RepositoryError):
    pass

class UnsafeRepositoryError(RepositoryError):
    pass

class BranchConflictError(RepositoryError):
    pass

class RepositoryValidationError(RepositoryError):
    pass
