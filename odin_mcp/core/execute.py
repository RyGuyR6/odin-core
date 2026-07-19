from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from odin_mcp.core.orchestrator import Odin
from odin_mcp.core.brain_pipeline import BrainPipeline
from odin_mcp.core.brain_execution import BrainExecutionPipeline


@dataclass(slots=True)
class ExecuteResponse:

    success: bool

    goal: str

    context: object


class OdinExecuteAPI:

    """
    Public entrypoint for Odin.

    Everything eventually calls this.

        MCP
        REST
        CLI
        Dashboard
        Scheduler
        GitHub
    """

    def __init__(
        self,
        repo_root: Path,
    ):

        self.odin = Odin(repo_root)

        self.pipeline = BrainPipeline(
            self.odin.brain
        )

        self.execution = BrainExecutionPipeline(
            self.odin.brain
        )

    def execute(
        self,
        goal: str,
    ) -> ExecuteResponse:

        context = self.odin.brain.create_context(
            goal
        )

        context = self.pipeline.run(
            context
        )

        #
        # Execution disabled for now.
        #
        # Uncomment once planning
        # becomes repository-aware.
        #
        # context = self.execution.execute(context)
        #

        return ExecuteResponse(
            success=True,
            goal=goal,
            context=context,
        )
