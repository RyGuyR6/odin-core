from __future__ import annotations

from pathlib import Path

from odin_mcp.models.engineering_goal import EngineeringGoal
from odin_mcp.services.goal_planner import GoalPlanner
from odin_mcp.services.repository_planner import RepositoryPlanner
from odin_mcp.services.engineering_planner import EngineeringPlanner
from odin_mcp.services.autonomous_executor import AutonomousExecutor
from odin_mcp.services.repository_search_service import RepositorySearchService
from odin_mcp.services.engineering_service import EngineeringService
from odin_mcp.services.task_executor import EngineeringTaskExecutor
from odin_mcp.services.plan_executor import EngineeringPlanExecutor


class Odin:

    """
    Main autonomous engineering orchestrator.

    Future API:

        odin.execute(
            "Add JWT authentication."
        )
    """

    def __init__(
        self,
        repo_root: Path,
    ) -> None:

        self.goal_planner = GoalPlanner()

        self.repository_search = RepositorySearchService(
            repo_root
        )

        self.repository_planner = RepositoryPlanner(
            self.repository_search
        )

        self.engineering_service = EngineeringService(
            repo_root
        )

        self.engineering_planner = EngineeringPlanner()

        self.task_executor = EngineeringTaskExecutor(
            self.engineering_service
        )

        self.plan_executor = EngineeringPlanExecutor(
            self.task_executor
        )

        self.executor = AutonomousExecutor(
            self.plan_executor,
            repo_root,
        )

    def execute(
        self,
        request: str,
    ):

        goal = EngineeringGoal(
            request=request,
        )

        phases = self.goal_planner.create_breakdown(
            goal
        )

        analysis = self.repository_planner.analyze(
            request
        )

        return {
            "goal": goal,
            "phases": phases,
            "analysis": analysis,
        }
