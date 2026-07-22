from app.planning.models import ExecutionPlan


class Planner:

    def create_plan(self, goal: str) -> ExecutionPlan:
        """
        Placeholder planner.

        Later this will call GPT or another LLM.
        """

        return ExecutionPlan(goal=goal)


planner = Planner()
