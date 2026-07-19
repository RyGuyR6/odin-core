from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ValidationCommand:
    name: str
    command: list[str]


@dataclass(slots=True)
class ValidationResult:
    success: bool
    command: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class ValidationSummary:
    success: bool
    results: list[ValidationResult] = field(default_factory=list)


class ValidationService:

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def detect(self) -> list[ValidationCommand]:

        commands: list[ValidationCommand] = []

        if (self.repo_root / "pytest.ini").exists() \
           or (self.repo_root / "pyproject.toml").exists():

            if shutil.which("pytest"):
                commands.append(
                    ValidationCommand(
                        "pytest",
                        ["pytest", "-q"],
                    )
                )

        if (self.repo_root / "package.json").exists():

            if shutil.which("npm"):
                commands.append(
                    ValidationCommand(
                        "npm test",
                        ["npm", "test"],
                    )
                )

        return commands

    def run(self) -> ValidationSummary:

        summary = ValidationSummary(success=True)

        for command in self.detect():

            proc = subprocess.run(
                command.command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )

            result = ValidationResult(
                success=proc.returncode == 0,
                command=command.name,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )

            summary.results.append(result)

            if not result.success:
                summary.success = False

        return summary
