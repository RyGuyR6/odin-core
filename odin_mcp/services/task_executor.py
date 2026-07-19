from __future__ import annotations

from typing import Any

from odin_mcp.services.engineering_service import EngineeringService


class EngineeringTaskExecutor:
    """
    Executes complete engineering tasks.

    This is intentionally independent of any LLM.
    Future planners will build task dictionaries that
    are executed here.
    """

    def __init__(
        self,
        engineering: EngineeringService,
    ) -> None:
        self.engineering = engineering

    def execute(
        self,
        task: dict[str, Any],
    ) -> dict[str, Any]:

        action = task["action"]

        if action == "replace_text":
            return self.engineering.submit_change(
                path=task["path"],
                old=task["old"],
                new=task["new"],
                commit_message=task["commit_message"],
                push=task.get("push", False),
                remote=task.get("remote", "origin"),
                branch=task.get("branch"),
            )

        raise ValueError(
            f"Unsupported engineering task: {action}"
        )
